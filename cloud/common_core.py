#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""common_core.py — 新代码唯一底座（config / req / fetch_all / log / notify）。

为什么存在（#12，P1，三窗口收敛）：
  旧代码里 Supabase 密钥从 5 处读、HTTP 退避各写一份、告警被 13 处 import 无统一格式。
  自本模块起，**新写的采集 / 补齐 / 调度脚本一律 `import common_core as core`**，
  不再各自 load_env、自拼 requests、自调 health 告警。

提供：
  core.config(KEY, default=None)      统一读配置（环境变量 → cloud/env.sh → app/.env.local）
  core.req(method, path, **kw)        PostgREST 调用（service role，指数退避，429/5xx 重试）
  core.fetch_all(table, select, ...)  分页拉全表（单页上限 1000）
  core.log(level, msg, **fields)      结构化日志（stderr，含时间戳与模块）
  core.notify.info/warn/action/resolved(...)  分级通知（懒加载 notifier，双通道+冷却）
  core.DATA_DIR / core.SECRETS_DIR / core.TIERS / core.STATUS_*  统一常量

硬规则：
  - 密钥只从配置读取，绝不硬编码、不进日志/告警（log/notify 自动脱敏）。
  - 本模块只依赖 requests + 标准库；在无密钥的开发机上 import 不报错（调用 req 时才报错）。
