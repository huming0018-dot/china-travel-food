#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notifier.py — 看门狗唯一通知出口（分级 · 统一格式 · 去重 · 冷却 · 有界提醒）。

为什么存在（推送整顿）：此前 health.alert / warning_handler / progress_broadcast 各自为政，
标题与格式不一、10 分钟播报绕过冷却、且对 -100 持续推送【云端 headless 二维码】——
而实测云端 headless 扫码在“确认”环节必 fail（见 xhs-login-runbook），属于无效打扰。

四级（level）：
  INFO     例行进度播报，按固定节奏（cadence）推一条紧凑心跳。
  WARN     发现问题但系统正在自动处理（无需用户操作）；同 key 同内容按冷却折叠。
  ACTION   必须用户亲自处理（典型：-100 需在【本机真实 Chrome】重登）；
           一条工单只推一次，之后按 schedule 有界提醒，提醒用尽不再刷屏。
  RESOLVED 问题已解决；每个 key 只推一条收尾。

硬规则：
  - 所有外发都过本模块；任何消息结尾必须是“无需操作”或“唯一明确动作”之一。
  - 不推送原始 traceback / 登录遮罩图 / 过期二维码；内容做长度与脱敏。
  - 同一 key 内容哈希不变且在冷却内 → 不重复推。

通道复用 health 原语（TG / 飞书自建应用 / 飞书 webhook），不重复实现鉴权。

信号 → 模块目录（每条外发都必须能在此登记；无登记/无触发条件不得推送）：
  key                生产模块               触发条件（确定性）                 级别              节流
  heartbeat          progress_broadcast     每 10 分钟例行心跳                 INFO              cadence 600
  watchdog:killed    watchdog               强杀了卡死采集进程（runtime>30m）   WARN              cooldown 3600
  login:account_x    warning_handler        双出口 user/me 均 -100             ACTION→RESOLVED   有界 nudge
  map:quota          map_key_repair         全部地图 key 耗尽 / 恢复           WARN→RESOLVED     cooldown
  pool_autostart     account_repair         gap_pool 缺失并已自动拉起          WARN(health)      once
