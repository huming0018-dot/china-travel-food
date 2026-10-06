/**
 * run-extra.js — 边界路径补测（X1–X13）
 * 运行：node run-extra.js
 */
const path = require("path");
const fs = require("fs");
const { launch } = require("./harness");

const PID = "P-E2E0001";
const TASK1 = { task_id: "T-X-1", task_type: "keyword_pack", pack: ["烤鸭", "火锅"], target: "both", kpi_min: 2, quota_day: 20, progress: 0 };

let seq = 100;
function mkEnv(over = {}) {
  const n = ++seq;
  return {
    submission_id: "sub-x-" + n, participant_id: PID, task_id: TASK1.task_id, kw_index: 0, kpi_min: 2,
    proof_seq: n, captured_at: new Date().toISOString(), sync_version: 3, retry_count: 0, next_retry_at: 0,
    items: [
      { kind: "note", note_id: "x" + n + "a", note_url: "", title: "t", excerpt: "", author: "", rating: null, rating_reason: "", matched_store: "", anchor_score: 0, raw_query: "烤鸭" },
      { kind: "note", note_id: "x" + n + "b", note_url: "", title: "t", excerpt: "", author: "", rating: null, rating_reason: "", matched_store: "", anchor_score: 0, raw_query: "烤鸭" },
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

  const reset = async (seed = {}) => {
    await h.storageClear();
    await h.storageSet({
      fix_v344_flushed: true, participant_id: PID, agreed_at: new Date().toISOString(), collector_running: false,
      quota_blocked_until: 0, global_pause: false, gate_block_reason: "", ...seed,
    });
  };
  const m0 = state.swExceptions.length;

  // X1/X4 需要穿过时段/会话闸门（凌晨真实权重≈0.001 会被 circadian 拦下，属设计行为）
  const forceDaylight = () => h.swEval(`(() => {
    safety.isCircadianAllowed = async () => ({ ok: true, weight: 1 });
    safety.canStartSession = async () => ({ ok: true, actionsLeft: 99 });
    return true;
  })()`);

  // ── X1 fetch_tasks 返回 JSON null（data=null）→ 不应崩死，应走 error 路径 ──
  console.log("\n=== X1 crowd_fetch_tasks 返回 null ===");
  await reset({ done_task_ids: [] });
  await h.setMock({ crowd_fetch_tasks: { body: null } });
  await forceDaylight();
  const r1 = await h.swEval("doCollectOnce()");
  check("X1", "BUG-3 修复：data=null → 按'暂无任务'收场（no_task，不再 TypeError）", r1 && r1.status === "no_task", r1);

  // ── X2 过期 quota_blocked_until 自动解除 ──
  console.log("\n=== X2 过期 quota_blocked_until 解除 ===");
  await reset({ quota_blocked_until: Date.now() - 60000, done_task_ids: ["*"] });
  await h.setMock({ crowd_fetch_tasks: { body: { ok: false, reason: "no_open_tasks" } } });
  const r2 = await h.swEval("doCollectOnce()");
  const qb2 = (await h.storageGet(["quota_blocked_until"])).quota_blocked_until;
  check("X2", "过期 park 清零并继续调度", qb2 === 0 && r2 && r2.status !== "quota_blocked", { qb2, r2 });

  // ── X3 global_pause 熔断 ──
  console.log("\n=== X3 global_pause ===");
  await reset({ global_pause: true, proof_queue: [] });
  const r3 = await h.swEval("doCollectOnce()");
  check("X3", "全局暂停生效", r3 && r3.status === "global_pause", r3);

  // ── X4 队列满(≥100)且全部退避中 → queue_full 暂停采集 ──
  console.log("\n=== X4 队列水位 queue_full ===");
  const full = Array.from({ length: 100 }, () => mkEnv({ next_retry_at: Date.now() + 3600000 }));
  await reset({ proof_queue: full, active_task: TASK1 });
  await h.setMock({}); // 全部退避，不会发请求
  await forceDaylight();
  const r4 = await h.swEval("doCollectOnce()");
  check("X4", "队列满且无法排空 → queue_full", r4 && r4.status === "queue_full" && r4.count === 100, r4);
  check("X4", "退避中的信封未被误发请求", (await h.getRpcCalls()).length === 0, (await h.getRpcCalls()).length);

  // ── X5 历史信封缺 submission_id → 补齐并持久化 ──
  console.log("\n=== X5 历史信封补 submission_id ===");
  const legacy = mkEnv(); delete legacy.submission_id;
  await reset({ proof_queue: [legacy], active_task: TASK1 });
  await h.setMock({ crowd_submit_proof: { status: 500, body: {} } }); // 让它留在队列里
  await h.swEval("uploadProofs()");
  const q5 = (await h.storageGet(["proof_queue"])).proof_queue || [];
  check("X5", "补齐 submission_id 并随队列持久化", q5.length === 1 && typeof q5[0].submission_id === "string" && q5[0].submission_id.length > 0, q5[0] && q5[0].submission_id);

  // ── X6 逐条回执：部分终态部分 temp → 信封瘦身保留 temp 条目 ──
  console.log("\n=== X6 逐条 verdict 部分终态 ===");
  const env6 = mkEnv();
  await reset({ proof_queue: [env6], active_task: TASK1 });
  await h.setMock({
    crowd_submit_proof: {
      bodyFn: (req) => ({
        ok: true, accepted: 1,
        results: [
          { note_id: req.p_envelope.items[0].note_id, gate: "accepted" },
          { note_id: req.p_envelope.items[1].note_id, gate: "error", temp: true },
        ],
      }),
    },
  });
  await h.swEval("uploadProofs()");
  const q6 = (await h.storageGet(["proof_queue"])).proof_queue || [];
  check("X6", "accepted 条目移出、temp 条目保留退避", q6.length === 1 && q6[0].items.length === 1 && q6[0].items[0].note_id === env6.items[1].note_id && q6[0].retry_count === 1, q6[0] && { items: q6[0].items.length, rc: q6[0].retry_count });

  // ── X7 条目级 quota reason → 保留 ──
  console.log("\n=== X7 条目级 quota 保留 ===");
  await reset({ proof_queue: [mkEnv()], active_task: TASK1 });
  await h.setMock({
    crowd_submit_proof: {
      bodyFn: (req) => ({ ok: true, accepted: 0, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "error", reason: "quota_throttled" })) }),
    },
  });
  await h.swEval("uploadProofs()");
  const q7 = (await h.storageGet(["proof_queue"])).proof_queue || [];
  check("X7", "条目 reason 含 quota → 全部保留", q7.length === 1 && q7[0].items.length === 2, q7[0] && q7[0].items.length);

  // ── X8 ok:false 未知非永久 reason → 退避而非死信 ──
  console.log("\n=== X8 未知非永久 reason ===");
  await reset({ proof_queue: [mkEnv()], active_task: TASK1 });
  await h.setMock({ crowd_submit_proof: { body: { ok: false, reason: "server_busy" } } });
  await h.swEval("uploadProofs()");
  const s8 = await h.storageGet(["proof_queue", "deadLetter"]);
  check("X8", "server_busy → 退避保留不进死信", (s8.proof_queue || []).length === 1 && (s8.deadLetter || []).length === 0, { q: (s8.proof_queue || []).length, dl: (s8.deadLetter || []).length });

  // ── X9 HTTP 408/429 → 临时退避而非死信 ──
  console.log("\n=== X9 HTTP 429 退避 ===");
  await reset({ proof_queue: [mkEnv()], active_task: TASK1 });
  await h.setMock({ crowd_submit_proof: { status: 429, body: {} } });
  await h.swEval("uploadProofs()");
  const s9 = await h.storageGet(["proof_queue", "deadLetter"]);
  check("X9", "429 → 退避保留", (s9.proof_queue || []).length === 1 && (s9.deadLetter || []).length === 0, { q: (s9.proof_queue || []).length });

  // ── X10 回流检测：连续 3 次 accepted=0 → stalled 告警 ──
  console.log("\n=== X10 回流 stall ===");
  await reset({ active_task: TASK1 });
  await h.setMock({
    crowd_submit_proof: {
      bodyFn: (req) => ({ ok: true, accepted: 0, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "duplicate" })) }),
    },
  });
  for (let i = 0; i < 3; i++) {
    await h.storageSet({ proof_queue: [mkEnv()] });
    await h.swEval("uploadProofs()");
  }
  const s10 = await h.storageGet(["flow_state", "flow_stall_warned_at"]);
  check("X10", "连续3次零有效 → zero_count=3 且告警时间已记", s10.flow_state && s10.flow_state.zero_count === 3 && !!s10.flow_stall_warned_at, s10);

  // ── X11 quota_exceeded 无 reset_at → 兜底 UTC 下一零点（非本地午夜）──
  console.log("\n=== X11 quota 无 reset_at 兜底 ===");
  await reset({ proof_queue: [mkEnv()], active_task: TASK1 });
  await h.setMock({ crowd_submit_proof: { body: { ok: false, reason: "quota_exceeded", quota_day: 20, used_today: 20 } } });
  await h.swEval("uploadProofs()");
  const qb11 = (await h.storageGet(["quota_blocked_until"])).quota_blocked_until || 0;
  const utcNext = new Date(); utcNext.setUTCHours(24, 0, 0, 0);
  const localMid = new Date(); localMid.setHours(24, 0, 0, 0);
  check("X11", "park 到 UTC 零点+抖动（非本地午夜）",
    Math.abs(qb11 - utcNext.getTime()) <= 16 * 60000 && Math.abs(qb11 - localMid.getTime()) > 30 * 60000,
    { qb11, utcNext: utcNext.getTime(), localMid: localMid.getTime(), tzOffsetMin: new Date().getTimezoneOffset() });

  // ── X12 未填 participant_id → uploadProofs no_participant / 门禁引导 ──
  console.log("\n=== X12 无 participant_id ===");
  await reset({ participant_id: "", proof_queue: [mkEnv()] });
  const r12 = await h.swEval("uploadProofs()");
  check("X12", "无编号 → no_participant 且队列不动", r12 && r12.status === "no_participant", r12);

  // ── X13 并发 uploadProofs 互斥 ──
  console.log("\n=== X13 回传互斥 ===");
  await reset({ proof_queue: [mkEnv()], active_task: TASK1 });
  await h.setMock({ crowd_submit_proof: { delayMs: 1200, bodyFn: (req) => ({ ok: true, accepted: 2, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })) }) } });
  await h.swEval("(() => { self.__u1 = uploadProofs(); return 1; })()");
  await new Promise((r) => setTimeout(r, 200));
  const r13b = await h.swEval("uploadProofs()");
  const r13a = await h.swEval("self.__u1");
  check("X13", "并发第二个 uploadProofs 返回 busy", r13b && r13b.status === "busy" && r13a && r13a.status === "uploaded", { r13a, r13b });

  const excDelta = state.swExceptions.slice(m0);
  check("ALL-X", "补测全程无未捕获异常", excDelta.length === 0, excDelta);

  const pass = results.filter((r) => r.pass).length;
  const fail = results.filter((r) => !r.pass);
  console.log(`\n========== 补测汇总：${pass}/${results.length} 通过 ==========`);
  fail.forEach((f) => console.log(`  FAIL [${f.id}] ${f.name} → ${JSON.stringify(f.detail)}`));
  console.log("泄漏：", state.leaks.length, state.leaks);

  fs.mkdirSync(path.join(__dirname, "results"), { recursive: true });
  fs.writeFileSync(path.join(__dirname, "results", "extra.json"), JSON.stringify({ at: new Date().toISOString(), results, swExceptions: excDelta, leaks: state.leaks, swLogs: state.swLogs }, null, 2));
  await state.browser.close();
  fs.rmSync(state.userDataDir, { recursive: true, force: true });
  process.exit(fail.length ? 1 : 0);
})().catch((e) => { console.error("HARNESS CRASH:", e); process.exit(2); });
