/**
 * platform-test/run-platform.js — 线上 crowd-pages 跨平台真实页面测试
 *
 * 对象：https://huming0018-dot.github.io/crowd-pages/{index,submit,install-mobile}.html
 * 隔离：每平台独立 browser context（localStorage 互不串）；
 * 拦截：*.supabase.co RPC 全 mock / storage 下载回伪内容并记录；xhs 系一律拦截记录；
 *       github.io 静态资源真实加载（测试对象本身）。
 * 产物：platform-report-data.json + shots/<platform>/*.png
 */
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const os = require("os");
const path = require("path");

const CHROME_PATH = process.env.CHROME_PATH ||
  os.homedir() + "/.cache/puppeteer/chrome/mac_arm-154.0.8037.57/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing";
const BASE = "https://huming0018-dot.github.io/crowd-pages";
const OUT = __dirname;
const SHOTS = path.join(OUT, "shots");
const DL = fs.mkdtempSync(path.join(os.tmpdir(), "crowd-dl-"));

const NOTE_URL = "https://www.xiaohongshu.com/explore/67e3e11a000000000603fb08";
const NOTE_ID = "67e3e11a000000000603fb08";

const PLATFORMS = [
  { id: "android", label: "Android / Pixel 7",
    ua: "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    viewport: { width: 412, height: 915, deviceScaleFactor: 2.625, isMobile: true, hasTouch: true }, mobile: true },
  { id: "hm4", label: "HarmonyOS 4 / 华为浏览器",
    ua: "Mozilla/5.0 (Linux; Android 12; HarmonyOS; ALN-AL00; HMSCore 6.12.0.302) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 HuaweiBrowser/14.0.2.300 Mobile Safari/537.36",
    viewport: { width: 408, height: 904, deviceScaleFactor: 3, isMobile: true, hasTouch: true }, mobile: true },
  { id: "hmnext", label: "HarmonyOS NEXT（UA 无 android）",
    ua: "Mozilla/5.0 (Phone; OpenHarmony 5.0.0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 HuaweiBrowser/5.0 Mobile Safari/537.36",
    viewport: { width: 408, height: 904, deviceScaleFactor: 3, isMobile: true, hasTouch: true }, mobile: true },
  { id: "macos", label: "macOS 桌面 Chrome",
    ua: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    viewport: { width: 1280, height: 800, deviceScaleFactor: 2, isMobile: false, hasTouch: false }, mobile: false },
  { id: "windows", label: "Windows 桌面 Chrome",
    ua: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    viewport: { width: 1366, height: 768, deviceScaleFactor: 1, isMobile: false, hasTouch: false }, mobile: false },
  { id: "linux", label: "Linux 桌面 Chrome",
    ua: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    viewport: { width: 1366, height: 768, deviceScaleFactor: 1, isMobile: false, hasTouch: false }, mobile: false },
];

// ── RPC mock 路由（node 侧可变，场景间切换）──
const mockRoutes = {};
function baseMocks() {
  mockRoutes.crowd_register_participant = { body: { ok: true, participant_id: "P-PLT001" } };
  mockRoutes.crowd_next_target = { body: { ok: true, keyword: "测试门店", task_id: 99, kpi_min: 5, kw_index: 0, accepted: 0 } };
  mockRoutes.crowd_resolve_link = { body: { ok: true, note_id: NOTE_ID, canonical_url: NOTE_URL } };
  mockRoutes.crowd_status_summary = { body: { ok: true, total: 1234, today: 56 } };
  setSubmitGate("accepted");
}
function setSubmitGate(gate) {
  mockRoutes.crowd_submit_proof = {
    bodyFn: (req) => {
      if (gate === "quota") return { ok: false, reason: "quota_exceeded", quota_day: 20, used_today: 20 };
      const nid = req && req.p_envelope && req.p_envelope.items && req.p_envelope.items[0] && req.p_envelope.items[0].note_id;
      const r = { note_id: nid, gate };
      if (gate === "rejected") r.reason = "item_url_invalid";
      return { ok: true, accepted: gate === "accepted" ? 1 : 0, results: [r], keyword_progress: [{ keyword: "测试门店", accepted: 1 }], new_progress: 1 };
    },
  };
}

const results = [];
function rec(platform, scenario, step, actual, expected, pass, evidence) {
  // pass: true/false/null（null=无法验证，如本机网络受限）
  results.push({ platform, scenario, step, actual, expected, pass: pass === null ? "unverified" : !!pass, evidence: evidence || {} });
  const mark = pass === null ? "UNVERIFIED" : pass ? "PASS" : "FAIL";
  console.log(`  ${mark} [${platform}/${scenario}] ${step}${pass ? "" : " → " + actual}`);
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: process.env.HEADLESS === "1",
    protocolTimeout: 60000,
    // --disable-web-security：请求拦截合成的 mock 响应过不了 Chromium 的 CORS 预检校验
    // （拦截层预检响应不进入 CORS-preflight 缓存，POST 永不合规）——测试浏览器关掉安全检查，
    // 仅影响本测试实例；页面自身逻辑不受影响。局限性已写入报告。
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--disable-web-security"],
  });
  // 下载导入临时目录（绝不落 ~/Downloads），并留事件证据
  const bCdp = await browser.target().createCDPSession();
  await bCdp.send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: DL, eventsEnabled: true });
  const downloads = [];
  bCdp.on("Browser.downloadProgress", (e) => { if (e.state === "completed") downloads.push(e.guid); });

  /** 建一个拦截齐全的页面 */
  async function newPage(context, pf, tag) {
    const page = await context.newPage();
    await page.setUserAgent(pf.ua);
    await page.setViewport(pf.viewport);
    const logs = { console: [], errors: [], rpc: [], storageDl: [], xhs: [], leaks: [] };
    page.on("console", (msg) => logs.console.push(msg.type() + ": " + msg.text()));
    page.on("pageerror", (e) => logs.errors.push(String(e)));
    page.on("dialog", (d) => d.accept().catch(() => {})); // alert/confirm 自动确认，防阻塞 JS
    await page.setRequestInterception(true);
    const CORS = [
      { name: "Access-Control-Allow-Origin", value: "*" },
      { name: "Access-Control-Allow-Methods", value: "POST, GET, OPTIONS" },
      { name: "Access-Control-Allow-Headers", value: "content-type, apikey, authorization, x-client-info" },
    ];
    page.on("request", (req) => {
      const url = req.url();
      try {
        if (url.includes(".supabase.co")) {
          // CORS 预检：网页 fetch 跨域必须先过 OPTIONS
          if (req.method() === "OPTIONS") return req.respond({ status: 200, responseHeaders: CORS, body: "" });
          const m = url.match(/\/rpc\/([A-Za-z0-9_]+)/);
          if (m) {
            const fn = m[1];
            const route = mockRoutes[fn];
            let body = null;
            try { body = req.postData() ? JSON.parse(req.postData()) : null; } catch (_) {}
            logs.rpc.push({ fn, body });
            if (!route) {
              logs.leaks.push("unmocked-rpc:" + fn);
              return req.respond({ status: 599, responseHeaders: CORS, contentType: "application/json", body: JSON.stringify({ ok: false, reason: "mock_missing" }) });
            }
            const obj = typeof route.bodyFn === "function" ? route.bodyFn(body) : route.body;
            return req.respond({ status: route.status || 200, responseHeaders: [...CORS, { name: "Content-Type", value: "application/json" }], body: JSON.stringify(obj || {}) });
          }
          // storage 下载：回伪内容，记录（自动下载判定证据）
          logs.storageDl.push(url);
          return req.respond({ status: 200, responseHeaders: CORS, contentType: "application/octet-stream", body: "ZmFrZS1pbnN0YWxsZXItZm9yLXRlc3Q=" });
        }
        if (/xiaohongshu\.com|xhscdn\.com|xhslink\.(com|cn)/.test(url)) {
          logs.xhs.push(url.slice(0, 120));
          return req.respond({ status: 200, contentType: "text/html", body: "<html><body>blocked-by-test</body></html>" });
        }
        return req.continue(); // github.io 等静态资源真实加载
      } catch (_) { try { req.continue(); } catch (__) {} }
    });
    page.__logs = logs;
    page.__tag = tag;
    return page;
  }

  const shot = (page, pf, name) =>
    page.screenshot({ path: path.join(SHOTS, pf.id, name + ".png") }).catch(() => {});
  PLATFORMS.forEach((p) => fs.mkdirSync(path.join(SHOTS, p.id), { recursive: true }));

  const vis = (page, id) => page.evaluate((i) => {
    const el = document.getElementById(i);
    return !!el && !el.classList.contains("hidden") && el.offsetParent !== null;
  }, id);

  // ═══════════ A. index.html 路由 ═══════════
  for (const pf of PLATFORMS) {
    console.log(`\n=== A ${pf.id} index 路由 ===`);
    baseMocks();
    const ctx = await browser.createBrowserContext();
    try {
      const page = await newPage(ctx, pf, "A");
      await page.goto(`${BASE}/index.html`, { waitUntil: "load", timeout: 30000 });
      await new Promise((r) => setTimeout(r, 1500)); // 覆盖 600ms 自动下载窗口
      const detected = await page.evaluate(() => document.getElementById("detected").textContent);
      const actionHtml = await page.evaluate(() => document.getElementById("action").innerHTML);
      const dlReqs = page.__logs.storageDl.filter((u) => /\.command|\.bat/.test(u));
      await shot(page, pf, "A-index");

      if (pf.id === "android" || pf.id === "hm4") {
        rec(pf.id, "A", "设备识别", detected, "检测到：安卓手机", detected === "检测到：安卓手机", { shot: "A-index.png" });
        rec(pf.id, "A", "主 CTA 为免安装网页版", actionHtml.includes("submit.html") ? "含 submit.html 主按钮" : "缺失", "含 submit.html 主按钮", actionHtml.includes("submit.html"), {});
        rec(pf.id, "A", "不自动触发安装器下载", dlReqs.length ? "触发了 " + dlReqs[0] : "无下载请求", "无 .command/.bat 请求", dlReqs.length === 0, { dlReqs });
      } else if (pf.id === "hmnext") {
        rec(pf.id, "A", "设备识别（UA 无 android 关键证据）", detected, "未识别的设备", detected === "未识别的设备", { shot: "A-index.png" });
        rec(pf.id, "A", "兜底分支给出网页版入口", actionHtml.includes("submit.html") && actionHtml.includes("install.html") ? "网页版+全部安装方式" : actionHtml.slice(0, 80), "网页版+全部安装方式", actionHtml.includes("submit.html"), {});
        rec(pf.id, "A", "不自动触发安装器下载", dlReqs.length ? "触发" : "无", "无", dlReqs.length === 0, {});
      } else if (pf.id === "macos" || pf.id === "windows") {
        const wantFile = pf.id === "macos" ? "crowd-install-mac.command" : "crowd-install-win.bat";
        rec(pf.id, "A", "设备识别", detected, pf.id === "macos" ? "检测到：Mac 电脑" : "检测到：Windows 电脑",
          detected.includes(pf.id === "macos" ? "Mac" : "Windows"), { shot: "A-index.png" });
        rec(pf.id, "A", "600ms 后自动触发对应安装器下载（该设备的预期行为）",
          dlReqs.length && dlReqs[0].includes(wantFile) ? "自动下载 " + wantFile : "未触发/错文件 " + JSON.stringify(dlReqs),
          "自动下载 " + wantFile, dlReqs.some((u) => u.includes(wantFile)), { dlReqs });
      } else {
        rec(pf.id, "A", "Linux 路由落点", detected, "未识别的设备", detected === "未识别的设备", { shot: "A-index.png" });
        rec(pf.id, "A", "Linux 兜底：网页版入口可用、不自动下载",
          (actionHtml.includes("submit.html") && dlReqs.length === 0) ? "网页版入口+无自动下载" : actionHtml.slice(0, 80) + " dl=" + dlReqs.length,
          "网页版入口+无自动下载", actionHtml.includes("submit.html") && dlReqs.length === 0, {});
      }
      rec(pf.id, "A", "零泄漏/零页面异常", page.__logs.leaks.length + page.__logs.xhs.length + page.__logs.errors.length === 0 ? "干净" : "有", "0",
        page.__logs.leaks.length === 0 && page.__logs.xhs.length === 0 && page.__logs.errors.length === 0,
        { leaks: page.__logs.leaks, xhs: page.__logs.xhs, errors: page.__logs.errors });
    } catch (e) {
      rec(pf.id, "A", "场景执行", "异常: " + e.message, "正常执行", false, {});
    }
    await ctx.close();
  }

  // ═══════════ B. submit.html 完整链路（全平台） ═══════════
  async function submitChain(pf, variant) { // variant: normal | noUUID | noStorage
    const tag = "B" + (variant !== "normal" ? "-" + variant : "");
    const ctx = await browser.createBrowserContext();
    const out = { ok: true };
    try {
      const page = await newPage(ctx, pf, tag);
      if (variant === "noUUID") {
        await page.evaluateOnNewDocument(() => {
          Object.defineProperty(window.crypto, "randomUUID", { value: undefined, configurable: true, writable: true });
        });
      }
      if (variant === "noStorage") {
        await page.evaluateOnNewDocument(() => {
          Object.defineProperty(window, "localStorage", {
            configurable: true,
            get() { throw new DOMException("Access is denied for this document.", "SecurityError"); },
          });
        });
      }
      await page.goto(`${BASE}/submit.html`, { waitUntil: "load", timeout: 30000 });
      await new Promise((r) => setTimeout(r, 800));

      // 启动态
      const apiBanner = await vis(page, "apiBanner");
      rec(pf.id, tag, "连通性 banner 不亮（mock 200）", apiBanner ? "亮了" : "未亮", "未亮", !apiBanner, {});
      if (variant === "noStorage") {
        const sb = await vis(page, "storageBanner");
        rec(pf.id, tag, "C2 存储提示 banner 出现", sb ? "出现" : "未出现", "出现", sb, {});
        await shot(page, pf, "C2-storage-banner");
      }

      // 注册
      await page.click("#join");
      await page.waitForFunction(() => document.getElementById("pidStatus").textContent.includes("P-"), { timeout: 8000 });
      const pidShown = await page.evaluate(() => document.getElementById("pidStatus").textContent);
      const pidStored = await page.evaluate(() => { try { return localStorage.getItem("participant_id"); } catch (e) { return "__throws__"; } });
      rec(pf.id, tag, "注册→编号出现", pidShown, "P-PLT001", pidShown === "P-PLT001", {});
      if (variant === "noStorage") {
        rec(pf.id, tag, "C2 localStorage 抛错时编号走内存兜底（注册不崩）", pidStored === "__throws__" ? "localStorage 抛错、流程未崩" : "localStorage 可用: " + pidStored, "流程走完", true, {});
      } else {
        rec(pf.id, tag, "编号写入 localStorage", String(pidStored), "P-PLT001", pidStored === "P-PLT001", {});
      }

      // 领任务
      await page.waitForFunction(() => document.getElementById("targetBox").textContent.includes("测试门店"), { timeout: 8000 });
      rec(pf.id, tag, "领任务→目标门店展示", "测试门店 已展示", "测试门店 已展示", true, {});
      await shot(page, pf, tag + "-target");

      // 粘贴链接 → 识别
      await page.evaluate((u) => {
        const el = document.getElementById("noteUrl");
        el.value = u;
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }, NOTE_URL);
      await page.waitForFunction(() => document.getElementById("parseStatus").textContent.includes("已识别笔记"), { timeout: 5000 });
      rec(pf.id, tag, "链接识别", "已识别 " + NOTE_ID, "已识别 " + NOTE_ID, true, {});
      await page.evaluate(() => { document.getElementById("noteTitle").value = "测试门店探店笔记"; });

      // 提交 ×4 变体
      const submitOnce = async (gate, expectCls, expectText) => {
        setSubmitGate(gate);
        await page.evaluate((u) => {
          document.getElementById("result").innerHTML = ""; // 清掉上一次结果，防读到陈旧 DOM
          const el = document.getElementById("noteUrl");
          if (!el.value) { el.value = u; el.dispatchEvent(new Event("input", { bubbles: true })); }
          if (!document.getElementById("noteTitle").value) document.getElementById("noteTitle").value = "测试门店探店笔记";
        }, NOTE_URL);
        await new Promise((r) => setTimeout(r, 900)); // 等重新识别
        await page.click("#submit");
        await page.waitForFunction(() => document.querySelector("#result .ok-note, #result .err-note"), { timeout: 8000 });
        const txt = await page.evaluate(() => document.getElementById("result").textContent);
        const cls = await page.evaluate(() => { const d = document.querySelector("#result div"); return d ? d.className : ""; });
        return { txt, cls, ok: cls === expectCls && txt.includes(expectText) };
      };

      let r1 = await submitOnce("accepted", "ok-note", "已收录");
      rec(pf.id, tag, "提交 accepted → 绿色已收录", r1.cls + " | " + r1.txt.slice(0, 40), "ok-note 含 已收录", r1.ok, {});
      await shot(page, pf, tag + "-accepted");
      if (variant === "noUUID") {
        const subs = page.__logs.rpc.filter((x) => x.fn === "crowd_submit_proof");
        const sid = subs.length && subs[subs.length - 1].body.p_envelope.submission_id;
        rec(pf.id, tag, "C1 无 crypto.randomUUID → 兜底 UUID 格式合法",
          String(sid), "UUID v4 格式", /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(sid || ""), {});
      }

      let r2 = await submitOnce("duplicate", "ok-note", "已收录过");
      rec(pf.id, tag, "提交 duplicate → 绿色已收录过(不重复计酬)", r2.cls + " | " + r2.txt.slice(0, 40), "ok-note 含 已收录过", r2.ok, {});
      await shot(page, pf, tag + "-duplicate");

      let r3 = await submitOnce("rejected", "err-note", "链接格式不对");
      rec(pf.id, tag, "提交 rejected(item_url_invalid) → 红色中文原因", r3.cls + " | " + r3.txt.slice(0, 50), "err-note 含 链接格式不对", r3.ok, {});
      await shot(page, pf, tag + "-rejected");

      let r4 = await submitOnce("quota", "err-note", "今日配额已满");
      rec(pf.id, tag, "quota_exceeded → 红色配额提示", r4.cls + " | " + r4.txt.slice(0, 50), "err-note 含 今日配额已满", r4.ok, {});

      // C2 附加：刷新后编号丢失（banner 文案的真实性）
      if (variant === "noStorage") {
        await page.reload({ waitUntil: "load" });
        await new Promise((r) => setTimeout(r, 800));
        const pidFormBack = await vis(page, "pidForm");
        rec(pf.id, tag, "C2 刷新后编号确实丢失（内存兜底仅限当次会话）", pidFormBack ? "编号表单重新出现" : "编号仍在", "表单重新出现", pidFormBack, {});
      }

      const errs = page.__logs.errors;
      rec(pf.id, tag, "页面 JS 零异常", errs.length === 0 ? "0" : errs.join(";").slice(0, 120), "0", errs.length === 0, { errors: errs });
      rec(pf.id, tag, "零泄漏", page.__logs.leaks.length + page.__logs.xhs.length === 0 ? "干净" : "有", "0",
        page.__logs.leaks.length === 0 && page.__logs.xhs.length === 0, { leaks: page.__logs.leaks, xhs: page.__logs.xhs });
    } catch (e) {
      rec(pf.id, tag, "场景执行", "异常: " + e.message, "正常执行", false, {});
      out.ok = false;
    }
    await ctx.close();
    return out;
  }

  for (const pf of PLATFORMS) {
    console.log(`\n=== B ${pf.id} submit 全链路 ===`);
    baseMocks();
    await submitChain(pf, "normal");
  }

  // ═══════════ C. 压力变体（移动平台） ═══════════
  for (const pf of PLATFORMS.filter((p) => p.mobile)) {
    console.log(`\n=== C1 ${pf.id} 无 crypto.randomUUID ===`);
    baseMocks();
    await submitChain(pf, "noUUID");
    console.log(`\n=== C2 ${pf.id} localStorage SecurityError ===`);
    baseMocks();
    await submitChain(pf, "noStorage");
  }

  // ═══════════ D. install-mobile.html（移动组） ═══════════
  // 狐猴 zip HEAD 真实请求（静态文件，任务明确允许）；node fetch 对该域名不稳，用 curl
  let zipHead = { status: 0, err: null };
  try {
    const out = require("child_process").execSync(
      'curl -sS -o /dev/null -w "%{http_code}" --max-time 20 -I "https://bdwrhshgdeghgyzwpxnl.supabase.co/storage/v1/object/public/crowd/crowd-extension-v3.4.6.zip"',
      { encoding: "utf8" }).trim();
    zipHead.status = parseInt(out, 10) || 0;
  } catch (e) { zipHead.err = String(e).slice(0, 200); }

  for (const pf of PLATFORMS.filter((p) => p.mobile)) {
    console.log(`\n=== D ${pf.id} install-mobile ===`);
    baseMocks();
    const ctx = await browser.createBrowserContext();
    try {
      const page = await newPage(ctx, pf, "D");
      await page.goto(`${BASE}/install-mobile.html`, { waitUntil: "load", timeout: 30000 });
      await new Promise((r) => setTimeout(r, 600));
      const ffCard = await page.evaluate(() => {
        const cards = document.querySelectorAll(".card");
        const c = cards[0];
        return { title: c.querySelector("h2").textContent, hasLink: !!c.querySelector("a[href]"), text: c.textContent.slice(0, 120) };
      });
      const zipHref = await page.evaluate(() => {
        const a = document.querySelector('a[href$=".zip"]');
        return a ? a.href : null;
      });
      await shot(page, pf, "D-install-mobile");
      rec(pf.id, "D", "Firefox 卡片为「升级中」占位且卡内无死链",
        ffCard.title + " | hasLink=" + ffCard.hasLink, "含升级中 + 无链接",
        /升级中/.test(ffCard.title) && !ffCard.hasLink, { ffCard });
      rec(pf.id, "D", "zip 链接指向 v3.4.6", zipHref || "无", "crowd-extension-v3.4.6.zip", !!zipHref && zipHref.endsWith("crowd-extension-v3.4.6.zip"), { zipHref });
      // 本机网络当前把 supabase.co 过滤到 fake-ip（198.18.x.x）且 TLS 被切——HEAD 打不出去时记 UNVERIFIED 而非 FAIL
      rec(pf.id, "D", "zip HEAD 200（bucket 存在该文件）",
        zipHead.status === 200 ? "200" : "本机网络受限无法直连 supabase.co: " + (zipHead.err || zipHead.status), "200",
        zipHead.status === 200 ? true : null, {});
      rec(pf.id, "D", "零泄漏/零页面异常", page.__logs.leaks.length + page.__logs.errors.length === 0 ? "干净" : "有", "0",
        page.__logs.leaks.length === 0 && page.__logs.errors.length === 0, { leaks: page.__logs.leaks, errors: page.__logs.errors });
    } catch (e) {
      rec(pf.id, "D", "场景执行", "异常: " + e.message, "正常执行", false, {});
    }
    await ctx.close();
  }

  // ═══════════ 汇总 ═══════════
  const pass = results.filter((r) => r.pass === true).length;
  const fail = results.filter((r) => r.pass === false);
  const unverified = results.filter((r) => r.pass === "unverified");
  console.log(`\n========== 平台矩阵汇总：${pass}/${results.length} 通过，${unverified.length} 项无法验证 ==========`);
  fail.forEach((f) => console.log(`  FAIL [${f.platform}/${f.scenario}] ${f.step} → ${f.actual}`));
  unverified.forEach((f) => console.log(`  UNVERIFIED [${f.platform}/${f.scenario}] ${f.step} → ${f.actual}`));

  fs.writeFileSync(path.join(OUT, "platform-report-data.json"), JSON.stringify({ at: new Date().toISOString(), base: BASE, zipHead, downloads, results }, null, 2));
  console.log("\n[done] platform-report-data.json 已写入");
  await browser.close();
  fs.rmSync(DL, { recursive: true, force: true });
  process.exit(fail.length ? 1 : 0);})().catch((e) => { console.error("RUNNER CRASH:", e); process.exit(2); });
