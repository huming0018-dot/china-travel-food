import type { NextApiRequest, NextApiResponse } from 'next';
import { adminClient, cors, failure, hash, inviteRPC, platforms, releases } from '@/lib/crowd-server';
import { accessRequest, privateBackendConfigured } from '@/lib/crowd-access';
export const config = { api: { bodyParser: { sizeLimit: '2kb' } } };

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  try {
    cors(req, res); if (req.method === 'OPTIONS') return res.status(204).end();
    if (req.method !== 'POST') return res.status(405).end();
    if (!privateBackendConfigured()) return res.json(await accessRequest('enroll', req.body || {}));
    const { invite, install_secret, consent, platform } = req.body || {};
    if (typeof invite !== 'string' || typeof install_secret !== 'string' || !/^[a-f0-9]{64}$/.test(invite) || !/^[a-f0-9]{64}$/.test(install_secret) || !platforms.includes(platform)) throw new Error('invalid_request');
    if (consent !== 'crowd-public-v4') throw new Error('consent_required');
    if (!releases()[platform as typeof platforms[number]]) throw new Error('release_not_ready');
    const client = adminClient(), payload = { token_hash: hash(invite), device_hash: hash(install_secret), platform };
    const allocation = await inviteRPC(client, 'reserve', payload);
    const email = hash(install_secret) + '@crowd.invalid';
    // A stable reserved UUID makes interrupted Auth creation retryable; never reset a password.
    let existing = await client.auth.admin.getUserById(allocation.user_id);
    if (!existing.data.user) {
      await client.auth.admin.createUser({ id: allocation.user_id, email, password: 'Cr4!' + install_secret, email_confirm: true,
        user_metadata: { username: 'crowd-' + allocation.user_id }, app_metadata: { crowd_installation: true } });
      existing = await client.auth.admin.getUserById(allocation.user_id);
    }
    if (!existing.data.user || existing.data.user.email !== email) throw new Error('backend_unavailable');
    await inviteRPC(client, 'complete', { ...payload, consent });
    // Tokens are obtained directly from Supabase by the client and never returned to the portal.
    return res.json({ email, joined: true });
  } catch (error) { return failure(res, error); }
}
