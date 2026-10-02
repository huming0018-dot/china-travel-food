/**
 * background.js — 众包美食家插件后台 Service Worker（v3 回流检测 + 报名即用 + 自动续领）
 *
 * 职责（全部在插件内闭环，符合 CROWD-CONTRACT-003 + crowd_rpc_security.sql）：
 *  1. 任务拉取：RPC crowd_fetch_tasks(participant_id, exclude_task_ids) → 返回 open 任务包（排除已完成）
 *  2. 关键词轮转：任务包 pack 内按索引顺序逐个采集，每关键词回传 accepted 达 kpi_min 标记完成
 *  3. 完成续领：包内全部关键词完成 → 记录 done_task_ids + 清 active_task → 下轮 heartbeat 自动领新包
 *  4. 回传 + 回流检测（v3）：RPC crowd_submit_proof → 服务端确认（ok=true 才算"真的入库"）→
 *     recordFlow() 记录 accepted/new_progress，连续零有效 → 回流异常告警（防虚假通过）
 *  5. 参与者状态：不再直连 crowd_participants 表（防泄漏），由 RPC 服务端校验
 *
 * 安全模型（2026-10-02 加固 + 续领 + 回流检测）：
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
  const pid = await safety._get("participant_id", "");
  if (!pid) return { ok: false, reason: "未填写参与编号（请打开插件选项页填写）" };
  if (!/^P-[A-Z0-9]{6,12}$/.test(pid)) return { ok: false, reason: "参与编号格式错误（应为 P-XXXXXX）" };
  return { ok: true, pid };
}

// ---------------------------------------------------------------- 关键词进度
async function kwState(taskId) {
  return (await safety._get("kw_state_" + taskId, null)) || {};
}

// 返回当前应采集的关键词索引：第一个未完成的关键词；全完成返回 -1
async function nextKwIndex(task) {
  const st = await kwState(task.task_id);
  for (let i = 0; i < task.pack.length; i++) {
    const k = st["" + i];
    if (!k || !k.done) return i;
  }
  return -1;
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

  // RPC：服务端校验非黑名单，返回 open 任务包（排除本地已完成的）
  const done = await safety._get("done_task_ids", []);
  const rpc = await callRpc("crowd_fetch_tasks", {
    p_participant_id: gate.pid,
    p_exclude_task_ids: done,
  });
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
  // 应用服务端拟合安全参数（只降不升：远程值永不放宽本地基线）
  await safety.applyRemoteLimits(r.safety_limits || null);
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

  // 轮转：取第一个未完成的关键词
  const idx = await nextKwIndex(task);
  if (idx < 0) {
    // 全部关键词完成 → 归档任务并续领
    await finalizeTask(task);
    return { status: "task_done_rotate", task_id: task.task_id };
  }
  const keyword = task.pack[idx];

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
  const seqBase = await safety._get("proof_seq_" + task.task_id + "_" + idx, 0);

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
    kw_index: idx, // 关键词进度定位（续领/轮转用）
    proof_seq: seqBase,
    captured_at: now,
    sync_version: CONFIG.SYNC_VERSION,
    items,
  };
  if (participant) {
    const q = await safety._get("proof_queue", []);
    q.push(envelope);
    const update = { proof_queue: q };
    update["proof_seq_" + task.task_id + "_" + idx] = seqBase + 1;
    await safety._set(update);
  }
  return { status: "collected", count: items.length, kw_index: idx, gate };
}

// ---------------------------------------------------------------- 回传（RPC）+ 回流检测 + 进度累计
async function uploadProofs() {
  const q = await safety._get("proof_queue", []);
  if (!q.length) return { status: "empty" };

  const participant = await safety._get("participant_id", null);
  if (!participant) return { status: "no_participant" };

  // 逐个信封回传（服务端幂等，重复静默跳过；失败保留队列下次重试）
  const failed = [];
  const touchedTasks = new Set();
  for (const body of q) {
    const rpc = await callRpc("crowd_submit_proof", {
      p_participant_id: participant,
      p_envelope: body,
    });
    // v3 回流检测：无论 accepted 多少，服务端返回 ok=true 即"服务端确实接收"（防虚假通过）
    if (rpc.ok && rpc.data && rpc.data.ok) {
      const d = rpc.data;
      const accepted = (d.accepted || 0);
      const flow = await safety.recordFlow(d);
      if (flow.stalled) {
        // 连续 N 次零有效 → 记录回流异常（popup 显示；不阻断采集，服务端去重属正常）
        await safety._set({ flow_stall_warned_at: Date.now() });
      }
      if (body.task_id != null && body.kw_index != null) {
        const key = "kw_state_" + body.task_id;
        const st = (await safety._get(key, {})) || {};
        const cur = st["" + body.kw_index] || { accepted: 0, done: false };
        cur.accepted = (cur.accepted || 0) + accepted;
        st["" + body.kw_index] = cur;
        await safety._set({ [key]: st });
        touchedTasks.add(body.task_id);
      }
    } else {
      failed.push(body);
    }
  }

  // 完成判定：包内所有关键词 accepted >= kpi_min → 归档任务
  const active = await safety._get("active_task", null);
  if (active && touchedTasks.has(active.task_id)) {
    const st = (await safety._get("kw_state_" + active.task_id, {})) || {};
    let allDone = active.pack.length > 0;
    for (let i = 0; i < active.pack.length; i++) {
      const k = st["" + i];
      if (!k || (k.accepted || 0) < active.kpi_min) { allDone = false; break; }
    }
    if (allDone) await finalizeTask(active);
  }

  // 全部成功则清队列；有失败保留失败子集（下次重试）
  await safety._set({ proof_queue: failed });
  return { status: failed.length ? "partial_failed" : "uploaded", failed: failed.length };
}

// ---------------------------------------------------------------- 任务归档（完成 → 续领）
async function finalizeTask(task) {
  // 记录已完成任务（服务端不再发放）
  const done = await safety._get("done_task_ids", []);
  if (!done.includes(task.task_id)) {
    done.push(task.task_id);
    await safety._set({ done_task_ids: done });
  }
  // 清理本地任务状态与进度
  const rm = {};
  rm["active_task"] = null;
  rm["kw_state_" + task.task_id] = null;
  await safety._set(rm);
}

// ---------------------------------------------------------------- 调度
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "collect_heartbeat") {
    doCollectOnce().then((r) => {
      console.log("[crowd] heartbeat →", r.status, r.reason || "", r.task_id ? "task=" + r.task_id : "");
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
      safety._get("done_task_ids", []),
      safety.flowSnapshot(),
    ]).then(async ([cd, ds, q, task, pid, gate, done, flow]) => {
      let kwProgress = null;
      if (task) {
        const st = (await safety._get("kw_state_" + task.task_id, {})) || {};
        kwProgress = task.pack.map((kw, i) => {
          const k = st["" + i];
          return { kw, accepted: k ? (k.accepted || 0) : 0, done: !!(k && k.done) };
        });
      }
      sendResponse({
        cooldown: cd,
        day: ds,
        queueLen: q.length,
        participantId: pid,
        gateBlockReason: gate,
        doneCount: done.length,
        flow, // v3: {zeroCount, stallThreshold, stalled, lastProgress, lastOkAgoSec}
        activeTask: task ? { task_id: task.task_id, pack_len: task.pack.length, kpi_min: task.kpi_min, kwProgress } : null,
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
  console.log("[crowd] installed v3 flow-check, sync_version=", CONFIG.SYNC_VERSION);
});
