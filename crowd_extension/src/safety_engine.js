/**
 * safety_engine.js — 众包采集安全线引擎 v2（服务端拟合下发 + 本地只降不升）
 *
 * 铁律：
 * 1. 本地默认阈值 = 硬编码 SAFETY_LIMITS（保守基线，永不放大）。
 * 2. 服务端按拟合模型下发 remote_limits（quota_day/gap/session/cooldown），
 *    插件 applyRemoteLimits() 应用时【只降不升】——任何远程值都不能超过本地基线。
 * 3. 日搜索、会话时长、动作间隔、冷却时间均在本地持久化，重启不重置。
 * 4. 触发"访问频繁"→ 强制冷却；冷却期任何采集动作都被拒绝。
 * 5. 一机一号：device_salt 在首次运行时生成并永久绑定，不随账号变化。
 *
 * 拟合依据（2026-10-02 调研固化，详见 cloud/COLLECTION_SOP.md §L1）：
 *   - XHS 实测安全节奏：搜索 ≤2 次/分（间隔 ≥28s），速率码永久翻倍（上限 120s）
 *   - 软限流信号：code=0 空 data → 长冷却自恢复，不重登/换号
 *   - 本地基线取更保守值（间隔 60-120s ≈ 1 次/分，为实测限值的 2 倍余量）
 *   - 日配额上限 = min(服务端拟合 quota_day, 本地 DAILY_SEARCH_MAX)
 *
 * 契约版本：CROWD-CONTRACT-002 (sync_version=1)
 */
const SAFETY_VERSION = 2;

const SAFETY_LIMITS = Object.freeze({
  // 日搜索上限（本地保守基线；服务端拟合值只降不升）
  DAILY_SEARCH_MAX: 30,
  // 动作间隔（秒）：硬下限 60s，随机化到 60-120s（对应 ≤1 次/分）
  SEARCH_GAP_MIN: 60,
  SEARCH_GAP_MAX: 120,
  // 单次会话时长（分钟）与强制冷却（分钟）
  SESSION_MAX_MIN: 15,
  SESSION_COOLDOWN_MIN: 30,
  // 每篇浏览最小停留（秒）
  VIEW_STAY_MIN_S: 30,
  // 触发"访问频繁"后冷却（分钟）
  RATE_LIMIT_COOLDOWN_MIN: 15,
  // 单任务包最低 KPI（未达标不计酬）
  KPI_MIN_DEFAULT: 5,
  // 本地回传队列上限（proof 条数），达到后暂停采集等待回传
  LOCAL_QUEUE_MAX: 100,
});

class SafetyEngine {
  constructor(storage) {
    this.s = storage || chrome.storage.local;
    this.remote = null; // 服务端拟合参数（仅存储应用后的有效值）
  }

  /** 应用服务端拟合参数（只降不升：任何远程值不能放宽本地基线） */
  async applyRemoteLimits(remote) {
    if (!remote || typeof remote !== "object") return;
    const clamp = (val, base, fallback) => {
      if (typeof val !== "number" || !(val > 0)) return fallback;
      return Math.min(val, base); // 只降不升
    };
    this.remote = {
      quota_day: clamp(remote.quota_day, SAFETY_LIMITS.DAILY_SEARCH_MAX, null),
      gap_min: clamp(remote.gap_min, SAFETY_LIMITS.SEARCH_GAP_MAX, null),   // 下限也封顶在基线 max
      gap_max: clamp(remote.gap_max, SAFETY_LIMITS.SEARCH_GAP_MAX, null),
      session_min: clamp(remote.session_min, SAFETY_LIMITS.SESSION_MAX_MIN, null),
      cooldown_min: clamp(remote.cooldown_min, SAFETY_LIMITS.SESSION_COOLDOWN_MIN, null),
    };
    await this._set({ remote_limits_applied: this.remote, remote_limits_at: Date.now() });
  }

  async _get(key, fallback) {
    const r = await this.s.get(key);
    return r[key] !== undefined ? r[key] : fallback;
  }

  async _set(obj) {
    await this.s.set(obj);
  }

  /** 首次运行生成并持久化设备指纹盐（一机一号） */
  async getDeviceSalt() {
    let salt = await this._get("device_salt", null);
    if (!salt) {
      salt = "dev-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      await this._set({ device_salt: salt });
    }
    return salt;
  }

  /** 读取当日状态：{date, searches, sessionStart} */
  async _dayState() {
    const today = new Date().toISOString().slice(0, 10);
    const st = await this._get("day_state", null);
    if (!st || st.date !== today) {
      const fresh = { date: today, searches: 0, sessionStart: null };
      await this._set({ day_state: fresh });
      return fresh;
    }
    return st;
  }

  /** 当前任务包配额（只降不升：任务包 quota_day → 远程拟合 → 本地基线，取最严） */
  async _currentQuota() {
    const task = await this._get("active_task", null);
    const taskQ = task && task.quota_day ? task.quota_day : null;
    const remoteQ = this.remote && this.remote.quota_day ? this.remote.quota_day : null;
    let q = SAFETY_LIMITS.DAILY_SEARCH_MAX;
    if (remoteQ) q = Math.min(q, remoteQ);
    if (taskQ) q = Math.min(q, taskQ);
    return q;
  }

  /** 是否处于冷却期 */
  async inCooldown() {
    const cd = await this._get("cooldown_until", 0);
    if (cd && Date.now() < cd) {
      return { active: true, until: cd, leftMin: Math.ceil((cd - Date.now()) / 60000) };
    }
    return { active: false };
  }

