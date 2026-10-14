#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""腾讯位置服务 WebService —— SK 签名鉴权助手。

为什么存在：WebService key 若用 IP 白名单，在 Clash/TUN 代理节点自动切换时
出口 IP 不断变化（实测 61.169.205.50→122.96.34.99），IP 白名单永远追不上、
持续报 status=112。改用 SK 签名鉴权后与出口 IP 无关，任何网络都可调用。

算法（腾讯官方）：
  1) 参数（含 key、不含 sig）按「参数名」ASCII 升序排列；
  2) 用「未做任何 url 编码的原始值」拼  path + "?" + k=v&k=v + SK；
  3) sig = md5(上述串 UTF-8) 的【小写十六进制 hex】（不是 Base64！）；
  4) 最终发送时仅对每个 value 做 url 编码，并追加 &sig=<sig>。
注意请求路径必须与实际一致（geocoder 末尾斜杠有无均可，但签名与请求要相同）。

密钥来源（F14 修复，2026-10-14）：
  不再硬编码任何 key/SK，只从明确配置读取（优先级从高到低）：
    1) 单值 TENCENT_MAP_KEY / TENCENT_MAP_SK
    2) 池   TENCENT_MAP_KEYS / TENCENT_MAP_SKS（逗号分隔，取第 1 把；多 key 池由 map_quota 管理）
  缺失时抛 MapCredentialUnavailable（结构化“通道不可用”），调用方应停用腾讯通道、
  不要回退到任何内置密钥，也不影响高德等其它通道。
"""
import hashlib
import os
import re
from urllib.parse import quote

import requests

BASE = "https://apis.map.qq.com"


class MapCredentialUnavailable(RuntimeError):
    """腾讯地图通道未配置 key/SK：结构化不可用，调用方应停用该通道（不影响其它 provider）。"""


def _configured_key_sk():
    """从环境读取 (key, sk)；缺失抛 MapCredentialUnavailable。绝不使用内置 fallback。"""
    key = os.environ.get("TENCENT_MAP_KEY", "").strip()
    sk = os.environ.get("TENCENT_MAP_SK", "").strip()
    if not key:
        pool_keys = [x.strip() for x in os.environ.get("TENCENT_MAP_KEYS", "").split(",") if x.strip()]
        if pool_keys:
            key = pool_keys[0]
    if not sk:
        pool_sks = [x.strip() for x in os.environ.get("TENCENT_MAP_SKS", "").split(",") if x.strip()]
        if pool_sks:
            sk = pool_sks[0]
    if not key or not sk:
        raise MapCredentialUnavailable(
            "腾讯地图 key/SK 未配置：设置 TENCENT_MAP_KEY/TENCENT_MAP_SK 或 "
            "TENCENT_MAP_KEYS/TENCENT_MAP_SKS（deploy.env）。本通道已停用，不影响其它地图通道。"
        )
    return key, sk


# 值里若含查询串结构性字符（& + = # %），服务端解析签名时会把它当成分隔/空格/转义，
# 导致重算签名不一致 → status=111（实测 "Mr & Mrs Bund"、"a+b c" 必现）。
# 签名与发送前统一替换为空格并折叠，保证“签名用原值”与“发送值”解析后完全一致。
def _clean_value(v):
    return re.sub(r"\s+", " ", re.sub(r"[&+=#%]", " ", str(v))).strip()


def build_signed_url(path, params, key=None, sk=None):
    if key is None or sk is None:
        key, sk = _configured_key_sk()
    p = {k: _clean_value(v) for k, v in dict(params).items()}
    p["key"] = key
    items = sorted(p.items())
    raw = "&".join(f"{k}={v}" for k, v in items)  # 签名用原始未编码值（已无结构性字符）
    sig = hashlib.md5((path + "?" + raw + sk).encode("utf-8")).hexdigest()
    sent = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in items)  # 发送只编码 value
    return BASE + path + "?" + sent + "&sig=" + sig


def signed_get(path, params, timeout=20, key=None, sk=None):
    return requests.get(build_signed_url(path, params, key=key, sk=sk), timeout=timeout)


if __name__ == "__main__":
    try:
        r = signed_get("/ws/place/v1/suggestion",
                       {"keyword": "麻布屋", "region": "上海",
                        "region_fix": 1, "page_size": 10})
        j = r.json()
        print("status", j.get("status"), j.get("message", ""),
              "候选数", len(j.get("data", [])))
        for c in j.get("data", [])[:4]:
            print(" -", c["title"], c.get("address"), c.get("location"))
    except MapCredentialUnavailable as e:
        print("NO_CREDENTIALS:", e)
        raise SystemExit(2)
