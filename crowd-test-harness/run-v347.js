/**
 * run-v347.js — v3.4.7 独立验证补测（V1–V7）
 *  V1 同意门与队列解耦（发布安全关键：老安装升级后滞留信封必须能回传）
 *  V2 F12 认证熔断（401×3 → auth_fail_count/quota_blocked_until/信封留存；恢复 → 排空清零）
 *  V3 F14 必拒条目预检（真实采集链路）
 *  V4 F10 last_sid 幂等重放去重
 *  V5 F15 upload_retry alarm 不饿死
 *  V6 F13 warmup NaN 回退探针
 *  V7 F16 done_task_ids 封顶探针
 * 运行：node run-v347.js
 */
const path = require("path");
const fs = require("fs");
const { launch } = require("./harness");

const PID = "P-E2E0001";
const AGREED = new Date().toISOString();
const TASK = { task_id: "T-V-1", task_type: "keyword_pack", pack: ["烤鸭"], target: "both", kpi_min: 10, quota_day: 20, progress: 0 };

let seq = 400;
function mkEnv(over = {}) {
  const n = ++seq;
  return {
    submission_id: "sub-v-" + n, participant_id: PID, task_id: TASK.task_id, kw_index: 0, kpi_min: 10,
    proof_seq: n, captured_at: new Date().toISOString(), sync_version: 3, retry_count: 0, next_retry_at: 0,
    items: [
      { kind: "note", note_id: "v" + n + "a", note_url: "", title: "t", excerpt: "", author: "", rating: null, rating_reason: "", matched_store: "", anchor_score: 0, raw_query: "烤鸭" },
      { kind: "note", note_id: "v" + n + "b", note_url: "", title: "t", excerpt: "", author: "", rating: null, rating_reason: "", matched_store: "", anchor_score: 0, raw_query: "烤鸭" },
    ],
    ...over,
  };
}

const results = [];
function check(id, name, cond, detail) {
  results.push({ id, name, pass: !!cond, detail });
  console.log(`  ${cond ? "PASS" : "FAIL"}  [${id}] ${name}${cond ? "" : "  → " + JSON.stringify(detail)}`);
}

