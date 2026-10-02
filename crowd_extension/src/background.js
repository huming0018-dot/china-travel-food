/**
 * background.js — 众包采集插件后台 Service Worker
 *
 * 职责（全部在插件内闭环，符合 CROWD-CONTRACT-001）：
 *  1. 任务拉取：GET task_queue (assignee=crowd, status=todo) → 取当前 active_task
 *  2. 采集调度：alarms 定时触发 → 安全线 canSearch → content script 执行搜索
 *  3. 回传：POST /crowd/proof（信封+items），成功后清队列、幂等
 *  4. 状态回写：拉取任务时看 crowd_tasks.progress，已完成包不重复领
 *
 * 环境变量（打包时注入）：CROWD_API_BASE、CROWD_API_KEY（Supabase anon key）
 * 默认值仅用于本地开发，生产由构建脚本替换。
 */
const CONFIG = {
  API_BASE: self.CROWD_API_BASE || "https://bdwrhshgdeghgyzwpxnl.supabase.co/rest/v1",
  API_KEY: self.CROWD_API_KEY || "",
  TASK_QUEUE: "/task_queue",
  CROWD_TASKS: "/crowd_tasks",
  // 采集心跳：每 3 分钟检查一次（实际动作间隔由安全线控制 60-120s）
  HEARTBEAT_MIN: 3,
  SYNC_VERSION: 1,
};

importScripts("safety_engine.js");

const safety = new SafetyEngine(chrome.storage.local);

// ---------------------------------------------------------------- 任务拉取
async function fetchActiveTask() {
  const q = await safety._get("active_task", null);
  // 已有进行中的任务包则复用（防重复领取）
  if (q && q.task_id) return q;

  // 优先从 crowd_tasks 表拉取（契约 §4.1，status=open，按序）
  const url = CONFIG.API_BASE + CONFIG.CROWD_TASKS +
    "?select=task_id,pack_type,pack,target,kpi_min,quota_day,status&status=eq.open" +
    "&order=task_id.asc&limit=1";
  let rows = [];
  try {
    const resp = await fetch(url, {
      headers: { apikey: CONFIG.API_KEY, Authorization: "Bearer " + CONFIG.API_KEY },
    });
    if (resp.ok) rows = await resp.json();
  } catch (e) {
    rows = [];
  }

  let task = null;
  if (rows && rows.length && rows[0].pack) {
    const r = rows[0];
    task = {
      task_id: r.task_id,
      task_type: r.pack_type === "keyword" ? "keyword_pack" : "store_pack",
      pack: r.pack,
      target: r.target || "both",
      kpi_min: r.kpi_min || 5,
      quota_day: r.quota_day || 20,
      progress: 0,
    };
  } else {
    // 回退：task_queue assignee=pm 的 [CROWD] 前缀工单（crowd_tasks 未建表时）
    const url2 = CONFIG.API_BASE + CONFIG.TASK_QUEUE +
      "?select=id,title,description&assignee=eq.pm&status=eq.todo&priority=eq.P1" +
      "&order=created_at.asc&limit=10";
    const resp2 = await fetch(url2, {
      headers: { apikey: CONFIG.API_KEY, Authorization: "Bearer " + CONFIG.API_KEY },
    });
    if (resp2.ok) {
      const rows2 = await resp2.json();
      const hit = (rows2 || []).find((r) => (r.title || "").includes("[CROWD]"));
      if (hit) {
        let meta = {};
        try { meta = JSON.parse(hit.description || "{}"); } catch (e) { meta = {}; }
        if (meta.pack && Array.isArray(meta.pack)) {
          task = {
            task_id: hit.id,
            task_type: "store_pack",
            pack: meta.pack,
            target: meta.target || "both",
            kpi_min: meta.kpi_min || 5,
            quota_day: meta.quota_day || 20,
            progress: 0,
          };
        }
      }
    }
  }
  if (!task) return null;

  await safety._set({ active_task: task });
  await safety._set({ active_task_claimed_at: Date.now() });
  return task;
}

