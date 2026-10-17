import { createHash } from 'crypto';
import { createClient } from '@supabase/supabase-js';
import type { NextApiRequest } from 'next';

const hex = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const uuid = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(v);
const plain = (v: unknown): v is Record<string, any> => !!v && typeof v === 'object' && !Array.isArray(v);
const exact = (v: unknown, keys: string[]): v is Record<string, any> => plain(v) && Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
export const formats = { json: 'application/json; charset=utf-8', html: 'text/html; charset=utf-8', jsonl: 'application/x-ndjson; charset=utf-8', csv: 'text/csv; charset=utf-8' };
export type Format = keyof typeof formats;
export type Snapshot = { slug: string; title: string; project_id: string; report_hash: string; formats: Record<Format, { sha256: string; bytes: number }> };
export class PublicationError extends Error {
  constructor(public code: string, public status: number) { super(code); }
}
function fail(code: string, status = 503): never { throw new PublicationError(code, status); }
const hash = (bytes: Buffer | string) => createHash('sha256').update(bytes).digest('hex');
const short = (v: unknown): v is string => typeof v === 'string' && /^[a-z0-9][a-z0-9-]{0,63}$/.test(v);

function endpoint() {
  let u: URL;
  try { u = new URL(process.env.NEXT_PUBLIC_SUPABASE_URL || ''); } catch { return fail('publication_not_configured'); }
  if (u.protocol !== 'https:' || !u.hostname.endsWith('.supabase.co') || u.username || u.password || u.port || u.pathname !== '/' || u.search || u.hash) fail('publication_not_configured');
  return u.origin;
}

function accessConfig() {
  const raw = process.env.CTFS_PUBLICATION_ACCESS_JSON || '', expected = process.env.CTFS_PUBLICATION_ACCESS_SHA256;
  if (!raw || Buffer.byteLength(raw) > 131072 || !hex(expected) || hash(raw) !== expected) fail('publication_not_configured');
  let config: unknown;
  try { config = JSON.parse(raw); } catch { return fail('publication_not_configured'); }
  if (!exact(config, ['schema', 'grants']) || config.schema !== 'ctfs-publication-access-v1' || !Array.isArray(config.grants) || config.grants.length > 100) fail('publication_not_configured');
  const users = new Set<string>();
  for (const grant of config.grants) {
    if (!exact(grant, ['user_id', 'snapshots']) || !uuid(grant.user_id) || users.has(grant.user_id) || !Array.isArray(grant.snapshots) || grant.snapshots.length > 50) fail('publication_not_configured');
    users.add(grant.user_id); const slugs = new Set<string>();
    for (const s of grant.snapshots) {
      if (!exact(s, ['slug', 'title', 'project_id', 'report_hash', 'formats']) || !short(s.slug) || slugs.has(s.slug) || typeof s.title !== 'string' || !s.title.trim() || s.title.length > 120 || /[\x00-\x1f]/.test(s.title) || !short(s.project_id) || !hex(s.report_hash) || !exact(s.formats, Object.keys(formats))) fail('publication_not_configured');
      slugs.add(s.slug);
      for (const f of Object.keys(formats)) if (!exact(s.formats[f], ['sha256', 'bytes']) || !hex(s.formats[f].sha256) || !Number.isSafeInteger(s.formats[f].bytes) || s.formats[f].bytes < 1 || s.formats[f].bytes > 1000000) fail('publication_not_configured');
      if (s.formats.json.sha256 !== s.report_hash) fail('publication_not_configured');
    }
  }
  return config.grants as { user_id: string; snapshots: Snapshot[] }[];
}

export async function authorizedSnapshots(req: NextApiRequest): Promise<Snapshot[]> {
  const auth = req.headers.authorization;
  if (typeof auth !== 'string' || !/^Bearer [A-Za-z0-9._~-]{1,8192}$/.test(auth)) fail('login_required', 401);
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!key) fail('publication_not_configured');
  const client = createClient(endpoint(), key!, { auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false }, global: { fetch: (input, init) => fetch(input, { ...init, redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(10000) }) } });
  let response;
  try { response = await client.auth.getUser(auth.slice(7)); } catch { return fail('login_required', 401); }
  if (response.error || !uuid(response.data?.user?.id)) fail('login_required', 401);
  const grant = accessConfig().find(g => g.user_id === response.data.user!.id);
  if (!grant || !grant.snapshots.length) fail('project_access_denied', 403);
  return grant.snapshots;
}

async function boundedJSON(response: Response) {
  if (!response.ok || !response.body) fail('publication_unavailable');
  const reader = response.body!.getReader(); const chunks: Buffer[] = []; let size = 0;
  try {
    for (;;) { const { done, value } = await reader.read(); if (done) break; size += value.length; if (size > 6500000) fail('publication_unavailable'); chunks.push(Buffer.from(value)); }
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(Buffer.concat(chunks))); } catch { return fail('publication_unavailable'); }
}

export async function readSnapshot(snapshot: Snapshot, format: Format): Promise<Buffer> {
  const owner = process.env.CROWD_MACHINE_OWNER_KEY;
  if (!hex(owner)) fail('publication_not_configured');
  let value;
  try {
    const response = await fetch(endpoint() + '/functions/v1/crowd-machine', { method: 'POST', redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(15000), headers: { 'Content-Type': 'application/json', apikey: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, 'X-Crowd-Owner-Key': owner! }, body: JSON.stringify({ action: 'publication_get', payload: { report_hash: snapshot.report_hash, format } }) });
    value = await boundedJSON(response);
  } catch { return fail('publication_unavailable'); }
  if (!exact(value, ['ok', 'result']) || value.ok !== true) fail('publication_unavailable');
  const r = value.result;
  if (!exact(r, ['schema', 'owner_scope', 'report_hash', 'project_id', 'as_of', 'tool_version', 'item_count', 'format', 'mime', 'bytes', 'sha256', 'body_utf8', 'media_bytes_included']) || r.schema !== 'crowd-publication-read-v1' || r.owner_scope !== 'crowd-owner-main' || r.report_hash !== snapshot.report_hash || r.project_id !== snapshot.project_id || r.format !== format || r.mime !== formats[format] || r.media_bytes_included !== false || typeof r.body_utf8 !== 'string' || !Number.isSafeInteger(r.item_count) || r.item_count < 1 || r.item_count > 2000 || typeof r.as_of !== 'string' || r.as_of.length > 64 || typeof r.tool_version !== 'string' || r.tool_version.length > 32) fail('publication_mismatch');
  const bytes = Buffer.from(r.body_utf8, 'utf8'), pin = snapshot.formats[format];
  if (bytes.length !== pin.bytes || bytes.length !== r.bytes || bytes.length > 1000000 || r.sha256 !== pin.sha256 || hash(bytes) !== pin.sha256) fail('publication_mismatch');
  if (format === 'json') {
    let report;
    try { report = JSON.parse(r.body_utf8); } catch { return fail('publication_mismatch'); }
    if (!plain(report) || report.project_id !== snapshot.project_id || report.as_of !== r.as_of || report.tool_version !== r.tool_version || !Array.isArray(report.items) || report.items.length !== r.item_count) fail('publication_mismatch');
  }
  return bytes;
}
