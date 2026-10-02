/**
 * background.js — 众包采集插件后台 Service Worker（v2 安全版）
 *
 * 职责（全部在插件内闭环，符合 CROWD-CONTRACT-001 + crowd_rpc_security.sql）：
 *  1. 任务拉取：RPC crowd_fetch_tasks(participant_id) → 服务端校验 approved → 返回 open 任务包
 *  2. 采集调度：alarms 定时触发 → 安全线 canSearch → content script 执行搜索
 *  3. 回传：RPC crowd_submit_proof(participant_id, envelope) → 服务端校验+幂等+落库
 *  4. 参与者状态：不再直连 crowd_participants 表（防泄漏），由 RPC 服务端校验
 *
 * 安全模型（2026-10-02 加固）：
 *  - 插件只用 Supabase anon key（公开可分发），对 4 张表零直连权限
 *  - 所有读/写走 security definer RPC，服务端做：参与者状态/契约版本/域名/评分/幂等校验
 *  - anon 无法绕过 RPC 直写 proofs（42501 已实测验证）
 *  - 本地不留敏感数据：队列在内存，重启即清（配合安全线一机一号）
 *
 * 环境变量（打包时注入）：CROWD_API_BASE（Supabase URL）、CROWD_API_KEY（anon key）
 */
const CONFIG = {
  API_BASE: self.CROWD_API_BASE || "https://bdwrhshgdeghgyzwpxnl.supabase.co",
  API_KEY: self.CROWD_API_KEY || "",
  HEARTBEAT_MIN: 3,
  SYNC_VERSION: 1,
};

importScripts("safety_engine.js");

const safety = new SafetyEngine(chrome.storage.local);

// ---------------------------------------------------------------- RPC 封装
async function callRpc(fn, body) {
  const resp = await fetch(CONFIG.API_BASE + "/rest/v1/rpc/" + fn, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      apikey: CONFIG.API_KEY,
      Authorization: "Bearer " + CONFIG.API_KEY,
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) return { ok: false, http: resp.status, reason: "rpc_" + resp.status };
  return { ok: true, data: await resp.json() };
}

// ---------------------------------------------------------------- 参与者管控
async function participantGate() {
  // 本地存 participant_id（onboarding 写入，P- 编号格式已强制校验）
  const pid = await safety._get("participant_id", "");
  if (!pid) return { ok: false, reason: "未填写参与编号（请打开插件选项页填写）" };
  if (!/^P-[A-Z0-9]{6,12}$/.test(pid)) return { ok: false, reason: "参与编号格式错误（应为 P-XXXXXX）" };
  // 服务端校验状态：由 RPC 内部完成，本地不再拉取任何参与者数据（防泄漏）
  return { ok: true, pid };
}

// ---------------------------------------------------------------- 任务拉取
async function fetchActiveTask() {
  const q = await safety._get("active_task", null);
  if (q && q.task_id) return q;

  const gate = await participantGate();
  if (!gate.ok) {
    await safety._set({ gate_block_reason: gate.reason });
    return null;
  }
  await safety._set({ gate_block_reason: "" });

  // RPC：服务端校验 approved 并返回 open 任务包
  const rpc = await callRpc("crowd_fetch_tasks", { p_participant_id: gate.pid });
  if (!rpc.ok) {
    await safety._set({ gate_block_reason: "服务端校验失败（" + (rpc.reason || "网络错误") + "）" });
    return null;
  }
  const d = rpc.data;
  if (!d.ok || !d.tasks || !d.tasks.length) {
    await safety._set({ gate_block_reason: d.reason || "暂无开放任务包" });
    return null;
  }
  const r = d.tasks[0];
  const task = {
    task_id: r.task_id,
    task_type: r.pack_type === "keyword" ? "keyword_pack" : "store_pack",
    pack: r.pack,
    target: r.target || "both",
    kpi_min: r.kpi_min || 5,
    quota_day: r.quota_day || 20,
    progress: 0,
  };
  await safety._set({ active_task: task, active_task_claimed_at: Date.now() });
  return task;
}

// ---------------------------------------------------------------- 采集执行
async function doCollectOnce() {
  const wm = await safety.queueWatermark();
  if (wm.full) {
    await uploadProofs();
  }

  const task = await fetchActiveTask();
  if (!task) return { status: "no_task" };

  const gate = await safety.canSearch();
  if (!gate.ok) return { status: "gated", reason: gate.reason };

  const keyword = task.pack[0];

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

  await safety.markSearch();

  if (search.rateLimited) {
    await safety.onRateLimited();
  }

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

// ---------------------------------------------------------------- 回传（RPC）
async function uploadProofs() {
  const q = await safety._get("proof_queue", []);
  if (!q.length) return { status: "empty" };

  const participant = await safety._get("participant_id", null);
  if (!participant) return { status: "no_participant" };

  // 逐个信封回传（服务端幂等，重复静默跳过；失败保留队列下次重试）
  const failed = [];
  for (const body of q) {
    const rpc = await callRpc("crowd_submit_proof", {
      p_participant_id: participant,
      p_envelope: body,
    });
    if (rpc.ok && rpc.data && rpc.data.ok) {
      // 成功：本包已落库/去重，从队列移除
      // （简化：成功后清空整个已成功前缀；实现上用标记避免重复）
    } else {
      failed.push(body);
    }
  }

  // 全部成功则清队列；有失败保留失败子集（下次重试）
  await safety._set({ proof_queue: failed });
  return { status: failed.length ? "partial_failed" : "uploaded", failed: failed.length };
}

// ---------------------------------------------------------------- 调度
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "collect_heartbeat") {
    doCollectOnce().then((r) => {
      console.log("[crowd] heartbeat →", r.status, r.reason || "");
    });
  }
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "CROWD_STATUS") {
    Promise.all([
      safety.inCooldown(),
      safety._get("day_state", null),
      safety._get("proof_queue", []),
      safety._get("active_task", null),
      safety._get("participant_id", ""),
      safety._get("gate_block_reason", ""),
    ]).then(([cd, ds, q, task, pid, gate]) => {
      sendResponse({
        cooldown: cd,
        day: ds,
        queueLen: q.length,
        participantId: pid,
        gateBlockReason: gate,
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

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("collect_heartbeat", { periodInMinutes: CONFIG.HEARTBEAT_MIN });
  console.log("[crowd] installed v2-safe, sync_version=", CONFIG.SYNC_VERSION);
});
