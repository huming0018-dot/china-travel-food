#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""public_status.py — 全局公共状态快照

采集三个维度的状态，供所有窗口共享：
  1. 采集账号：cookie状态、probe结果、代理状态
  2. API配额：地图（高德/腾讯）日/月消耗
  3. 数据概览：餐厅数、评论数、覆盖率、费用估算

用法：
  python3 public_status.py           # 打印完整状态
  python3 public_status.py --brief   # 简要模式（一行摘要）
"""
import sys, os, json, pathlib, time
from datetime import datetime, timezone, timedelta

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path(os.environ.get("FOOD_PIPELINE_DIR", str(HERE / "vendor" / "pipeline")))
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

CST = timezone(timedelta(hours=8))


def load_json(path):
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except Exception:
        return {}


def section(title):
    print(f"\n{'─'*40}")
    print(f"  {title}")
    print(f"{'─'*40}")


# ────────────────────── 1. 采集账号状态 ──────────────────────
def collector_status():
    section("📱 采集账号状态")
    pool = load_json(DATA / "_cookie_pool_state.json")
    if not pool:
        print("  (无cookie状态文件)")
        return
    for account, info in pool.items():
        status = info.get("status", "unknown")
        cooling = info.get("cooling", False)
        cool_until = info.get("cool_until", 0)
        cool_str = ""
        if cooling and cool_until:
            remain = int(cool_until - time.time())
            if remain > 0:
                mins = remain // 60
                cool_str = f" (冷却{mins}min)"
        dead_reason = info.get("dead_reason", "")
        reason_str = f" [{dead_reason}]" if dead_reason else ""
        icon = {"active": "🟢", "dead": "🔴", "parked": "🟡"}.get(status, "⚪")
        print(f"  {icon} {account}: {status}{cool_str}{reason_str}")


# ────────────────────── 2. API配额消耗 ──────────────────────
def quota_status():
    section("📊 API配额消耗")
    ledger = load_json(DATA / "map_quota_ledger.json")
    keys = ledger.get("keys", {})
    if not keys:
        print("  (无配额账本)")
        return
    limits = {"tencent": 9000, "amap": 4500}  # 默认限额
    for key_id, rec in keys.items():
        provider = rec.get("provider", "?")
        daily = rec.get("daily", {}).get("used", 0)
        monthly = rec.get("monthly", {}).get("used", 0)
        dead = rec.get("dead_reason", "")
        limit = limits.get(provider, 5000)
        dead_icon = "🔴" if dead else "🟢"
        if provider == "amap":
            print(f"  {dead_icon} {key_id}: 月{monthly}/4500" + (f" [{dead}]" if dead else ""))
        else:
            print(f"  {dead_icon} {key_id}: 日{daily}/{limit}" + (f" [{dead}]" if dead else ""))


# ────────────────────── 3. 数据概览 ──────────────────────
def data_status():
    section("🍜 数据概览")
    try:
        import common as C
    except Exception:
        print("  (common.py不可用)")
        return

    # 餐厅统计
    try:
        active = C.fetch_all("restaurants", select="id,opening_hours,phone,score_taste", extra="status=eq.active")
        no_hours = sum(1 for r in active if not r.get("opening_hours"))
        no_phone = sum(1 for r in active if not r.get("phone"))
        no_taste = sum(1 for r in active if not r.get("score_taste"))
        total = len(active) if active else 1
        print(f"  在营餐厅: {len(active)}")
        print(f"  营业时间空: {no_hours} ({no_hours*100//total}%)")
        print(f"  电话空: {no_phone} ({no_phone*100//total}%)")
        print(f"  口味分空: {no_taste} ({no_taste*100//total}%)")
    except Exception as e:
        print(f"  餐厅统计失败: {e}")

    # 评论统计
    try:
        reviews = C.fetch_all("reviews", select="source_platform")
        xhs = sum(1 for r in reviews if r.get("source_platform") == "xiaohongshu")
        amap = sum(1 for r in reviews if r.get("source_platform") == "amap")
        print(f"  评论总数: {len(reviews)} (小红书{xhs}/高德{amap})")
    except Exception as e:
        print(f"  评论统计失败: {e}")


# ────────────────────── 4. 费用估算 ──────────────────────
def cost_status():
    section("💰 费用估算")
    # 地图API：免费额度内，0成本
    print("  地图API: ¥0（免费额度内）")
    # 服务器：腾讯云轻量
    print("  服务器: ~¥100/月（腾讯云轻量）")
    # Apify（待启用）
    print("  Apify: 待启用（预计~$50/月）")
    # 小红书采集：0成本（自有账号）
    print("  小红书: ¥0（自有账号/待Apify切换）")


# ────────────────────── 5. 服务器状态 ──────────────────────
def server_status():
    section("🖥️ 服务器状态")
    try:
        import subprocess
        # 磁盘
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            print(f"  磁盘: {parts[2]}/{parts[1]} ({parts[4]})")
        # 容器运行时间
        r2 = subprocess.run(["cat", "/proc/1/stat"], capture_output=True, text=True, timeout=5)
        if r2.stdout:
            start_ticks = int(r2.stdout.split()[21])
            uptime_sec = start_ticks // 100  # 粗略
            hours = uptime_sec // 3600
            print(f"  容器运行: {hours}小时")
    except Exception as e:
        print(f"  (服务器状态获取失败: {e})")


# ────────────────────── 主函数 ──────────────────────
def main():
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    print(f"╔════════════════════════════════════════╗")
    print(f"║  公共状态快照 · {now}        ║")
    print(f"╚════════════════════════════════════════╝")

    collector_status()
    quota_status()
    data_status()
    cost_status()
    server_status()
    print()


if __name__ == "__main__":
    brief = "--brief" in sys.argv
    if brief:
        # 简要模式：只输出一行
        try:
            pool = load_json(DATA / "_cookie_pool_state.json")
            accounts = []
            for a, info in pool.items():
                s = info.get("status", "?")
                accounts.append(f"{a}={s}")
            print(f"账号: {'/'.join(accounts)}")
        except Exception:
            print("状态获取失败")
    else:
        main()
