/**
 * run-all.js — 场景 A–E + 竞态 + 门禁格式 全量跑测
 * 运行：node run-all.js   （HEADFUL=1 弹窗模式）
 * 产物：results/summary.json + 控制台逐项断言
 */
const path = require("path");
const fs = require("fs");
const { launch } = require("./harness");

const PID = "P-E2E0001"; // 注意：participantGate 正则 /^P-[A-Z0-9]{6,12}$/，'P-TEST-E2E' 里的 '-' 会判非法
const TASK1 = {
  task_id: "T-E2E-1",
  task_type: "keyword_pack",
  pack: ["烤鸭", "火锅"],
  target: "both",
  kpi_min: 2,
  quota_day: 20,
  progress: 0,
};

let envSeq = 0;
function mkEnvelope(over = {}) {
  const n = ++envSeq;
  return {
    submission_id: "sub-e2e-" + n,
    participant_id: PID,
    task_id: TASK1.task_id,
    kw_index: 0,
    kpi_min: 2,
    proof_seq: n,
    captured_at: new Date().toISOString(),
    sync_version: 3,
    retry_count: 0,
    next_retry_at: 0,
    items: [
      { kind: "note", note_id: "n" + n + "a", note_url: "https://x/n" + n + "a", title: "t" + n + "a", excerpt: "", author: "a", rating: null, rating_reason: "", matched_store: "", anchor_score: 0, raw_query: "烤鸭" },
      { kind: "note", note_id: "n" + n + "b", note_url: "https://x/n" + n + "b", title: "t" + n + "b", excerpt: "", author: "b", rating: null, rating_reason: "", matched_store: "", anchor_score: 0, raw_query: "烤鸭" },
    ],
    ...over,
  };
}

const results = [];
function check(scenario, name, cond, detail) {
  results.push({ scenario, name, pass: !!cond, detail: detail === undefined ? "" : detail });
  console.log(`  ${cond ? "PASS" : "FAIL"}  ${name}${cond ? "" : "  → " + JSON.stringify(detail)}`);
}

