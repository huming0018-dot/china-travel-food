#!/usr/bin/env python3
"""
crowd_smoke_monitor.py — 众包美食家回流 smoke 监听器（PM 侧）

用途：
  001 参与者 smoke 期间全程监听回流是否真实落地：
    - crowd_proofs 是否有新行（gate_status 分布）
    - crowd_tasks.progress 是否随回传增长
    - crowd_participants.total_effective 是否累计
    - 输出人类可读差异（本轮 vs 基线）

用法：
  export HTTPS_PROXY=http://127.0.0.1:7897
  python3 cloud/crowd_smoke_monitor.py            # 单次快照（对照上一快照差异）
  python3 cloud/crowd_smoke_monitor.py --loop 600 # 每 600s 轮询，Ctrl-C 退出
  python3 cloud/crowd_smoke_monitor.py --json     # 输出 JSON（供脚本消费）

依赖：
  Management API token 路径固定（sessions 目录），或环境变量 SBP_TOKEN
"""
import json
import os
import sys
import time
import urllib.request

TOKEN_PATH = "/Users/deuce/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.sessions/38444479935001090/agents/m_0cwp6SalkKS/system/sbp_token.txt"
PROJECT = "bdwrhshgdeghgyzwpxnl"
SNAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data", "crowd_smoke_last.json")


def get_token():
    t = os.environ.get("SBP_TOKEN")
    if t:
        return t
    with open(TOKEN_PATH) as f:
        return f.read().strip()


def sql(query):
    req = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{PROJECT}/database/query",
        data=json.dumps({"query": query}).encode(), method="POST",
        headers={"Authorization": "Bearer " + get_token(), "Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=60)
    return json.loads(r.read().decode())


def snapshot():
    proofs = sql(
        "select count(*) as n, "
        "coalesce(sum(case when gate_status='accepted' then 1 else 0 end),0) as acc, "
        "coalesce(sum(case when gate_status='rejected' then 1 else 0 end),0) as rej "
        "from crowd_proofs;")[0]
    tasks = sql(
        "select coalesce(sum(progress),0) as total_progress, "
        "coalesce(sum(case when status='open' then 1 else 0 end),0) as open_n, "
        "coalesce(sum(case when status='done' then 1 else 0 end),0) as done_n "
        "from crowd_tasks;")[0]
    parts = sql(
        "select count(*) as n, coalesce(sum(total_effective),0) as effective "
        "from crowd_participants;")[0]
    recent = sql(
        "select participant_id, gate_status, created_at from crowd_proofs "
        "order by created_at desc limit 5;")
    return {
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "proofs": {"n": proofs["n"], "accepted": proofs["acc"], "rejected": proofs["rej"]},
        "tasks": {"progress": tasks["total_progress"], "open": tasks["open_n"], "done": tasks["done_n"]},
        "participants": {"n": parts["n"], "effective": parts["effective"]},
        "recent_proofs": recent,
    }


def diff(prev, cur):
    """prev→cur 的变化（用于判断回流是否真实落地）"""
    d = {}
    for k in ("proofs", "tasks", "participants"):
        if prev and prev.get(k) != cur.get(k):
            d[k] = {"from": prev.get(k), "to": cur.get(k)}
    return d


def main():
    as_json = "--json" in sys.argv
    loop = None
    if "--loop" in sys.argv:
        i = sys.argv.index("--loop")
        loop = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 300

    prev = None
    if os.path.exists(SNAP_FILE):
        try:
            prev = json.load(open(SNAP_FILE))
        except Exception:
            prev = None

    cur = snapshot()
    os.makedirs(os.path.dirname(SNAP_FILE), exist_ok=True)
    json.dump(cur, open(SNAP_FILE, "w"))

    d = diff(prev, cur)
    if as_json:
        print(json.dumps({"cur": cur, "diff": d}, ensure_ascii=False))
        return

    print("── 众包美食家回流监听 ─────────────────────")
    print(f"  时间: {cur['at']}")
    print(f"  proofs: {cur['proofs']['n']} 条 (accepted {cur['proofs']['accepted']} / rejected {cur['proofs']['rejected']})")
    print(f"  tasks: progress 合计 {cur['tasks']['progress']} (open {cur['tasks']['open']} / done {cur['tasks']['done']})")
    print(f"  参与者: {cur['participants']['n']} 人, 累计有效 {cur['participants']['effective']}")
    if cur["recent_proofs"]:
        print("  最近回传:")
        for r in cur["recent_proofs"]:
            print(f"    {r['participant_id']} {r['gate_status']} @ {r['created_at']}")
    if d:
        print("  ◆ 自上次快照变化:")
        for k, v in d.items():
            print(f"    {k}: {v['from']} → {v['to']}")
    else:
        print("  （无变化）")
    if loop:
        print(f"  继续监听中，每 {loop}s 刷新（Ctrl-C 退出）...")
        while True:
            time.sleep(loop)
            prev2 = cur
            cur = snapshot()
            json.dump(cur, open(SNAP_FILE, "w"))
            d2 = diff(prev2, cur)
            if d2:
                print(f"  [{cur['at']}] 变化: {json.dumps(d2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
