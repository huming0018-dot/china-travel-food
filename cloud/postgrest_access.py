"""Existing raw PostgREST access mechanics, without project configuration.

Uses requests exceptions/response semantics; this is not a new Supabase SDK.
The caller supplies authentication, transport and pacing. No import-time I/O.
"""
import requests as _requests

def headers(k: str) -> dict:
    if not k:
        raise RuntimeError(
            "Missing API key")
    return {"apikey": k, "Authorization": f"Bearer {k}",
            "Content-Type": "application/json"}


def request(method: str, path: str, *, base_url: str, get_headers, send, sleep,
            retries: int = 6, **kw):
    """PostgREST 调用，429/5xx 指数退避重试。path 以 '/' 开头（如 '/restaurants?select=id'）。
    返回 requests.Response（调用方自行判状态）。"""
    url = base_url + path
    last = None
    for i in range(retries):
        try:
            r = send(method, url, headers=get_headers(),
                                  timeout=kw.pop("timeout", 45), **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                last = r
                sleep(min(2 ** i, 15))
                continue
            return r
        except _requests.RequestException as e:
            last = e
            sleep(min(2 ** i, 15))
    raise RuntimeError(f"{method} {path} 连续失败: {last}")


def fetch_all(table: str, select: str = "*", page: int = 1000,
              use_service: bool = True, order_col: str = "id", extra: str = "", *, request, sleep) -> list:
    """分页拉全表（PostgREST 单页上限 1000）。"""
    out, off = [], 0
    while True:
        path = f"/{table}?select={select}&limit={page}&offset={off}&order={order_col}"
        if extra:
            path += "&" + extra
        r = request("GET", path, use_service=use_service)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        out.extend(rows)
        if len(rows) < page:
            break
        off += page
        sleep(0.12)
    return out


