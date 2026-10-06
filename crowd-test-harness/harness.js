/**
 * harness.js — 众包美食家 MV3 扩展 E2E 测试底座
 *
 * 安全保证：
 *  - 独立临时 user-data-dir，绝不触碰用户 Chrome profile。
 *  - --host-resolver-rules 把 supabase.co / xiaohongshu.com 全部映射到 127.0.0.1：
 *    即使拦截漏网，真实请求也会在 DNS 层死掉，永远到不了生产。
 *  - 双层 Mock：
 *    L1  CDP Fetch 域拦截 SW target 的网络请求（真·request interception）；
 *    L2  若 L1 探针失败，在 SW 上下文包装 self.fetch 兜底（运行时覆写，不改源码）。
 *  - 页面层：所有新建 page 挂 setRequestInterception，xhs 返回伪搜索页，supabase 直接 abort。
 */
const puppeteer = require("puppeteer-core");
const fs = require("fs");
const os = require("os");
const path = require("path");

const EXT_DIR = path.resolve(__dirname, "../crowd_extension");
// 注意：品牌版 Google Chrome 启动时忽略 --load-extension / --disable-extensions-except
// （"not allowed in Google Chrome, ignoring"），必须用 chrome-for-testing（Chromium 内核）。
const CHROME_PATH = process.env.CHROME_PATH ||
  os.homedir() + "/.cache/puppeteer/chrome/mac_arm-154.0.8037.57/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing";

function fakeSearchHtml(pageUrl, mode) {
  let kw = "";
  try { kw = new URL(pageUrl).searchParams.get("keyword") || ""; } catch (_) {}
  if (mode === "risk") {
    // 风控页：URL 带 keyword（page_keyword 匹配）但无卡片，正文含「访问频繁」
    return `<!doctype html><html><head><meta charset="utf-8"><title>${kw} - 搜索</title></head>
<body><div id="global"><div class="block">访问频繁，请稍后再试</div></div></body></html>`;
  }
  if (mode === "f14") {
    // F14 预检卡片组：A 标题"烤"(1字，应丢) / B 标题"烤肉"(2字，应留) /
    // C 标题"！"(标点剥离后 0 字，应丢) / D 标题空（仅作者，应丢）
    return `<!doctype html><html><head><meta charset="utf-8"><title>${kw} - 搜索</title></head>
<body><div id="global">
  <section class="note-item"><div><a href="/explore/F14DROP01?xsec_token=t"><span class="title">烤</span></a><span class="author"><span class="name">作者A</span></span></div></section>
  <section class="note-item"><div><a href="/explore/F14KEEP01?xsec_token=t"><span class="title">烤肉</span></a><span class="author"><span class="name">作者B</span></span></div></section>
  <section class="note-item"><div><a href="/explore/F14DROP02?xsec_token=t"><span class="title">！</span></a><span class="author"><span class="name">作者C</span></span></div></section>
  <section class="note-item"><div><a href="/explore/F14DROP03?xsec_token=t"><span class="title"></span></a><span class="author"><span class="name">作者D</span></span></div></section>
</div></body></html>`;
  }
  const cards = [1, 2, 3, 4].map((i) => `
    <section class="note-item">
      <div>
        <a href="/explore/NOTE00${i}abc?xsec_token=tok${i}">
          <span class="title">${kw}探店笔记第${i}篇</span>
        </a>
        <span class="author"><span class="name">作者${i}</span></span>
      </div>
    </section>`).join("\n");
  return `<!doctype html><html><head><meta charset="utf-8"><title>${kw} - 搜索</title></head>
<body><div id="global">${cards}</div></body></html>`;
}