(async () => {
  const h = await launch();
  const { state } = h;
  console.log("[harness] intercept mode:", state.interceptMode);
  const excMark = () => state.swExceptions.length;
  let m;

  const reset = async (seed = {}) => {
    await h.storageClear();
    await h.storageSet({
      fix_v344_flushed: true, participant_id: PID, agreed_at: AGREED, collector_running: false,
      quota_blocked_until: 0, global_pause: false, gate_block_reason: "", auth_fail_count: 0, ...seed,
    });
  };
  const forceDaylight = () => h.swEval(`(() => {
    safety.isCircadianAllowed = async () => ({ ok: true, weight: 1 });
    safety.canStartSession = async () => ({ ok: true, actionsLeft: 99 });
    safety.canSearch = async () => ({ ok: true, waitMs: 0, quotaLeft: 50, gap: 0 });
    return true;
  })()`);
  const forceRetryNow = async () => {
    const q = (await h.storageGet(["proof_queue"])).proof_queue || [];
    q.forEach((b) => { b.next_retry_at = 0; });
    await h.storageSet({ proof_queue: q });
  };

  // ── V1 同意门与队列解耦（participant_id 有、agreed_at 无 = 老安装升级形态）──
  console.log("\n=== V1 同意门与队列解耦 ===");
  await reset();
  await h.swEval("chrome.storage.local.remove('agreed_at')"); // 模拟老安装：有 participant_id、无 agreed_at
  const envV1a = mkEnv(), envV1b = mkEnv();
  await h.storageSet({ proof_queue: [envV1a, envV1b] });
  await h.setMock({
    crowd_fetch_tasks: { body: { ok: true, tasks: [{ task_id: "T-V-NEW", pack_type: "keyword", pack: ["火锅"], kpi_min: 1, quota_day: 20 }], safety: { pause: false } } },
    crowd_submit_proof: { bodyFn: (req) => ({ ok: true, accepted: req.p_envelope.items.length, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })), keyword_progress: [{ keyword: "烤鸭", accepted: 2 }] }) },
  });
  m = excMark();
  const gateV1 = await h.swEval("fetchActiveTask()");
  const gbrV1 = (await h.storageGet(["gate_block_reason"])).gate_block_reason;
  check("V1", "无 agreed_at → fetchActiveTask 被门禁拦截", gateV1 === null && /知情同意/.test(gbrV1 || ""), { gateV1, gbrV1 });
  const colV1 = await h.swEval("doCollectOnce()");
  check("V1", "无 agreed_at → 采集不启动（no_task）", colV1 && colV1.status === "no_task", colV1);
  // 注意：doCollectOnce 的 upload-first 在门禁之前，队列已被排空——重新置队列单独验 uploadProofs 路径
  await h.storageSet({ proof_queue: [mkEnv(), mkEnv()] });
  const upV1 = await h.swEval("uploadProofs()");
  const qV1 = (await h.storageGet(["proof_queue"])).proof_queue || [];
  check("V1", "无 agreed_at → 滞留队列仍正常回传排空（uploadProofs 不走同意门）",
    upV1 && upV1.status === "uploaded" && upV1.sent === 2 && qV1.length === 0, { upV1, qV1 });
  const callsV1 = (await h.getRpcCalls()).filter((c) => c.fn === "crowd_submit_proof").length;
  check("V1", "滞留信封真实发出（含 collect 内 upload-first 的 2 封 + 直接 uploadProofs 的 2 封）", callsV1 === 4, callsV1);
  check("V1", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── V2 F12 认证熔断 ──
  console.log("\n=== V2 F12 401 熔断与恢复 ===");
  await reset({ proof_queue: [mkEnv()], active_task: TASK });
  await h.setMock({ crowd_submit_proof: { status: 401, body: { message: "JWT expired" } } });
  m = excMark();
  const authSeq = [];
  for (let i = 0; i < 3; i++) {
    await forceRetryNow();
    await h.swEval("uploadProofs()");
    authSeq.push((await h.storageGet(["auth_fail_count"])).auth_fail_count);
  }
  const sV2 = await h.storageGet(["auth_fail_count", "quota_blocked_until", "gate_block_reason", "proof_queue", "deadLetter"]);
  check("V2", "连续 401 → auth_fail_count 1→2→3 递增", authSeq.join() === "1,2,3", authSeq);
  check("V2", "第三次后熔断：quota_blocked_until ≈ +30min",
    Math.abs((sV2.quota_blocked_until || 0) - (Date.now() + 30 * 60000)) < 60000,
    { quota_blocked_until: sV2.quota_blocked_until, deltaMin: ((sV2.quota_blocked_until || 0) - Date.now()) / 60000 });
  check("V2", "熔断原因 popup 可见（gate_block_reason 含认证）", /认证/.test(sV2.gate_block_reason || ""), sV2.gate_block_reason);
  check("V2", "401 全程：信封不丢、不进死信", (sV2.proof_queue || []).length === 1 && (sV2.deadLetter || []).length === 0, { q: (sV2.proof_queue || []).length, dl: (sV2.deadLetter || []).length });
  // 恢复 200 → 排空且计数清零
  await h.setMock({ crowd_submit_proof: { bodyFn: (req) => ({ ok: true, accepted: 2, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })), keyword_progress: [{ keyword: "烤鸭", accepted: 2 }] }) } });
  await forceRetryNow();
  const upV2 = await h.swEval("uploadProofs()");
  const sV2b = await h.storageGet(["auth_fail_count", "proof_queue", "quota_blocked_until"]);
  check("V2", "恢复 200 → 队列排空 + auth_fail_count 清零",
    upV2.status === "uploaded" && (sV2b.proof_queue || []).length === 0 && sV2b.auth_fail_count === 0,
    { upV2, auth_fail_count: sV2b.auth_fail_count });
  console.log("  [观察] 认证恢复后 quota_blocked_until 是否自动解除:", sV2b.quota_blocked_until > Date.now() ? "不解除（park 满 30min，到期自然解除）" : "已解除");
  // 403 同路径探针
  await reset({ proof_queue: [mkEnv()], active_task: TASK });
  await h.setMock({ crowd_submit_proof: { status: 403, body: {} } });
  await h.swEval("uploadProofs()");
  const sV2c = await h.storageGet(["auth_fail_count", "proof_queue", "deadLetter"]);
  check("V2", "403 同走 auth 临时退避（计数+1，不死信）", sV2c.auth_fail_count === 1 && (sV2c.proof_queue || []).length === 1 && (sV2c.deadLetter || []).length === 0, { afc: sV2c.auth_fail_count });
  check("V2", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── V3 F14 必拒条目预检（真实采集链路）──
  console.log("\n=== V3 F14 预检 ===");
  await reset({ proof_queue: [], active_task: TASK });
  await forceDaylight();
  h.setFakePageMode("f14");
  await h.setMock({
    crowd_submit_proof: { bodyFn: (req) => ({ ok: true, accepted: req.p_envelope.items.length, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })), keyword_progress: [{ keyword: "烤鸭", accepted: req.p_envelope.items.length }] }) },
  });
  m = excMark();
  const rV3 = await h.swEval("doCollectOnce()");
  h.setFakePageMode("normal");
  const submitV3 = (await h.getRpcCalls()).filter((c) => c.fn === "crowd_submit_proof");
  const sentIds = submitV3.length && submitV3[0].body.p_envelope.items.map((it) => it.note_id);
  check("V3", "采集成功且有信封发出", rV3 && rV3.status === "collected" && submitV3.length >= 1, { rV3, calls: submitV3.length });
  check("V3", "只有标题过线的 F14KEEP01 送出；'烤'(1字)/'！'(标点剥离0字)/空标题 三条被丢",
    sentIds && sentIds.join() === "F14KEEP01", sentIds);
  check("V3", "SW 日志有 F14 预检丢弃记录", state.swLogs.some((l) => /F14 预检丢弃必拒条目 x3/.test(l.line)), state.swLogs.filter((l) => /F14/.test(l.line)).map((l) => l.line));
  check("V3", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── V4 F10 last_sid 幂等重放去重 ──
  console.log("\n=== V4 F10 last_sid 去重 ===");
  await reset({ proof_queue: [], active_task: TASK });
  const envV4 = mkEnv({ submission_id: "sub-v-replay" });
  // 兜底路径（服务端不回 keyword_progress）：ok 回执重放两次
  await h.setMock({
    crowd_submit_proof: { bodyFn: (req) => ({ ok: true, accepted: 2, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })) }) },
  });
  m = excMark();
  await h.storageSet({ proof_queue: [envV4] });
  await h.swEval("uploadProofs()");
  let kwV4 = (await h.storageGet(["kw_state_" + TASK.task_id]))["kw_state_" + TASK.task_id] || {};
  const acc1 = kwV4["0"] && kwV4["0"].accepted;
  await h.storageSet({ proof_queue: [envV4] }); // 同一 submission_id 重放同一回执
  await h.swEval("uploadProofs()");
  kwV4 = (await h.storageGet(["kw_state_" + TASK.task_id]))["kw_state_" + TASK.task_id] || {};
  const acc2 = kwV4["0"] && kwV4["0"].accepted;
  check("V4", "同一 submission_id 回执重放 → accepted 不翻倍（2 → 2）", acc1 === 2 && acc2 === 2, { acc1, acc2 });
  check("V4", "last_sid 已记录", kwV4["0"] && kwV4["0"].last_sid === "sub-v-replay", kwV4["0"]);
  // 新信封（不同 sid）正常累计
  const envV4b = mkEnv();
  await h.storageSet({ proof_queue: [envV4b] });
  await h.swEval("uploadProofs()");
  kwV4 = (await h.storageGet(["kw_state_" + TASK.task_id]))["kw_state_" + TASK.task_id] || {};
  check("V4", "新 submission_id 正常累计（2 → 4）", kwV4["0"] && kwV4["0"].accepted === 4, kwV4["0"]);
  // 权威分支整行覆盖时 last_sid 保留
  await h.setMock({
    crowd_submit_proof: { bodyFn: (req) => ({ ok: true, accepted: 2, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })), keyword_progress: [{ keyword: "烤鸭", accepted: 7 }] }) },
  });
  const envV4c = mkEnv();
  await h.storageSet({ proof_queue: [envV4c] });
  await h.swEval("uploadProofs()");
  kwV4 = (await h.storageGet(["kw_state_" + TASK.task_id]))["kw_state_" + TASK.task_id] || {};
  check("V4", "keyword_progress 权威覆盖 accepted=7 且 last_sid 不丢", kwV4["0"] && kwV4["0"].accepted === 7 && !!kwV4["0"].last_sid, kwV4["0"]);
  check("V4", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── V5 F15 upload_retry alarm 不饿死 ──
  console.log("\n=== V5 F15 alarm 不饿死 ===");
  await h.swEval("new Promise((res) => chrome.alarms.clearAll(() => res(1)))");
  m = excMark();
  await h.swEval("initBackground()");
  const a1 = await h.swEval("new Promise((res) => chrome.alarms.get('upload_retry', (a) => res(a && a.scheduledTime)))");
  await new Promise((r) => setTimeout(r, 1200));
  await h.swEval("initBackground()");
  const a2 = await h.swEval("new Promise((res) => chrome.alarms.get('upload_retry', (a) => res(a && a.scheduledTime)))");
  check("V5", "两次 initBackground 后 upload_retry scheduledTime 不变（不重置计时）", !!a1 && a1 === a2, { a1, a2, diffMs: a2 - a1 });
  check("V5", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── V6 F13 warmup NaN 回退探针 ──
  console.log("\n=== V6 F13 warmup NaN ===");
  await reset();
  await h.storageSet({ warmup_state: { first_run_date: "garbage-date" } });
  m = excMark();
  const csV6 = await h.swEval("safety.canSearch()");
  check("V6", "first_run_date 损坏 → 回退 fraction=1，配额闸门正常（quotaLeft 为有限数）",
    csV6 && csV6.ok === true && Number.isFinite(csV6.quotaLeft), csV6 && { ok: csV6.ok, quotaLeft: csV6.quotaLeft });
  check("V6", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── V7 F16 done_task_ids 封顶探针 ──
  console.log("\n=== V7 F16 done_task_ids 封顶 ===");
  await reset();
  const big = Array.from({ length: 200 }, (_, i) => "T-OLD-" + i);
  await h.storageSet({ done_task_ids: big, active_task: null });
  m = excMark();
  await h.swEval(`finalizeTask(${JSON.stringify({ task_id: "T-NEW-201", pack: ["x"], kpi_min: 1 })})`);
  const doneV7 = (await h.storageGet(["done_task_ids"])).done_task_ids || [];
  check("V7", "200 封顶滚动：加入第 201 个后长度仍 200，最旧被挤出",
    doneV7.length === 200 && doneV7.includes("T-NEW-201") && !doneV7.includes("T-OLD-0"),
    { len: doneV7.length, hasNew: doneV7.includes("T-NEW-201"), hasOldest: doneV7.includes("T-OLD-0") });
  check("V7", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  const pass = results.filter((r) => r.pass).length;
  const fail = results.filter((r) => !r.pass);
  console.log(`\n========== v347 补测：${pass}/${results.length} 通过 ==========`);
  fail.forEach((f) => console.log(`  FAIL [${f.id}] ${f.name} → ${JSON.stringify(f.detail)}`));
  console.log("泄漏：", state.leaks.length, state.leaks);
  console.log("页面异常：", state.pageErrors.length, "SW 异常：", state.swExceptions.length);

  fs.mkdirSync(path.join(__dirname, "results"), { recursive: true });
  fs.writeFileSync(path.join(__dirname, "results", "v347.json"), JSON.stringify({ at: new Date().toISOString(), results, leaks: state.leaks, swExceptions: state.swExceptions, pageErrors: state.pageErrors }, null, 2));
  await state.browser.close();
  fs.rmSync(state.userDataDir, { recursive: true, force: true });
  process.exit(fail.length ? 1 : 0);
})().catch((e) => { console.error("HARNESS CRASH:", e); process.exit(2); });
