#!/usr/bin/env python3
"""Standalone Telegram sender. Private notify.env; failed alerts persist locally."""
import json
import os
import pathlib
import tempfile
try:
    from .telegram_delivery import send_telegram
except ImportError:
    from telegram_delivery import send_telegram
HERE = pathlib.Path(__file__).resolve().parent
OUTBOX = HERE / 'notify_pending.json'


def load_env():
    f = HERE / 'notify.env'
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            k, sep, v = line.partition('=')
            if sep and k.strip() not in os.environ:
                os.environ[k.strip()] = v.strip().strip('\"\'')


def _telegram(title, message):
    return bool(send_telegram(title, message))


def _pending():
    if not OUTBOX.exists():
        return []
    # A corrupt queue is an error, not permission to discard queued alerts.
    pending = json.loads(OUTBOX.read_text())
    if not isinstance(pending, list):
        raise ValueError('invalid notification outbox')
    return pending


def _save(pending):
    fd, path = tempfile.mkstemp(dir=HERE, prefix='.notify-')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(pending, f, ensure_ascii=False)
        os.replace(path, OUTBOX)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def flush_pending():
    """At most one queued alert per cron run; share cron's flock."""
    load_env()
    pending = _pending()
    if pending and _telegram(*pending[0]):
        _save(pending[1:])


def send(title, message):
    load_env()
    t = _telegram(title, message)
    pending = _pending()
    item = [title, message]
    if t:
        pending = [p for p in pending if p != item]
    elif item not in pending:
        pending.append(item)
    _save(pending)
    print(f'notify tg={t} queued={len(pending)}')
    return t


if __name__ == '__main__':
    # Execute under cron's flock when self-testing on a server.
    send('上海美食图鉴·看门狗自检', '通知通道测试：收到说明外部入站看门狗推送正常。无需操作。')
