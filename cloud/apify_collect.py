#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apify_collect.py — Apify 托管采集器（小红书为主，#15，P1）。

为什么存在：
  本地 cookie 在数据中心 IP 反复失效、账号被风控（已验证死路）。Apify 由托管住宅代理 +
  actor 自签名完成抓取，**免 cookie、错误行不计费**。本模块是 Apify 的唯一调用入口，
  采集结果先过 data_gate，再交 atlas_write 幂等入库。

默认 actor：sian.agency/xiaohongshu-rednote-scraper（用户量最大、活跃、免 cookie）。
  操作：searchNote / noteDetail / noteComments / userDetail / userNotes / searchUser。

流程（纯 REST，requests，无 SDK 依赖）：
  start_run(actor, run_input) → wait_for_run(run_id) → get_dataset(dataset_id)
  → normalize(items) → data_gate.admit → 落 JSONL（--commit 才写 reviews）。

用法：
  export APIFY_TOKEN=apify_api_xxx
  python3 apify_collect.py search --keyword "上海 本帮菜" --limit 20
  python3 apify_collect.py detail --url "https://www.xiaohongshu.com/explore/<id>?xsec_token=..."
  python3 apify_collect.py describe            # 拉取默认 actor 输入 schema，核对字段名
"""
import argparse as _argparse
import json as _json
import pathlib as _pl
import sys as _sys
import time as _time

import requests as _requests

HERE = _pl.Path(__file__).resolve().parent
_sys.path.insert(0, str(HERE))

import common_core as core  # noqa: E402
import data_gate as gate    # noqa: E402

API = "https://api.apify.com/v2"
DEFAULT_ACTOR = "sian.agency/xiaohongshu-rednote-scraper"
PLATFORM = "xiaohongshu"

# 候选 actor（part2 调研）
ACTORS = {
    "sian": "sian.agency/xiaohongshu-rednote-scraper",
    "atomus": "atomus/xiaohongshu-scraper",
    "zen": "zen-studio/rednote-search-scraper",
}


# ────────────────────── token / 基础 ──────────────────────
def _token():
    t = core.config("APIFY_TOKEN", "")
    if not t:
        raise RuntimeError("缺少 APIFY_TOKEN（配置环境变量或写入 cloud/env.sh）")
    return t


def _apify(method, path, **kw):
    url = API + path
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}token={_token()}"
    r = _requests.request(method, url, timeout=kw.pop("timeout", 60), **kw)
    r.raise_for_status()
    return r.json().get("data", {})


# ────────────────────── actor 输入 schema 核对 ──────────────────────
def describe_input(actor=DEFAULT_ACTOR):
    """拉取 actor 输入 schema（首次接入/字段不确定时核对，避免用错 key 白跑计费）。"""
    try:
        d = _apify("GET", f"/acts/{actor}/input-schema")
        return d if isinstance(d, dict) else _json.loads(d)
    except Exception as e:
        return {"error": repr(e)[:120]}


# ────────────────────── run 生命周期 ──────────────────────
def start_run(run_input: dict, actor=DEFAULT_ACTOR):
    d = _apify("POST", f"/acts/{actor}/runs", json=run_input, timeout=90)
    core.log("info", "Apify run 已启动", run_id=d.get("id"))
    return d.get("id")


def wait_for_run(run_id, poll=8, max_wait=1800):
    """轮询到终态（SUCCEEDED/FAILED/ABORTED/TIMED-OUT）。"""
    deadline = _time.time() + max_wait
    while _time.time() < deadline:
        d = _apify("GET", f"/actor-runs/{run_id}")
        status = d.get("status")
        if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            return d
        _time.sleep(poll)
    raise TimeoutError(f"run {run_id} 超过 {max_wait}s 未结束")


def get_dataset(run_data):
    ds = run_data.get("defaultDatasetId")
    items = _apify("GET", f"/datasets/{ds}/items",
                   params={"clean": "true", "format": "json"}, timeout=120)
    return items if isinstance(items, list) else []


# ────────────────────── run_input 构造（sian 默认） ──────────────────────
def build_input(action, **kw):
    """构造 sian actor 输入。字段以 describe_input 拉到的实时 schema 为准。"""
    inp = {"action": action}
    if action == "searchNote":
        inp.update({"keyword": kw["keyword"], "searchType": "note",
                    "sortType": kw.get("sort", "general"), "page": kw.get("page", 1)})
    elif action == "noteDetail":
        inp.update({"noteUrl": kw["url"]})
    elif action == "noteComments":
        inp.update({"noteId": kw["note_id"], "page": kw.get("page", 1)})
    elif action == "userDetail":
        inp.update({"userId": kw["user_id"]})
    elif action == "userNotes":
        inp.update({"userId": kw["user_id"], "page": kw.get("page", 1)})
    elif action == "searchUser":
        inp.update({"keyword": kw["keyword"]})
    else:
        raise ValueError(f"未知 action {action}")
    if kw.get("limit"):
        inp["maxItems"] = kw["limit"]
    return inp


# ────────────────────── 归一到 reviews 数据契约 ──────────────────────
def _pick(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d.get(k)
    return default


def normalize_note(item: dict):
    """把不同 actor 的笔记字段归一为 reviews 契约（part1 §1.2）。无 source_url 则丢弃。"""
    user = item.get("user") or {}
    post_id = _pick(item, "noteId", "id", "note_id")
    url = _pick(item, "notePageUrl", "url", "note_url")
    if not url and post_id:
        url = f"https://www.xiaohongshu.com/explore/{post_id}"
    rec = {
        "source_platform": PLATFORM,
        "post_id": str(post_id) if post_id else "",
        "source_url": url or "",
        "title": _pick(item, "noteTitle", "title", default=""),
        "content": _pick(item, "noteDesc", "desc", "description", default=""),
        "author_id": _pick(user, "user_id", "userId", "id", default=""),
        "author_name": _pick(user, "nickname", "userName", "name", default=""),
        "is_verified": _pick(user, "verified", "userVerified", default=False),
        "publish_date": _pick(item, "postedAt", "timestamp", "time", default=""),
        "likes": _pick(item, "likedCount", "liked_count", default=0),
        "collects": _pick(item, "collectedCount", "collected_count", default=0),
        "comments_count": _pick(item, "commentsCount", "comments_count", default=0),
        "shares": _pick(item, "sharedCount", "shared_count", default=0),
        "images": _pick(item, "noteImageUrls", "images", default=[]),
        "video_url": _pick(item, "video_url", "videoUrl", default=""),
        "poi_name": _pick(item, "poi_name", "location", default=""),
        "xsec_token": _pick(item, "xsecToken", "xsec_token", default=""),
    }
    return rec


def normalize_comment(item: dict, post_id=""):
    user = item.get("user") or {}
    return {
        "source_platform": PLATFORM, "kind": "comment", "post_id": str(post_id),
        "comment_id": str(_pick(item, "id", "comment_id", default="")),
        "source_url": _pick(item, "url", default=""),
        "author_id": _pick(user, "user_id", "id", default=""),
        "author_name": _pick(user, "nickname", "name", default=""),
        "content": _pick(item, "content", "text", default=""),
        "comment_date": _pick(item, "timestamp", "time", default=""),
        "likes": _pick(item, "like_count", "likedCount", default=0),
    }


# reviews 行的轻量闸 schema（source_url 必填）
REVIEW_SCHEMA = {
    "required": ["source_platform", "source_url"],
    "fields": {
        "source_platform": {"type": "str"},
        "source_url": {"type": "str", "url": True},
        "likes": {"type": "int", "min": 0},
        "collects": {"type": "int", "min": 0},
        "comments_count": {"type": "int", "min": 0},
    },
}


# ────────────────────── 高层采集 ──────────────────────
def collect(run_input, actor=DEFAULT_ACTOR, out_dir=""):
    """启动→等待→下载→归一→过闸。返回 gated 结果与 run 元信息。"""
    run_id = start_run(run_input, actor)
    run_data = wait_for_run(run_id)
    if run_data.get("status") != "SUCCEEDED":
        core.notify.warn(f"Apify run {run_id} 终态 {run_data.get('status')}",
                         key=f"apify:{run_id}")
    items = get_dataset(run_data)
    raw = [normalize_note(it) for it in items]
    raw = [r for r in raw if r["source_url"]]
    result = gate.admit(raw, schema=REVIEW_SCHEMA, do_cross=False)
    meta = {"run_id": run_id, "status": run_data.get("status"),
            "items": len(items), "cost_usd": run_data.get("usageTotalUsd"),
            "report": gate.report(result)}
    if out_dir:
        _dump(out_dir, result, run_id)
    core.log("info", "Apify 采集完成", **meta["report"])
    return result, meta


def _dump(out_dir, result, run_id):
    d = _pl.Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{run_id}_accepted.jsonl").write_text(
        "\n".join(_json.dumps(x["record"], ensure_ascii=False)
                  for x in result["accepted"]), encoding="utf-8")
    (d / f"{run_id}_rejected.jsonl").write_text(
        "\n".join(_json.dumps(x, ensure_ascii=False) for x in result["rejected"]),
        encoding="utf-8")


# ────────────────────── CLI ──────────────────────
def main():
    ap = _argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("describe")

    s = sub.add_parser("search")
    s.add_argument("--keyword", required=True)
    s.add_argument("--sort", default="general")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--actor", default="sian")
    s.add_argument("--out", default="/app/data/apify_ingest/xiaohongshu")

    d = sub.add_parser("detail")
    d.add_argument("--url", required=True)
    d.add_argument("--actor", default="sian")
    d.add_argument("--out", default="/app/data/apify_ingest/xiaohongshu")

    args = ap.parse_args()

    if args.cmd == "describe":
        print(_json.dumps(describe_input(), ensure_ascii=False, indent=1))
        return
    if args.cmd == "search":
        inp = build_input("searchNote", keyword=args.keyword, sort=args.sort,
                          limit=args.limit)
    else:
        inp = build_input("noteDetail", url=args.url)

    actor = ACTORS.get(args.actor, args.actor)
    result, meta = collect(inp, actor=actor, out_dir=args.out)
    print(_json.dumps(meta, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
