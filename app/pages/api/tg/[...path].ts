import type { NextApiRequest, NextApiResponse } from 'next';

/**
 * Telegram Bot API 反向代理（Vercel Serverless，供国内腾讯云容器 / 看门狗访问）。
 *
 * 背景：容器直连 https://api.telegram.org 被墙；旧 Deno Deploy 免费反代 503
 * USAGE_EXCEEDED 停用。本函数随 PWA 部署在 *.vercel.app（国内可达、Vercel 海外
 * 出口可访问 Telegram），替代 Deno 反代。
 *
 * 安全模型（与旧 Deno 反代一致）：
 * - 仅放行 /api/tg/bot<token>/<method>，严格正则校验，其余路径一律 403；
 * - 不内嵌/不存储 bot token：调用方（容器）在路径里自带 token，没有 token 的人
 * - 无法利用本代理；只透传 content-type，方法仅允许 GET/POST。
 * 容器把 TELEGRAM_API_BASE 设为 https://<本应用域名>/api/tg 即可。
 */
export const config = { api: { bodyParser: false } };

const PATH_RE = /^\/api\/tg\/(bot\d+:[\w-]+)\/([A-Za-z_]+)(\?.*)?$/;
const TELEGRAM = 'https://api.telegram.org';

function readRaw(req: NextApiRequest): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', (chunk: Buffer | string) => {
      data += typeof chunk === 'string' ? chunk : chunk.toString('utf8');
    });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  const m = (req.url || '').match(PATH_RE);
  if (!m || (req.method !== 'GET' && req.method !== 'POST')) {
    res.statusCode = 403;
    return res.end('tg proxy: only /api/tg/bot<token>/<method> is allowed');
  }
  const target = `${TELEGRAM}/${m[1]}/${m[2]}${m[3] || ''}`;

  const headers: Record<string, string> = {};
  const ct = req.headers['content-type'];
  if (ct) headers['content-type'] = Array.isArray(ct) ? ct[0] : ct;

  const init: RequestInit = { method: req.method, headers };
  if (req.method === 'POST') init.body = await readRaw(req);

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch (e) {
    res.statusCode = 502;
    return res.end('upstream error: ' + (e as Error).message);
  }
  const text = await upstream.text();
  res.statusCode = upstream.status;
  res.setHeader('content-type', upstream.headers.get('content-type') || 'application/json');
  res.end(text);
}
