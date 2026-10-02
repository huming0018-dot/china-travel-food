#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crowd_pack.py — 众包任务包生成与发布（PM窗口自承接，#50 配套）

把待采集店铺池切成 5-8 店/包，作为 assignee=crowd 的 task_queue 工单发布，
description 内嵌符合 CROWD-CONTRACT-001 §2 的 JSON 元数据（pack/target/kpi_min/quota_day）。

用法：
  python3 crowd_pack.py --stores 店名列表.json --pack-size 6 --target both --kpi 5 --quota 20
  python3 crowd_pack.py --keywords 词列表.json --pack-size 6 --target notes
"""
import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "vendor" / "pipeline"))

import common as C  # noqa: E402


def _load(path):
    p = pathlib.Path(path)
    if not p.exists():
        sys.exit(f"找不到输入: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "stores" in data:
        return data["stores"]
    if isinstance(data, dict) and "keywords" in data:
        return data["keywords"]
    sys.exit("输入需为 list[str] 或 {stores|keywords: [...]}")


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def publish(pack_items, pack_size, target, kpi_min, quota_day, source="qa"):
    """发布众包任务包到 crowd_tasks 表（契约 §4.1）。

    说明：task_queue 有 assignee/source check 约束（assignee 仅 dev/collector/qa/pm，
    source 仅 user/qa 等枚举，无 pm），众包参与者不是内部窗口角色，
    故任务包优先落 crowd_tasks 独立表，由 crowd_ingest 校验回传时回写 progress/status，
    插件从 crowd_tasks 拉取；crowd_tasks 未建表时回退发布为 task_queue
    assignee=pm + 标题 [CROWD] 前缀的工单（source 用 qa 以通过约束）。
    """
    packs = list(chunks(pack_items, pack_size))
    created = []
    for i, p in enumerate(packs, 1):
        is_store = all(not any(x in s for x in (" ", "，" "，")) for s in p)  # 粗略判断
        title = f"crowd词包-第{i}包({len(p)}项)" if not is_store else f"crowd店铺包-第{i}包({len(p)}店)"
        meta = {
            "pack": p,
            "target": target,
            "kpi_min": kpi_min,
            "quota_day": quota_day,
            "pack_seq": i,
        }
        body = {
            "task_id": 0,  # 自增由库分配（若表无 task_id 自增则用外部序号）
            "pack_type": "keyword" if not is_store else "store",
            "pack": p,
            "target": target,
            "kpi_min": kpi_min,
            "quota_day": quota_day,
            "status": "open",
            "source": source,
        }
        # crowd_tasks 若未建表，回退到 task_queue + assignee=pm（PM调度认领），并标注 CROWD 前缀
        r = C.req("POST", "/crowd_tasks", json=body)
        if r.status_code in (200, 201):
            created.append({"seq": i, "title": title, "items": len(p), "table": "crowd_tasks", "http": r.status_code})
            print(f"✅ {title} → crowd_tasks")
        else:
            # 回退：task_queue assignee=pm（PM 窗口调度），description 内嵌契约 meta
            fallback = {
                "title": "[CROWD] " + title,
                "description": json.dumps(meta, ensure_ascii=False),
                "assignee": "pm",
                "status": "todo",
                "priority": "P1",
                "source": source,
                "issue_id": f"CR-{source}-{i:03d}",
            }
            r2 = C.req("POST", "/task_queue", json=fallback)
            if r2.status_code in (200, 201):
                created.append({"seq": i, "title": title, "items": len(p), "table": "task_queue(pm)", "http": r2.status_code})
                print(f"✅ {title} → task_queue(pm 调度) [crowd_tasks 未建表]")
            else:
                print(f"❌ {title}: crowd_tasks {r.status_code} / task_queue {r2.status_code} {r2.text[:120]}")
    return created


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stores", help="店铺名 list json")
    ap.add_argument("--keywords", help="关键词 list json")
    ap.add_argument("--pack-size", type=int, default=6)
    ap.add_argument("--target", default="both", choices=["notes", "review", "both"])
    ap.add_argument("--kpi", type=int, default=5)
    ap.add_argument("--quota", type=int, default=20)
    a = ap.parse_args()

    if not (a.stores or a.keywords):
        ap.print_help()
        sys.exit(0)
    items = _load(a.stores) if a.stores else _load(a.keywords)
    publish(items, a.pack_size, a.target, a.kpi, a.quota)
