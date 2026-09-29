#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_chat_providers.py — 网页版模型通道（复用用户已有网页会员额度 + 联网搜索，
不走 API、不买 key）。与 model_providers.py 的 API 通道输出【同一 schema】，
结果只 upsert lead_hypotheses（hid 幂等），绝不直写事实表。

方法论：references/llm-sourcing-fleet.md（网页层）+ browser-use-automation-mac。

============================================================
认识论红线（与 model_providers 一致，不可违反）：
1. 网页模型输出是【线索】，绝不直写事实表，只进 lead_hypotheses。
2. 多站点/多模型一致只作【先验】（语料同源），晋升仍需权威 URL 或 ≥2 独立声音。
3. 联网来源必须逐条落 source_url；无 URL 不作证实（confirm_voices=0）。
4. 宁空不假：无记忆显式 null，禁止编造人名/年份/原话；冲突留 unverified。
5. 浏览器单实例串行、ref-first、动作间礼貌等待、遇反爬退避不硬刷。
============================================================

设计：网页交互在本机受控浏览器（seed_browser_use, plane=bu）完成；
本模块只负责把「浏览器采回的回答 JSON」归一成与 API 通道一致的账本行，
并复用 hae_engine.norm_row/upsert_rows 幂等入表。采集到的原始 JSONL 落到
/app/data/hae/web_recall_*.jsonl（命名卷），再 --web-ingest。
"""
import argparse
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import hae_engine as H  # noqa: E402  复用 norm_row / upsert_rows / HYP_TABLE / today

# ---------------------------------------------------------------------------
# 网页站点注册表：url / 是否需登录 / 联网搜索开关位置（采集时人工/bu 开启）
# ---------------------------------------------------------------------------
WEB_SITES = {
    "doubao": {
        "label": "豆包网页版",
        "url": "https://www.doubao.com/chat/",
        "login": "需登录（用户会员）；联网=对话框上方/工具里开启「联网搜索」",
        "web_search": "对话框附近「联网搜索」开关，发送前确认开启",
    },
    "kimi": {
        "label": "Kimi 网页版",
        "url": "https://www.kimi.com/",
        "login": "需登录（发送即弹微信扫码/手机验证码）",
        "web_search": "对话框开启「联网搜索」；Kimi 自带来源侧栏",
    },
    "deepseek": {
        "label": "DeepSeek 网页版",
        "url": "https://chat.deepseek.com/",
        "login": "需登录（直接跳 /sign_in，手机验证码/微信扫码）",
        "web_search": "DeepSeek-R1/对话可联网时读取引用来源",
    },
    # WorkBuddy：仅桌面客户端、无可控浏览器网页版 → 跳过（不做桌面 GUI）。
    "workbuddy": {
        "label": "WorkBuddy",
        "url": None,
        "login": "仅桌面客户端，无受控浏览器网页版 → 跳过（不做桌面 GUI）",
        "web_search": None,
    },
}


def normalize_web_row(site: str, model_name: str, item: dict,
                      sources: list, seed_name: str, prompt_hash: str) -> dict:
    """把单条网页模型输出归一成账本行（与 model_providers.fleet_recall 同 schema）。
    - proposed_by 记 web + 站点 + 模型 + 日期，可复现。
    - 联网来源必挂 confirmed_source_urls；无 URL 不作证实（voices=0）。
    """
    urls = [u for u in (sources or []) if isinstance(u, str) and u.startswith("http")]
    row = {
        "subject_type": item.get("subject_type", "restaurant"),
        "subject_name": item.get("subject_name", seed_name),
        "relation": item.get("relation", "related_to"),
        "object": item.get("object"),
        "when": item.get("when"),
        "claim_text": item.get("claim_text") or "(网页模型未给 claim)",
        "confidence": float(item.get("confidence", 0.30)),
        "known_vs_inferred": item.get("known_vs_inferred", "推断"),
        "status": "hypothesized",
        "confirm_queries": item.get("confirm_queries", []),
        "falsify_queries": item.get("falsify_queries") or ["(缺证伪)"],
        "confirmed_source_urls": urls,
        "confirm_voices": 1 if urls else 0,   # 带 URL=1 个联网线索；不替代权威取证
        "proposed_by": {"channel": "web", "site": site,
                        "model": model_name, "prompt_hash": prompt_hash,
                        "date": H.today()},
        "is_seed": False,
    }
    return H.norm_row(row)


def web_recall_to_rows(captured: dict) -> list:
    """captured = {site, model_name, prompt_hash, sources[], items[]}
    （即浏览器一次探针采回的整包）。逐 item 归一。"""
    rows = []
    for it in captured.get("items", []):
        if not isinstance(it, dict):
            continue
        rows.append(normalize_web_row(
            captured.get("site", "web"),
            captured.get("model_name", "web-chat"),
            it,
            captured.get("sources", []),
            captured.get("seed_name", ""),
            captured.get("prompt_hash", hashlib.sha1(
                json.dumps(captured.get("items", []),
                           ensure_ascii=False).encode()).hexdigest()[:12]),
        ))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--web-ingest", help="浏览器采回的整包 JSONL（每行一个 captured dict）")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--web-sites", action="store_true", help="打印网页站点登录/联网说明（不打印凭据）")
    args = ap.parse_args()

    if args.web_sites:
        print(json.dumps(WEB_SITES, ensure_ascii=False, indent=2))
        return

    if args.web_ingest:
        rows = []
        for line in pathlib.Path(args.web_ingest).read_text(
                encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            captured = json.loads(line)
            rows.extend(web_recall_to_rows(captured))
        res = H.upsert_rows(rows, apply=args.apply)
        print(json.dumps({"n_rows": len(rows), "upsert": res},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
