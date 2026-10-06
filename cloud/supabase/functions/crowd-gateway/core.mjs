// Server-to-server access only. No service key or Auth token leaves this gateway.
export async function digest(value) {
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)))].map(x => x.toString(16).padStart(2, '0')).join('');
}
const hex = x => typeof x === 'string' && /^[a-f0-9]{64}$/.test(x);
const uuid = x => typeof x === 'string' && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(x);
const reply = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' } });
const fail = message => ({ data: null, error: { message } });
const known = ['invalid_invite', 'invite_expired', 'invite_full', 'installation_already_joined', 'consent_required'];
const safeError = error => error ? { message: known.includes(error.message) ? error.message : 'backend_unavailable' } : null;

async function body(request) {
  if (request.headers.get('Content-Type')?.split(';')[0] !== 'application/json') throw new Error('invalid_request');
  const reader = request.body?.getReader(); if (!reader) throw new Error('invalid_request');
  const chunks = []; let size = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read(); if (done) break;
      size += value.length; if (size > 4096) throw new Error('invalid_request'); chunks.push(value);
    }
  } finally { await reader.cancel(); reader.releaseLock(); }
  const all = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { all.set(chunk, offset); offset += chunk.length; }
  const parsed = JSON.parse(new TextDecoder().decode(all));
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('invalid_request');
  return parsed;
}

export async function handle(request, backend, expectedHash) {
  if (request.method !== 'POST') return reply(fail('method_not_allowed'), 405);
  // Browser callers never receive CORS permission; the bearer below is server-only.
  if (request.headers.has('Origin')) return reply(fail('server_only'), 403);
  const key = request.headers.get('X-Crowd-Gateway-Key') || '';
  if (!hex(expectedHash) || !hex(key) || await digest(key) !== expectedHash) return reply(fail('gateway_required'), 403);
  try {
    const input = await body(request);
    if (input.action === 'health') {
      const result = await backend.rpc('crowd_v4_invite', { p_action: 'list', p_payload: {} });
      return result.error ? reply(fail('backend_unavailable'), 503) : reply({ data: { ready: true }, error: null });
    }
    if (input.action === 'rpc') {
      const args = input.args;
      if (input.name !== 'crowd_v4_invite' || !args || typeof args !== 'object' || Array.isArray(args) || !['list','create','revoke','check','reserve','complete'].includes(args.p_action) || !args.p_payload || typeof args.p_payload !== 'object' || Array.isArray(args.p_payload)) return reply(fail('invalid_request'), 400);
      const result = await backend.rpc(input.name, { p_action: args.p_action, p_payload: args.p_payload });
      return reply({ data: result.data, error: safeError(result.error) });
    }
    if (!['auth_read','auth_create'].includes(input.action)) return reply(fail('invalid_request'), 400);
    const reservation = input.reservation;
    if (!uuid(input.id) || !reservation || !hex(reservation.token_hash) || !hex(reservation.device_hash) || !['android','ios','harmony','windows','macos'].includes(reservation.platform)) return reply(fail('invalid_request'), 400);
    // Recheck the invitation and reserved UUID before every Auth operation. A
    // gateway key cannot read unrelated accounts or choose their account IDs.
    const allocation = await backend.rpc('crowd_v4_invite', { p_action: 'reserve', p_payload: { token_hash: reservation.token_hash, device_hash: reservation.device_hash, platform: reservation.platform } });
    if (allocation.error) return reply({ data: null, error: safeError(allocation.error) });
    if (allocation.data?.user_id !== input.id) return reply(fail('invalid_request'), 400);
    const email = reservation.device_hash + '@crowd.invalid';
    if (input.action === 'auth_create') {
      if (typeof input.password !== 'string' || !/^Cr4![a-f0-9]{64}$/.test(input.password) || await digest(input.password.slice(4)) !== reservation.device_hash) return reply(fail('invalid_request'), 400);
      const prior = await backend.auth.admin.getUserById(input.id);
      if (prior.data?.user) return reply(fail('account_exists'), 409); // Never reset an account password.
      const created = await backend.auth.admin.createUser({ id: input.id, email, password: input.password, email_confirm: true, app_metadata: { crowd_installation: true } });
      if (created.error) return reply(fail('backend_unavailable'));
    }
    const result = await backend.auth.admin.getUserById(input.id), user = result.data?.user;
    if (!user) return reply({ data: { user: null }, error: { message: 'account_not_ready' } });
    if (user.email !== email || user.app_metadata?.crowd_installation !== true) return reply(fail('installation_identity_mismatch'));
    return reply({ data: { user: { id: user.id, email: user.email } }, error: null });
  } catch { return reply(fail('invalid_request'), 400); }
}
