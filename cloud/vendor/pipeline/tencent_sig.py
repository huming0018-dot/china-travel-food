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
"""
import hashlib
import os
from urllib.parse import quote

import requests

# 云端从 deploy.env 注入 TENCENT_MAP_KEY / TENCENT_MAP_SK；本地/管线用内置默认值。
KEY = os.environ.get("TENCENT_MAP_KEY", "").strip() or "7PQBZ-7IDKZ-YUHXF-7V2GG-M2B3O-4OBT6"
SK = os.environ.get("TENCENT_MAP_SK", "").strip() or "4ibuevVyzenm3Xcz3X6b4rljRlhZHlZo"
BASE = "https://apis.map.qq.com"


def build_signed_url(path, params):
    p = dict(params)
    p["key"] = KEY
    items = sorted(p.items())
    raw = "&".join(f"{k}={v}" for k, v in items)  # 签名用原始未编码值
    sig = hashlib.md5((path + "?" + raw + SK).encode("utf-8")).hexdigest()
    sent = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in items)  # 发送只编码 value
    return BASE + path + "?" + sent + "&sig=" + sig


def signed_get(path, params, timeout=20):
    return requests.get(build_signed_url(path, params), timeout=timeout)


if __name__ == "__main__":
    r = signed_get("/ws/place/v1/suggestion",
                   {"keyword": "麻布屋", "region": "上海",
                    "region_fix": 1, "page_size": 10})
    j = r.json()
    print("status", j.get("status"), j.get("message", ""),
          "候选数", len(j.get("data", [])))
    for c in j.get("data", [])[:4]:
        print(" -", c["title"], c.get("address"), c["location"])
