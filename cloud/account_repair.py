#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""account_repair.py — 小红书账号「自动修复」（由看门狗 watchdog 每 20 分钟调用）。

为什么存在：账号健康有两条口径——浏览器通道(health.py)会写 dead/restricted，
签名直连通道(xhs_api，采集池实际使用)却常 code=0；二者无人对账，导致「其实在干活却报死号」，
而真·采集池挂掉也没人拉起。本模块做确定性修复阶梯：

  R0 守护采集池：gap_pool 进程/presence 缺失 → 自动拉起（不重复拉起）。
  R1 签名通道复核（权威）：逐账号 pin 探测；浏览器标 dead/restricted 但签名 code=0 → 改判 ok。
  R2 换出口 IP：默认出口软封/网络失败/共享 IP 限流 → 经广州代理(IP 轮换)再探一次。
  R3 真失效才叫人：双出口都 -100（web_session 过期，无法自愈）→ 保持 dead 并一次性告警扫码。
状态统一写回 xhs_cookie_pool，供 cloud_router 与 progress_broadcast 使用，二者随之自愈。

只做「修机制/状态」，绝不手工补数据；探测每账号最多 2 次（默认+代理），省配额。
"""
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
ACCT_DIR = pathlib.Path(os.environ.get("XHS_ACCOUNTS_DIR", "/secrets/xhs_accounts"))
PROXY_F = DATA / "account_proxies.json"


def log(m):
    print(f"[repair] {m}", flush=True)


# ------------------------------------------------ R0 守护采集池
def _find_proc(needle):
    """读 /proc 找命令行含 needle 的 pid 列表（不依赖 pgrep/ps）。"""
    pids = []
    for d in pathlib.Path("/proc").glob("[0-9]*"):
        try:
            cmd = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "ignore")
        except Exception:
            continue
        if needle in cmd and "account_repair" not in cmd:
            pids.append(int(d.name))
    return pids


def ensure_pool():
    """gap_pool 不在则拉起（与 @reboot 同命令）；返回 (started:bool, alive:bool)。"""
    alive = bool(_find_proc("gap_pool.py"))
    if alive:
        return False, True
    log("gap_pool 未运行，自动拉起…")
    cmd = ("cd /app/cloud && . /app/cloud/env.sh && "
           "nohup /usr/local/bin/python gap_pool.py 6 >> /app/data/pool.log 2>&1 &")
    try:
        subprocess.Popen(["bash", "-lc", cmd], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(8)
    except Exception as e:
        log(f"拉起 gap_pool 失败：{e}")
        return False, False
    ok = bool(_find_proc("gap_pool.py"))
    log(f"gap_pool 拉起{'成功' if ok else '失败'}")
    return ok, ok


# ------------------------------------------------ R1/R2 账号复核
def _proxies_for(account):
    try:
        m = json.loads(PROXY_F.read_text(encoding="utf-8"))
        px = m.get(account)
        return {"http": px, "https": px} if px else None
    except Exception:
        return None


def probe(account, use_proxy=False):
    """签名通道 pin 探测（权威、低风险、不碰搜索限流），返回归一化 code。

    判定：GET /api/sns/web/v2/user/me，code==0 且 guest==false 才算活。
      返回 0=可用 / -100=登录过期(或游客态) / 其它=对应风控码；网络失败返回 None。
    旧实现用「搜索 POST + sign.get_search_id()」，而 xhshow 0.1.9 已移除 get_search_id，
    且搜索受速率软限流、返回值在 0/空/-100 间漂移，会把刚登录的活账号误判成死号。
    """
    import requests
    import xhs_api
    proxies = _proxies_for(account) if use_proxy else None
    api = xhs_api.XhsApi(min_gap=3.0, pin=account, proxies=proxies)
    if not api.accounts:
        return None
    a = api.accounts[0]["ck"]
    uri = "/api/sns/web/v2/user/me"
    try:
        h = api.sign.sign_headers("GET", uri, a)
        h.update(xhs_api.BASE_HEADERS)
        h["Cookie"] = api._cookie_header(a)
        r = requests.get(xhs_api.EDITH + uri, headers=h, timeout=20, proxies=proxies)
        j = r.json()
        code = j.get("code")
        d = j.get("data") or {}
        if code == 0 and d.get("guest") is False:
            return 0
        if code == -100 or d.get("guest") is True:
            return -100
        return code
    except Exception:
        return None


def reconcile_account(account):
    """返回 (verdict, detail)。verdict: ok / dead / soft / unknown。"""
    import xhs_cookie_pool as P
    code = probe(account, use_proxy=False)
    via = "默认出口"
    # R2：默认出口非 0（软封/-100/网络）→ 换独立 IP 再探
    if code != 0:
        time.sleep(4)
        code2 = probe(account, use_proxy=True)
        if code2 is not None:
            code, via = code2, "广州代理出口"

    if code == 0:
        P.mark_ok(account)  # R1：浏览器误判的 dead/restricted 自动改判
        return "ok", f"签名通道 code=0（{via}），已改判可用"
    if code == -100:
        # R3：双出口均登录过期 → 无法自愈，需扫码
        P.mark_dead(account, "双出口签名探测 -100：web_session 过期")
        return "dead", "双出口均 -100，需重新扫码登录"
    if code is None:
        return "unknown", "双出口网络均失败（基础设施，非账号）"
    # 其余风控码（300011/限流等）→ 软封，保持 restricted 等下轮，不当死号
    P.mark_restricted(account, f"签名通道 code={code}，软封冷却")
    return "soft", f"签名通道 code={code}，软封待下轮"


def human_alert_if_needed(results):
    """真·死号：交给 warning_handler 告警专项——后台拉二维码、双通道推送、
    刷新/提醒并验证到重登成功（取代只发一条一次性告警）。"""
    for account, (verdict, detail) in results.items():
        if verdict == "dead":
            try:
                import warning_handler
                warning_handler.request_login(account, detail)
            except Exception as e:
                print(f"[repair] warning_handler 不可用({e})，回退普通告警")
                import health
                health.alert(detail, title=f"🍜 {account} 需重新登录",
                             key=f"login_dead_{account}", once=True)


# ------------------------------------------------ 主入口
def run():
    started, alive = ensure_pool()
    accounts = []
    if ACCT_DIR.exists():
        accounts = sorted(p.stem for p in ACCT_DIR.glob("*.json"))

    results = {}
    for a in accounts:
        verdict, detail = reconcile_account(a)
        results[a] = (verdict, detail)
        log(f"{a}: {verdict} — {detail}")
        time.sleep(2)

    human_alert_if_needed(results)
    if started:
        import health
        health.alert("检测到采集池未运行，已自动拉起。",
                     title="🍜 采集池自动恢复", key="pool_autostart", once=True)

    summary = {a: v for a, (v, _) in results.items()}
    log(f"汇总：pool_alive={alive} accounts={summary}")
    return results, alive


if __name__ == "__main__":
    run()
