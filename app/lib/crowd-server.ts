import { createClient } from '@supabase/supabase-js';
import { createHash, randomBytes, timingSafeEqual } from 'crypto';
import type { NextApiRequest, NextApiResponse } from 'next';
import { gatewayClient } from './crowd-gateway';

export const platforms = ['android', 'ios', 'harmony', 'windows', 'macos'] as const;
export type Platform = typeof platforms[number];
export type Release = { channel: string; url: string; extension_id?: string; sha256?: string; version: string; verified: boolean };
export const hash = (value: string) => createHash('sha256').update(value).digest('hex');
export function origin() {
  const u = new URL(process.env.CROWD_PUBLIC_ORIGIN || 'https://app-lyart-eta-22.vercel.app');
  if (u.protocol !== 'https:' || u.username || u.password || u.pathname !== '/' || u.search || u.hash) throw new Error('portal_not_configured');
  return u.origin;
}
export function releases(): Partial<Record<Platform, Release>> {
  const source = JSON.parse(process.env.CROWD_RELEASES_JSON || '{}');
  const output: Partial<Record<Platform, Release>> = {};
  for (const platform of platforms) {
    const r = source[platform]; if (!r || r.verified !== true || !/^4\.\d+\.\d+$/.test(r.version)) continue;
    const u = new URL(r.url); if (u.protocol !== 'https:' || u.username || u.password) continue;
    if (['desktop','apk'].includes(r.channel) && (u.search || u.hash)) continue;
    const desktop = ['windows', 'macos'].includes(platform), extension = desktop && r.channel === 'extension';
    if (extension && (!/^[a-p]{32}$/.test(r.extension_id || '') || !['chromewebstore.google.com', 'microsoftedge.microsoft.com'].includes(u.hostname))) continue;
    if (desktop && !extension && (r.channel !== 'desktop' || u.origin !== origin() || !u.pathname.startsWith('/crowd/releases/') || !/^[a-f0-9]{64}$/.test(r.sha256 || ''))) continue;
    if (platform === 'ios' && !((r.channel === 'testflight' && u.hostname === 'testflight.apple.com') || (r.channel === 'appstore' && u.hostname === 'apps.apple.com'))) continue;
    if (platform === 'android' && (r.channel !== 'apk' || u.origin !== origin() || u.pathname !== '/crowd/releases/crowd-android-v' + r.version + '-debug.apk' || !/^[a-f0-9]{64}$/.test(r.sha256 || ''))) continue;
    if (platform === 'harmony' && !(r.channel === 'appgallery' && u.hostname === 'appgallery.huawei.com')) continue;
    output[platform] = { channel: r.channel, url: u.href, version: r.version, verified: true,
      ...(extension ? { extension_id: r.extension_id } : {}), ...(r.sha256 ? { sha256: r.sha256 } : {}) };
  }
  return output;
}
export function adminClient(): ReturnType<typeof gatewayClient> {
  if (process.env.CROWD_GATEWAY_TOKEN) return gatewayClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!, process.env.CROWD_GATEWAY_TOKEN);
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!key) throw new Error('backend_not_configured');
  const client = createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, key, { auth: { persistSession: false, autoRefreshToken: false } });
  return { rpc: async (name, args) => await client.rpc(name, args), auth: { admin: {
    getUserById: async id => await client.auth.admin.getUserById(id),
    createUser: async user => await client.auth.admin.createUser(user)
  } } };
}
export async function inviteRPC(client: ReturnType<typeof adminClient>, action: string, payload: Record<string, unknown>) {
  const { data, error } = await client.rpc('crowd_v4_invite', { p_action: action, p_payload: payload });
  if (error) {
    const known = ['invalid_invite', 'invite_expired', 'invite_full', 'installation_already_joined', 'consent_required'];
    throw new Error(known.find(code => error.message === code) || 'backend_unavailable');
  }
  return data;
}
export function operator(req: NextApiRequest) {
  const expected = process.env.CROWD_OPERATOR_KEY || '', supplied = (req.headers.authorization || '').replace(/^Bearer /, '');
  if (expected.length < 32 || Buffer.byteLength(supplied) !== Buffer.byteLength(expected) || !timingSafeEqual(Buffer.from(expected), Buffer.from(supplied))) throw new Error('operator_required');
}
export function headers(res: NextApiResponse) { res.setHeader('Cache-Control', 'no-store'); res.setHeader('Referrer-Policy', 'no-referrer'); res.setHeader('X-Content-Type-Options', 'nosniff'); }
export function cors(req: NextApiRequest, res: NextApiResponse) {
  headers(res);
  const from = req.headers.origin;
  const allowed = [origin(), 'https://crowd.local', 'null', ...Object.values(releases()).filter(r => r?.extension_id).map(r => 'chrome-extension://' + r!.extension_id)];
  if (from && !allowed.includes(from)) throw new Error('origin_denied');
  if (from) { res.setHeader('Access-Control-Allow-Origin', from); res.setHeader('Vary', 'Origin'); }
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS'); res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}
export function failure(res: NextApiResponse, error: unknown) {
  const message = error instanceof Error ? error.message : 'backend_unavailable';
  const safe = ['invalid_invite', 'invite_expired', 'invite_full', 'installation_already_joined', 'consent_required', 'operator_required', 'origin_denied', 'invalid_request', 'release_not_ready'];
  res.status(message === 'operator_required' || message === 'origin_denied' ? 403 : safe.includes(message) ? 400 : 503).json({ error: safe.includes(message) ? message : 'backend_unavailable' });
}
export const token = () => randomBytes(32).toString('hex');
