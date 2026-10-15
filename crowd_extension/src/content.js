/**
 * content.js — 注入小红书页面的辅助采集脚本（知情自愿众包）
 *
 * 采集语义（审计问题 3 修复）：
 * - 本脚本不主动搜索、不发起新导航；只对参与者当前亲手打开的页面做只读提取，
 *   辅助参与者把"正在看的内容"结构化，而不是替参与者决定看什么。
 * - background 通过 { type:"CROWD_SEARCH", keyword, task_id?, target? } 触发：
 *   · keyword 必填，缺失返回 { ok:false, error:"MISSING_KEYWORD" }；
 *   · task_id / target 为可选任务上下文（也可打包在 msg.task 对象里），
 *     本脚本在响应中原样回显，供 background 核对任务归属。
 * - 采集前校验当前页面与任务关键词一致（页面与任务不匹配时一条都不采）：
 *   · 搜索结果页 /search_result?keyword=... ：取 URL 的 keyword 参数
 *     （URLSearchParams 自动完成 URL 解码）；
 *   · 其他页面：读取页面搜索框当前值；
 *   · 与传入 keyword 不一致、或页面上无法确定搜索词时，返回
 *     { ok:false, error:"PAGE_MISMATCH", page_keyword:<实际页面词或 null>, items:[] }。
 * - 列表页：每张卡片独立提取自己的 title/note_url/note_id/author；
 *   任何字段缺失一律留 null，严禁跨卡片复制任何字段；列表页不提取正文
 *   （excerpt 恒为 null，正文只在详情页提取）。
 * - 详情页：只提取当前这一篇笔记自己的标题/正文/作者/发布时间；
 *   同样禁止回退到任何其他笔记的数据。
 * - note_id 只从笔记链接 URL 提取（/explore/<id> 或 /discovery/item/<id>）；
 *   拿不到为 null，并以 note_id_missing:true 显式标注。
 *
 * 只读公开页面内容，不采集私信/设置/账号信息；作者昵称在 service worker 层做最小化。
 * 契约版本：CROWD-CONTRACT-001 §3（响应新增字段均向后兼容）。
 */
