/**
 * safety_engine.js — 众包采集安全线引擎（硬编码，不可由参与者调整）
 *
 * 铁律：
 * 1. 所有阈值硬编码在 SAFETY_LIMITS，插件 UI 不暴露任何可调参数。
 * 2. 日搜索、会话时长、动作间隔、冷却时间均在本地持久化，重启不重置。
 * 3. 触发"访问频繁"→ 强制冷却；冷却期任何采集动作都被拒绝。
 * 4. 一机一号：device_salt 在首次运行时生成并永久绑定，不随账号变化。
 *
 * 契约版本：CROWD-CONTRACT-001 (sync_version=1)
 */
const SAFETY_VERSION = 1;

const SAFETY_LIMITS = Object.freeze({
  // 日搜索上限（配额只降不升：任务包 quota_day 小于此值时以任务包为准）
  DAILY_SEARCH_MAX: 30,
  // 动作间隔（秒）：硬下限 60s，随机化到 60-120s
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

  /** 当前任务包配额（只降不升） */
  async _currentQuota() {
    const task = await this._get("active_task", null);
    const q = task && task.quota_day ? task.quota_day : SAFETY_LIMITS.DAILY_SEARCH_MAX;
    return Math.min(q, SAFETY_LIMITS.DAILY_SEARCH_MAX);
  }

  /** 是否处于冷却期 */
  async inCooldown() {
    const cd = await this._get("cooldown_until", 0);
    if (cd && Date.now() < cd) {
      return { active: true, until: cd, leftMin: Math.ceil((cd - Date.now()) / 60000) };
    }
    return { active: false };
  }

  /** 检查会话：超过 SESSION_MAX_MIN 则进入强制冷却 */
  async _sessionGuard() {
    const st = await this._dayState();
    const now = Date.now();
    if (!st.sessionStart) {
      st.sessionStart = now;
      await this._set({ day_state: st });
      return { ok: true };
    }
    const mins = (now - st.sessionStart) / 60000;
    if (mins > SAFETY_LIMITS.SESSION_MAX_MIN) {
      const until = now + SAFETY_LIMITS.SESSION_COOLDOWN_MIN * 60000;
      await this._set({ cooldown_until: until });
      st.sessionStart = null;
      await this._set({ day_state: st });
      return { ok: false, reason: `会话超时，冷却 ${SAFETY_LIMITS.SESSION_COOLDOWN_MIN}min`, until };
    }
    return { ok: true };
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

    // 4. 动作间隔（随机 60-120s，基于上次搜索时间）
    const last = await this._get("last_search_at", 0);
    const gap = SAFETY_LIMITS.SEARCH_GAP_MIN +
      Math.floor(Math.random() * (SAFETY_LIMITS.SEARCH_GAP_MAX - SAFETY_LIMITS.SEARCH_GAP_MIN + 1));
    const wait = Math.max(0, last + gap * 1000 - Date.now());
    return { ok: true, waitMs: wait, quotaLeft: quota - st.searches };
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