  /** 检查会话：超过会话上限则进入强制冷却（远程拟合只降不升） */
  async _sessionGuard() {
    const st = await this._dayState();
    const now = Date.now();
    const sessionMax = this.remote && this.remote.session_min
      ? Math.min(this.remote.session_min, SAFETY_LIMITS.SESSION_MAX_MIN)
      : SAFETY_LIMITS.SESSION_MAX_MIN;
    const cooldownMin = this.remote && this.remote.cooldown_min
      ? Math.min(this.remote.cooldown_min, SAFETY_LIMITS.SESSION_COOLDOWN_MIN)
      : SAFETY_LIMITS.SESSION_COOLDOWN_MIN;
    if (!st.sessionStart) {
      st.sessionStart = now;
      await this._set({ day_state: st });
      return { ok: true };
    }
    const mins = (now - st.sessionStart) / 60000;
    if (mins > sessionMax) {
      const until = now + cooldownMin * 60000;
      await this._set({ cooldown_until: until });
      st.sessionStart = null;
      await this._set({ day_state: st });
      return { ok: false, reason: `会话超时，冷却 ${cooldownMin}min`, until };
    }
    return { ok: true };
  }

  /** 当前生效的安全参数（供 popup 展示/审计） */
  async currentLimits() {
    const q = await this._currentQuota();
    const gapMin = this.remote && this.remote.gap_min
      ? Math.max(SAFETY_LIMITS.SEARCH_GAP_MIN, Math.min(this.remote.gap_min, SAFETY_LIMITS.SEARCH_GAP_MAX))
      : SAFETY_LIMITS.SEARCH_GAP_MIN;
    const gapMax = this.remote && this.remote.gap_max
      ? Math.min(this.remote.gap_max, SAFETY_LIMITS.SEARCH_GAP_MAX)
      : SAFETY_LIMITS.SEARCH_GAP_MAX;
    return {
      quotaDay: q,
      gapMin,
      gapMax,
      sessionMin: this.remote && this.remote.session_min ? Math.min(this.remote.session_min, SAFETY_LIMITS.SESSION_MAX_MIN) : SAFETY_LIMITS.SESSION_MAX_MIN,
      cooldownMin: this.remote && this.remote.cooldown_min ? Math.min(this.remote.cooldown_min, SAFETY_LIMITS.SESSION_COOLDOWN_MIN) : SAFETY_LIMITS.SESSION_COOLDOWN_MIN,
      source: this.remote ? "remote_fitted" : "local_base",
    };
  }

  /** 搜索动作准入检查：通过则返回 {ok, waitMs}，失败返回 {ok:false, reason} */
  async canSearch() {
    // 1. 冷却期
    const cd = await this.inCooldown();
    if (cd.active) return { ok: false, reason: `冷却中，剩余 ${cd.leftMin}min` };

    // 2. 会话时长
    const sg = await this._sessionGuard();
    if (!sg.ok) return sg;

    // 3. 日配额
    const st = await this._dayState();
    const quota = await this._currentQuota();
    if (st.searches >= quota) {
      return { ok: false, reason: `已达日配额 ${quota} 次` };
    }

    // 4. 动作间隔（随机 gapMin-gapMax，基于上次搜索时间；远程拟合只降不升）
    const last = await this._get("last_search_at", 0);
    const gapMin = this.remote && this.remote.gap_min
      ? Math.max(SAFETY_LIMITS.SEARCH_GAP_MIN, Math.min(this.remote.gap_min, SAFETY_LIMITS.SEARCH_GAP_MAX))
      : SAFETY_LIMITS.SEARCH_GAP_MIN;
    const gapMax = this.remote && this.remote.gap_max
      ? Math.max(gapMin, Math.min(this.remote.gap_max, SAFETY_LIMITS.SEARCH_GAP_MAX))
      : SAFETY_LIMITS.SEARCH_GAP_MAX;
    const gap = gapMin + Math.floor(Math.random() * (gapMax - gapMin + 1));
    const wait = Math.max(0, last + gap * 1000 - Date.now());
    return { ok: true, waitMs: wait, quotaLeft: quota - st.searches, gap };
  }

  /** 记录一次搜索（必须在 canSearch ok 后调用） */
  async markSearch() {
    const st = await this._dayState();
    st.searches += 1;
    await this._set({ day_state: st, last_search_at: Date.now() });
    return st.searches;
  }

  /** 触发"访问频繁"：强制冷却 RATE_LIMIT_COOLDOWN_MIN */
  async onRateLimited() {
    const until = Date.now() + SAFETY_LIMITS.RATE_LIMIT_COOLDOWN_MIN * 60000;
    await this._set({ cooldown_until: until });
    return until;
  }

  /** 浏览停留守卫：采集前保证阅读时长 */
  async ensureViewStay(noteId) {
    const key = "view_" + noteId;
    const t = await this._get(key, 0);
    if (!t) {
      await this._set({ [key]: Date.now() });
      return { first: true };
    }
    const elapsed = (Date.now() - t) / 1000;
    return { first: false, elapsed, ok: elapsed >= SAFETY_LIMITS.VIEW_STAY_MIN_S };
  }

  /** 本地队列水位检查 */
  async queueWatermark() {
    const q = await this._get("proof_queue", []);
    return { count: q.length, max: SAFETY_LIMITS.LOCAL_QUEUE_MAX, full: q.length >= SAFETY_LIMITS.LOCAL_QUEUE_MAX };
  }
}

if (typeof module !== "undefined") module.exports = { SafetyEngine, SAFETY_LIMITS, SAFETY_VERSION };
