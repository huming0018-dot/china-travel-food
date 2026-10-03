/**
 * safety_engine.js — 众包美食家安全线引擎 v3（服务端拟合下发 + 本地只降不升 + 回流检测）
 *
 * 铁律：
 * 1. 本地默认阈值 = 硬编码 SAFETY_LIMITS（保守基线，永不放大）。
 * 2. 服务端按拟合模型下发 remote_limits（quota_day/gap/session/cooldown），
 *    插件 applyRemoteLimits() 应用时【只降不升】——任何远程值都不能超过本地基线。
 * 3. 日搜索、会话时长、动作间隔、冷却时间均在本地持久化，重启不重置。
 * 4. 触发"访问频繁"→ 强制冷却；冷却期任何采集动作都被拒绝。
 * 5. 一机一号：device_salt 在首次运行时生成并永久绑定，不随账号变化。
 * 6. 回流检测（v3）：每次 RPC 回传后记录服务端返回 new_progress/accepted，
 *    连续 N 次零有效回传 → 判定"回流失效"（防虚假通过）。
 *
 * 契约版本：CROWD-CONTRACT-003 (sync_version=1)
 */
const SAFETY_VERSION = 3;

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
  // 回流检测：连续 N 次回传零有效 → 判回流失效
  FLOW_STALL_THRESHOLD: 3,
});

class SafetyEngine {
  constructor(storage) {
    this.s = storage || chrome.storage.local;
    this.remote = null; // 服务端拟合参数（仅存储应用后的有效值）
  }

  /** 应用服务端拟合参数（只降不升：任何远程值不能放宽本地基线） */
  async applyRemoteLimits(remote) {
    if (!remote || typeof remote !== "object") return;
    // 收紧方向：次数/会话上限取 min（越少越严）；间隔/冷却下限取 max（越长越严）
    const clampUpper = (val, base) => (typeof val === "number" && val > 0 ? Math.min(val, base) : null);
    const clampLower = (val, base) => (typeof val === "number" && val > 0 ? Math.max(val, base) : null);
    this.remote = {
      quota_day: clampUpper(remote.quota_day, SAFETY_LIMITS.DAILY_SEARCH_MAX),
      gap_min: clampLower(remote.gap_min, SAFETY_LIMITS.SEARCH_GAP_MIN),   // 下限不低于本地 60s
      gap_max: clampUpper(remote.gap_max, SAFETY_LIMITS.SEARCH_GAP_MAX),   // 上限不高于本地 120s
      session_min: clampUpper(remote.session_min, SAFETY_LIMITS.SESSION_MAX_MIN),
      cooldown_min: clampLower(remote.cooldown_min, SAFETY_LIMITS.SESSION_COOLDOWN_MIN), // 冷却不短于本地 30min
    };
    await this._set({ remote_limits_applied: this.remote, remote_limits_at: Date.now() });
  }

  /** 重启后从 storage 恢复已应用的服务端配置（外部审计 #11：原实现重启丢 remote） */
  async restoreRemote() {
    try {
      const saved = await this._get("remote_limits_applied", null);
      if (saved && typeof saved === "object" && saved.cooldown_min !== undefined) {
        this.remote = saved;
      }
    } catch (e) { /* storage 异常时保持 null，走本地基线 */ }
    return this.remote;
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
      ? Math.max(this.remote.cooldown_min, SAFETY_LIMITS.SESSION_COOLDOWN_MIN)
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
      cooldownMin: this.remote && this.remote.cooldown_min ? Math.max(this.remote.cooldown_min, SAFETY_LIMITS.SESSION_COOLDOWN_MIN) : SAFETY_LIMITS.SESSION_COOLDOWN_MIN,
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

  // ────────────────────── 回流检测（v3） ──────────────────────
  /**
   * 记录一次 RPC 回传结果，判定是否"回流失效"。
   * rpcResp = {ok, accepted, new_progress} 来自 crowd_submit_proof。
   * 判定规则：服务端返回 ok=true 视为"服务端确实接收"（防虚假通过）；
   * 若连续 FLOW_STALL_THRESHOLD 次 accepted=0（全部去重/拒收）→ 回流失效告警。
   */
  async recordFlow(rpcResp) {
    if (!rpcResp || rpcResp.ok !== true) {
      // 网络失败/服务端拒：计数清零（这不是"回流失效"，是回传失败，下次会重试）
      return { stalled: false, reason: "upload_failed" };
    }
    const accepted = rpcResp.accepted || 0;
    const st = await this._get("flow_state", { zero_count: 0, last_progress: null, last_ok_ts: 0 });
    st.last_ok_ts = Date.now();
    if (rpcResp.new_progress != null) st.last_progress = rpcResp.new_progress;
    if (accepted === 0) {
      st.zero_count = (st.zero_count || 0) + 1;
    } else {
      st.zero_count = 0;
    }
    const stalled = st.zero_count >= SAFETY_LIMITS.FLOW_STALL_THRESHOLD;
    await this._set({ flow_state: st, flow_last_result: { at: Date.now(), accepted, new_progress: rpcResp.new_progress } });
    return { stalled, reason: stalled ? "flow_stalled" : "flow_ok", zero_count: st.zero_count };
  }

  /** 回流健康快照（供 popup 展示） */
  async flowSnapshot() {
    const st = await this._get("flow_state", { zero_count: 0, last_progress: null, last_ok_ts: 0 });
    return {
      zeroCount: st.zero_count || 0,
      stallThreshold: SAFETY_LIMITS.FLOW_STALL_THRESHOLD,
      stalled: (st.zero_count || 0) >= SAFETY_LIMITS.FLOW_STALL_THRESHOLD,
      lastProgress: st.last_progress,
      lastOkAgoSec: st.last_ok_ts ? Math.round((Date.now() - st.last_ok_ts) / 1000) : null,
    };
  }
}

if (typeof module !== "undefined") module.exports = { SafetyEngine, SAFETY_LIMITS, SAFETY_VERSION };
