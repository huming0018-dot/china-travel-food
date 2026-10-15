#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crowd_risk_watch.py — 众包采集器风控信号自动看护（v3.5.3 配套，宿主机 cron 每 10 分钟）。

为什么需要：
  v3.5.3 客户端把账号处罚/限流、登录失效、验证码、访问频繁四类风险信号上报到
  crowd_risk_log（RPC crowd_report_risk）。但该 RPC 只写日志、不做处置，数据库函数也
  无法直连 Telegram。本脚本在宿主机定时轮询 crowd_risk_log，把信号落成服务端动作：

  1. account_penalty / auth_lost（账号被处罚/限流、登录失效）：
     立即把该 participant 的 quota_day 置 0（服务端停额，与客户端本地 7 天停采形成双保险，
     即使设备未升级也无法再领新任务），并推 Telegram 高优告警（含设备编号与命中文案）。
  2. captcha / rate_limited / freq_abnormal（验证码/访问频繁）：客户端已自冷却，
     同一设备 30 分钟内出现 ≥3 条才推 TG（避免单次抖动刷屏）。
  3. 日产量骤降（每天北京 18:00 后第一次巡检时检查一次）：今日 proofs 低于近 7 天同时段
     日中位数的 30% 且中位数有统计意义时推一条 WARN（可能是平台级风控/通道故障）。

水位：$FOOD_DATA_DIR/crowd_risk_watch.json
  - last_id：已处理的最大 crowd_risk_log.id（只处理新行，幂等）
  - drop_check_date：已做过当日骤降检查的北京日期（每天只算一次）
  - freq_alert_at：{participant_id: 上次频率告警时间戳}（30 分钟节流）

只修机制、不手工补单店、不自动解封；密钥只从环境变量读（source deploy.env）。

用法：
  python3 cloud/crowd_risk_watch.py
部署（crontab）：
  */10 * * * * /home/ubuntu/china-travel-food/cloud/crowd_risk_watch_cron.sh \\
      >> /home/ubuntu/china-travel-food/.data/crowd_risk_watch.log 2>&1
