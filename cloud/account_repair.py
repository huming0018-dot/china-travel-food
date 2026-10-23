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


def _load_force_ck(account):
    """健康复核专用：绕过 cookie 池 state 的 dead/parked 预过滤，强制读取账号 cookie。

    关键：健康复核必须独立判定死活，不能被旧标记影响。XhsApi 构造时会按
    _cookie_pool_state.json 剔除 dead/parked 账号，若复用它，一旦账号被标死，
    探测就在发请求前 api.accounts 为空、直接返回 None（根本没发网络请求），
    再被 reconcile 误判成「双出口网络失败」、不走 R3 扫码告警，形成「死号永远
    无法复核 / 无法自愈 / 无法告警」的死锁（历史：2026-10 双账号 -100 被静默掩盖
    十天，UGC 采集零产出，看门狗每轮报 OK）。
    返回 ck dict（含 web_session）；文件缺失/无 web_session/解析失败返回 None。
    """
    f = ACCT_DIR / f"{account}.json"
    if not f.exists():
        return None
    try:
        ck = {c["name"]: c["value"] for c in json.loads(f.read_text(encoding="utf-8"))}
    except Exception:
        return None
    return ck if ck.get("web_session") else None


def _is_neterr(v):
    return isinstance(v, tuple) and bool(v) and v[0] == "NETERR"


def probe(account, use_proxy=False):
    """健康复核（权威、低风险、只读 user/me）。强制加载 cookie，不被 state 旧标记过滤。

    判定：GET /api/sns/web/v2/user/me，code==0 且 guest==false 才算活。
    返回：
      0=活号；-100=登录过期/游客态；其它 int=对应风控码（软封）；
      "no_cookie"=无 cookie 文件/无 web_session（需人工登录，非网络问题）；
      ("NETERR", reason)=真网络异常（请求发不出去，基础设施），携带原因（含代理连接失败）。
    旧实现用「搜索 POST + sign.get_search_id()」，而 xhshow 0.1.9 已移除 get_search_id，
    且搜索受速率软限流、返回值在 0/空/-100 间漂移，会把刚登录的活账号误判成死号。
    """
    import requests
    import xhs_api
    proxies = _proxies_for(account) if use_proxy else None
    ck = _load_force_ck(account)
    if not ck:
        return "no_cookie"
    api = xhs_api.XhsApi(min_gap=3.0, pin=None)  # 仅借用签名器，不使用它被 state 过滤后的账号
    uri = "/api/sns/web/v2/user/me"
    try:
        h = api.sign.sign_headers("GET", uri, ck)
        h.update(xhs_api.BASE_HEADERS)
        h["Cookie"] = api._cookie_header(ck)
        r = requests.get(xhs_api.EDITH + uri, headers=h, timeout=20, proxies=proxies)
        j = r.json()
        code = j.get("code")
        d = j.get("data") or {}
        if code == 0 and d.get("guest") is False:
            return 0
        if code == -100 or d.get("guest") is True:
            return -100
        return code
    except Exception as e:
        return ("NETERR", f"{type(e).__name__}: {e}")


