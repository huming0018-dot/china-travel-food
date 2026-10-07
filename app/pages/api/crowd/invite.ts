import type { NextApiRequest, NextApiResponse } from 'next';
import { adminClient, failure, hash, headers, inviteRPC, operator, origin, releases, token } from '@/lib/crowd-server';
import { accessRequest, privateBackendConfigured } from '@/lib/crowd-access';
const QRCode = require('qrcode');
export const config = { api: { bodyParser: { sizeLimit: '2kb' } } };
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  headers(res); if (req.method !== 'POST') return res.status(405).end();
  try {
    if (!privateBackendConfigured()) {
      const result = await accessRequest('invite', req.body || {}, req.headers.authorization);
      if (result.link) result.qr = await QRCode.toDataURL(result.link, { width: 320, margin: 2, errorCorrectionLevel: 'M' });
      return res.json(result);
    }
    operator(req); const available = releases(); if (!Object.keys(available).length) throw new Error('release_not_ready');
    const { action = 'create', max_people = 100, quota_day = 20, days = 7, invite } = req.body || {};
    const client = adminClient();
    if (action === 'revoke') {
      if (typeof invite !== 'string' || !/^[a-f0-9]{64}$/.test(invite)) throw new Error('invalid_invite');
      return res.json(await inviteRPC(client, 'revoke', { token_hash: hash(invite) }));
    }
    if (action !== 'create' || !Number.isInteger(max_people) || max_people < 1 || max_people > 500 || !Number.isInteger(quota_day) || quota_day < 1 || quota_day > 60 || !Number.isInteger(days) || days < 1 || days > 90) throw new Error('invalid_request');
    const value = token(), link = origin() + '/crowd#invite=' + value, expires_at = new Date(Date.now() + days * 86400000).toISOString();
    const qr = await QRCode.toDataURL(link, { width: 320, margin: 2, errorCorrectionLevel: 'M' });
    await inviteRPC(client, 'create', { token_hash: hash(value), max_people, quota_day, expires_at });
    return res.json({ link, qr, expires_at, max_people, quota_day });
  } catch (error) { return failure(res, error); }
}
