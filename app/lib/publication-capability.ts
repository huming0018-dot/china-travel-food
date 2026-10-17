// This is a reader of existing Storage signed URLs, never an issuer.
export const FORMATS = ['json', 'html', 'jsonl', 'csv'] as const;
export type Format = typeof FORMATS[number];
export type Delivery = {schema: string; owner_scope: string; report_hash: string; project_id: string; issued_at: string; expires_at: string; expires_in: number; formats: Record<Format, {sha256: string; bytes: number; mime: string; signed_url: string}>; media_bytes_included: false};
const HOST = 'bdwrhshgdeghgyzwpxnl.supabase.co';
const MIME = {json: 'application/json; charset=utf-8', html: 'text/html; charset=utf-8', jsonl: 'application/x-ndjson; charset=utf-8', csv: 'text/csv; charset=utf-8'};
const HASH = /^[a-f0-9]{64}$/;
const fail = (code = 'link_invalid'): never => { throw new Error(code); };
function record(v: any): boolean { return v !== null && typeof v === 'object' && !Array.isArray(v) && Object.getPrototypeOf(v) === Object.prototype; }
function keys(v: any, expected: string[]) { if (!record(v) || Object.keys(v).sort().join('|') !== expected.slice().sort().join('|')) fail(); }
function instant(v: any): number { if (typeof v !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(v)) return fail(); const n = Date.parse(v); if (!Number.isFinite(n) || new Date(n).toISOString() !== v) fail(); return n; }
export function validateDelivery(v: any, now = Date.now()): Delivery {
  keys(v, ['schema','owner_scope','report_hash','project_id','issued_at','expires_at','expires_in','formats','media_bytes_included']);
  if (v.schema !== 'crowd-publication-links-v1' || v.owner_scope !== 'crowd-owner-main' || !HASH.test(v.report_hash) || typeof v.report_hash !== 'string' || v.project_id !== 'shanghai-existing-six-domain' || v.media_bytes_included !== false || v.expires_in !== 900) fail();
  const start = instant(v.issued_at), end = instant(v.expires_at);
  if (end - start !== 900000 || start > now + 30000) fail();
  if (end <= now) fail('link_expired');
  keys(v.formats, [...FORMATS]);
  FORMATS.forEach(f => {
    const item = v.formats[f]; keys(item, ['sha256','bytes','mime','signed_url']);
    if (typeof item.sha256 !== 'string' || !HASH.test(item.sha256) || !Number.isSafeInteger(item.bytes) || item.bytes < 1 || item.bytes > 1000000 || item.mime !== MIME[f] || typeof item.signed_url !== 'string' || item.signed_url.length > 8192) fail();
    let u: URL; try { u = new URL(item.signed_url); } catch { return fail(); }
    const expected = '/storage/v1/object/sign/crowd-publication-snapshots/publications/crowd-owner-main/' + v.report_hash + '/report.' + f;
    if (u.protocol !== 'https:' || u.host !== HOST || u.username || u.password || u.hash || u.pathname !== expected || !item.signed_url.startsWith('https://' + HOST + expected + '?')) fail();
    const params = Array.from(u.searchParams.entries());
    if (params.length !== 2 || u.searchParams.getAll('token').length !== 1 || u.searchParams.getAll('download').length !== 1 || !/^[A-Za-z0-9_.-]{1,4096}$/.test(u.searchParams.get('token') || '') || u.searchParams.get('download') !== '') fail();
  });
  if (v.formats.json.sha256 !== v.report_hash) fail();
  return v;
}
export function parseFragment(hash: string, now = Date.now()): Delivery {
  if (!/^#publication=[A-Za-z0-9_-]+$/.test(hash) || hash.length > 32768) fail();
  try {
    const b64 = hash.slice(13).replace(/-/g, '+').replace(/_/g, '/');
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const value = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes));
    return validateDelivery(value, now);
  } catch (e) { if (e instanceof Error && e.message === 'link_expired') throw e; return fail(); }
}
export async function verifiedBytes(delivery: Delivery, format: Format, signal: AbortSignal, current: () => boolean): Promise<Uint8Array> {
  validateDelivery(delivery);
  if (!current() || signal.aborted || !FORMATS.includes(format)) return fail('link_changed');
  const entry = delivery.formats[format];
  let response: Response;
  try { response = await fetch(entry.signed_url, {method: 'GET', credentials: 'omit', referrerPolicy: 'no-referrer', cache: 'no-store', redirect: 'error', signal}); }
  catch { return fail(signal.aborted ? 'link_changed' : 'link_unavailable'); }
  if (!response.ok || !response.body || response.redirected) { await response.body?.cancel(); return fail('link_unavailable'); }
  const reader = response.body.getReader(), parts: Uint8Array[] = []; let size = 0;
  try {
    while (true) {
      const piece = await reader.read(); if (piece.done) break;
      size += piece.value.byteLength;
      if (size > entry.bytes || !current() || signal.aborted) fail('link_mismatch');
      parts.push(piece.value);
    }
  } catch { await reader.cancel().catch(() => {}); return fail('link_mismatch'); }
  finally { reader.releaseLock(); }
  if (size !== entry.bytes) return fail('link_mismatch');
  const bytes = new Uint8Array(size); let pos = 0; parts.forEach(p => {bytes.set(p, pos); pos += p.length;});
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))).map(b => b.toString(16).padStart(2, '0')).join('');
  validateDelivery(delivery);
  if (!current() || signal.aborted) return fail('link_changed');
  if (digest !== entry.sha256) return fail('link_mismatch');
  return bytes;
}
export function reportFromBytes(bytes: Uint8Array, delivery: Delivery): any {
  let report: any; try { report = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(bytes)); } catch { return fail('link_mismatch'); }
  // JSON.parse accepts overflowing numeric literals. Never turn them into null on display/export.
  function finite(value: any, depth: number): void { if (depth > 100) fail('link_mismatch'); if (typeof value === 'number' && !Number.isFinite(value)) fail('link_mismatch'); if (value && typeof value === 'object') Object.keys(value).forEach(k => finite(value[k], depth + 1)); }
  finite(report, 0);
  if (!record(report) || report.project_id !== delivery.project_id || !Array.isArray(report.items)) return fail('link_mismatch');
  return report;
}