"""
import datetime as _dt
import json as _json
import os as _os
import pathlib as _pl
import sys as _sys
import time as _time

import requests as _requests

# ---------------------------------------------------------------- 路径
# cloud/common_core.py → HERE=cloud/，REPO_ROOT=仓库根
HERE = _pl.Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
DATA_DIR = _os.environ.get("FOOD_DATA_DIR", "/app/data")
SECRETS_DIR = _os.environ.get("FOOD_SECRETS_DIR", "/secrets")

# 配置文件候选（存在才读）：cloud/env.sh（容器）、app/.env.local（Next）
_ENV_FILES = [
    HERE / "env.sh",
    REPO_ROOT / "app" / ".env.local",
]

# ---------------------------------------------------------------- 常量
STATUS_OPEN = "active"
STATUS_CLOSED = "closed"
VALID_STATUS = {STATUS_OPEN, STATUS_CLOSED}
DISTRICTS = {
    "黄浦区", "徐汇区", "静安区", "长宁区", "浦东新区", "闵行区", "杨浦区",
    "虹口区", "普陀区", "嘉定区", "宝山区", "松江区", "青浦区", "奉贤区",
    "金山区", "崇明区",
}

_SECRET_MARKERS = ("SUPABASE_SERVICE_ROLE_KEY", "SERVICE_ROLE", "TOKEN", "SECRET",
                   "PASSWORD", "web_session", "Bearer ", "sk-")


# ---------------------------------------------------------------- 配置
def _parse_env_file(path: _pl.Path) -> dict:
    """解析 KEY=VALUE / export KEY="VALUE"，忽略注释与非赋值行。"""
    out = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        return {}
    return out


_FILE_CACHE = None


def _file_config() -> dict:
    global _FILE_CACHE
    if _FILE_CACHE is None:
        merged = {}
        for f in _ENV_FILES:
            if f.exists():
                merged.update(_parse_env_file(f))
        _FILE_CACHE = merged
    return _FILE_CACHE


def config(key: str, default=None):
    """配置读取顺序：进程环境变量 → 配置文件（env.sh / .env.local）→ default。"""
    if key in _os.environ:
        return _os.environ[key]
    return _file_config().get(key, default)


def _supabase_base() -> str:
    url = config("NEXT_PUBLIC_SUPABASE_URL", "")
    return url.rstrip("/") + "/rest/v1"


def _api_key(use_service: bool = True) -> str:
    if use_service:
        k = config("SUPABASE_SERVICE_ROLE_KEY", "")
    else:
        k = config("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")
    return k or ""


# ---------------------------------------------------------------- 日志
def _redact(text: str) -> str:
    s = str(text)
    for marker in ("Bearer ", "sk-", "web_session=", "SUPABASE_SERVICE_ROLE_KEY"):
        if marker in s:
            s = s.replace(marker, marker[:3] + "***")
    return s


def log(level: str, msg: str, **fields):
    """结构化日志一行 JSON（stderr）。level: debug/info/warn/error。"""
    rec = {"ts": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "lvl": level.upper(), "mod": HERE.stem, "msg": _redact(msg)}
    for k, v in fields.items():
        rec[k] = _redact(v)
    print(_json.dumps(rec, ensure_ascii=False), file=_sys.stderr, flush=True)


# ---------------------------------------------------------------- HTTP
def headers(use_service: bool = True) -> dict:
    k = _api_key(use_service)
    if not k:
        raise RuntimeError(
            "缺少密钥：配置 SUPABASE_SERVICE_ROLE_KEY（或 cloud/env.sh、app/.env.local）")
    return {"apikey": k, "Authorization": f"Bearer {k}",
            "Content-Type": "application/json"}


def req(method: str, path: str, use_service: bool = True, retries: int = 6, **kw):
    """PostgREST 调用，429/5xx 指数退避重试。path 以 '/' 开头（如 '/restaurants?select=id'）。
    返回 requests.Response（调用方自行判状态）。"""
    url = _supabase_base() + path
    last = None
    for i in range(retries):
        try:
            r = _requests.request(method, url, headers=headers(use_service),
                                  timeout=kw.pop("timeout", 45), **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                last = r
                _time.sleep(min(2 ** i, 15))
                continue
            return r
        except _requests.RequestException as e:
            last = e
            _time.sleep(min(2 ** i, 15))
    raise RuntimeError(f"{method} {path} 连续失败: {last}")


def fetch_all(table: str, select: str = "*", page: int = 1000,
              use_service: bool = True, order_col: str = "id", extra: str = "") -> list:
    """分页拉全表（PostgREST 单页上限 1000）。"""
    out, off = [], 0
    while True:
        path = f"/{table}?select={select}&limit={page}&offset={off}&order={order_col}"
        if extra:
            path += "&" + extra
        r = req("GET", path, use_service=use_service)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        out.extend(rows)
        if len(rows) < page:
            break
        off += page
        _time.sleep(0.12)
    return out


# ---------------------------------------------------------------- 通知
class _Notify:
    """分级通知门面，懒加载 notifier（避免无通道环境的硬依赖）。"""

    @staticmethod
    def _send(level, body, action=None, key=None, **kw):
        try:
            import notifier as N  # 同目录
        except Exception:
            try:
                _sys.path.insert(0, str(HERE))
                import notifier as N
            except Exception:
                log("warn", f"notify 不可用（{level}）：{body[:60]}")
                return False
        try:
            return N.emit(level, body, action=action, dedup_key=key, **kw)
        except AttributeError:
            # 兼容旧 notifier：直接 format + deliver
            head, full = N.format(level, body, action=action)
            return N._deliver(head, full)
        except Exception as e:
            log("error", "notify 发送失败", err=repr(e)[:80])
            return False

    def info(self, body, key=None, **kw):
        return self._send("INFO", body, key=key, **kw)

    def warn(self, body, key=None, **kw):
        return self._send("WARN", body, key=key, **kw)

    def action(self, body, action=None, key=None, **kw):
        return self._send("ACTION", body, action=action, key=key, **kw)

    def resolved(self, body, key=None, **kw):
        return self._send("RESOLVED", body, key=key, **kw)


notify = _Notify()


# ---------------------------------------------------------------- 管线定位
def pipeline_dir() -> _pl.Path:
    """确定性文本工具 common.py 所在目录（cjk_norm / clean_phone / addr_core…）。"""
    candidates = [
        HERE / "vendor" / "pipeline",
        REPO_ROOT / "pipeline",
        _pl.Path("/app/pipeline"),
    ]
    for c in candidates:
        if (c / "common.py").exists():
            return c
    return candidates[0]


def pipeline_common():
    """导入并返回管线 common（确定性清洗工具集）。"""
    d = str(pipeline_dir())
    if d not in _sys.path:
        _sys.path.insert(0, d)
    import common as P
    return P


# ---------------------------------------------------------------- 自检
def selfcheck() -> dict:
    return {
        "repo_root": str(REPO_ROOT),
        "data_dir": DATA_DIR,
        "secrets_dir": SECRETS_DIR,
        "supabase_url_configured": bool(config("NEXT_PUBLIC_SUPABASE_URL")),
        "service_key_configured": bool(_api_key(True)),
        "pipeline_common": str(pipeline_dir()),
    }


if __name__ == "__main__":
    print(_json.dumps(selfcheck(), ensure_ascii=False, indent=1))
