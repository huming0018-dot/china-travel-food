import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import vm from 'node:vm';
import { handle, digest } from '../../cloud/supabase/functions/crowd-gateway/core.mjs';
const require = createRequire(import.meta.url);
const token = '1'.repeat(64), expected = await digest(token), secret = '2'.repeat(64), device = await digest(secret);
const id = '00000000-0000-4000-8000-000000000001', reservation = { token_hash: '3'.repeat(64), device_hash: device, platform: 'android' };
let calls = [], account = null, expired = false, created = 0;
const backend = {
  rpc: async (name, args) => { calls.push({ name, args }); return expired ? { data: null, error: { message: 'invite_expired' } } : { data: args.p_action === 'reserve' ? { user_id: id } : [], error: null }; },
  auth: { admin: {
    getUserById: async () => ({ data: { user: account }, error: null }),
    createUser: async user => {
      // Existing production handle_new_user trigger inserts this into varchar(50).
      if ((user.user_metadata?.username ?? user.email).length > 50) return {data: {user: null}, error: {message: 'value too long for type character varying(50)'}};
      ++created; account = { ...user }; return { data: { user: account }, error: null };
    }
  } }
};
async function request(input, headers = {}, body) {
  return handle(new Request('https://test.supabase.co/functions/v1/crowd-gateway', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Crowd-Gateway-Key': token, ...headers }, body: body || JSON.stringify(input) }), backend, expected);
}
assert.equal((await request({ action: 'health' }, { 'X-Crowd-Gateway-Key': '0'.repeat(64) })).status, 403);
assert.equal((await request({ action: 'health' }, { Origin: 'https://test.example' })).status, 403);
assert.equal(calls.length, 0, 'unauthorized requests must not reach privileged backend');
assert.equal((await request({}, {}, ' '.repeat(4097))).status, 400);
assert.equal((await request({ action: 'rpc', name: 'crowd_v4_admin', args: { p_action: 'anything', p_payload: {} } })).status, 400);
assert.equal(calls.length, 0, 'gateway cannot execute arbitrary admin RPC');
assert.equal((await (await request({ action: 'health' })).json()).data.ready, true);
const alien = '00000000-0000-4000-8000-000000000002';
assert.equal((await request({ action: 'auth_create', id: alien, reservation, password: 'Cr4!' + secret })).status, 400);
assert.equal(created, 0, 'only the invitation-reserved account can be created');
expired = true;
assert.equal((await (await request({ action: 'auth_read', id, reservation })).json()).error.message, 'invite_expired');
expired = false;
assert.equal((await request({ action: 'auth_create', id, reservation, password: 'Cr4!' + '0'.repeat(64) })).status, 400);
assert.equal(created, 0, 'password must match hashed installation identity');
const joined = await (await request({ action: 'auth_create', id, reservation, password: 'Cr4!' + secret })).json();
assert.equal(joined.data.user.email, device + '@crowd.invalid');
assert.equal((await request({ action: 'auth_create', id, reservation, password: 'Cr4!' + secret })).status, 409);
assert.equal(created, 1, 'retries cannot reset an existing password');
assert.equal(JSON.stringify(joined).includes(secret), false);
assert.equal(JSON.stringify(joined).includes('app_metadata'), false);
account.email = 'unrelated@example.test';
const hidden = await (await request({ action: 'auth_read', id, reservation })).json();
assert.equal(hidden.data, null); assert.equal(JSON.stringify(hidden).includes(account.email), false);

// Execute the actual Next server adapter against the gateway handler, including
// Auth interruption/retry and server-only headers; no live users are created.
account = null;
const ts = require('../../app/node_modules/typescript'), module = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(new URL('../../app/lib/crowd-gateway.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText, {
  module, exports: module.exports, URL, AbortSignal, fetch: async (url, init) => handle(new Request(url, init), backend, expected)
});
const client = module.exports.gatewayClient('https://test.supabase.co', 'eyJ.TEST_PUBLIC', token);
assert.ok((await client.auth.admin.getUserById(id)).error, 'adapter cannot read Auth before reservation');
await client.rpc('crowd_v4_invite', { p_action: 'reserve', p_payload: reservation });
assert.equal((await client.auth.admin.getUserById(id)).data.user, null);
assert.equal((await client.auth.admin.createUser({ id, password: 'Cr4!' + secret })).data.user.id, id);
assert.equal((await client.auth.admin.getUserById(id)).data.user.email, device + '@crowd.invalid');
assert.ok((await client.rpc('arbitrary_rpc', { p_action: 'list', p_payload: {} })).error);
assert.throws(() => module.exports.gatewayClient('https://evil.example', 'eyJ.TEST_PUBLIC', token));
const modern = module.exports.gatewayClient('https://test.supabase.co', 'sb_publishable_TEST_PUBLIC', token);
assert.equal((await modern.rpc('crowd_v4_invite', { p_action: 'list', p_payload: {} })).error, null);
assert.throws(() => module.exports.gatewayClient('https://test.supabase.co', 'sb_secret_TEST_SERVER', token));
console.log('PASS gateway: privileged access denied without server key, bounded body, RPC allowlist, reserved Auth identity, password binding, expired invites, account isolation, retry without password reset, actual server adapter');
