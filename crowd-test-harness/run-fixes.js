/**
 * run-fixes.js — v3.4.6 修复回归（R1–R11）
 * 覆盖：F1 合并写回（含"死信不复活"负例）、F2 看门狗持锁、F3 服务端永久词表、
 *       条目级重试上限、F4 配额条目重裁排空、F9 死信去重、F7 inline wait 阈值、
 *       F8 孤儿标签清理、F5 风控信号透传、F6 同意/拒绝流程。
 * 运行：node run-fixes.js
 */
const path = require("path");
const fs = require("fs");
const { launch } = require("./harness");

const PID = "P-E2E0001";
const TASK1 = { task_id: "T-R-1", task_type: "keyword_pack", pack: ["烤鸭"], target: "both", kpi_min: 5, quota_day: 20, progress: 0 };

let seq = 300;
function mkEnv(over = {}) {
  const n = ++seq;
  return {
    submission_id: "sub-r-" + n, participant_id: PID, task_id: TASK1.task_id, kw_index: 0, kpi_min: 5,
    proof_seq: n, captured_at: new Date().toISOString(), sync_version: 3, retry_count: 0, next_retry_at: 0,
    items: [
      { kind: "note", note_id: "r" + n + "a", note_url: "", title: "t", excerpt: "", author: "", rating: null, rating_reason: "", matched_store: "", anchor_score: 0, raw_query: "烤鸭" },
      { kind: "note", note_id: "r" + n + "b", note_url: "", title: "t", excerpt: "", author: "", rating: null, rating_reason: "", matched_store: "", anchor_score: 0, raw_query: "烤鸭" },
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
  const extId = new URL(state.worker.url()).host;
  const excMark = () => state.swExceptions.length;

  const reset = async (seed = {}) => {
    await h.storageClear();
    await h.storageSet({
      fix_v344_flushed: true, participant_id: PID, agreed_at: new Date().toISOString(), collector_running: false,
      quota_blocked_until: 0, global_pause: false, gate_block_reason: "", ...seed,
    });
  };
  const forceDaylight = () => h.swEval(`(() => {
    safety.isCircadianAllowed = async () => ({ ok: true, weight: 1 });
    safety.canStartSession = async () => ({ ok: true, actionsLeft: 99 });
    return true;
  })()`);

  // ── R1 F1：回传在途+并发入队 → 新信封合并保留 ──
  console.log("\n=== R1 F1 合并写回（正例）===");
  await reset({ proof_queue: [mkEnv()], active_task: TASK1 });
  await h.setMock({
    crowd_submit_proof: { delayMs: 1500, bodyFn: (req) => ({ ok: true, accepted: 2, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })) }) },
  });
  let m = excMark();
  await h.swEval("(() => { self.__r1 = uploadProofs(); return 1; })()");
  await new Promise((r) => setTimeout(r, 400));
  const envNew = mkEnv();
  await h.swEval(`(async () => {
    const r = await chrome.storage.local.get("proof_queue");
    const q = r.proof_queue || []; q.push(${JSON.stringify(envNew)});
    await chrome.storage.local.set({ proof_queue: q }); return q.length;
  })()`);
  await h.swEval("self.__r1");
  await new Promise((r) => setTimeout(r, 300));
  const qR1 = (await h.storageGet(["proof_queue"])).proof_queue || [];
  check("R1", "F1 修复：窗口内新入队信封被 merge 保留，不再丢失",
    qR1.length === 1 && qR1[0].submission_id === envNew.submission_id && qR1[0].retry_count === 0,
    qR1.map((e) => e.submission_id));
  check("R1", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── R2 F1 负例：本轮已死信/已终态的信封不得被 merge 复活 ──
  console.log("\n=== R2 F1 合并写回（负例：死信不复活）===");
  const envDead = mkEnv();
  const envOk = mkEnv();
  await reset({ proof_queue: [envDead, envOk], active_task: TASK1 });
  await h.setMock({
    crowd_submit_proof: {
      delayMs: 1200,
      bodyFn: (req) => {
        if (req.p_envelope.submission_id === envDead.submission_id) return { ok: false, reason: "task_not_open" };
        return { ok: true, accepted: 2, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })) };
      },
    },
  });
  m = excMark();
  await h.swEval("(() => { self.__r2 = uploadProofs(); return 1; })()");
  await new Promise((r) => setTimeout(r, 500));
  const envC2 = mkEnv();
  await h.swEval(`(async () => {
    const r = await chrome.storage.local.get("proof_queue");
    const q = r.proof_queue || []; q.push(${JSON.stringify(envC2)});
    await chrome.storage.local.set({ proof_queue: q }); return q.length;
  })()`);
  await h.swEval("self.__r2");
  await new Promise((r) => setTimeout(r, 300));
  const sR2 = await h.storageGet(["proof_queue", "deadLetter"]);
  const idsR2 = (sR2.proof_queue || []).map((e) => e.submission_id);
  check("R2", "已死信信封不复活、已发送信封不回潮、新信封保留",
    idsR2.length === 1 && idsR2[0] === envC2.submission_id &&
    (sR2.deadLetter || []).length === 1 && sR2.deadLetter[0].envelope.submission_id === envDead.submission_id,
    { queue: idsR2, dl: (sR2.deadLetter || []).map((d) => d.envelope.submission_id) });
  check("R2", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── R3 F2：看门狗超时后锁不释放，inner settle 后才放行 ──
  console.log("\n=== R3 F2 看门狗持锁 ===");
  await reset({ proof_queue: [mkEnv()], active_task: TASK1 });
  await h.setMock({
    crowd_submit_proof: { delayMs: 3500, bodyFn: (req) => ({ ok: true, accepted: 2, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })) }) },
    crowd_fetch_tasks: { body: { ok: false, reason: "no_open_tasks" } }, // w3 探针会走到领取路径，给mock防 599 兜底计数
  });
  await forceDaylight();
  await h.swEval("CONFIG.COLLECT_WATCHDOG_MS = 1200"); // 缩短看门狗（测试期运行时调整）
  m = excMark();
  const tR3 = Date.now();
  const w1 = await h.swEval("doCollectOnce()");
  const el1 = Date.now() - tR3;
  const w2 = await h.swEval("doCollectOnce()"); // inner 仍在跑（RPC 3.5s）→ 必须 busy
  // 轮询等 inner 彻底 settle（inner 内含两次 3.5s RPC + 采集动作，约 10s）
  let settled = false;
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 700));
    if ((await h.swEval("_running")) === false) { settled = true; break; }
  }
  const w3 = await h.swEval("doCollectOnce()"); // 锁已释放 → 放行（quota/时段等状态决定具体状态）
  await h.swEval("CONFIG.COLLECT_WATCHDOG_MS = 90000"); // 还原
  // w3 又启动了一轮完整采集，等它 settle 再进入后续场景，杜绝跨测试干扰
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 700));
    if ((await h.swEval("_running")) === false) break;
  }
  check("R3", "看门狗 1.2s 超时返回 watchdog_timeout", w1 && w1.status === "watchdog_timeout" && el1 < 2500, { w1, el1 });
  check("R3", "超时后 inner 未 settle 期间重入 → busy（锁未悬空释放）", w2 && w2.status === "busy", w2);
  check("R3", "inner settle 后锁释放 → 不再 busy", settled && w3 && w3.status !== "busy", { settled, w3 });
  check("R3", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── R4 F3：服务端永久 reason 词表全部进死信 ──
  console.log("\n=== R4 F3 永久 reason 词表 ===");
  const permReasons = ["participant_unavailable", "envelope_parse_error", "stale_client", "envelope_missing_task_or_seq", "participant_id_mismatch", "captured_at_future", "captured_at_too_old", "task_not_open"];
  await reset({ proof_queue: permReasons.map((r) => mkEnv()), active_task: TASK1 });
  let rIdx = 0;
  await h.setMock({
    crowd_submit_proof: { bodyFn: () => ({ ok: false, reason: permReasons[Math.min(rIdx++, permReasons.length - 1)] }) },
  });
  m = excMark();
  await h.swEval("uploadProofs()");
  const sR4 = await h.storageGet(["proof_queue", "deadLetter"]);
  check("R4", "8 个服务端永久 reason 全部死信、队列清空",
    (sR4.proof_queue || []).length === 0 && (sR4.deadLetter || []).length === 8,
    { q: (sR4.proof_queue || []).length, dl: (sR4.deadLetter || []).map((d) => d.reason) });
  check("R4", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── R5 条目级重试上限：gate=error ×8 → retry_exhausted 死信 ──
  console.log("\n=== R5 条目级重试上限 ===");
  await reset({ proof_queue: [mkEnv()], active_task: TASK1 });
  await h.setMock({
    crowd_submit_proof: { bodyFn: (req) => ({ ok: true, accepted: 0, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "error", reason: "item_insert_error" })) }) },
  });
  m = excMark();
  let rcSeen = [];
  for (let i = 0; i < 8; i++) {
    await h.swEval("uploadProofs()");
    const q = (await h.storageGet(["proof_queue"])).proof_queue || [];
    rcSeen.push(q[0] ? q[0].retry_count : "gone");
    if (q[0]) { q[0].next_retry_at = 0; await h.storageSet({ proof_queue: q }); }
  }
  const sR5 = await h.storageGet(["proof_queue", "deadLetter"]);
  check("R5", "第 8 次重试后整封转死信 retry_exhausted:error",
    rcSeen.join() === "1,2,3,4,5,6,7,gone" && (sR5.deadLetter || []).length === 1 && sR5.deadLetter[0].reason === "retry_exhausted:error",
    { rcSeen, dl: (sR5.deadLetter || []).map((d) => d.reason) });
  check("R5", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── R6 F4 客户端侧：quota 拒收条目豁免重试上限，服务端重裁后排空 ──
  console.log("\n=== R6 quota 条目重裁 ===");
  await reset({ proof_queue: [mkEnv()], active_task: TASK1 });
  let round = 0;
  await h.setMock({
    crowd_submit_proof: {
      bodyFn: (req) => {
        round++;
        if (round === 1) return { ok: true, accepted: 0, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "error", reason: "quota_throttled" })) };
        return { ok: true, accepted: 2, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "accepted" })) };
      },
    },
  });
  m = excMark();
  await h.swEval("uploadProofs()");
  let qR6 = (await h.storageGet(["proof_queue"])).proof_queue || [];
  const kept = qR6.length === 1 && qR6[0].items.length === 2;
  qR6[0].next_retry_at = 0;
  await h.storageSet({ proof_queue: qR6 });
  await h.swEval("uploadProofs()");
  qR6 = (await h.storageGet(["proof_queue"])).proof_queue || [];
  check("R6", "quota 条目保留（park 语义不动）→ 服务端重裁 accepted 后排空", kept && qR6.length === 0, { kept, finalQ: qR6.length });
  check("R6", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── R7 F9：死信去重 ──
  console.log("\n=== R7 F9 死信去重 ===");
  const dupId = "sub-r-dup";
  await reset({ proof_queue: [mkEnv({ submission_id: dupId }), mkEnv({ submission_id: dupId })], active_task: TASK1 });
  await h.setMock({ crowd_submit_proof: { body: { ok: false, reason: "task_not_open" } } });
  m = excMark();
  await h.swEval("uploadProofs()");
  const sR7 = await h.storageGet(["proof_queue", "deadLetter"]);
  check("R7", "同 submission_id 两封信 → 死信只留一条", (sR7.deadLetter || []).length === 1 && (sR7.proof_queue || []).length === 0, (sR7.deadLetter || []).length);
  check("R7", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── R8 F7：waitMs 26s > 25s 阈值 → 立即返回 wait 不内联睡眠 ──
  console.log("\n=== R8 F7 inline wait 阈值 ===");
  await reset({ proof_queue: [], active_task: TASK1 });
  await forceDaylight();
  await h.swEval(`(() => { safety.canSearch = async () => ({ ok: true, waitMs: 26000, quotaLeft: 10, gap: 26 }); return 1; })()`);
  m = excMark();
  const tR8 = Date.now();
  const rR8 = await h.swEval("doCollectOnce()");
  const elR8 = Date.now() - tR8;
  check("R8", "waitMs=26s 超过 25s 阈值 → 立即返回 wait（旧阈值 180s 会内联睡 26s 被 SW 杀死）",
    rR8 && rR8.status === "wait" && rR8.waitMs === 26000 && elR8 < 5000, { rR8, elR8 });
  check("R8", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── R9 F8：initBackground 清理孤儿采集标签 ──
  console.log("\n=== R9 F8 孤儿标签清理 ===");
  const orphan = await state.browser.newPage();
  await orphan.goto("https://www.xiaohongshu.com/search_result?keyword=%E7%83%A4%E9%B8%AD&xsec_source=pc_crowd", { waitUntil: "load" }).catch(() => {});
  const normalTab = await state.browser.newPage();
  await normalTab.goto("https://www.xiaohongshu.com/explore", { waitUntil: "load" }).catch(() => {});
  await new Promise((r) => setTimeout(r, 500));
  m = excMark();
  await h.swEval("initBackground()");
  await new Promise((r) => setTimeout(r, 800));
  const urls = (await state.browser.pages()).map((p) => p.url());
  check("R9", "带 xsec_source=pc_crowd 的采集标签被关闭", !urls.some((u) => u.includes("xsec_source=pc_crowd")), urls.filter((u) => u.includes("xiaohongshu")));
  check("R9", "用户自己的小红书标签不受影响", urls.some((u) => u.includes("xiaohongshu.com/explore")), urls.filter((u) => u.includes("xiaohongshu")));
  check("R9", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));

  // ── R10 F5：风控页（无卡片 UNSUPPORTED_PAGE）rateLimited 仍送达状态机 ──
  console.log("\n=== R10 F5 风控信号透传 ===");
  await reset({ proof_queue: [], active_task: TASK1 });
  await forceDaylight();
  await h.swEval(`(() => { safety.canSearch = async () => ({ ok: true, waitMs: 0, quotaLeft: 10, gap: 0 }); return 1; })()`);
  h.setFakePageMode("risk"); // 伪页面：无卡片 + 「访问频繁」
  await h.setMock({});
  m = excMark();
  const rR10 = await h.swEval("doCollectOnce()");
  const sR10 = await h.storageGet(["risk_state", "cooldown_until"]);
  const today = new Date().toISOString().slice(0, 10);
  check("R10", "解析失败页也把 rateLimited 送达：返回带 rateLimited:true",
    rR10 && rR10.status === "search_failed" && rR10.rateLimited === true, rR10);
  check("R10", "风控状态机生效：当日停止 + 冷却 24–72h",
    sR10.risk_state && sR10.risk_state.stop_date === today && sR10.cooldown_until > Date.now() + 20 * 3600 * 1000,
    { risk_state: sR10.risk_state, cooldown: sR10.cooldown_until });
  check("R10", "无新增 SW 异常", state.swExceptions.length === m, state.swExceptions.slice(m));
  h.setFakePageMode("normal");

  // ── R11 F6：拒绝分支清半成品 ──
  console.log("\n=== R11 F6 拒绝分支 ===");
  await h.storageClear();
  await h.storageSet({ fix_v344_flushed: true, participant_id: "P-HALF0001", collector_running: true }); // 半成品状态
  await h.swEval("chrome.alarms.create('collect_heartbeat', { periodInMinutes: 3 })");
  const ob = await state.browser.newPage();
  await ob.goto(`chrome-extension://${extId}/src/onboarding.html`, { waitUntil: "load" });
  await ob.click("#refuse");
  await new Promise((r) => setTimeout(r, 1200));
  const sR11 = await h.storageGet(["participant_id", "collector_running", "agreed_at"]);
  const alarmsR11 = await h.swEval("new Promise((res) => chrome.alarms.getAll((a) => res(a.map((x) => x.name))))");
  check("R11", "拒绝后 participant_id/agreed_at 清除、collector_running=false",
    sR11.participant_id === undefined && sR11.agreed_at === undefined && sR11.collector_running === false, sR11);
  check("R11", "拒绝后 collect_heartbeat 已停", !alarmsR11.includes("collect_heartbeat"), alarmsR11);
  await ob.close();

  const pass = results.filter((r) => r.pass).length;
  const fail = results.filter((r) => !r.pass);
  console.log(`\n========== 修复回归：${pass}/${results.length} 通过 ==========`);
  fail.forEach((f) => console.log(`  FAIL [${f.id}] ${f.name} → ${JSON.stringify(f.detail)}`));
  console.log("泄漏：", state.leaks.length, state.leaks);
  console.log("SW 异常总数：", state.swExceptions.length);

  fs.mkdirSync(path.join(__dirname, "results"), { recursive: true });
  fs.writeFileSync(path.join(__dirname, "results", "fixes.json"), JSON.stringify({ at: new Date().toISOString(), results, leaks: state.leaks, swExceptions: state.swExceptions, rpcCalls: state.rpcCalls }, null, 2));
  await state.browser.close();
  fs.rmSync(state.userDataDir, { recursive: true, force: true });
  process.exit(fail.length ? 1 : 0);
})().catch((e) => { console.error("HARNESS CRASH:", e); process.exit(2); });
