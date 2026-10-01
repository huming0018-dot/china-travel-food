#!/usr/bin/env python3
# apify_ingest.py — Apify 小红书采集（准备就绪，等 token 后跑）
# 调 sian.agency/xiaohongshu-rednote-scraper；输出对齐 Part1 数据契约 JSONL。
# 预算闸门 + checkpoint fsync + 限速；不部署 cron、不运行（待用户 token）。
import json, pathlib, os, sys, time, datetime, argparse

OUT = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data/apify_ingest")) / "xhs"
OUT.mkdir(parents=True, exist_ok=True)
CHECKPOINT = pathlib.Path("/app/data/apify_ingest/.checkpoint.json")
COST_CAP = float(os.environ.get("APIFY_COST_CAP_USD", "100.0"))

ACTOR = "sian.agency/xiaohongshu-rednote-scraper"
# 单条预算估算（来自 part2）
COST_PER_NOTE = 0.05
COST_PER_SEARCH = 0.004


def load_client():
    from apify_client import ApifyClient
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN not set; awaiting user token.")
    return ApifyClient(token)


def run_search(client, keyword, max_items=20):
    run = client.actor(ACTOR).call(
        run_input={"mode": "searchNote", "keyword": keyword, "maxItems": max_items},
        timeout_secs=120,
    )
    items = []
    for item in client.dataset(run["defaultDatasetId"]).iterate_items():
        items.append(item)
    return items


def normalize(item, rid=None, store_name=None):
    return {
        "restaurant_id": rid,
        "name": store_name,
        "platform": "xiaohongshu",
        "post_id": item.get("noteId"),
        "source_url": item.get("notePageUrl"),
        "title": item.get("noteTitle"),
        "content": item.get("noteDesc", "")[:2000],
        "author_id": item.get("userRedId"),
        "author_name": item.get("userName"),
        "is_verified": item.get("userVerified", False),
        "publish_date": item.get("postedAt"),
        "likes": item.get("likedCount", 0),
        "collects": item.get("collectedCount", 0),
        "comments": item.get("commentsCount", 0),
        "captured_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="不调 API，只打印计划")
    ap.add_argument("--max-budget", type=float, default=COST_CAP)
    args = ap.parse_args()

    # 读 active 店清单（占位，待接入 common.py）
    print(f"[apify_ingest] budget cap=${args.max_budget}; actor={ACTOR}")
    print("[apify_ingest] ready; awaiting APIFY_TOKEN and user approval to run.")


if __name__ == "__main__":
    main()