async function launch() {
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "crowd-e2e-profile-"));
  const browser = await puppeteer.launch({
    executablePath: CHROME_PATH,
    headless: process.env.HEADLESS === "1" ? true : false, // Chrome ≥137 的 headless 不再加载扩展，默认 headed（独立临时 profile，不碰用户窗口）
    protocolTimeout: 30000,
    userDataDir,
    ignoreDefaultArgs: ["--disable-extensions"],
    defaultViewport: { width: 1280, height: 800 },
    args: [
      `--disable-extensions-except=${EXT_DIR}`,
      `--load-extension=${EXT_DIR}`,
      "--no-sandbox",
      "--disable-dev-shm-usage",
      // 硬保险：拦截万一漏网，域名解析到本地直接连接失败，绝不触达生产
      '--host-resolver-rules=MAP *.supabase.co 127.0.0.1, MAP *.xiaohongshu.com 127.0.0.1, MAP supabase.co 127.0.0.1, MAP xiaohongshu.com 127.0.0.1',
    ],
  });

  const state = {
    browser,
    userDataDir,
    swLogs: [],        // SW console 全量
    swExceptions: [],  // SW 未捕获异常
    pageErrors: [],    // 各页面异常
    rpcCalls: [],      // 实际发出的 RPC（含 mock 命中的）
    leaks: [],         // 未被 mock 处理的 supabase 请求（应为空）
    mockRoutes: {},    // fn -> {status, body, delayMs} | {fail:true}
    interceptMode: null,
    fakePageMode: "normal", // normal | risk（伪 xhs 页形态）
  };

  // ── 页面层拦截：xhs 伪页面 / supabase abort ──
  const hookPage = async (page) => {
    try {
      page.on("pageerror", (e) => state.pageErrors.push(String(e)));
      // 真实网络回包审计：凡走到 requestfinished 的 xhs 系请求且未被 harness 标记 = 真实泄漏
      page.on("requestfinished", (req) => {
        const url = req.url();
        if ((url.includes("xiaohongshu.com") || url.includes("xhscdn.com") || url.includes("supabase.co")) && !req.__mockedByHarness) {
          state.leaks.push({ where: "page-real-network", url: url.slice(0, 160) });
        }
      });
      await page.setRequestInterception(true);
      page.on("request", (req) => {
        const url = req.url();
        try {
          if (url.includes("xiaohongshu.com") || url.includes("xhscdn.com")) {
            req.__mockedByHarness = true;
            if (url.includes("/search_result")) {
              return req.respond({ status: 200, contentType: "text/html; charset=utf-8", body: fakeSearchHtml(url, state.fakePageMode) });
            }
            return req.respond({ status: 200, contentType: "text/html", body: "<html><body></body></html>" });
          }
          if (url.includes("supabase.co")) {
            req.__mockedByHarness = true;
            const m = url.match(/\/rpc\/([A-Za-z0-9_]+)/);
            const fn = m ? m[1] : null;
            const route = fn && state.mockRoutes[fn];
            if (route && !route.fail) {
              // 页面侧（如 onboarding 注册）也走同一份 mock
              let reqBody = null;
              try { reqBody = req.postData() ? JSON.parse(req.postData()) : null; } catch (_) {}
              state.rpcCalls.push({ fn, body: reqBody, at: Date.now(), via: "page" });
              const bodyObj = typeof route.bodyFn === "function" ? route.bodyFn(reqBody) : route.body;
              return req.respond({ status: route.status || 200, contentType: "application/json", body: JSON.stringify(bodyObj !== undefined ? bodyObj : {}) });
            }
            state.leaks.push({ where: "page-supabase-abort", url: url.slice(0, 160) });
            return req.abort();
          }
          return req.continue();
        } catch (_) {}
      });
    } catch (_) {}
  };
  browser.on("targetcreated", (t) => {
    if (t.type() === "page") t.page().then(hookPage).catch(() => {});
  });
  for (const p of await browser.pages()) await hookPage(p);

  // ── 拿到 SW ──
  const swTarget = await browser.waitForTarget(
    (t) => t.type() === "service_worker" && t.url().includes("background_v348.js"),
    { timeout: 20000 }
  );
  const worker = await swTarget.worker();
  state.worker = worker;

  const cdp = await swTarget.createCDPSession();
  await cdp.send("Runtime.enable");
  cdp.on("Runtime.consoleAPICalled", (ev) => {
    const line = ev.args.map((a) => (a.value !== undefined ? a.value : a.description || "")).join(" ");
    state.swLogs.push({ type: ev.type, line, at: Date.now() });
  });
  cdp.on("Runtime.exceptionThrown", (ev) => {
    const d = ev.exceptionDetails;
    state.swExceptions.push({
      text: d.text,
      desc: d.exception && (d.exception.description || d.exception.value) || "",
      at: Date.now(),
    });
  });

  // ── L1：CDP Fetch 拦截 SW 的 supabase 请求 ──
  await cdp.send("Fetch.enable", { patterns: [{ urlPattern: "*" }] });
  cdp.on("Fetch.requestPaused", async (ev) => {
    const url = ev.request.url;
    const respond = async (params) => {
      try { await cdp.send("Fetch.fulfillRequest", { requestId: ev.requestId, ...params }); } catch (_) {}
    };
    if (!url.includes("bdwrhshgdeghgyzwpxnl.supabase.co")) {
      try { await cdp.send("Fetch.continueRequest", { requestId: ev.requestId }); } catch (_) {}
      return;
    }
    const m = url.match(/\/rpc\/([A-Za-z0-9_]+)/);
    const fn = m ? m[1] : "(non-rpc)";
    let reqBody = null;
    try { reqBody = ev.request.postData ? JSON.parse(ev.request.postData) : null; } catch (_) {}
    state.rpcCalls.push({ fn, body: reqBody, at: Date.now() });
    const route = state.mockRoutes[fn];
    if (!route) {
      state.leaks.push({ where: "sw", url, reason: "no-mock-route" });
      console.log("  [leak-guard] 未配 mock 的 RPC 被 599 拦截:", fn, "(未出网)");
      return respond({ responseCode: 599, body: Buffer.from(JSON.stringify({ ok: false, reason: "mock_missing" })).toString("base64") });
    }
    if (route.fail) {
      try { await cdp.send("Fetch.failRequest", { requestId: ev.requestId, errorReason: "connectionFailed" }); } catch (_) {}
      return;
    }
    const bodyObj = typeof route.bodyFn === "function" ? route.bodyFn(reqBody) : route.body;
    const bodyStr = JSON.stringify(bodyObj !== undefined ? bodyObj : {});
    const doRespond = () => respond({
      responseCode: route.status || 200,
      responseHeaders: [{ name: "Content-Type", value: "application/json" }],
      body: Buffer.from(bodyStr).toString("base64"),
    });
    if (route.delayMs) setTimeout(doRespond, route.delayMs); else doRespond();
  });

  // ── L1 探针：确认 Fetch 域真的能拦到 SW 的 fetch ──
  state.mockRoutes.__probe = { body: { ok: true } };
  const probeResult = await worker.evaluate(async () => {
    try {
      const r = await fetch("https://bdwrhshgdeghgyzwpxnl.supabase.co/rest/v1/rpc/__probe", { method: "POST", body: "{}" });
      return { intercepted: true, status: r.status };
    } catch (e) {
      return { intercepted: false, err: String(e) };
    }
  });
  delete state.mockRoutes.__probe;
  state.interceptMode = probeResult.intercepted ? "cdp-fetch" : "sw-fetch-wrapper";

  if (!probeResult.intercepted) {
    // ── L2 兜底：SW 内包装 fetch（运行时覆写，不改源码）──
    await worker.evaluate(() => {
      self.__mockRoutes = self.__mockRoutes || {};
      self.__mockCalls = self.__mockCalls || [];
      const of = self.fetch.bind(self);
      self.fetch = async (url, opts) => {
        const u = String(url);
        if (u.includes("bdwrhshgdeghgyzwpxnl.supabase.co")) {
          const m = u.match(/\/rpc\/([A-Za-z0-9_]+)/);
          const fn = m ? m[1] : "(non-rpc)";
          const r = self.__mockRoutes[fn];
          self.__mockCalls.push({ fn, body: opts && opts.body ? JSON.parse(opts.body) : null, at: Date.now() });
          if (!r) return new Response(JSON.stringify({ ok: false, reason: "mock_missing" }), { status: 599 });
          if (r.fail) throw new TypeError("Failed to fetch (mocked)");
          if (r.delayMs) await new Promise((res) => setTimeout(res, r.delayMs));
          return new Response(JSON.stringify(r.body !== undefined ? r.body : {}), {
            status: r.status || 200,
            headers: { "Content-Type": "application/json" },
          });
        }
        return of(url, opts);
      };
    });
  }

  // 停掉 onInstalled 建的 alarm，避免 3/5min 周期干扰场景确定性
  // （先留档启动时的 alarm 列表供 S0 断言，再清）
  state.bootAlarms = await worker.evaluate(() => new Promise((res) => chrome.alarms.getAll((a) => res(a.map((x) => x.name)))));
  await worker.evaluate(() => new Promise((res) => chrome.alarms.clearAll(() => res(true))));

  // chrome.tabs.create 运行时包装（测试脚手架，不改源码）：
  // 先建 about:blank，等 600ms 让 node 侧给新 page 挂好请求拦截，再导航到真实目标 URL。
  // 消除"SW 建 tab → 导航请求先于 setRequestInterception 到达"的竞态（否则真站直连）。
  await worker.evaluate(() => {
    const orig = chrome.tabs.create.bind(chrome.tabs);
    chrome.tabs.create = async (props) => {
      const tab = await orig({ url: "about:blank", active: props && props.active });
      await new Promise((r) => setTimeout(r, 600));
      if (props && props.url) await chrome.tabs.update(tab.id, { url: props.url });
      return tab;
    };
  });

  // ── 帮助函数 ──
  const helpers = {
    state,
    worker,
    cdp,
    browser,

    /** 设置 RPC mock 路由；L2 模式下同步进 SW */
    async setMock(routes) {
      state.mockRoutes = routes || {};
      state.rpcCalls = [];
      if (state.interceptMode === "sw-fetch-wrapper") {
        await worker.evaluate((r) => { self.__mockRoutes = r; self.__mockCalls = []; }, state.mockRoutes);
      }
    },
    setFakePageMode(mode) { state.fakePageMode = mode || "normal"; },
    async getRpcCalls() {
      if (state.interceptMode === "sw-fetch-wrapper") {
        return worker.evaluate(() => self.__mockCalls || []);
      }
      return state.rpcCalls;
    },

    async storageSet(obj) { return worker.evaluate((o) => chrome.storage.local.set(o), obj); },
    async storageGet(keys) { return worker.evaluate((k) => chrome.storage.local.get(k), keys); },
    async storageClear() { return worker.evaluate(() => chrome.storage.local.clear()); },

    /** 在 SW 上下文执行表达式（可调用 uploadProofs / doCollectOnce / fetchActiveTask 等全局函数） */
    async swEval(expr) { return worker.evaluate(expr); },
  };

  return helpers;
}

module.exports = { launch, EXT_DIR };
