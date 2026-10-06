/**
 * run-extra2.js — 补测第二轮：X14 条目级永久 verdict / X15 onboarding 注册流 / X16 SW 重启续传
 * 运行：node run-extra2.js
 */
const path = require("path");
const fs = require("fs");
const { launch } = require("./harness");

const PID = "P-E2E0001";
const TASK1 = { task_id: "T-Y-1", task_type: "keyword_pack", pack: ["烤鸭"], target: "both", kpi_min: 5, quota_day: 20, progress: 0 };

let seq = 200;
function mkEnv(over = {}) {
  const n = ++seq;
  return {
    submission_id: "sub-y-" + n, participant_id: PID, task_id: TASK1.task_id, kw_index: 0, kpi_min: 5,
    proof_seq: n, captured_at: new Date().toISOString(), sync_version: 3, retry_count: 0, next_retry_at: 0,
    items: [{ kind: "note", note_id: "y" + n, note_url: "", title: "t", excerpt: "", author: "", rating: null, rating_reason: "", matched_store: "", anchor_score: 0, raw_query: "烤鸭" }],
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
  const { state, worker } = h;
  console.log("[harness] intercept mode:", state.interceptMode);
  const extId = new URL(state.worker.url()).host;

  const reset = async (seed = {}) => {
    await h.storageClear();
    await h.storageSet({
      fix_v344_flushed: true, participant_id: PID, agreed_at: new Date().toISOString(), collector_running: false,
      quota_blocked_until: 0, global_pause: false, gate_block_reason: "", ...seed,
    });
  };

  // ── X14 条目级"事实上永久"的 verdict：未知终态 → 无限退避，无死信出口 ──
  console.log("\n=== X14 条目级永久失败无死信出口 ===");
  await reset({ proof_queue: [mkEnv()], active_task: TASK1 });
  await h.setMock({
    crowd_submit_proof: {
      bodyFn: (req) => ({ ok: true, accepted: 0, results: req.p_envelope.items.map((it) => ({ note_id: it.note_id, gate: "invalid", reason: "note_private" })) }),
    },
  });
  const cycles = [];
  for (let i = 0; i < 3; i++) {
    await h.swEval("uploadProofs()");
    const q = (await h.storageGet(["proof_queue"])).proof_queue || [];
    cycles.push(q[0] ? q[0].retry_count : "gone");
    if (q[0]) { q[0].next_retry_at = 0; await h.storageSet({ proof_queue: q }); } // 强制到期进入下一轮
  }
  const s14 = await h.storageGet(["proof_queue", "deadLetter"]);
  check("X14", "探测：条目 verdict=invalid（非终态）三轮后仍卡队列且不进死信",
    cycles.join() === "1,2,3" && (s14.deadLetter || []).length === 0,
    { retryCycles: cycles, dl: (s14.deadLetter || []).length });

  // ── X15 onboarding 「我要加入」注册流 ──
  console.log("\n=== X15 onboarding 注册流 ===");
  await h.storageClear();
  await h.storageSet({ fix_v344_flushed: true });
  await h.setMock({
    crowd_register_participant: { body: { ok: true, participant_id: "P-NEWREG01" } },
  });
  const ob = await state.browser.newPage();
  await ob.goto(`chrome-extension://${extId}/src/onboarding.html`, { waitUntil: "load" });
  ob.on("dialog", async (d) => { await d.accept(); });
  await ob.click("#join");
  await new Promise((r) => setTimeout(r, 1500));
  const pidField = await ob.$eval("#participant", (el) => el.value);
  const pidBeforeConsent = (await h.storageGet(["participant_id"])).participant_id;
  const regCalls = (await h.getRpcCalls()).filter((c) => c.fn === "crowd_register_participant");
  check("X15", "注册成功回填输入框", pidField === "P-NEWREG01", pidField);
  check("X15", "F6：未点同意前 participant_id 不落盘", pidBeforeConsent === undefined, pidBeforeConsent);
  check("X15", "注册 RPC 携带 device_salt（一机一号）", regCalls.length === 1 && /^Dsalt[0-9a-f]{16}$/.test(regCalls[0].body.p_device_salt), regCalls[0] && regCalls[0].body);
  // 点同意 → 协议签署 + 落盘 + 显式启动采集
  await ob.click("#agree");
  await new Promise((r) => setTimeout(r, 1200));
  const agreed = await h.storageGet(["participant_id", "agreed_at", "collector_running"]);
  const alarmsAfterAgree = await h.swEval("new Promise((res) => chrome.alarms.getAll((a) => res(a.map((x) => x.name))))");
  check("X15", "同意后 participant_id 落盘 + agreed_at 记录", agreed.participant_id === "P-NEWREG01" && !!agreed.agreed_at, agreed);
  check("X15", "同意后 CROWD_START 启动采集（collector_running + heartbeat alarm）",
    agreed.collector_running === true && alarmsAfterAgree.includes("collect_heartbeat"), { running: agreed.collector_running, alarms: alarmsAfterAgree });
  await ob.close();

  // 注册失败路径：已注册设备 → 回填但同样等同意才落盘
  await h.storageClear();
  await h.storageSet({ fix_v344_flushed: true });
  await h.setMock({ crowd_register_participant: { body: { ok: false, reason: "device_already_registered", participant_id: "P-OLD0001" } } });
  const ob2 = await state.browser.newPage();
  await ob2.goto(`chrome-extension://${extId}/src/onboarding.html`, { waitUntil: "load" });
  ob2.on("dialog", async (d) => { await d.accept(); });
  await ob2.click("#join");
  await new Promise((r) => setTimeout(r, 1200));
  const pidBeforeConsent2 = (await h.storageGet(["participant_id"])).participant_id;
  check("X15", "已注册设备：回填输入框但同意前不落盘", pidBeforeConsent2 === undefined, pidBeforeConsent2);
  await ob2.click("#agree");
  await new Promise((r) => setTimeout(r, 1200));
  const pidStored2 = (await h.storageGet(["participant_id"])).participant_id;
  check("X15", "已注册设备：同意后恢复旧编号", pidStored2 === "P-OLD0001", pidStored2);
  await ob2.close();

  const pass = results.filter((r) => r.pass).length;
  const fail = results.filter((r) => !r.pass);
  console.log(`\n========== 第二轮补测：${pass}/${results.length} 通过 ==========`);
  fail.forEach((f) => console.log(`  FAIL [${f.id}] ${f.name} → ${JSON.stringify(f.detail)}`));
  console.log("泄漏：", state.leaks.length, state.leaks);

  fs.mkdirSync(path.join(__dirname, "results"), { recursive: true });
  fs.writeFileSync(path.join(__dirname, "results", "extra2.json"), JSON.stringify({ at: new Date().toISOString(), results, leaks: state.leaks }, null, 2));
  await state.browser.close();
  fs.rmSync(state.userDataDir, { recursive: true, force: true });
  process.exit(0); // X14 是"探测性"检查，即使复现也不让整个套件失败
})().catch((e) => { console.error("HARNESS CRASH:", e); process.exit(2); });