(() => {
  const XHS_DOMAIN = "www.xiaohongshu.com";
  const NOTE_CARD_SELECTOR = "section.note-item, div.note-item";
  const NOTE_LINK_SELECTOR = "a[href*='/explore/'], a[href*='/discovery/item/']";
  const NOTE_ID_RE = /\/(?:explore|discovery\/item)\/([0-9a-zA-Z]+)/;

  const _text = (el) => (el && typeof el.textContent === "string" ? el.textContent.trim() : "") || null;
  // 作者昵称净化（v3.4.13）：xhs 的 name 节点常把发布日期拼在昵称后——剥掉尾部时间形态
  // （YYYY-MM-DD / YYYY-MM / N秒|分钟|小时|天|周|个月|年前 / 昨天|前天|刚刚 / 前位是数字的 MM-DD）
  const _cleanAuthor = (s) => {
    s = String(s || "").trim();
    let prev;
    do {
      prev = s;
      s = s.replace(/(\d{4}-\d{2}(-\d{2})?|\d+\s*(秒|分钟|小时|天|周|个月|年)前|昨天|前天|刚刚)$/, "").trim();
    } while (s !== prev && s.length > 0);
    s = s.replace(/(\d)(\d{1,2})-(\d{1,2})$/, (m, pre, mo, dd) =>
      (+mo >= 1 && +mo <= 12 && +dd >= 1 && +dd <= 31) ? pre : m).trim();
    return s;
  };

  /** 归一化搜索词用于比对：Unicode 规范化 + 压缩空白 + 小写 */
  function normKw(s) {
    return (typeof s === "string" ? s : "")
      .normalize("NFC")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  const _sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  /**
   * 搜索结果页温和拟态滚动（v3.5.2 提产「少搜多榨」）：
   * 真实用户看搜索结果几乎都会向下划一下。平缓下划 2 次（约 0.85 视口/次）、
   * 每次停顿 2–4s 等待瀑布流加载下一批卡片，把单页可提取卡片从首屏 ~20 张
   * 提升到 ~40 张。只在同一 SERP 内做、不发起新搜索、不访问笔记详情，
   * 风控增量远低于新开搜索；停留、下划反而更像真人浏览。
   * 仅搜索结果页生效；详情页/其他页面直接返回。滚动失败不阻断采集。
   */
  async function gentleScrollForMore() {
    // v3.5.3 稳妥降风险：禁用程序化平滑滚动。
    // v3.5.2「每个搜索页固定 smooth 滚动 2 次、幅度/次数/停顿完全一致」是典型机器特征，
    // 已被小红书判定为「AI 不规范使用 / 模拟浏览」并对账号限流 7 天（ahuhu 事件）。
    // 现在单页只取首屏自然加载的卡片（~20 张），宁可单页少榨，也不做无人值守的合成滚动。
    // 真正的「真人前台浏览时辅助」应在真实用户手势（wheel/触摸）下触发，不能在后台标签页自动执行。
    return;
  }

  /**
   * 读取当前页面的实际搜索词。
   * 优先取搜索页 URL 的 keyword 参数（自动 URL 解码）；
   * 否则读页面搜索框当前值；都无法确定时返回 null。
   */
  function getPageKeyword() {
    try {
      const u = new URL(location.href);
      if (u.pathname.startsWith("/search_result")) {
        const kw = u.searchParams.get("keyword");
        if (kw && kw.trim()) return kw.trim();
      }
    } catch (e) {
      /* location 解析失败时继续尝试搜索框 */
    }
    const input = document.querySelector(
      "input#search-input, input[name='search'], .search-box input, input[placeholder*='搜索']"
    );
    const v = input && typeof input.value === "string" ? input.value.trim() : "";
    return v || null;
  }

  /** 列表页：逐卡片独立提取。字段缺失留 null，禁止跨卡片复制。 */
  function extractNoteCards() {
    const cards = document.querySelectorAll(NOTE_CARD_SELECTOR);
    const out = [];
    cards.forEach((c) => {
      // 该卡片自己的笔记链接（唯一允许提取 note_id 的来源）
      const a = c.querySelector(NOTE_LINK_SELECTOR);
      let note_url = null;
      let note_id = null;
      if (a && a.href) {
        const m = a.href.match(NOTE_ID_RE);
        note_id = m ? m[1] : null;
        note_url = a.href.split("?")[0] + "?xsec_source=pc_crowd";
      }
      // 该卡片自己的标题与作者（只在这张卡片的子树内查找）
      const title = _text(c.querySelector(".title")) || _text(a);
      const author = _cleanAuthor(_text(c.querySelector(".author .name, .name, [class*='author'] [class*='name']")));

      // 链接、标题、作者全空 → 不是有效笔记卡片，跳过
      if (!note_url && !title && !author) return;

      out.push({
        kind: "note",
        note_id, // 拿不到为 null，并显式标注
        note_id_missing: note_id === null,
        note_url,
        title,
        author,
        excerpt: null, // 列表页不取正文；正文只在对应详情页独立提取
      });
    });
    return out;
  }

  /** 详情页：只提取当前这篇笔记自己的内容，不回退到任何其他笔记的数据。 */
  function extractNoteDetail() {
    const title = _text(document.querySelector("#detail-title, h1, .note-content .title, .title"));
    const desc = _text(document.querySelector("#detail-desc, .desc, .note-content, [class*='desc']"));
    const author = _cleanAuthor(_text(
      document.querySelector(".author .name, .user-name, [class*='author'] [class*='name']")
    ));
    const published_at = _text(
      document.querySelector(".bottom-container .date, .date, [class*='date']")
    );
    const m = location.pathname.match(NOTE_ID_RE);
    const note_id = m ? m[1] : null;
    return {
      kind: "note",
      note_id,
      note_id_missing: note_id === null,
      note_url: location.href.split("?")[0] + "?xsec_source=pc_crowd",
      title,
      excerpt: desc ? desc.slice(0, 200) : null,
      author,
      published_at,
    };
  }

  // F5 修复：风控检测独立成函数并透传到所有返回路径（含 ok:false 分支）。
  // 原来只在成功分支带 rateLimited，页面触发风控又没解析出卡片时信号丢失，SW 会顶着风控继续采。
  // ── 风控/账号状态检测（v3.5.3）：从只认「访问频繁」扩展为四类信号 ──
  // 旧版只认「访问频繁」四个字，对账号处罚/限流（「AI 不规范使用」「流量曝光限制」）、
  // 登录态失效、验证码/滑块完全识别不到，导致账号被限流后仍在后台空跑、系统无感知（ahuhu 事件）。
  // 词表优先选用处罚页专有词，尽量避免普通笔记正文误报；命中即按最严重一类上报。
  const RISK_PATTERNS = [
    {
      kind: "account_penalty", // 账号处罚/限流/封禁/AI 不规范
      re: /流量曝光|商业权益|处置结果|不规范|模拟浏览|浏览行为异常|用户状态异常|功能受限|被限流|账号的流量|账号.{0,12}(异常|违规|封禁|处罚|受限|被限制|已被封)|限制.{0,6}(曝光|使用|商业|账号|功能)/,
    },
    {
      kind: "captcha", // 验证码 / 滑块 / 人机验证（强组合，避免普通笔记误报）
      re: /安全验证|人机验证|滑块验证|拖动.{0,6}(完成|验证|拼图)|完成.{0,3}验证|访问验证|captcha|verifycaptcha/i,
    },
    {
      kind: "auth_lost", // 登录态失效 / 未登录 / 登录页
      re: /扫码登录|请先登录|登录后(查看|继续|浏览)|登录失效|登录过期|登录已过期|请登录|账号密码登录|手机验证码登录/,
    },
    {
      kind: "rate_limited", // 访问频繁
      re: /访问频繁|操作频繁|请求频繁|过于频繁|频率过快|频繁/,
    },
  ];

  function detectRisk() {
    try {
      // 1) URL 被重定向到登录 / passport 页（强信号；搜索页自身不算）
      const u = (location.pathname || "") + (location.search || "");
      if (/\/login|\/signin|passport|loginredirect/i.test(u) && !/search_result/.test(u)) {
        return { kind: "auth_lost", matched: "login_redirect" };
      }
      // 2) 页面文案（前 3000 字足够覆盖整页处罚/验证提示）
      const txt = (document.body && document.body.innerText ? document.body.innerText : "").slice(0, 3000);
      for (const p of RISK_PATTERNS) {
        const m = txt.match(p.re);
        if (m) return { kind: p.kind, matched: m[0].slice(0, 24) };
      }
      // 3) 验证组件 DOM 兜底（小红书滑块/验证码容器）
      const box = document.querySelector(
        '[id*="captcha" i],[class*="captcha" i],[class*="slider" i],[class*="verify-slider" i]'
      );
      if (box) return { kind: "captcha", matched: "captcha_dom" };
      return { kind: null, matched: null };
    } catch (_) {
      return { kind: null, matched: null };
    }
  }

  // 向后兼容：是否处于任一风控态（旧调用方仍用布尔）
  function detectRateLimited() {
    return !!detectRisk().kind;
  }

  // v3.5.2：温和滚动需要异步等待，listener 走 async 主流程 + return true 保持消息通道。
  // 在最终结果上统一注入最新风险信号（成功/失败路径都覆盖，避免风险信号被 ok:false 分支吞掉）
  function attachRisk(res) {
    try {
      if (res && typeof res === "object") {
        const r = detectRisk();
        res.riskKind = r.kind; // account_penalty | auth_lost | captcha | rate_limited | null
        res.riskMatched = r.matched;
        res.rateLimited = !!res.rateLimited || !!r.kind;
      }
    } catch (_) { /* 风险检测失败不阻断采集 */ }
    return res;
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (!msg || msg.type !== "CROWD_SEARCH") return undefined;
    handleSearch(msg)
      .then((res) => sendResponse(attachRisk(res)))
      .catch((e) => sendResponse(attachRisk({
        ok: false,
        error: "EXTRACT_FAILED",
        reason: e && e.message ? e.message : String(e),
        items: [],
      })));
    return true; // 异步 sendResponse
  });

  async function handleSearch(msg) {
    if (!location.hostname.includes(XHS_DOMAIN)) {
      return { ok: false, error: "NOT_ON_XHS", reason: "not_on_xhs", items: [], rateLimited: detectRateLimited() };
    }

    // 任务上下文：keyword 必填；task_id/target 可选（支持 msg.task 打包传入）
    const keyword = typeof msg.keyword === "string" ? msg.keyword.trim() : "";
    const taskCtx = (msg.task && typeof msg.task === "object" ? msg.task : {}) || {};
    const task_id = msg.task_id || taskCtx.task_id || null;
    const target = msg.target || taskCtx.target || null;

    if (!keyword) {
      return { ok: false, error: "MISSING_KEYWORD", reason: "missing_keyword", items: [], rateLimited: detectRateLimited() };
    }

    // 采集前校验：当前页面搜索词必须与任务关键词一致，不一致一条都不采
    const page_keyword = getPageKeyword();
    if (page_keyword === null || normKw(page_keyword) !== normKw(keyword)) {
      return {
        ok: false,
        error: "PAGE_MISMATCH",
        reason: "page_mismatch",
        keyword,
        page_keyword,
        task_id,
        target,
        items: [],
        rateLimited: detectRateLimited(),
      };
    }

    // 搜索结果页：提取前先温和下划加载更多瀑布流卡片（少搜多榨，不发起新搜索）。
    await gentleScrollForMore();

    const isNotePage = NOTE_ID_RE.test(location.pathname);
    const cards = extractNoteCards();
    const page_type = cards.length ? "search" : isNotePage ? "note" : "unknown";
    const rateLimited = detectRateLimited();
    if (page_type === "unknown") {
      return {
        ok: false,
        error: "UNSUPPORTED_PAGE",
        reason: "unsupported_page",
        keyword,
        page_keyword,
        items: [],
        rateLimited,
      };
    }
    // 列表页逐卡片独立数据；详情页仅当前笔记自身数据
    const items = cards.length ? cards : [extractNoteDetail()];
    return {
      ok: true,
      keyword,
      page_keyword,
      page_type,
      task_id,
      target,
      items,
      rateLimited,
    };
  }
})();
