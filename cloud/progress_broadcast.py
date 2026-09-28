#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""progress_broadcast.py — 每 10 分钟进度播报（Telegram + 飞书，强制推送、绕过告警冷却）。

设计：只读本地状态文件 + 极少量 HEAD 计数，不占浏览器、不触发采集；离线由容器 cron 保证。
数据来源：
  /app/data/coverage/ledger.json   覆盖达标 / 缺口
  /app/data/pool_logs/*.log        各账号 worker 当前叶子与进度
  /app/data/_cookie_pool_state.json 账号健康
  /app/data/coverage/frontier.json 候选池规模
  /app/data/{SEARCH_RESTRICTED,COOKIE_INVALID} 阻塞标记
推送：直接调用 health._telegram / health._feishu_app / health._feishu（不经 should_send 冷却）。
"""
import datetime
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import health  # noqa: E402

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def load_json(path, default):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def tail_meaningful(path, n=1):
    """取日志最后 n 条非空行（去掉纯空白）。"""
    try:
        lines = [s for s in pathlib.Path(path).read_text(
            encoding="utf-8", errors="ignore").splitlines() if s.strip()]
        return lines[-n:]
    except Exception:
        return []


def coverage_section():
    rows = load_json(DATA / "coverage/ledger.json", [])
    leaves = [r for r in rows if r.get("leaf")]
    if not leaves:
        return "覆盖：账本未生成"
    met = sum(1 for r in leaves if r.get("met"))
    gap = sum(int(r.get("gap_n", 0)) for r in leaves if not r.get("met"))
    pct = met / len(leaves) * 100
    return f"覆盖：达标 {met}/{len(leaves)} ({pct:.0f}%)，总缺口 {gap} 家 verified 好店"


def pool_section():
    logdir = DATA / "pool_logs"
    parts = []
    if logdir.exists():
        for f in sorted(logdir.glob("*.log")):
            lines = tail_meaningful(f, 1)
            acc = f.stem
            last = lines[0].strip()[:90] if lines else "无日志"
            parts.append(f"  {acc}: {last}")
    if not parts:
        # 退回到 pool.log 尾部
        lines = tail_meaningful(DATA / "pool.log", 3)
        return "采集池：\n" + "\n".join(f"  {s.strip()[:90]}" for s in lines) if lines else "采集池：未运行"
    return "采集池（worker 当前进度）：\n" + "\n".join(parts)


def account_section():
    st = load_json(DATA / "_cookie_pool_state.json", {})
    if not st:
        return "账号：状态文件缺失"
    accs = st.get("accounts", st)
    if isinstance(accs, dict):
        bits = []
        for aid, info in accs.items():
            if isinstance(info, dict):
                code = info.get("status") or info.get("state") or info.get("code") or "?"
                bits.append(f"{aid}={code}")
            else:
                bits.append(f"{aid}={info}")
        return "账号健康：" + "，".join(bits)
    return f"账号健康：{accs}"


def blockers_section():
    marks = []
    if (DATA / "SEARCH_RESTRICTED").exists():
        marks.append("搜索风控300011")
    if (DATA / "COOKIE_INVALID").exists():
        marks.append("登录态失效")
    return "阻塞：" + ("、".join(marks) if marks else "无")


def frontier_section():
    fr = load_json(DATA / "coverage/frontier.json", {})
    n = len(fr) if isinstance(fr, dict) else 0
    return f"候选池 frontier：{n} 个候选"


def db_counts_section():
    """极轻量 HEAD 精确计数（失败则跳过，不影响播报）。"""
    try:
        import common as C
        def count(table, extra=""):
            r = C.req("HEAD", f"/{table}?select=id" + (("&" + extra) if extra else ""),
                      use_service=True)
            # Supabase 计数在 Content-Range: 0..n-1/total 或 Range
            cr = r.headers.get("content-range", "")
            if "/" in cr:
                return cr.rsplit("/", 1)[-1]
            return "?"
        nr = count("restaurants", "status=eq.active")
        nv = count("reviews")
        return f"数据库：{nr} 家在营，{nv} 条评价"
    except Exception:
        return "数据库：计数跳过"


def build_message():
    sep = "—" * 18
    lines = [
        "上海美食图鉴 · 进度播报",
        now(),
        sep,
        coverage_section(),
        db_counts_section(),
        frontier_section(),
        account_section(),
        blockers_section(),
        pool_section(),
    ]
    return "\n".join(lines)


def main():
    msg = build_message()
    title = "🍜 进度播报"
    results = {}
    try:
        r = health._telegram(msg, title)
        if r is not None:
            results["telegram"] = r
    except Exception as e:
        print("TG err", e)
    try:
        r = health._feishu_app(msg, title)
        if r is not None:
            results["feishu_app"] = r
    except Exception as e:
        print("FS app err", e)
    try:
        r = health._feishu(msg, title)
        if r is not None:
            results["feishu"] = r
    except Exception as e:
        print("FS err", e)
    print(msg)
    print("推送结果：", results)
    return 0 if any(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
