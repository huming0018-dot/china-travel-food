/**
 * content.js — 注入小红书页面，执行搜索/采集，返回结构化 proof 数据
 *
 * 与 CROWD-CONTRACT-001 §3 字段严格对齐。只读公开页面内容，
 * 不采集私信/设置/账号信息；作者昵称在 service worker 层做最小化。
 */
(() => {
  const XHS_DOMAIN = "www.xiaohongshu.com";
  const NOTE_CARD_SELECTOR = "section.note-item, div.note-item";

  /** 从当前页面读取搜索结果的笔记卡片（只读 DOM） */
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
      out.push({
        note_id: m[1],
        note_url: href.split("?")[0] + "?xsec_source=pc_crowd",
        title,
        author: "",
        excerpt: "",
        kind: "note",
      });
    });
    return out;
  }

  /** 从当前打开的单篇笔记页读取正文（excerpt）与作者（脱敏由后端做） */
  function extractNoteDetail() {
    const title = (document.querySelector("h1, .title") || {}).textContent || "";
    const descEl = document.querySelector(".desc, .note-content, [class*='desc']");
    const desc = (descEl && descEl.textContent.trim()) || "";
    const authorEl = document.querySelector(".author .name, .user-name, [class*='author'] [class*='name']");
    const author = (authorEl && authorEl.textContent.trim()) || "";
    return { title: title.trim(), excerpt: desc.slice(0, 200), author };
  }

  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type !== "CROWD_SEARCH") return;

    // 模拟真人：先浏览当前页 ≥30s 的等待由安全线 engine 在 SW 侧控制，
    // content 侧只负责在当前已打开的小红书页面上采集（不发起新导航）。
    if (!location.hostname.includes(XHS_DOMAIN)) {
      sendResponse({ ok: false, reason: "not_on_xhs" });
      return;
    }

    try {
      const cards = extractNoteCards();
      const detail = extractNoteDetail();
      const items = cards.length
        ? cards.map((c) => ({ ...c, excerpt: detail.excerpt, author: detail.author }))
        : [{
            kind: "note",
            note_id: location.pathname.split("/").pop() || "",
            note_url: location.href,
            title: detail.title,
            excerpt: detail.excerpt,
            author: detail.author,
          }];
      sendResponse({ ok: true, items, rateLimited: /访问频繁|频繁/.test(document.body.innerText.slice(0, 500)) });
    } catch (e) {
      sendResponse({ ok: false, reason: e.message });
    }
  });
})();
