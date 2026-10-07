import type { NextApiRequest, NextApiResponse } from 'next';
import { accessRequest } from '@/lib/crowd-access';
import { failure, headers } from '@/lib/crowd-server';

export const config = { api: { bodyParser: { sizeLimit: '2kb' } } };
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  headers(res); if (req.method !== 'POST') return res.status(405).end();
  try {
    const { action = 'list', after_id = 0 } = req.body || {};
    if (!['list','export'].includes(action) || !Number.isSafeInteger(after_id) || after_id < 0) throw new Error('invalid_request');
    const payload = action === 'list' ? { kind: 'proofs' } : { after_id };
    return res.json(await accessRequest('operations', { action, payload }, req.headers.authorization));
  } catch (error) { return failure(res, error); }
}
