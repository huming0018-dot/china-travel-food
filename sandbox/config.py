#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""config.py — 统一配置，所有开关和密钥从环境变量读。"""
import os
from pathlib import Path

DATA = Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
# 本地测试兼容：如果/app/data不存在，用临时目录
if not DATA.exists() and str(DATA).startswith("/app"):
    import tempfile
    DATA = Path(tempfile.mkdtemp(prefix="food_test_"))
    DATA.mkdir(parents=True, exist_ok=True)

# ── 数据库 ──
SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# ── 高德 ──
AMAP_KEYS = [k for k in os.environ.get("AMAP_KEYS", "").split(",") if k]
AMAP_SKS = [k for k in os.environ.get("AMAP_SKS", "").split(",") if k]

# ── 腾讯地图 ──
TENCENT_MAP_KEY = os.environ.get("TENCENT_MAP_KEY", "")

# ── Telegram ──
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
TG_API_BASE = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org")

# ── Apify ──
APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
APIFY_DISABLED = os.environ.get("APIFY_DISABLED", "1") == "1"
APIFY_MONTHLY_BUDGET = float(os.environ.get("APIFY_MONTHLY_BUDGET", "0.5"))

# ── 开关 ──
BATCH = int(os.environ.get("BATCH", "15"))
TZ = os.environ.get("TZ", "Asia/Shanghai")

# ── 路径 ──
SECRETS = DATA / ".secrets"
SECRETS.mkdir(parents=True, exist_ok=True)


def load_secret(name: str) -> str:
    """从环境变量或文件加载密钥。"""
    v = os.environ.get(name, "").strip()
    if v:
        return v
    fp = SECRETS / name.lower()
    if fp.exists():
        return fp.read_text().strip()
    return ""
