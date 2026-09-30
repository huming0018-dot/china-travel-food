#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gap_pool.py — 上海美食图鉴「并行采集池」常驻守护。

职责：
  1. 周期性识别签名 API 下健康的小红书账号（code 0 健康；-100 登录过期）；
  2. 每个健康账号拉起一个 worker：gap_runner.py --pool --account <name>；
  3. worker 退出后按账号最新健康状态决定重启（账号失效则等其恢复，不反复拉起）；
  4. 写 presence 文件 POOL_RUNNING，cloud_router 见此文件即在 gap 轮次让位，避免重复采集。

部署：容器内常驻（docker-compose restart: always），日志 /app/data/pool.log。
"""
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
DATA = pathlib.Path("/app/data")
PRESENCE = DATA / "POOL_RUNNING"
LOGDIR = DATA / "pool_logs"
LOGDIR.mkdir(parents=True, exist_ok=True)

QUERIES = int(sys.argv[1]) if len(sys.argv) > 1 else 6
RESCAN_EVERY = 300  # 账号健康重扫周期（秒）


def classify():
    """返回 {account_name: code}（0=可派 worker）。逐账号绑定探测，复用 account_repair.probe
    的 GET user/me 权威判据（guest=false），不再用搜索 POST/get_search_id——
    搜索软限流会自恢复，不应据此阻止 worker 派发（与 account_repair 同一口径）。"""
    sys.path.insert(0, str(HERE))
    import account_repair
    base = pathlib.Path("/secrets/xhs_accounts")
    out = {}
    for f in sorted(base.glob("*.json")):
        try:
            out[f.stem] = account_repair.probe(f.stem, use_proxy=False)
        except Exception:
            out[f.stem] = -1
        time.sleep(2.0)
    return out


def spawn(account):
    log = open(LOGDIR / f"{account}.log", "a", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    p = subprocess.Popen(
        [sys.executable, str(HERE / "gap_runner.py"),
         "--pool", "--account", account, "--queries", str(QUERIES)],
        stdout=log, stderr=subprocess.STDOUT, env=env)
    return p


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    PRESENCE.write_text(json.dumps(
        {"started": time.strftime("%Y-%m-%d %H:%M:%S"),
         "queries": QUERIES}, ensure_ascii=False), encoding="utf-8")
    print(f"[pool] 启动，queries={QUERIES}；presence={PRESENCE}", flush=True)

    # 启动先清理上一轮残留的陈旧认领（无活 worker 持有的 claim），避免叶子被永久卡死
    try:
        import reap_claims
        n = reap_claims.reap()
        if n:
            print(f"[pool] 启动清理陈旧认领 {n} 个。", flush=True)
    except Exception as e:
        print("[pool] reap_claims 异常：", e, flush=True)

    workers = {}   # account -> Popen
    last_class = 0.0
    last_reap = 0.0
    health = {}
    try:
        while True:
            # 周期性清理 worker 崩溃后残留、无人持有的陈旧认领（每 5 分钟）
            if time.time() - last_reap > 300:
                try:
                    import reap_claims
                    n = reap_claims.reap()
                    if n:
                        print(f"[pool] 周期清理陈旧认领 {n} 个。", flush=True)
                except Exception as e:
                    print("[pool] reap_claims 异常：", e, flush=True)
                last_reap = time.time()

            if not workers or time.time() - last_class > RESCAN_EVERY:
                try:
                    health = classify()
                except Exception as e:
                    print("[pool] classify 失败：", e, flush=True)
                    health = {a: 0 for a in workers}
                last_class = time.time()

                # 只在状态变化时打印，避免空转刷屏
                if health != globals().get('_last_health', {}):
                    print("[pool] 账号状态：", health, flush=True)
                    globals()['_last_health'] = dict(health)

                # 为每个健康账号确保一个 worker
                for account, code in health.items():
                    if code == 0 and account not in workers:
                        workers[account] = spawn(account)
                        print(f"[pool] 拉起 worker: {account}", flush=True)

            # 收割已退出的 worker
            for account in list(workers):
                rc = workers[account].poll()
                if rc is not None:
                    print(f"[pool] worker {account} 退出 rc={rc}", flush=True)
                    workers.pop(account)
                    # 立即重扫，决定是否重启
                    last_class = 0.0

            # 判断是否有健康账号在跑
            healthy = [a for a, c in health.items() if c == 0] if health else []
            if not healthy:
                # 无健康账号：休眠60秒，不空转
                time.sleep(60)
            else:
                time.sleep(15)
    finally:
        for p in workers.values():
            p.terminate()
        if PRESENCE.exists():
            PRESENCE.unlink()
        print("[pool] 已停止并清除 presence。", flush=True)


if __name__ == "__main__":
    main()
