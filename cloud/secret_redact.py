#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""secret_redact.py — 日志/异常脱敏（F15）。

用途：任何可能落盘/打印的内容（URL、请求头、异常对象、账本、调试 JSON），
先经本工具递归脱敏，再 print / log，避免把以下信息写进日志：
  - Authorization / apikey / token / cookie / web_session / secret / sk / sig 等字段（含完整值）；
  - URL 查询串里的 key / sig / sk / signature / token / access_token / api_key 等；
  - 已知形态的秘密：Supabase JWT(eyJ...)、腾讯地图 key(XXXXX-XXXXX-...)、Telegram bot token；
  - 调用方传入的运行时已知秘密值（extra_secrets），整串抹掉，不残留任何可还原后缀。

设计原则：
  - 宁可多删不可漏删；命中即整段替换为 ***REDACTED***，不做“保留前几位”的部分掩码；
  - 递归处理 dict / list / tuple / set / str / Exception；不抛异常（脱敏本身不能再炸日志）；
  - 纯函数、无网络、无副作用，可在任意模块安全调用。
"""
import re

REDACTED = "***REDACTED***"

# 视为秘密的字典键（小写匹配）
SENSITIVE_KEYS = {
    "authorization", "apikey", "api_key", "x-api-key", "key", "sk", "secret",
    "token", "access_token", "refresh_token", "id_token", "client_secret",
    "cookie", "set-cookie", "web_session", "session", "signature", "sig",
    "password", "passwd", "service_role", "service_role_key",
}

# URL 查询串里视为秘密的参数名（小写匹配）
SENSITIVE_QUERY_PARAMS = {
    "key", "sk", "sig", "signature", "token", "access_token", "refresh_token",
    "api_key", "apikey", "web_session", "session", "secret", "client_secret",
}

# 已知秘密形态（按顺序套用）
_PATTERNS = [
    # Telegram bot token: 123456789:AAH...
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"),
    # JWT（Supabase anon/service_role 均为 eyJ 开头三段式）
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\b"),
    # 腾讯地图 key：5 段起、每段 5 位大写字母数字、连字符分隔
    re.compile(r"\b[A-Z0-9]{5}(?:-[A-Z0-9]{5}){5}\b"),
]

# Bearer / 授权方案前缀
_BEARER_RE = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._\-]+")
# URL 查询串敏感参数
_QUERY_RE = re.compile(
    r"(?i)([?&](?:key|sk|sig|signature|token|access_token|refresh_token|"
    r"api_key|apikey|web_session|session|secret|client_secret))=([^&\s\"'<>]*)"
)
# JSON / 字典字面量里的敏感字段："key": "value" 或 'key': 'value'
_JSON_RE = re.compile(
    r"(?i)([\"'](?:authorization|apikey|api_key|x-api-key|key|sk|secret|token|"
    r"access_token|refresh_token|id_token|client_secret|cookie|set-cookie|"
    r"web_session|signature|sig|password|service_role|service_role_key)[\"']\s*:\s*"
    r")([\"'])(.*?)(\2)"
)


def _is_sensitive_key(k):
    if not isinstance(k, str):
        return False
    return k.strip().lower() in SENSITIVE_KEYS


def redact_str(s, extra_secrets=None):
    """对字符串做全量脱敏。"""
    out = s
    # 1) JSON 字面量敏感字段
    out = _JSON_RE.sub(lambda m: m.group(1) + m.group(2) + REDACTED + m.group(2), out)
    # 2) URL 查询串敏感参数
    out = _QUERY_RE.sub(lambda m: m.group(1) + "=" + REDACTED, out)
    # 3) Bearer 前缀
    out = _BEARER_RE.sub(lambda m: m.group(1) + REDACTED, out)
    # 4) 已知秘密形态
    for pat in _PATTERNS:
        out = pat.sub(REDACTED, out)
    # 5) 运行时已知的具体秘密值（整串抹掉，包括任何后缀）
    for secret in extra_secrets or ():
        if secret and isinstance(secret, str) and len(secret) >= 6:
            out = out.replace(secret, REDACTED)
    return out


def redact_secrets(obj, extra_secrets=None):
    """递归脱敏 dict / list / tuple / set / str / Exception，原样返回其它类型。"""
    try:
        if isinstance(obj, BaseException):
            return redact_str(f"{type(obj).__name__}: {obj}", extra_secrets)
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if _is_sensitive_key(k):
                    out[k] = REDACTED
                else:
                    out[k] = redact_secrets(v, extra_secrets)
            return out
        if isinstance(obj, (list, tuple, set)):
            red = [redact_secrets(v, extra_secrets) for v in obj]
            if isinstance(obj, tuple):
                return tuple(red)
            if isinstance(obj, set):
                return set(red)
            return red
        if isinstance(obj, str):
            return redact_str(obj, extra_secrets)
    except Exception:
        # 脱敏失败时返回最保守占位，绝不让原始秘密漏出，也不影响主流程
        return REDACTED
    return obj


def safe_log(obj, extra_secrets=None):
    """便捷封装：返回脱敏后的字符串，可直接 print。"""
    return redact_secrets(obj, extra_secrets)