(async () => {
  console.log("[harness] launching browser…");
  const h = await launch();
  const { worker, state } = h;
  console.log("[harness] intercept mode:", state.interceptMode);

  // 每次场景前快照异常数，场景结束后看增量
  const excMark = () => state.swExceptions.length;
  const excDelta = (m) => state.swExceptions.slice(m);

  const resetStorage = async (seed = {}) => {
    await h.storageClear();
    await h.storageSet({
      fix_v344_flushed: true, // 防 SW 重启时 v3.4.4 自愈再次改写 next_retry_at
      participant_id: PID,
      agreed_at: new Date().toISOString(), // F6（v3.4.7）：participantGate 查 agreed_at
      collector_running: false,
      quota_blocked_until: 0,
      global_pause: false,
      gate_block_reason: "",
      ...seed,
    });
  };

  // ─────────────────────────── S0 启动冒烟 ───────────────────────────
  console.log("\n=== S0 SW 启动冒烟 ===");
  const boot = await h.storageGet(["fix_v344_flushed", "participant_id", "collector_running"]);
  const bootAlarms = state.bootAlarms || []; // harness 启动时已留档（随后 clearAll 防干扰）
  check("S0", "SW 加载无未捕获异常", state.swExceptions.length === 0, state.swExceptions);
  check("S0", "v3.4.4 自愈已执行(fix_v344_flushed=true)", boot.fix_v344_flushed === true, boot);
  check("S0", "F6：安装 ≠ 同意——onInstalled(install) 不自动开跑（collector_running=false）", boot.collector_running === false, boot.collector_running);
  check("S0", "F6：安装后不建 collect_heartbeat（仅 upload_retry 兜底）",
    bootAlarms.includes("upload_retry") && !bootAlarms.includes("collect_heartbeat"), bootAlarms);
  check("S0", "SW 启动日志存在", state.swLogs.length > 0, state.swLogs.length);

  // ─────────────────────────── 场景A 正常回传 ───────────────────────────
  console.log("\n=== 场景A 正常回传（gate 字段解析 / 队列排空 / 进度同步）===");
  await resetStorage({ active_task: TASK1 });
  const envA1 = mkEnvelope({ kw_index: 0 });
  const envA2 = mkEnvelope({ kw_index: 1, items: [mkEnvelope().items[0]] }); // kw1 单条，且服务端不回 keyword_progress → 走本地兜底
  await h.storageSet({ proof_queue: [envA1, envA2] });

  await h.setMock({
    crowd_submit_proof: {
      bodyFn: (req) => {
        const env = req && req.p_envelope;
        if (env && env.kw_index === 1) {
          // 故意用 verdict 字段 + 不回 keyword_progress：测本地累计兜底补置 done
          return { ok: true, accepted: 1, results: [{ note_id: env.items[0].note_id, verdict: "accepted" }], task_status: "open" };
        }
        return {
          ok: true,
          accepted: 2,
          results: [
            { note_id: env.items[0].note_id, gate: "accepted" },
            { note_id: env.items[1].note_id, gate: "duplicate" },
          ],
          keyword_progress: [{ keyword: "烤鸭", accepted: 2 }],
          task_status: "open",
        };
      },
    },
  });

  let m = excMark();
  const retA = await h.swEval("uploadProofs()");
  const afterA = await h.storageGet(["proof_queue", "kw_state_" + TASK1.task_id, "flow_state"]);
  const callsA = await h.getRpcCalls();
  check("场景A", "返回 status=uploaded 且 sent=2", retA && retA.status === "uploaded" && retA.sent === 2, retA);
  check("场景A", "队列排空（gate=accepted/duplicate 均为终态）", (afterA.proof_queue || []).length === 0, afterA.proof_queue);
  const kwA = afterA["kw_state_" + TASK1.task_id] || {};
  check("场景A", "kw0 由 keyword_progress 同步 accepted=2 且 done", kwA["0"] && kwA["0"].accepted === 2 && kwA["0"].done === true, kwA);
  check("场景A", "kw1 无 keyword_progress 时本地兜底累计 accepted=1", kwA["1"] && kwA["1"].accepted === 1, kwA);
  check("场景A", "submission_id 随重试复用（两次调用各自保持入队时 id）",
    callsA.length === 2 && callsA.every((c) => c.body && c.body.p_envelope && /^sub-e2e-/.test(c.body.p_envelope.submission_id)),
    callsA.map((c) => c.body && c.body.p_envelope && c.body.p_envelope.submission_id));
  check("场景A", "flow_state 记录成功回传", afterA.flow_state && afterA.flow_state.zero_count === 0, afterA.flow_state);
  check("场景A", "无新增 SW 异常", excDelta(m).length === 0, excDelta(m));

  // ─────────────────────────── 场景B 配额 park ───────────────────────────
  console.log("\n=== 场景B 配额 quota_exceeded（park 到服务端 reset_at）===");
  await resetStorage({ active_task: TASK1 });
  const envB = mkEnvelope();
  await h.storageSet({ proof_queue: [envB] });
  const resetAt = new Date(Date.now() + 2 * 3600 * 1000).toISOString(); // 2h 后，明显偏离本地午夜
  await h.setMock({
    crowd_submit_proof: { body: { ok: false, reason: "quota_exceeded", quota_day: 20, used_today: 20, reset_at: resetAt } },
  });
  m = excMark();
  const retB = await h.swEval("uploadProofs()");
  const afterB = await h.storageGet(["proof_queue", "quota_blocked_until", "gate_block_reason"]);
  const qb = afterB.quota_blocked_until || 0;
  const resetTs = Date.parse(resetAt);
  check("场景B", "信封留在队列", (afterB.proof_queue || []).length === 1, afterB.proof_queue);
  check("场景B", "retry_count 未被配额烧毁（保持 0）", afterB.proof_queue && afterB.proof_queue[0].retry_count === 0, afterB.proof_queue && afterB.proof_queue[0].retry_count);
  check("场景B", "quota_blocked_until ≈ 服务端 reset_at + 5~15min 抖动",
    qb >= resetTs + 5 * 60000 - 1000 && qb <= resetTs + 16 * 60000, { qb, resetTs, diffMin: (qb - resetTs) / 60000 });
  check("场景B", "信封 next_retry_at 与 quota_blocked_until 一致",
    afterB.proof_queue && afterB.proof_queue[0].next_retry_at === qb, afterB.proof_queue && afterB.proof_queue[0].next_retry_at);
  const collectB = await h.swEval("doCollectOnce()");
  check("场景B", "采集被 park：doCollectOnce → quota_blocked", collectB && collectB.status === "quota_blocked", collectB);
  check("场景B", "gate_block_reason 含配额说明", /配额/.test(afterB.gate_block_reason || ""), afterB.gate_block_reason);
  check("场景B", "无新增 SW 异常", excDelta(m).length === 0, excDelta(m));

  // ─────────────────────────── 场景C 500/网络错误退避 ───────────────────────────
  console.log("\n=== 场景C 服务端 500 / 网络错误：退避重试不丢数据 ===");
  await resetStorage({ active_task: TASK1 });
  const envC = mkEnvelope();
  await h.storageSet({ proof_queue: [envC] });
  await h.setMock({ crowd_submit_proof: { status: 500, body: { error: "boom" } } });
  m = excMark();
  const t0 = Date.now();
  const retC1 = await h.swEval("uploadProofs()");
  let qC = (await h.storageGet(["proof_queue"])).proof_queue || [];
  check("场景C", "500 → 信封保留且 retry_count=1", qC.length === 1 && qC[0].retry_count === 1, qC);
  check("场景C", "退避 ≈ 60s（RETRY_BASE_MS）", qC.length === 1 && qC[0].next_retry_at >= t0 + 55000 && qC[0].next_retry_at <= t0 + 70000, qC[0] && qC[0].next_retry_at - t0);
  const callsBefore = (await h.getRpcCalls()).length;
  const retC2 = await h.swEval("uploadProofs()");
  const callsAfter = (await h.getRpcCalls()).length;
  check("场景C", "退避期内不再发请求（backoff skip）", callsAfter === callsBefore && retC2.backoff === 1, { retC2, callsBefore, callsAfter });

  // 强制到期 + 网络层失败（failRequest → fetch reject → network_error temp=true）
  qC[0].next_retry_at = 0;
  await h.storageSet({ proof_queue: qC });
  await h.setMock({ crowd_submit_proof: { fail: true } });
  const t1 = Date.now();
  await h.swEval("uploadProofs()");
  qC = (await h.storageGet(["proof_queue"])).proof_queue || [];
  check("场景C", "网络错误 → retry_count=2，退避 ≈ 120s（指数；含 ≤15s RPC 超时窗口）",
    qC.length === 1 && qC[0].retry_count === 2 && qC[0].next_retry_at >= t1 + 110000 && qC[0].next_retry_at <= t1 + 140000,
    qC[0] && { retry_count: qC[0].retry_count, backoffMs: qC[0].next_retry_at - t1 });

  // 恢复成功 → 队列排空
  qC[0].next_retry_at = 0;
  await h.storageSet({ proof_queue: qC });
  await h.setMock({
    crowd_submit_proof: {
      bodyFn: (req) => ({ ok: true, accepted: 2, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })), task_status: "open" }),
    },
  });
  const retC3 = await h.swEval("uploadProofs()");
  qC = (await h.storageGet(["proof_queue"])).proof_queue || [];
  check("场景C", "恢复后重传成功、队列排空、不丢数据", retC3.status === "uploaded" && qC.length === 0, { retC3, qC });
  check("场景C", "无新增 SW 异常", excDelta(m).length === 0, excDelta(m));

  // ─────────────────────────── 场景D 永久原因死信 ───────────────────────────
  console.log("\n=== 场景D task_not_open / HTTP 400 → 死信，不无限重试 ===");
  await resetStorage({ active_task: TASK1 });
  const envD1 = mkEnvelope();
  const envD2 = mkEnvelope();
  await h.storageSet({ proof_queue: [envD1] });
  await h.setMock({ crowd_submit_proof: { body: { ok: false, reason: "task_not_open" } } });
  m = excMark();
  const retD1 = await h.swEval("uploadProofs()");
  let afterD = await h.storageGet(["proof_queue", "deadLetter"]);
  check("场景D", "task_not_open → 从队列移除", (afterD.proof_queue || []).length === 0, afterD.proof_queue);
  check("场景D", "进死信且留痕 reason", (afterD.deadLetter || []).length === 1 && /task_not_open/.test(afterD.deadLetter[0].reason), afterD.deadLetter);
  check("场景D", "死信保留原信封（可申诉）", afterD.deadLetter && afterD.deadLetter[0].envelope.submission_id === envD1.submission_id, afterD.deadLetter);

  await h.storageSet({ proof_queue: [envD2] });
  await h.setMock({ crowd_submit_proof: { status: 400, body: { message: "bad request" } } });
  const retD2 = await h.swEval("uploadProofs()");
  afterD = await h.storageGet(["proof_queue", "deadLetter"]);
  check("场景D", "HTTP 400（非 5xx/408/429）→ 死信", (afterD.proof_queue || []).length === 0 && (afterD.deadLetter || []).length === 2, { retD2, dl: (afterD.deadLetter || []).length });
  check("场景D", "返回 status=dead_letter", retD2.status === "dead_letter", retD2);
  check("场景D", "无新增 SW 异常（死信走 logError console.warn，不算异常）", excDelta(m).length === 0, excDelta(m));

  // ─────────────────────────── 场景E 任务领取 + 全链路采集 ───────────────────────────
  console.log("\n=== 场景E 任务领取 / kw 轮转 / 全链路采集回传 ===");
  await resetStorage({ done_task_ids: [] });
  await h.setMock({
    crowd_fetch_tasks: {
      body: {
        ok: true,
        tasks: [{ task_id: "T-E2E-2", pack_type: "keyword", pack: ["烤串", "奶茶"], kpi_min: 1, quota_day: 20, safety_limits: { quota_day: 10 } }],
        safety: { pause: false },
      },
    },
    crowd_submit_proof: {
      bodyFn: (req) => ({
        ok: true,
        accepted: req.p_envelope.items.length,
        results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })),
        keyword_progress: [{ keyword: req.p_envelope.raw_query || req.p_envelope.items[0].raw_query, accepted: 1 }],
        task_status: "open",
      }),
    },
  });
  m = excMark();
  const claimed = await h.swEval("fetchActiveTask()");
  check("场景E", "领取任务 T-E2E-2，pack_type keyword → keyword_pack", claimed && claimed.task_id === "T-E2E-2" && claimed.task_type === "keyword_pack", claimed);
  const limits = await h.storageGet(["remote_limits_applied"]);
  check("场景E", "服务端 safety_limits 只紧不松落地（quota_day=10）", limits.remote_limits_applied && limits.remote_limits_applied.quota_day === 10, limits.remote_limits_applied);
  check("场景E", "初始 nextKwIndex=0", (await h.swEval(`nextKwIndex(${JSON.stringify(claimed)})`)) === 0);

  // 人为置 kw0 done → 轮转到 1；全 done → -1
  await h.storageSet({ ["kw_state_T-E2E-2"]: { "0": { accepted: 1, done: true } } });
  check("场景E", "kw0 done 后 nextKwIndex=1", (await h.swEval(`nextKwIndex(${JSON.stringify(claimed)})`)) === 1);
  await h.storageSet({ ["kw_state_T-E2E-2"]: { "0": { accepted: 1, done: true }, "1": { accepted: 1, done: true } } });
  check("场景E", "全部 done → nextKwIndex=-1", (await h.swEval(`nextKwIndex(${JSON.stringify(claimed)})`)) === -1);
  await h.storageSet({ ["kw_state_T-E2E-2"]: {} });

  // 全链路：覆写安全门为确定性放行（时段/会话/间隔均为采样随机，测试只验调度主链）
  await h.swEval(`(() => {
    safety.isCircadianAllowed = async () => ({ ok: true, weight: 1 });
    safety.canStartSession = async () => ({ ok: true, actionsLeft: 10, started: true });
    safety.canSearch = async () => ({ ok: true, waitMs: 0, quotaLeft: 50, gap: 0 });
    return true;
  })()`);
  const retE1 = await h.swEval("doCollectOnce()");
  const afterE1 = await h.storageGet(["proof_queue", "kw_state_T-E2E-2", "active_task", "done_task_ids"]);
  check("场景E", "doCollectOnce → collected", retE1 && retE1.status === "collected", retE1);
  check("场景E", "采到条目并已即时回传清空队列", (afterE1.proof_queue || []).length === 0, afterE1.proof_queue);
  const kwE = afterE1["kw_state_T-E2E-2"] || {};
  check("场景E", "kw0（烤串）进度同步且 done（kpi_min=1）", kwE["0"] && kwE["0"].accepted >= 1 && kwE["0"].done === true, kwE);
  const callsE = await h.getRpcCalls();
  const submitE = callsE.filter((c) => c.fn === "crowd_submit_proof");
  check("场景E", "信封内容来自伪 xhs 页面（note_id NOTE00*）",
    submitE.length >= 1 && submitE[0].body.p_envelope.items.every((it) => /^NOTE00/.test(it.note_id)),
    submitE[0] && submitE[0].body.p_envelope.items.map((it) => it.note_id));

  // 第二轮：奶茶 → 全部 done → uploadProofs 内完成判定 finalizeTask
  const retE2 = await h.swEval("doCollectOnce()");
  const afterE2 = await h.storageGet(["active_task", "done_task_ids", "kw_state_T-E2E-2"]);
  check("场景E", "第二轮采集 kw1（奶茶）collected", retE2 && retE2.status === "collected" && retE2.kw_index === 1, retE2);
  check("场景E", "全部关键词达标 → active_task 归档(null)", afterE2.active_task === null, afterE2.active_task);
  check("场景E", "done_task_ids 记录 T-E2E-2（服务端不再发放）", (afterE2.done_task_ids || []).includes("T-E2E-2"), afterE2.done_task_ids);
  check("场景E", "无新增 SW 异常", excDelta(m).length === 0, excDelta(m));

  // ─────────────────────────── 场景F 回传-入队竞态 ───────────────────────────
  console.log("\n=== 场景F uploadProofs 在途时并发入队（读-改-写竞态探测）===");
  await resetStorage({ active_task: TASK1 });
  const envF1 = mkEnvelope();
  await h.storageSet({ proof_queue: [envF1] });
  await h.setMock({
    crowd_submit_proof: { delayMs: 1500, bodyFn: (req) => ({ ok: true, accepted: 2, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })), task_status: "open" }) },
  });
  m = excMark();
  // 启动 uploadProofs（不 await），在 RPC 挂起期间按采集路径方式 push 一个新信封
  await h.swEval("(() => { self.__raceP = uploadProofs(); return 'started'; })()");
  await new Promise((r) => setTimeout(r, 400)); // 确保 upload 已读队列、RPC 在途
  const envF2 = mkEnvelope();
  await h.swEval(`(async () => {
    const r = await chrome.storage.local.get("proof_queue");
    const q = r.proof_queue || [];
    q.push(${JSON.stringify(envF2)});
    await chrome.storage.local.set({ proof_queue: q });
    return q.length;
  })()`);
  const raceRet = await h.swEval("self.__raceP");
  await new Promise((r) => setTimeout(r, 300));
  const qF = (await h.storageGet(["proof_queue"])).proof_queue || [];
  check("场景F", "竞态窗口入队的信封不丢失", qF.some((e) => e.submission_id === envF2.submission_id),
    { queueIds: qF.map((e) => e.submission_id), lost: envF2.submission_id, raceRet });
  check("场景F", "无新增 SW 异常", excDelta(m).length === 0, excDelta(m));

  // ─────────────────────────── 场景G 门禁格式 ───────────────────────────
  console.log("\n=== 场景G participant_id 门禁（'P-TEST-E2E' 格式探测）===");
  await resetStorage({ participant_id: "P-TEST-E2E" });
  m = excMark();
  const gateG = await h.swEval("fetchActiveTask()");
  const gbr = (await h.storageGet(["gate_block_reason"])).gate_block_reason;
  check("场景G", "带 '-' 的参与编号被门禁拒绝", gateG === null && /格式错误/.test(gbr || ""), { gateG, gbr });

  // ─────────────────────────── 汇总 ───────────────────────────
  const pass = results.filter((r) => r.pass).length;
  const fail = results.filter((r) => !r.pass);
  console.log(`\n========== 汇总：${pass}/${results.length} 通过 ==========`);
  if (fail.length) {
    console.log("失败项：");
    fail.forEach((f) => console.log(`  [${f.scenario}] ${f.name} → ${JSON.stringify(f.detail)}`));
  }
  console.log("SW 未捕获异常总数：", state.swExceptions.length);
  if (state.swExceptions.length) state.swExceptions.forEach((e) => console.log("  EXC:", e.text, e.desc));
  console.log("页面异常总数：", state.pageErrors.length);
  state.pageErrors.slice(0, 5).forEach((e) => console.log("  PAGE-EXC:", e));
  console.log("未走 mock 的 supabase 泄漏：", state.leaks.length, state.leaks);
  console.log("拦截模式：", state.interceptMode);

  fs.mkdirSync(path.join(__dirname, "results"), { recursive: true });
  fs.writeFileSync(
    path.join(__dirname, "results", "summary.json"),
    JSON.stringify({
      at: new Date().toISOString(),
      interceptMode: state.interceptMode,
      pass, total: results.length,
      results,
      swExceptions: state.swExceptions,
      pageErrors: state.pageErrors,
      leaks: state.leaks,
      swLogs: state.swLogs,
    }, null, 2)
  );
  console.log("\n[done] results/summary.json 已写入");

  await state.browser.close();
  fs.rmSync(state.userDataDir, { recursive: true, force: true });
  process.exit(fail.length ? 1 : 0);
})().catch((e) => {
  console.error("HARNESS CRASH:", e);
  process.exit(2);
});
