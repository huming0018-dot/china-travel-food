#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成精简、快速、不挂代理的 SearXNG settings.yml（只留已验证快引擎）。"""
import os
import secrets
import pathlib

OUT = pathlib.Path("/tmp/fooddeploy/searxng")
OUT.mkdir(parents=True, exist_ok=True)
secret = secrets.token_hex(32)

settings = f"""use_default_settings: true

server:
  secret_key: "{secret}"
  limiter: false
  image_proxy: false
  port: 8080
  bind_address: "0.0.0.0"

search:
  formats:
    - html
    - json
  default_lang: "zh-CN"
  max_request_timeout: 9

outgoing:
  request_timeout: 6
  max_request_timeout: 9
  useragent_suffix: ""

engines:
  - name: google
    disabled: true
  - name: duckduckgo
    disabled: true
  - name: brave
    disabled: true
  - name: qwant
    disabled: true
  - name: wikipedia
    disabled: true
  - name: bing
    disabled: false
    timeout: 6
  - name: mojeek
    disabled: false
    timeout: 6
  - name: startpage
    disabled: false
    timeout: 6
  - name: yandex
    disabled: false
    timeout: 6
"""
(OUT / "settings.yml").write_text(settings, encoding="utf-8")
print("wrote", OUT / "settings.yml")
