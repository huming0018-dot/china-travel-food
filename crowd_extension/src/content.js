/* Only rendered public content. Never intercept private APIs, cookies or network. */
(function (root) {
  'use strict';
  const C = root.CrowdCore;
  const visible = el => !!el && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== 'hidden';
  const first = selectors => [...document.querySelectorAll(selectors)].find(visible);
  const text = el => el?.innerText?.trim() || '';
  const noteBody = () => first('#detail-desc, .note-detail .note-text, .note-container .note-text, .note-scroller .desc, .note-content .desc');
  const noteLinks = () => [...document.querySelectorAll('a[href*="/explore/"], a[href*="/discovery/item/"]')].filter(visible);
  function gate() {
    if (first('[class*="captcha"], [id*="captcha"], iframe[src*="captcha"], [class*="verify-slider"]')) return 'captcha';
    const modal = first('[role="dialog"], .error-page, .error-container, .login-container, .login-modal');
    const message = text(modal);
    if (/访问频繁|操作频繁|请求过于频繁|稍后再试|访问受限/.test(message)) return 'rate_limit';
    if (first('.login-container input, .login-modal input, input[placeholder*="手机号"]') || /登录后查看|请先登录/.test(message)) return 'login_required';
    return null;
  }
  function count(selectors) {
    const value = text(first(selectors)).replace(/,/g, '');
    const m = value.match(/^(\d+(?:\.\d+)?)\s*([万wWkK千]?)\+?$/);
    if (!m) return null;
    return Math.round(Number(m[1]) * ({万: 10000, w: 10000, W: 10000, k: 1000, K: 1000, 千: 1000}[m[2]] || 1));
  }
  function note() {
    let identity;
    try { identity = C.noteURL(location.href); } catch (_) { return {ready: false}; }
    const body = noteBody();
    const original = text(body); if (original.length < 8) return {ready: false};
    const title = text(first('#detail-title, .note-detail .title, .note-container .title')).slice(0, 300);
    const raw = original.slice(0, 24000);
    const date = text(first('.note-content .date, .note-detail .date, .note-container .date')) || null;
    const dateISO = date?.match(/\b(20\d{2}-\d{2}-\d{2})\b/);
    const hashtags = [...new Set([...raw.matchAll(/#([^\s#]{1,60})/g)].map(m => m[1]))];
    return {ready: true, record: {schema_version: 4,
      standard: {platform: 'xiaohongshu', note_id: identity.id, url: identity.url, title,
        captured_at: new Date().toISOString(), published_at: dateISO ? dateISO[1] : null,
        author_display: text(first('.author-wrapper .username, .note-detail .author .name')).slice(0, 100) || null,
        like_count: count('.interact-container .like-wrapper .count'),
        collect_count: count('.interact-container .collect-wrapper .count'),
        comment_count: count('.interact-container .chat-wrapper .count')},
      extra: {hashtags, published_label: date, author_opinion_quotes: raw.split(/\n+/).filter(x => /好吃|难吃|推荐|踩雷|鲜|咸|甜|辣|油腻|服务|排队|价格/.test(x)).slice(0, 30)},
      evidence: {text: raw, original_length: original.length, truncated: original.length > raw.length,
        selector: body.id ? '#' + body.id : '.' + String(body.className).trim().replace(/\s+/g, '.'),
        parser_version: C.VERSION, source: 'rendered_public_dom'}}};
  }
  function probe(action) {
    // Opt-in diagnostics use categories/counts, never page text or navigation tokens.
    if (action === 'diagnostics') return {ready: true, page: {
      kind: /^\/search_result\/?$/.test(location.pathname) ? 'search' : /^\/(explore|discovery\/item)\//.test(location.pathname) ? 'note' : 'other',
      document: document.readyState, gate: gate(), links: Math.min(noteLinks().length, 500),
      body_chars: Math.min(text(noteBody()).length, 24000), visible: !document.hidden,
      search_note_links: Math.min([...document.querySelectorAll('a[href*="/search_result/"]')].filter(visible).length, 500)
    }};
    const blocked = gate(); if (blocked) return {ready: false, gate: blocked};
    if (action === 'scroll') {
      const box = first('.note-scroller, .note-detail .scroll-container');
      (box || window).scrollBy({top: Math.round(innerHeight * C.between(35, 65) / 100), behavior: 'smooth'});
      return {ready: true};
    }
    if (action === 'search') {
      const links = noteLinks().map(a => a.href);
      return {ready: links.length > 0 || !!first('.search-empty, .empty-page, .no-result'), links};
    }
    return note();
  }
  root.CrowdPage = {probe};
  if (typeof chrome !== 'undefined' && chrome.runtime?.onMessage) {
    chrome.runtime.onMessage.addListener((message, sender, reply) => {
      if (sender.id !== chrome.runtime.id || message.type !== 'crowd_probe') return;
      try { reply(probe(message.action)); } catch (e) { reply({ready: false, error: e.message}); }
    });
    chrome.runtime.sendMessage({type: 'page_ready'}).catch(() => {});
  }
})(globalThis);
