import type { NextApiRequest, NextApiResponse } from 'next';
import { authorizedSnapshots, readSnapshot, formats, Format, PublicationError } from '../../lib/publication-server';

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  res.setHeader('Cache-Control', 'private, no-store'); res.setHeader('Vary', 'Authorization, Cookie');
  res.setHeader('Referrer-Policy', 'no-referrer'); res.setHeader('X-Content-Type-Options', 'nosniff');
  if (req.method !== 'GET') { res.setHeader('Allow', 'GET'); return res.status(405).end(); }
  try {
    const query = req.query || {};
    if (Object.keys(query).some(k => !['snapshot', 'format', 'download'].includes(k)) || Object.values(query).some(v => typeof v !== 'string') || query.download !== undefined && query.download !== '1') throw new PublicationError('invalid_publication_request', 400);
    const snapshots = await authorizedSnapshots(req);
    if (!query.snapshot) {
      if (Object.keys(query).length) throw new PublicationError('invalid_publication_request', 400);
      return res.json({ read_only: true, snapshots: snapshots.map(s => ({ slug: s.slug, title: s.title, project_id: s.project_id, report_hash: s.report_hash })) });
    }
    const snapshot = snapshots.find(s => s.slug === query.snapshot);
    if (!snapshot) throw new PublicationError('project_access_denied', 403);
    const format = typeof query.format === 'string' ? query.format : 'json';
    if (!Object.hasOwn(formats, format)) throw new PublicationError('invalid_publication_request', 400);
    const bytes = await readSnapshot(snapshot, format as Format);
    res.setHeader('Content-Type', formats[format as Format]); res.setHeader('Content-Length', bytes.length);
    res.setHeader('X-Content-SHA256', snapshot.formats[format as Format].sha256); res.setHeader('X-CTFS-Report-Hash', snapshot.report_hash);
    if (query.download === '1' || format === 'html') res.setHeader('Content-Disposition', `attachment; filename="ctfs-${snapshot.slug}.${format}"`);
    if (format === 'html') res.setHeader('Content-Security-Policy', "sandbox; default-src 'none'; frame-ancestors 'none'");
    return res.status(200).send(bytes);
  } catch (error) {
    const known = error instanceof PublicationError ? error : new PublicationError('publication_unavailable', 503);
    return res.status(known.status).json({ error: known.code });
  }
}