通道开关：health.channel_enabled（NOTIFY_* 或 /app/data/notify_channels.json），可独立暂停某通道。
心跳正文由 progress_broadcast.build_compact 生成，固定 3~4 行：覆盖 / 库 / 账号(含候选·阻塞) / 开发。
"""
import datetime
import hashlib
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import health  # noqa: E402

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
LEDGER_F = DATA / "notifier_ledger.json"

INFO, WARN, ACTION, RESOLVED = "INFO", "WARN", "ACTION", "RESOLVED"
LEVEL_TAG = {INFO: "🟢 播报", WARN: "🟡 自动处理中", ACTION: "🔴 需要你操作", RESOLVED: "✅ 已解决"}

# 默认节奏 / 冷却 / 提醒计划（秒）—— 柔和模式：少打扰
DEFAULT_CADENCE = 3600         # 例行播报 60 分钟（原10分钟）
WARN_COOLDOWN = 7200           # 同类自动处理告警 2 小时（原1小时）
ACTION_NUDGE = (86400, 86400, 86400)  # 首次后每天提醒一次，共3次（原30/60/60/120分钟4次）
MAX_BODY = 1200


# ────────────────────── 账本 ──────────────────────
def _load():
    try:
        return json.loads(LEDGER_F.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(L):
    try:
        LEDGER_F.parent.mkdir(parents=True, exist_ok=True)
        LEDGER_F.write_text(json.dumps(L, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _h(text):
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:16]


def _now_str():
    return datetime.datetime.now().strftime("%m-%d %H:%M")


def sanitize(text):
    """折叠多余空行、截断长度、去掉常见密钥前缀（不外发凭据）。"""
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    out, blank = [], 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank <= 1:
                out.append("")
            continue
        blank = 0
        out.append(ln)
    s = "\n".join(out).strip()
    for marker in ("sb_secret_", "sb_publishable_", "Bearer ", "sk-", "web_session="):
        if marker in s:
            s = s.replace(marker, marker[:3] + "***")
    return s[:MAX_BODY]


# ────────────────────── 格式 ──────────────────────
def format(level, body, action=None, footer=None):
    head = f"{LEVEL_TAG.get(level, level)} · 上海美食图鉴 · {_now_str()}"
    body = sanitize(body)
    # 正文【不含 head】：发送原语会统一在最前面拼一次 head，避免标题重复出现两行。
    parts = ["─" * 16, body]
    if action:
        parts += ["", f"👉 需要你做：{action}"]
    elif level in (INFO, WARN, RESOLVED):
        parts += ["", "（无需操作）"]
    if footer:
        parts += [footer]
    return head, "\n".join(parts)


# ────────────────────── 发送（双通道） ──────────────────────
def _deliver(header, full):
    results = {}
    for fn, name in ((health._telegram, "telegram"),
                     (health._feishu_app, "feishu_app"),
                     (health._feishu, "feishu")):
        try:
            r = fn(full, header)
            if r is not None:
                results[name] = bool(r)
        except Exception as e:
            print("[notifier] channel fail", name, repr(e)[:60])
    ok = any(results.values())
    if not results:
        print("[notifier] 未配置任何推送通道")
    return ok


def _record(L, key, level, full, **extra):
    rec = L.get(key, {})
    rec.update({"level": level, "last_ts": int(time.time()),
                "last_hash": _h(full), "count": rec.get("count", 0) + 1})
    rec.update(extra)
    L[key] = rec
    return rec


# ────────────────────── 对外 API ──────────────────────
def info(body, key="heartbeat", cadence=DEFAULT_CADENCE, footer=None):
    """例行心跳：仅当距上次 ≥ cadence 才推。"""
    header, full = format(INFO, body, footer=footer)
    L = _load()
    rec = L.get(key)
    if rec and int(time.time()) - int(rec.get("last_ts", 0)) < cadence:
        return False
    ok = _deliver(header, full)
    if ok:
        _record(L, key, INFO, full)
        _save(L)
    return ok


def warn(body, key, cooldown=WARN_COOLDOWN, header_title=None):
    """自动处理中的问题：同 key 同内容按 cooldown 折叠；内容变化（进展）才再推。"""
    header, full = format(WARN, body)
    L = _load()
    rec = L.get(key)
    if rec and rec.get("last_hash") == _h(full) \
            and int(time.time()) - int(rec.get("last_ts", 0)) < cooldown:
        return False
    if rec and rec.get("last_hash") != _h(full) \
            and int(time.time()) - int(rec.get("last_ts", 0)) < 300:
        # 进展更新至少间隔 5 分钟，避免抖动刷屏
        return False
    ok = _deliver(header, full)
    if ok:
        _record(L, key, WARN, full, state="open")
        _save(L)
    return ok


def action(body, key, action_text, nudge_schedule=ACTION_NUDGE, footer=None):
    """需要用户处理：首次立即推；之后按 nudge_schedule 有界提醒；用尽不刷屏。
    若用户已处理（调用方应改走 resolve），不重复。"""
    header, full = format(ACTION, body, action=action_text, footer=footer)
    L = _load()
    rec = L.get(key)
    now_i = int(time.time())
    if rec and rec.get("state") == "resolved":
        return False
    if not rec:
        ok = _deliver(header, full)
        if ok:
            _record(L, key, ACTION, full, state="open", nudges=0, opened=now_i)
            _save(L)
        return ok
    # 已开过单：按计划决定是否提醒
    nudges = int(rec.get("nudges", 0))
    if nudges >= len(nudge_schedule):
        return False
    due_at = int(rec.get("last_ts", 0)) + int(nudge_schedule[nudges])
    if now_i < due_at:
        return False
    ok = _deliver(header, full + f"\n\n（提醒 {nudges+1}/{len(nudge_schedule)}：仍待处理）")
    if ok:
        rec.update({"last_ts": now_i, "nudges": nudges + 1, "last_hash": _h(full)})
        L[key] = rec
        _save(L)
    return ok


def resolve(body, key, footer=None):
    """问题解决：每个 key 只推一条收尾；未开过单不推。"""
    L = _load()
    rec = L.get(key)
    if not rec or rec.get("state") == "resolved":
        return False
    header, full = format(RESOLVED, body, footer=footer)
    ok = _deliver(header, full)
    if ok:
        rec.update({"state": "resolved", "level": RESOLVED,
                    "last_ts": int(time.time()), "last_hash": _h(full)})
        L[key] = rec
        _save(L)
    return ok


if __name__ == "__main__":
    print("channels:", {k: ("set" if os.environ.get(k) else "missing")
                        for k in ("TELEGRAM_BOT_TOKEN", "FEISHU_APP_ID", "FEISHU_WEBHOOK")})
