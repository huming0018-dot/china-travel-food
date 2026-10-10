"""Shared Telegram routes. Queue acceptance is not a delivery receipt.

No credentials or response bodies are logged. The standalone watchdog needs
only a publishable/anon API key and a notification-scoped secret, never a DB key.
"""
import os
import time

import requests


def _json_post(url, body, headers=None, timeout=(3, 8)):
    try:
        r = requests.post(url, json=body, headers=headers, timeout=timeout,
                          allow_redirects=False)
        if r.status_code != 200:
            return {}
        data = r.json()
        return data if isinstance(data, dict) else {}
    except (requests.RequestException, ValueError):
        return {}


def send_telegram(title, message, *, main_app=False):
    """Return True only after Telegram acknowledgement; None if unconfigured.

    Bounded attempts: relay enqueue once, four receipt polls, proxy once,
    official once. Ambiguous timeouts can cause duplicates during failover.
    """
    text = f"{title}\n{message}"
    if not text.strip() or len(text) > 4000:
        return False
    url = (os.getenv("TELEGRAM_RELAY_URL") or
           os.getenv("NEXT_PUBLIC_SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.getenv("TELEGRAM_RELAY_API_KEY") or
           os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY") or "").strip()
    secret = (os.getenv("TELEGRAM_RELAY_SECRET") or "").strip()
    if main_app:
        # Existing application credentials stay in the application only.
        key = key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        secret = secret or os.getenv("CROWD_OPS_SECRET", "").strip()
    configured = False
    if url and key and secret:
        configured = True
        headers = {"apikey": key}
        # New publishable keys are not JWTs. Legacy anon/service JWTs need Bearer.
        if key.startswith("eyJ"):
            headers["Authorization"] = "Bearer " + key
        queued = _json_post(url + "/rest/v1/rpc/telegram_notify_enqueue",
                            {"p_text": text, "p_secret": secret}, headers)
        request_id = queued.get("request_id")
        if queued.get("ok") is True and type(request_id) is int:
            for attempt in range(4):
                receipt = _json_post(url + "/rest/v1/rpc/telegram_notify_receipt",
                                     {"p_request_id": request_id,
                                      "p_secret": secret}, headers, (3, 5))
                if receipt.get("delivered") is True:
                    print("TG route=relay delivered=true")
                    return True
                if receipt.get("pending") is not True:
                    break
                if attempt < 3:
                    time.sleep(1)
        print("TG route=relay delivered=false")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if token and chat:
        configured = True
        body = {"chat_id": chat, "text": text, "disable_web_page_preview": True}
        proxy = os.getenv("TELEGRAM_API_BASE", "").strip().rstrip("/")
        bases = list(dict.fromkeys(b for b in (proxy, "https://api.telegram.org") if b))
        for base in bases:
            result = _json_post(f"{base}/bot{token}/sendMessage", body)
            delivered = result.get("ok") is True
            route = "official" if base == "https://api.telegram.org" else "proxy"
            print(f"TG route={route} delivered={str(delivered).lower()}")
            if delivered:
                return True
    return False if configured else None
