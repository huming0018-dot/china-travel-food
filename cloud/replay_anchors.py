#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""replay_anchors.py — 已由 LLM 裁决并精确通过的锚点，在 LLM 配额耗尽时，
用【确定性 SearXNG（免 LLM）】重新取回支撑 URL，按信号关键词逐条核验后补登 findings。
gate 仍独立要求每个标签 ≥2 独立来源（不同域名），不满足不登。
只写 production_model；其他字段一律不动。
"""
import sys
import time

sys.path.insert(0, "/app/cloud")
import serp_producer as SP  # noqa: E402
import ingest  # noqa: E402
import production_model_probe as PMP  # noqa: E402

NEWS_HOST = ("news", "thepaper", "people", "ifeng", "nbd", "tmtpost", "36kr",
             "bjnews", "caixin", "sina", "163", "sohu", "qq.com")

ANCHORS = [
    {"brand": "小菜园", "rids": [559, 1525], "label": "预制料理包·复热",
     "kw": ["中央厨房", "料理包", "预制", "复热", "统一配送", "工厂", "料包", "加热"]},
    {"brand": "新荣记", "rids": [871, 1370, 1376, 1377, 1380], "label": "现炒现做",
     "kw": ["现炒", "锅气", "现做", "明厨", "现烧", "堂烹", "现点", "厨师现场", "现场制作"]},
]


def evidence_class(host):
    return "新闻报道/公众号" if any(x in (host or "") for x in NEWS_HOST) else "门店/连锁/测评"


def supports(d, kws):
    blob = (d.get("snippet") or "") + " " + (d.get("source_title") or "")
    return [k for k in kws if k in blob]


def main():
    total = 0
    for a in ANCHORS:
        bterms = PMP.brand_terms(a["brand"])
        bydom = {}
        for q in PMP.standard_queries(a["brand"]):
            res, _eng = SP.search_with_failover(q)
            kept = [d for d in res if PMP._mentions_brand(d, bterms)]
            for d in kept:
                hit = supports(d, a["kw"])
                if not hit:
                    continue
                host = d.get("source_host") or ""
                d["_hit"] = hit
                if host not in bydom or len(d.get("snippet") or "") > len(
                        bydom[host].get("snippet") or ""):
                    bydom[host] = d
            time.sleep(4)
        print(f"● {a['brand']} -> {a['label']}；支撑独立域 {len(bydom)}：{list(bydom)}")
        if len(bydom) < 2:
            print("   <2 独立来源，跳过（宁空不假）")
            continue
        for rid in a["rids"]:
            for host, d in bydom.items():
                reason = (f"{evidence_class(host)}：{a['brand']}出餐方式为{a['label']}"
                          f"（命中{','.join(d['_hit'])}）")
                if ingest.append_finding(
                        rid, "production_model", a["label"], 0.9, reason,
                        source_url=d.get("source_url"),
                        source_platform="production_probe_replay"):
                    total += 1
        print()
    print("新增 findings：", total)


if __name__ == "__main__":
    main()