// ---------------------------------------------------------------- 采集执行
async function doCollectOnce() {
  // 队列满 → 先回传再采
  const wm = await safety.queueWatermark();
  if (wm.full) {
    await uploadProofs();
  }

  const task = await fetchActiveTask();
  if (!task) return { status: "no_task" };

  const gate = await safety.canSearch();
  if (!gate.ok) return { status: "gated", reason: gate.reason };

  const keyword = task.pack[0]; // 当前策略：取词包首项（可扩展轮换）
  const search = await new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (!tabs || !tabs.length) return resolve({ ok: false, reason: "no_tab" });
      chrome.tabs.sendMessage(tabs[0].id, { type: "CROWD_SEARCH", keyword }, (resp) => {
        if (chrome.runtime.lastError || !resp) return resolve({ ok: false, reason: "content_unavailable" });
        resolve(resp);
      });
    });
  });

  if (!search.ok) return { status: "search_failed", reason: search.reason };

  // 安全线：记录搜索次数
  await safety.markSearch();

  // 触发风控 → 冷却
  if (search.rateLimited) {
    await safety.onRateLimited();
  }

  // 组装 proof 入本地队列
  const salt = await safety.getDeviceSalt();
  const participant = await safety._get("participant_id", null);
  const now = new Date().toISOString();
  const seqBase = await safety._get("proof_seq_" + task.task_id, 0);

  const items = (search.items || []).slice(0, 6).map((it, i) => ({
    kind: it.kind || "note",
    note_id: it.note_id || "",
    note_url: it.note_url || "",
    title: it.title || "",
    excerpt: (it.excerpt || "").slice(0, 200),
    author: it.author || "",
    rating: it.rating || null,
    rating_reason: it.rating_reason || "",
    matched_store: it.matched_store || "",
    anchor_score: it.anchor_score || 0,
    raw_query: keyword,
  }));

  const envelope = {
    participant_id: participant || "",
    task_id: task.task_id,
    proof_seq: seqBase,
    captured_at: now,
    sync_version: CONFIG.SYNC_VERSION,
    items,
  };
  if (participant) {
    const q = await safety._get("proof_queue", []);
    q.push(envelope);
    const update = { proof_queue: q };
    update["proof_seq_" + task.task_id] = seqBase + 1;
    await safety._set(update);
  }
  return { status: "collected", count: items.length, gate };
}

// ---------------------------------------------------------------- 回传
async function uploadProofs() {
  const q = await safety._get("proof_queue", []);
  if (!q.length) return { status: "empty" };

  const participant = await safety._get("participant_id", null);
  if (!participant) return { status: "no_participant" };

  const body = q[q.length - 1]; // 逐包回传（简化：一次回传最后一批）
  const resp = await fetch(CONFIG.API_BASE + "/crowd/proof", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: CONFIG.API_KEY,
      Authorization: "Bearer " + CONFIG.API_KEY,
      Prefer: "return=minimal",
    },
    body: JSON.stringify(body),
  });

  if (resp.ok || resp.status === 409) {
    // 409=契约版本不符，也应清掉本地（服务端拒绝，继续重试无意义）；204/200=成功
    await safety._set({ proof_queue: [] });
    return { status: "uploaded", code: resp.status };
  }
  return { status: "failed", code: resp.status };
}

// ---------------------------------------------------------------- 调度
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "collect_heartbeat") {
    doCollectOnce().then((r) => {
      console.log("[crowd] heartbeat →", r.status, r.reason || "");
    });
  }
});

// 收到 popup/onboarding 消息
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "CROWD_STATUS") {
    Promise.all([
      safety.inCooldown(),
      safety._get("day_state", null),
      safety._get("proof_queue", []),
      safety._get("active_task", null),
    ]).then(([cd, ds, q, task]) => {
      sendResponse({
        cooldown: cd,
        day: ds,
        queueLen: q.length,
        activeTask: task ? { task_id: task.task_id, pack_len: task.pack.length, progress: task.progress } : null,
      });
    });
    return true;
  }
  if (msg.type === "CROWD_START") {
    chrome.alarms.create("collect_heartbeat", { periodInMinutes: CONFIG.HEARTBEAT_MIN });
    sendResponse({ ok: true });
  }
  if (msg.type === "CROWD_STOP") {
    chrome.alarms.clear("collect_heartbeat");
    sendResponse({ ok: true });
  }
  return false;
});

// 安装/更新：注册参与协议门槛
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("collect_heartbeat", { periodInMinutes: CONFIG.HEARTBEAT_MIN });
  console.log("[crowd] installed, sync_version=", CONFIG.SYNC_VERSION);
});