def reconcile_account(account):
    """返回 (verdict, detail)。verdict: ok / dead / soft / unknown。

    关键：把「无 cookie」「真网络异常」「登录过期」三者分开，不再把探测为空/读不到
    账号一律吞成网络失败。默认出口能拿到明确 code（-100/0）时以它为准，代理失败
    只作兜底出口注记（代理挂了不影响 web_session 过期的权威判定）。
    """
    import xhs_cookie_pool as P
    r1 = probe(account, use_proxy=False)
    r2 = None
    # R2：默认出口未明确活号 → 换独立 IP 再探一次（省配额：活号直接返回）
    if r1 != 0:
        time.sleep(4)
        r2 = probe(account, use_proxy=True)

    def is_int(v, n):
        return isinstance(v, int) and not isinstance(v, bool) and v == n

    # 任一出口明确活 → R1 改判 ok
    if is_int(r1, 0) or is_int(r2, 0):
        via = "默认出口" if is_int(r1, 0) else "广州代理出口"
        P.mark_ok(account)
        return "ok", f"签名通道 code=0（{via}），已改判可用"
    # 任一出口明确 -100（另一出口未反证为活）→ R3 死号，需扫码
    if is_int(r1, -100) or is_int(r2, -100):
        note = ""
        if _is_neterr(r1) or _is_neterr(r2):
            note = "（另一出口网络/代理不可达，不影响默认出口 -100 判定）"
        P.mark_dead(account, "双出口签名探测 -100：web_session 过期")
        return "dead", f"web_session 过期(-100)，需重新扫码登录{note}"
    # 两出口都无 cookie → 等同死号，必须人工登录
    if r1 == "no_cookie" and r2 == "no_cookie":
        return "dead", "无 cookie 文件/无 web_session，需重新扫码登录"
    if r1 == "no_cookie" or r2 == "no_cookie":
        return "dead", "cookie 缺失或损坏，需重新扫码登录"
    # 两出口都真网络异常 → 基础设施问题（不再误标账号），携带原因
    if _is_neterr(r1) and _is_neterr(r2):
        return "unknown", (f"双出口网络均失败（基础设施，非账号）：默认[{r1[1][:70]}] "
                           f"代理[{r2[1][:70]}]")
    # 其余风控码（300011/限流等）→ 软封，保持 restricted 等下轮，不当死号
    for v in (r1, r2):
        if isinstance(v, int) and not isinstance(v, bool) and v not in (0, -100):
            P.mark_restricted(account, f"签名通道 code={v}，软封冷却")
            return "soft", f"签名通道 code={v}，软封待下轮"
    return "unknown", f"探测结果无法归类：r1={r1} r2={r2}"


# 连续 unknown（基础设施探测失败）升级阈值：watchdog 每 20 分钟一轮，9 轮≈3 小时
UNKNOWN_STREAK_ALERT = 9
UNKNOWN_INCIDENT_F = DATA / "_unknown_incident.json"


def escalate_unknown_if_needed(results):
    """所有账号连续多轮都 unknown（真网络/探测基础设施故障）时升级硬告警，
    避免「网络真挂了」被无限当成『OK 无新错误』静默；一旦有明确结论即清零。"""
    unknowns = [a for a, (v, _) in results.items() if v == "unknown"]
    details = {a: d for a, (v, d) in results.items() if v == "unknown"}
    try:
        prev = json.loads(UNKNOWN_INCIDENT_F.read_text(encoding="utf-8"))
    except Exception:
        prev = {"streak": 0, "alerted": False}
    if not unknowns:
        if prev.get("streak"):
            UNKNOWN_INCIDENT_F.write_text(json.dumps(
                {"streak": 0, "alerted": False, "ts": time.strftime("%Y-%m-%d %H:%M:%S")},
                ensure_ascii=False), encoding="utf-8")
        return
    streak = int(prev.get("streak", 0)) + 1
    alerted = bool(prev.get("alerted"))
    if streak >= UNKNOWN_STREAK_ALERT and not alerted:
        body = "小红书账号探测连续 %d 轮双出口网络失败，采集池无法获取登录态：%s" % (
            streak, "；".join(details[a] for a in unknowns))
        try:
            import health
            health.alert(body, title="🍜 账号探测连续网络失败（基础设施）",
                         key="probe_network_unknown", cooldown=6 * 3600)
        except Exception as e:
            log(f"unknown 升级告警失败（容器内通道可能不可用，仅留痕）：{e}")
        alerted = True
    UNKNOWN_INCIDENT_F.write_text(json.dumps(
        {"streak": streak, "alerted": alerted, "accounts": unknowns,
         "ts": time.strftime("%Y-%m-%d %H:%M:%S"), "details": details},
        ensure_ascii=False), encoding="utf-8")
    if streak >= UNKNOWN_STREAK_ALERT:
        log(f"⚠️ unknown 连续 {streak} 轮（基础设施告警）：{unknowns}")


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
    escalate_unknown_if_needed(results)
    if started:
        import health
        health.alert("检测到采集池未运行，已自动拉起。",
                     title="🍜 采集池自动恢复", key="pool_autostart", once=True)

    summary = {a: v for a, (v, _) in results.items()}
    log(f"汇总：pool_alive={alive} accounts={summary}")
    return results, alive


if __name__ == "__main__":
    run()
