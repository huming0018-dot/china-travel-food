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
    """返回 {account_name: code}。逐账号【绑定】探测，-100 不会被轮换掩盖。"""
    sys.path.insert(0, str(HERE))
    import xhs_api
    base = pathlib.Path("/secrets/xhs_accounts")
    out = {}
    for f in sorted(base.glob("*.json")):
        api = xhs_api.XhsApi(min_gap=3.0, pin=f.stem)
        if not api.accounts:
            continue
        j = api._send(
            "POST", "/api/sns/web/v1/search/notes",
            payload={"keyword": "拉面", "page": 1, "page_size": 5,
                     "search_id": api.sign.get_search_id(),
                     "sort": "general", "note_type": 0})
        out[f.stem] = j.get("code", -1)
        time.sleep(3.0)
    return out


def spawn(account):
    log = open(LOGDIR / f"{account}.log", "a", encoding="utf-8")
    p = subprocess.Popen(
        [sys.executable, str(HERE / "gap_runner.py"),
         "--pool", "--account", account, "--queries", str(QUERIES)],
        stdout=log, stderr=subprocess.STDOUT)
    return p


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    PRESENCE.write_text(json.dumps(
        {"started": time.strftime("%Y-%m-%d %H:%M:%S"),
         "queries": QUERIES}, ensure_ascii=False), encoding="utf-8")
    print(f"[pool] 启动，queries={QUERIES}；presence={PRESENCE}", flush=True)

    workers = {}   # account -> Popen
    last_class = 0.0
    health = {}
    try:
        while True:
            if not workers or time.time() - last_class > RESCAN_EVERY:
                try:
                    health = classify()
                except Exception as e:
                    print("[pool] classify 失败：", e, flush=True)
                    health = {a: 0 for a in workers}
                last_class = time.time()
                print("[pool] 账号状态：", health, flush=True)

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

            if not health:
                print("[pool] 未发现任何账号，60s 后重试。", flush=True)
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
