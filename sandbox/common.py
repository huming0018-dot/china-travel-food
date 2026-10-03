#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""common.py — 公共工具：DB、HTTP、日志、重试。"""
import json
import time
import logging
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import config

# ── 日志 ──
from logging.handlers import RotatingFileHandler

LOG_DIR = config.DATA / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),  # 控制台
        RotatingFileHandler(
            LOG_DIR / "app.log",
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("food")

# 错误日志单独沉淀到 error.log
error_handler = RotatingFileHandler(
    LOG_DIR / "error.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=10,
    encoding="utf-8",
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
log.addHandler(error_handler)


# ── HTTP ──
def http_get(url: str, params: dict = None, timeout: int = 15) -> dict:
    """安全GET请求，带超时和重试。"""
    if not url or not isinstance(url, str):
        log.error(f"HTTP无效URL: {url}")
        return {}
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": "FoodAtlas/1.0"})
            with urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            if attempt == 2:
                log.error(f"HTTP失败 {url[:60]}: {e}")
                return {}
            time.sleep(2 ** attempt)


def http_post(url: str, data: dict, timeout: int = 15) -> dict:
    """安全POST请求。"""
    if not url or not isinstance(url, str):
        log.error(f"POST无效URL: {url}")
        return {}
    try:
        body = json.dumps(data).encode("utf-8")
        req = Request(url, data=body, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        log.error(f"POST失败 {url[:60]}: {e}")
        return {}


# ── 数据库（Supabase REST）──
def db_get(table: str, query: str = "", limit: int = 100) -> list:
    """从Supabase读数据。"""
    if not table or not isinstance(table, str):
        log.error(f"DB读失败：无效表名={table}")
        return []
    if not config.SUPABASE_URL:
        log.error("DB未配置SUPABASE_URL")
        return []
    url = f"{config.SUPABASE_URL}/rest/v1/{table}?select=*&limit={limit}"
    if query:
        url += f"&{query}"
    req = Request(url, headers={
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
    })
    try:
        with urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        log.error(f"DB读失败 {table}: {e}")
        return []


def db_patch(table: str, rid: str, data: dict) -> bool:
    """写库。"""
    if not table or not isinstance(table, str):
        log.error(f"DB写失败：无效表名={table}")
        return False
    if not rid:
        log.error(f"DB写失败：无效id={rid}")
        return False
    if not data or not isinstance(data, dict):
        log.error(f"DB写失败：无效data={type(data)}")
        return False
    if not config.SUPABASE_URL:
        log.error("DB未配置SUPABASE_URL")
        return False
    url = f"{config.SUPABASE_URL}/rest/v1/{table}?id=eq.{rid}"
    body = json.dumps(data).encode("utf-8")
    req = Request(url, data=body, headers={
        "apikey": config.SUPABASE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }, method="PATCH")
    try:
        with urlopen(req, timeout=10) as r:
            return r.status < 300
    except Exception as e:
        log.error(f"DB写失败 {table}/{rid}: {e}")
        return False


# ── 文件 ──
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
