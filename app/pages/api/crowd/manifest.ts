import type { NextApiRequest, NextApiResponse } from 'next';
import { adminClient, failure, headers, origin, releases } from '@/lib/crowd-server';
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  headers(res); if (req.method !== 'GET') return res.status(405).end();
  try {
    const client = adminClient(); const { error } = await client.rpc('crowd_v4_invite', { p_action: 'list', p_payload: {} });
    if (error) throw new Error('backend_unavailable');
    return res.json({ origin: origin(), releases: releases(), ready: Object.keys(releases()).length > 0 });
  } catch (error) { return failure(res, error); }
}