"""
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

BASE = os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
REST = BASE + "/rest/v1"
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
TG_RELAY = os.environ.get("TELEGRAM_API_BASE", "")  # 通常是 Supabase Edge tg-relay

DATA_DIR = pathlib.Path(os.environ.get("FOOD_DATA_DIR",
                         "/home/ubuntu/china-travel-food/.data"))
WATER = DATA_DIR / "crowd_risk_watch.json"

BJ = dt.timezone(dt.timedelta(hours=8))  # 北京时区（固定 UTC+8，不依赖系统时区）

# 账号级（跨天持续停采 + 服务端停额）
ACCOUNT_KINDS = {"account_penalty", "auth_lost"}
# 频率/验证类（客户端自冷却，仅密集时告警）
FREQ_KINDS = {"captcha", "rate_limited", "freq_abnormal"}
FREQ_WINDOW_S = 30 * 60
FREQ_THRESHOLD = 3
FREQ_ALERT_COOLDOWN_S = 30 * 60
DROP_RATIO = 0.30        # 今日 < 近 7 天中位数 × 0.30
DROP_MIN_BASELINE = 30   # 中位数低于该值不判骤降（低基数不报警）


def log(*a):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), *a, flush=True)


def headers():
    if not KEY:
        sys.exit("缺少 SUPABASE_SERVICE_ROLE_KEY（请先 source deploy.env）")
    return {"apikey": KEY, "Authorization": "Bearer " + KEY,
            "Content-Type": "application/json"}


def request(method, path, body=None, extra_headers=None, retries=4):
    url = REST + path
    data = json.dumps(body).encode() if body is not None else None
    h = headers()
    if extra_headers:
        h.update(extra_headers)
    last = None
    for i in range(retries):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read().decode()
                return r.status, (json.loads(raw) if raw else None), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                last = f"HTTP {e.code}"
                time.sleep(min(2 ** i, 15))
                continue
            return e.code, e.read().decode()[:300], {}
        except Exception as e:
            last = repr(e)
            time.sleep(min(2 ** i, 15))
    raise RuntimeError(f"{method} {path} 连续失败: {last}")


def count(path):
    """PostgREST 精确计数：Prefer count=exact + Range 0-0，读 content-range '*/N'。"""
    st, _, hdr = request("GET", path + "&limit=1",
                         extra_headers={"Prefer": "count=exact", "Range": "0-0"})
    if st != 200:
        return None
    cr = hdr.get("Content-Range") or hdr.get("content-range") or ""
    if "/" in cr:
        try:
            return int(cr.split("/")[-1])
        except ValueError:
            return None
    return None


def load_water():
    try:
        return json.loads(WATER.read_text())
    except Exception:
        return {"last_id": 0, "drop_check_date": "", "freq_alert_at": {}}


def save_water(w):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = WATER.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(w, ensure_ascii=False, indent=2))
    tmp.replace(WATER)


def tg_send(text):
    """走 Edge tg-relay（JSON），失败再试官方直连（urlencoded）。返回是否送达。"""
    if not (TG_TOKEN and TG_CHAT and text):
        return False
    # 1) relay（容器/宿主机直连 api.telegram.org 被墙时的主通道）
    if TG_RELAY:
        url = TG_RELAY.rstrip("/") + "/bot" + TG_TOKEN + "/sendMessage"
        body = json.dumps({"chat_id": TG_CHAT, "text": text[:4000],
                           "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                if json.loads(r.read().decode()).get("ok"):
                    return True
        except Exception as e:
            log("tg relay fail:", repr(e)[:80])
    # 2) 官方直连兜底
    url = "https://api.telegram.org/bot" + TG_TOKEN + "/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text[:4000],
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(
                urllib.request.Request(url, data=data, method="POST"), timeout=20) as r:
            return bool(json.loads(r.read().decode()).get("ok"))
    except Exception as e:
        log("tg direct fail:", repr(e)[:80])
    return False


def set_quota_zero(pid):
    """把该参与者服务端日配额置 0（处罚/登录失效停额）。幂等。"""
    path = "/crowd_participants?" + urllib.parse.urlencode(
        {"participant_id": "eq." + pid})
    st, body, _ = request("PATCH", path, {"quota_day": 0},
                          extra_headers={"Prefer": "return=minimal"})
    if st in (200, 204):
        return True
    log("PATCH quota_day=0 失败", pid, st, str(body)[:160])
    return False


def recent_freq_count(pid, since_iso):
    """该设备最近窗口内 captcha/rate_limited/freq_abnormal 信号总数。"""
    sigs = ",".join(sorted(FREQ_KINDS))
    q = urllib.parse.urlencode({
        "participant_id": "eq." + pid,
        "signal": f"in.({sigs})",
        "created_at": "gte." + since_iso,
    })
    return count("/crowd_risk_log?select=id&" + q) or 0


def process_new_signals(w):
    """处理 crowd_risk_log 新行。返回是否有任何动作。"""
    last_id = int(w.get("last_id", 0) or 0)
    st, rows, _ = request(
        "GET",
        f"/crowd_risk_log?select=id,participant_id,signal,detail,created_at"
        f"&id=gt.{last_id}&order=id.asc&limit=500")
    if st != 200:
        log("拉取 crowd_risk_log 失败", st, str(rows)[:160])
        return False
    if not rows:
        return False

    max_id = last_id
    now = time.time()
    freq_alert_at = w.get("freq_alert_at", {})
    seen_account = set()
    for row in rows:
        rid = row.get("id") or 0
        max_id = max(max_id, rid)
        pid = (row.get("participant_id") or "").strip()
        signal = (row.get("signal") or "").strip()
        detail = (row.get("detail") or "").strip()
        if not pid:
            continue

        if signal in ACCOUNT_KINDS and pid not in seen_account:
            seen_account.add(pid)
            ok = set_quota_zero(pid)
            label = "登录态失效" if signal == "auth_lost" else "账号被处罚/限流"
            msg = (
                "🔴 众包采集器风控告警\n"
                f"设备：{pid}\n"
                f"信号：{label}（{signal}）\n"
                f"命中：{detail[:60] or '页面处罚/登录提示'}\n"
                f"处置：服务端已将该设备日配额置 0，客户端本地停采"
                + ("（处罚默认 7 天）" if signal == "account_penalty" else "（登录失效默认 2 天）")
                + ("\n唯一动作：确认账号恢复（登录/申诉通过）后再到选项页解除。" if ok else
                   "\n注意：停额写库失败，请人工核对该设备配额。")
            )
            tg_send(msg)
            log("账号风险", pid, signal, "quota0=", ok)

        elif signal in FREQ_KINDS:
            since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=FREQ_WINDOW_S)
            n = recent_freq_count(pid, since.strftime("%Y-%m-%dT%H:%M:%SZ"))
            last_alert = int(freq_alert_at.get(pid, 0) or 0)
            if n >= FREQ_THRESHOLD and (now - last_alert) > FREQ_ALERT_COOLDOWN_S:
                freq_alert_at[pid] = now
                tg_send(
                    "🟡 众包采集器频率告警\n"
                    f"设备：{pid}\n"
                    f"信号：{FREQ_WINDOW_S // 60} 分钟内 {n} 次验证码/访问频繁\n"
                    "处置：客户端已自冷却 24–72h；如持续出现请降低该设备任务密度。\n"
                    "无需操作（系统已自动处理）。"
                )
                log("频率告警", pid, "n=", n)

    w["last_id"] = max_id
    w["freq_alert_at"] = freq_alert_at
    return True


def day_bounds_bj(day_offset):
    """返回北京某日（今天-day_offset）的 [00:00, 次日00:00) UTC ISO 字符串对。"""
    now_bj = dt.datetime.now(BJ)
    d0 = (now_bj - dt.timedelta(days=day_offset)).replace(
        hour=0, minute=0, second=0, microsecond=0)
    start = d0.astimezone(dt.timezone.utc)
    end = start + dt.timedelta(days=1)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return start.strftime(fmt), end.strftime(fmt)


def proofs_in(start_iso, end_iso):
    # PostgREST 同列范围用 and=(created_at.gte.s,created_at.lt.e)；时间戳做 URL 编码
    s = urllib.parse.quote(start_iso, safe="")
    e = urllib.parse.quote(end_iso, safe="")
    return count(f"/crowd_proofs?select=id&and=(created_at.gte.{s},created_at.lt.{e})")


def check_output_drop(w):
    """每天北京 18:00 后第一次巡检：今日产量 vs 近 7 天日中位数，骤降则告警。"""
    now_bj = dt.datetime.now(BJ)
    today_str = now_bj.strftime("%Y-%m-%d")
    if w.get("drop_check_date") == today_str:
        return
    if now_bj.hour < 18:
        return  # 当天采集可能还没走完，18:00 后再判

    # 今日 proofs
    t0, t1 = day_bounds_bj(0)
    today_n = proofs_in(t0, now_bj.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    # 近 7 天每天 proofs（d=1..7）
    daily = []
    for d in range(1, 8):
        s, e = day_bounds_bj(d)
        n = proofs_in(s, e)
        if n is not None:
            daily.append(n)
    if today_n is None or len(daily) < 5:
        log("骤降检查数据不足 today=", today_n, "baseline=", daily)
        w["drop_check_date"] = today_str
        return
    daily_sorted = sorted(daily)
    median = daily_sorted[len(daily_sorted) // 2]
    if median >= DROP_MIN_BASELINE and today_n < median * DROP_RATIO:
        tg_send(
            "🟡 众包采集器日产量骤降\n"
            f"今日 proofs：{today_n}（北京 18:00 后）\n"
            f"近 7 天日中位数：{median}（区间 {daily_sorted[0]}–{daily_sorted[-1]}）\n"
            "可能是平台级风控或采集通道异常；风控信号若触发会另有告警。\n"
            "无需操作（自动看护中），若连续 2 天请人工排查。"
        )
        log("骤降告警 today=", today_n, "median=", median)
    else:
        log("骤降检查正常 today=", today_n, "median=", median)
    w["drop_check_date"] = today_str


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    w = load_water()
    process_new_signals(w)
    check_output_drop(w)
    save_water(w)
    log("巡检完成 last_id=", w.get("last_id"))


if __name__ == "__main__":
    main()
