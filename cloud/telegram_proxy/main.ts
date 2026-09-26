// main.ts — Telegram Bot API 反向代理（部署在 Deno Deploy，供国内腾讯云服务器访问）
//
// 用法：把云端环境变量 TELEGRAM_API_BASE 设为 https://<project>.deno.dev
// 仅转发 /bot<token>/<method> 到 https://api.telegram.org，其余路径一律拒绝。
const TELEGRAM_API = "https://api.telegram.org";

export default {
  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);
    // Telegram Bot Token 形如 123456789:AAH...，路径 /bot<token>/<method>
    if (!/^\/bot\d+:[\w-]+\//.test(url.pathname)) {
      return new Response(
        "Telegram proxy: only /bot<token>/<method> is allowed",
        { status: 403 },
      );
    }
    const target = TELEGRAM_API + url.pathname + url.search;

    // 仅透传必要请求头，避免把平台内部头带到上游
    const fwdHeaders = new Headers();
    for (const [k, v] of req.headers) {
      if (["content-type", "user-agent", "accept"].includes(k.toLowerCase())) {
        fwdHeaders.set(k, v);
      }
    }
    const init: RequestInit = { method: req.method, headers: fwdHeaders };
    if (req.method !== "GET" && req.method !== "HEAD") {
      init.body = await req.text();
    }

    let upstream: Response;
    try {
      upstream = await fetch(target, init);
    } catch (e) {
      return new Response("upstream error: " + (e as Error).message, {
        status: 502,
      });
    }

    // Telegram 响应为小体积 JSON，直接以文本回传，避免压缩头不一致
    const text = await upstream.text();
    const headers = new Headers();
    headers.set(
      "content-type",
      upstream.headers.get("content-type") || "application/json",
    );
    return new Response(text, { status: upstream.status, headers });
  },
};
