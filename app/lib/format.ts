// 字段安全渲染：数组 / JSON 串 / 对象 / 原始值 → 可显示文本
// 防止把 ["…"]、{"quotes":[…]} 这类原始结构直接渲染成 "[object Object]"
export function safeText(v: any, depth = 0): string {
  if (v === null || v === undefined) return '';

  if (Array.isArray(v)) {
    const parts = v.map((x) => safeText(x, depth + 1)).filter(Boolean);
    // 对象数组（如多条食客原话）逐条换行；标量数组（标签/差评）用顿号
    const hasObject = v.some((x) => x !== null && typeof x === 'object');
    return parts.join(hasObject ? '\n' : '、');
  }

  if (typeof v === 'string') {
    const s = v.trim();
    if ((s.startsWith('[') || s.startsWith('{')) && depth < 4) {
      try {
        return safeText(JSON.parse(s), depth + 1);
      } catch {
        return s;
      }
    }
    return v;
  }

  if (typeof v === 'object') {
    // 优先提取常见文本字段，并附上来源 / 作者 / 日期等元信息
    const labelKeys = ['quote', 'text', 'summary', 'content', 'comment', 'note', 'title', 'name'];
    for (const k of labelKeys) {
      const val = (v as Record<string, unknown>)[k];
      if (typeof val === 'string' && val.trim()) {
        const meta = [(v as any).source, (v as any).author, (v as any).date]
          .filter((x) => typeof x === 'string' && x.trim())
          .join(' · ');
        return meta ? `${val.trim()} —— ${meta}` : val.trim();
      }
    }
    // 否则递归对象的各个值
    return Object.values(v)
      .map((x) => safeText(x, depth + 1))
      .filter(Boolean)
      .join('\n');
  }

  return String(v);
}
