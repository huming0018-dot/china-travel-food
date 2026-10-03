/**
 * content.js — 注入小红书页面，执行采集，返回结构化 proof 数据
 *
 * v3.2 修复（外部审计 #3）：keyword 真实接线——搜索页校验当前查询与任务关键词匹配，
 * 详情页校验 note_id 与正文关联；每张卡片独立提取，不再把全局详情复制给每张卡片。
 *
 * 与 CROWD-CONTRACT-003 §3 字段对齐。只读公开页面内容，不采集私信/设置/账号信息。
 */
(() => {
  const XHS_DOMAIN = "www.xiaohongshu.com";
  const NOTE_CARD_SELECTOR = "section.note-item, div.note-item";
  const DETAIL_RE = /\/explore\/([0-9a-fA-F]{24})/;

  /** 从当前页面读取搜索结果的笔记卡片（只读 DOM，每卡片独立字段） */
  function extractNoteCards() {
    const cards = document.querySelectorAll(NOTE_CARD_SELECTOR);
    const out = [];
    cards.forEach((c) => {
      const a = c.querySelector("a[href*='/explore/']");
      if (!a) return;
      const href = a.href || "";
      const m = href.match(/\/explore\/([0-9a-zA-Z]+)/);
      if (!m) return;
      const titleEl = c.querySelector(".title, a[href*='/explore/'] span, .note-item .title");
      const title = (titleEl && titleEl.textContent.trim()) || "";
      // 卡片独立摘要（搜索结果卡片通常无正文，有则提取，无则留空）
      const descEl = c.querySelector(".desc, [class*='desc']");
      const excerpt = (descEl && descEl.textContent.trim()) || "";
      out.push({
        note_id: m[1],
        note_url: href.split("?")[0] + "?xsec_source=pc_crowd",
        title,
        author: "", // 搜索结果卡片页通常不显示作者；详情页模式单独提取
        excerpt: excerpt.slice(0, 200),
        kind: "note",
      });
    });
    return out;
  }

  /** 从当前打开的单篇笔记页读取正文与作者（独立提取，不共享） */
  function extractNoteDetail() {
    const title = (document.querySelector("h1, .title") || {}).textContent || "";
    const descEl = document.querySelector(".desc, .note-content, [class*='desc']");
    const desc = (descEl && descEl.textContent.trim()) || "";
    const authorEl = document.querySelector(".author .name, .user-name, [class*='author'] [class*='name']");
    const author = (authorEl && authorEl.textContent.trim()) || "";
    return { title: title.trim(), excerpt: desc.slice(0, 200), author };
  }

  /** 搜索页是否与任务关键词匹配（URL 编码/搜索框值/页面关键词元素） */
  function pageMatchesKeyword(keyword) {
    if (!keyword) return true; // 无关键词的任务不校验
    const kw = String(keyword).toLowerCase();
    const url = location.href.toLowerCase();
    try { if (url.includes(encodeURIComponent(keyword).toLowerCase())) return true; } catch (e) {}
    if (url.includes(kw)) return true;
    const qEl = document.querySelector("input[type='search'], [class*='search'] input, .search-input input");
    const q = (qEl && qEl.value) || "";
    if (q.toLowerCase().includes(kw)) return true;
    const tEl = document.querySelector("[class*='search-word'], .search-word, [class*='keyword'], [class*='query']");
    const t = (tEl && tEl.textContent) || "";
    if (t.toLowerCase().includes(kw)) return true;
    return false;
  }

  /** 详情页正文/标题是否与任务关键词任一 token 关联（宽松：≥1 命中） */
  function detailMatchesKeyword(keyword, detail) {
    if (!keyword) return true;
    const tokens = String(keyword).split(/[\s,，、]+/).filter(Boolean);
    if (!tokens.length) return true;
    const hay = ((detail.title || "") + " " + (detail.excerpt || "")).toLowerCase();
    return tokens.some((t) => hay.includes(t.toLowerCase()));
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type !== "CROWD_SEARCH") return;
    if (!location.hostname.includes(XHS_DOMAIN)) {
      sendResponse({ ok: false, reason: "not_on_xhs" });
      return;
    }

    try {
      const keyword = (msg.keyword || "").trim();
      const detailM = location.pathname.match(DETAIL_RE);
      const isDetail = !!detailM && document.querySelector(".note-content, .desc, [class*='desc']");
      let items;

      if (isDetail) {
        // 单篇详情页：用户明确打开的笔记 → 独立提取 + 宽松关键词关联校验
        const detail = extractNoteDetail();
        if (!detailMatchesKeyword(keyword, detail)) {
          sendResponse({ ok: false, reason: "当前笔记与任务关键词不相关（请打开任务词对应笔记）" });
          return;
        }
        items = [{
          kind: "note",
          note_id: detailM[1],
          note_url: location.href.split("?")[0] + "?xsec_source=pc_crowd",
          title: detail.title,
          excerpt: detail.excerpt,
          author: detail.author,
        }];
      } else {
        // 搜索页：先校验页面查询与任务关键词匹配（防错配：领甲店任务停在乙店页面）
        if (!pageMatchesKeyword(keyword)) {
          sendResponse({ ok: false, reason: "当前页面与任务关键词不匹配（请切到任务词搜索结果页）" });
          return;
        }
        items = extractNoteCards();
        if (!items.length) {
          sendResponse({ ok: false, reason: "当前页面未发现笔记卡片（请确认已展示搜索结果）" });
          return;
        }
      }

      sendResponse({
        ok: true,
        items,
        mode: isDetail ? "detail" : "search",
        rateLimited: /访问频繁|频繁/.test(document.body.innerText.slice(0, 500)),
      });
    } catch (e) {
      sendResponse({ ok: false, reason: e.message });
    }
  });
})();
