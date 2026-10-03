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
// 重启后恢复服务端下发安全线（外部审计 #11：原实现重启丢 remote）
safety.restoreRemote().catch(() => {});

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
  if (!/^P-[A-Z0-9]{8}$/.test(pid)) return { ok: false, reason: "参与编号格式错误（应为 P- + 8位大写字母数字）" };
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
// 并发互斥（v3.1）：service worker 单线程但 alarm 周期触发可能重入
// （例如上次采集/回传因网络慢超过 HEARTBEAT_MIN），必须防重入：
//  - _running 标志：doCollectOnce 执行期间拒绝再次进入（busy 直接跳过）
//  - finally 释放：无论成功/异常都复位，避免永久锁死
let _running = false;

async function doCollectOnce() {
  if (_running) return { status: "busy" }; // 防重入：上次任务未结束
  _running = true;
  try {
    return await _collectOnceInner();
  } finally {
    _running = false;
  }
}

async function _collectOnceInner() {
  const wm = await safety.queueWatermark();
  // v3.2：满队列 → 暂停采集、只回传（水位是暂停信号，不是"攒够才回传"门槛）
  if (wm.full) {
    await uploadProofs();
    return { status: "queue_full_uploaded", count: wm.count };
  }

  const task = await fetchActiveTask();
  if (!task) return { status: "no_task" };

  const gate = await safety.canSearch();
  if (!gate.ok) return { status: "gated", reason: gate.reason };
  // v3.2：遵守安全线返回的动作间隔（外部审计 #11：原实现忽略 waitMs）
  if (gate.waitMs > 0) {
    await new Promise((r) => setTimeout(r, gate.waitMs));
  }

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

  // v3.2：单篇详情页模式 → 保证每篇阅读停留 ≥ VIEW_STAY_MIN_S（外部审计 #11）
  if (search.mode === "detail" && search.items && search.items.length) {
    const nid = search.items[0].note_id;
    if (nid) {
      const stay = await safety.ensureViewStay(nid);
      if (!stay.first && !stay.ok && stay.elapsed < SAFETY_LIMITS.VIEW_STAY_MIN_S) {
        await new Promise((r) => setTimeout(r, (SAFETY_LIMITS.VIEW_STAY_MIN_S - stay.elapsed) * 1000));
      }
    }
  }

  await safety.markSearch();

  if (search.rateLimited) {
    await safety.onRateLimited();
  }

  const participant = await safety._get("participant_id", null);
  const deviceSalt = await safety.getDeviceSalt(); // 一机一号辅助信号进提交链路（#12）
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
    device_salt: deviceSalt, // v3.2：设备指纹辅助风控（服务端校验绑定）
    items,
  };
  if (participant) {
    const q = await safety._get("proof_queue", []);
    q.push(envelope);
    const update = { proof_queue: q };
    update["proof_seq_" + task.task_id + "_" + idx] = seqBase + 1;
    await safety._set(update);
  }

  // v3.2：每批采集后立即尝试回传（外部审计 #4：不再等队列满才回传）
  const up = await uploadProofs();
  return { status: "collected", count: items.length, kw_index: idx, gate, upload: up.status };
}

// ---------------------------------------------------------------- 回传（RPC）+ 回流检测 + 进度累计
// v3.2 修复（外部审计 #10）：
//  - 服务端已提交但响应丢失 → 本地保留信封重试，服务端幂等返回原结果（accepted 恢复）
//  - 永久错误（任务关闭/参与者停用/任务不存在）→ 移出队列记录 permanent_failures，不再无限重试
const PERMANENT_REASONS = ["task_not_open", "task_closed", "task_not_found", "participant_suspended", "participant_not_found", "invalid_participant"];

async function uploadProofs() {
  const q = await safety._get("proof_queue", []);
  if (!q.length) return { status: "empty" };

  const participant = await safety._get("participant_id", null);
  if (!participant) return { status: "no_participant" };

  // 逐个信封回传（服务端幂等，重复静默跳过；失败保留队列下次重试）
  const failed = [];
  const permanent = [];
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
        // v3.2：每词 accepted ≥ kpi_min → 置 done=true（外部审计 #5：原实现永不置位导致不轮转）
        if ((cur.accepted || 0) >= (d.kpi_min || 5)) cur.done = true;
        st["" + body.kw_index] = cur;
        await safety._set({ [key]: st });
        touchedTasks.add(body.task_id);
      }
    } else {
      // 区分永久失败与临时失败（外部审计 #10：永久失败不得无限重试）
      const reason = ((rpc.data && rpc.data.reason) || rpc.reason || "").toLowerCase();
      if (PERMANENT_REASONS.some((r) => reason.includes(r))) {
        permanent.push(body);
      } else {
        failed.push(body);
      }
    }
  }

  // 完成判定：包内所有关键词 done → 归档任务（外部审计 #5：前后端完成标准统一为"每词达标"）
  const active = await safety._get("active_task", null);
  if (active && touchedTasks.has(active.task_id)) {
    const st = (await safety._get("kw_state_" + active.task_id, {})) || {};
    let allDone = active.pack.length > 0;
    for (let i = 0; i < active.pack.length; i++) {
      const k = st["" + i];
      if (!k || !k.done) { allDone = false; break; }
    }
    if (allDone) await finalizeTask(active);
  }

  // 成功清除、临时失败保留重试、永久失败移出并留痕
  await safety._set({ proof_queue: failed });
  if (permanent.length) {
    const rec = await safety._get("permanent_failures", []);
    rec.push({ at: Date.now(), task_id: permanent[0].task_id, reason: permanent[0].task_id ? "permanent" : "permanent", envelopes: permanent.length });
    await safety._set({ permanent_failures: rec });
  }
  return { status: failed.length ? "partial_failed" : "uploaded", failed: failed.length, permanent: permanent.length };
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
      safety._get("permanent_failures", []),
    ]).then(async ([cd, ds, q, task, pid, gate, done, flow, perm]) => {
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
        permanentCount: perm.length, // v3.2: 永久失败信封数（任务关闭/参与者停用）
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
