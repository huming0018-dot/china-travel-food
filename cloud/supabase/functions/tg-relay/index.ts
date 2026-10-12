// Telegram Bot API relay.
// Supabase Edge is reachable from the China cloud host while api.telegram.org
// is blocked. Strict path gate: /functions/v1/tg-relay/bot<TOKEN>/<METHOD>
const UPSTREAM = "https://api.telegram.org";
const PATH_RE = /^\/(?:functions\/v1\/tg-relay|tg-relay)?(\/bot\d+:[\w-]+\/[A-Za-z_]+)\/?$/;

Deno.serve(async (req: Request) => {
  const url = new URL(req.url);
  const m = url.pathname.match(PATH_RE);
  if (!m) {
    return new Response(JSON.stringify({ ok: false, error: "forbidden" }), {
      status: 403, headers: { "content-type": "application/json" },
    });
  }
  if (req.method !== "GET" && req.method !== "POST") {
    return new Response(JSON.stringify({ ok: false, error: "method_not_allowed" }), {
      status: 405, headers: { "content-type": "application/json" },
    });
  }
  const target = UPSTREAM + m[1] + url.search;
  const headers = new Headers();
  const ct = req.headers.get("content-type");
  if (ct) headers.set("content-type", ct);
  const init: RequestInit = { method: req.method, headers };
  if (req.method === "POST") init.body = await req.text();
  try {
    const r = await fetch(target, init);
    const text = await r.text();
    return new Response(text, {
      status: r.status,
      headers: { "content-type": r.headers.get("content-type") || "application/json" },
    });
  } catch (e) {
    return new Response(JSON.stringify({ ok: false, error: "upstream", detail: String(e) }), {
      status: 502, headers: { "content-type": "application/json" },
    });
  }
});
