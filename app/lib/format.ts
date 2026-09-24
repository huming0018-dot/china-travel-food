// 字段安全渲染：数组 / JSON 串 / 原始值 → 可显示文本（防止把 ["\u.."] 这类原始结构直接渲染到页面）
export function safeText(v: any): string {
  if (v === null || v === undefined) return '';
  if (Array.isArray(v)) return v.map(safeText).filter(Boolean).join('、');
  if (typeof v === 'string') {
    const s = v.trim();
    if (s.startsWith('[') || s.startsWith('{')) {
      try { return safeText(JSON.parse(s)); } catch { return s; }
    }
    return v;
  }
  return String(v);
}
