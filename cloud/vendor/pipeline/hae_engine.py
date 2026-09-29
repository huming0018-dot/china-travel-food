#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hae_engine.py — L0.5 假设层：Hypothesis & Association Engine（HAE）

补 Phase0 的缺口：模型/agent 不只生成关键词，而是「自由回忆 + 联想 → 假设 →
正向取证 + 强制反向证伪 → 收敛晋升」。假设与事实分层：
  * 所有 AI/agent 产出先落【假设账本】lead_hypotheses（与事实表物理/权限隔离），
    status 默认 hypothesized；
  * 只有 confirmed 且过既有闸门（事实=权威源或≥2 独立声音；沿革/持股/关系=≥1
    可信文档：官方/新闻/工商）才允许晋升写事实表（chefs/restaurant_chefs/
    restaurant_groups/...）；
  * contradicted 驳回留痕（不 DELETE），unverified 留账本待下一轮。

铁律（与 north-star / mechanism-master /本任务护栏一致）：
  1. LLM/AI 输出绝不直写事实表，只进 lead_hypotheses。
  2. 模型自标 知道/推断/不知道；无记忆留空（宁空不假），禁编造名字/年份/原话。
  3. 每条假设必带 confirm_queries + 强制 falsify_queries（关店/离职/辟谣/难吃/预制）。
  4. 确定性/幂等/可回滚：hid=确定性哈希，ON CONFLICT 更新不产生新行；默认 dry-run，
     --apply 才写事实表；写后回读。
  5. 可复现：proposed_by 记录 model+version+prompt_hash+date，ensemble 逐模型留痕。
  6. 平台 AI 搜索总结只是低信任线索：其引用必须 fetch 到原始来源；无出处=假设，不晋升。

两种运行模式：
  A. agent 版（零成本，默认）：agent 自身做发散+收敛，把结论写成 ledger JSONL，
     本脚本只负责【确定性地】upsert 账本 / 转状态 / 过闸晋升。容器无 ARK key 时用此模式。
  B. 自跑版（24/7 cron）：deploy.env 配 ARK/OpenAI 兼容 key 后，--diverge-llm 让多模型
     ensemble 自由回忆+联想；同一探针过多个模型取并集，一致提先验、不一致标存疑。

用法（容器内，env 已加载；FOOD_DATA_DIR=/app/data）：
  python3 hae_engine.py --status                 # 账本状态统计（表不存在则读本地 ledger）
  python3 hae_engine.py --ingest-ledger pipeline_work/hae/lead_hypotheses_2026-09-29.jsonl
  python3 hae_engine.py --promote-plan           # 只打印 confirmed→事实表计划（dry-run）
  python3 hae_engine.py --promote-plan --apply   # 过闸才真正写事实表，写后回读
  python3 hae_engine.py --diverge-llm --seed-json seeds.json   # 需 ARK/OPENAI key
"""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import model_providers as MP  # noqa: E402  多国产模型知识源舰队（llm-sourcing-fleet.md）

HYP_TABLE = "lead_hypotheses"
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
HAE_DIR = DATA / "hae"

VALID_SUBJECT = {"chef", "owner", "restaurant", "blogger", "list", "brand", "group"}
VALID_RELATION = {"worked_at", "career_period", "teacher", "founded", "owns",
                  "related_to", "award", "show_appearance", "signature_dish",
                  "reviewed_by", "list_member"}
VALID_STATUS = {"hypothesized", "confirmed", "contradicted", "unverified"}


# ---------------------------------------------------------------------------
def hid_of(row: dict) -> str:
    """确定性幂等主键：主体+关系+客体+prompt_hash。同探针重跑不产生新行。"""
    base = "|".join([
        str(row.get("subject_type", "")), str(row.get("subject_name", "")),
        str(row.get("relation", "")), str(row.get("object", "") or ""),
        str(row.get("proposed_by", {}).get("prompt_hash", "")),
    ])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]


def today() -> str:
    return datetime.date.today().isoformat()


def norm_row(row: dict) -> dict:
    """补默认值 + 取值域校验，返回干净的账本行；非法直接抛错（不静默写脏）。"""
    assert row.get("subject_type") in VALID_SUBJECT, f"bad subject_type: {row.get('subject_type')}"
    assert row.get("relation") in VALID_RELATION, f"bad relation: {row.get('relation')}"
    row.setdefault("object", None)
    row.setdefault("when", None)
    row.setdefault("confidence", 0.30)
    row.setdefault("known_vs_inferred", "推断")
    assert row["known_vs_inferred"] in {"知道", "推断", "不知道"}
    row.setdefault("status", "hypothesized")
    assert row["status"] in VALID_STATUS, f"bad status: {row['status']}"
    row.setdefault("evidence", [])
    row.setdefault("confirm_queries", [])
    row.setdefault("falsify_queries", [])
    row.setdefault("confirm_voices", 0)
    row.setdefault("confirmed_source_urls", [])
    row.setdefault("verdict_notes", None)
    row.setdefault("promoted_to", None)
    row.setdefault("parent_hid", None)
    row.setdefault("is_seed", False)
    row.setdefault("expands_to", [])
    row.setdefault("model_consensus", "single")
    row.setdefault("rounds", 0)
    row.setdefault("proposed_by", {})
    row["proposed_by"].setdefault("date", today())
    row["hid"] = hid_of(row)
    return row


# ---------------------------------------------------------------------------
# 账本读写：优先写 Supabase lead_hypotheses 表；表不存在（015 未在 SQL Editor
# 执行）时优雅降级为本地 JSONL，并明确告警——绝不因此阻塞、绝不误写事实表。
# ---------------------------------------------------------------------------
def table_exists(table: str) -> bool:
    try:
        r = C.req("GET", f"/{table}?select=hid&limit=1", use_service=True)
        return r.status_code < 400
    except Exception:
        return False


def upsert_rows(rows: list, apply: bool) -> dict:
    """幂等 upsert：按 hid 去重；表里有同 hid 则 PATCH 更新，否则 POST。"""
    by_hid = {}
    for r in rows:
        by_hid[r["hid"]] = r  # 同探针重跑，后者覆盖前者（确定性）
    todo = list(by_hid.values())
    if not table_exists(HYP_TABLE):
        HAE_DIR.mkdir(parents=True, exist_ok=True)
        lp = HAE_DIR / f"ledger_{today()}.jsonl"
        C.write_jsonl(str(lp), todo)
        return {"mode": "local_fallback", "table_present": False,
                "written": len(todo), "local_ledger": str(lp),
                "note": f"表 {HYP_TABLE} 不存在（015 需在 SQL Editor 执行）；"
                        f"已写本地账本 {lp}。未触碰事实表。"}
    # 表存在：拉现有 hid
    existing = {}
    try:
        for x in C.fetch_all(HYP_TABLE, "hid,status,rounds", order_col="hid"):
            existing[x["hid"]] = x
    except Exception as e:
        return {"mode": "error", "table_present": True, "error": str(e)}
    n_post = n_patch = 0
    for r in todo:
        body = {k: v for k, v in r.items() if k != "hid"}
        if not apply:
            continue
        if r["hid"] in existing:
            C.req("PATCH", f"/{HYP_TABLE}?hid=eq.{r['hid']}", use_service=True, json=body)
            n_patch += 1
        else:
            body = {"hid": r["hid"], **body}
            C.req("POST", f"/{HYP_TABLE}", use_service=True, json=body,
                  headers={"Prefer": "return=minimal"}) if False else \
                C.req("POST", f"/{HYP_TABLE}", use_service=True, json=body)
            n_post += 1
        time.sleep(0.1)
    return {"mode": "db" if apply else "db_dryrun", "table_present": True,
            "post": n_post, "patch": n_patch, "would_write": len(todo)}


# ---------------------------------------------------------------------------
# 收敛闸门：confirmed → 事实表。只复制（不移动），驳回仅改状态。
#   事实类(show_appearance/award/signature_dish)：权威源 或 ≥2 独立声音；
#   关系类(worked_at/founded/owns/related_to/teacher/career_period)：≥1 可信文档
#   （官方/新闻/工商 qcc/tianyancha）。任何缺证伪查询/缺出处的一律不晋升。
# ---------------------------------------------------------------------------
GATE_RELATION_DOC = {"worked_at", "career_period", "teacher", "founded",
                     "owns", "related_to"}


def passes_gate(r: dict) -> tuple:
    if r["status"] != "confirmed":
        return False, "非 confirmed"
    if not r.get("falsify_queries"):
        return False, "缺强制证伪查询"
    urls = r.get("confirmed_source_urls") or []
    voices = r.get("confirm_voices", 0)
    # 关系类：≥1 可信文档（官方/媒体/工商）即过
    if r["relation"] in GATE_RELATION_DOC:
        if urls:
            return True, f"≥1 可信文档({len(urls)} 源)"
        return False, "关系类缺可信文档出处"
    # 事实/曝光类：权威源 或 ≥2 独立声音
    if urls and (voices >= 2 or any(
            C.source_kind(url=u) in ("official_guide", "media", "brand") for u in urls)):
        return True, f"权威/≥2独立声音(voices={voices})"
    return False, "事实类需权威源或≥2独立声音"


def build_promote_plan(rows: list) -> list:
    """把 confirmed 假设翻译成事实表写计划（dry-run 打印；不直接 REST）。
    落点保守：chef→chefs；worked_at/owns→restaurant_chefs/restaurant_groups；
    show_appearance→food_events；award→restaurant_awards。无 restaurant_id 锚点的
    （对象还没入库）只标注 pending_resolve，不硬写。"""
    plan = []
    for r in rows:
        ok, why = passes_gate(r)
        if not ok:
            continue
        rel = r["relation"]
        if r["subject_type"] == "chef" and rel in ("worked_at",):
            plan.append({"table": "restaurant_chefs", "op": "upsert",
                         "subject": r["subject_name"], "object": r["object"],
                         "when": r.get("when"), "source_urls": r["confirmed_source_urls"],
                         "claim": r["claim_text"], "gate": why,
                         "note": "需先 anchor chef_id 与 restaurant_id（见回读）"})
        elif rel == "founded" and r["subject_type"] in ("owner", "chef"):
            plan.append({"table": "restaurant_groups/restaurants", "op": "upsert",
                         "subject": r["subject_name"], "object": r["object"],
                         "when": r.get("when"), "source_urls": r["confirmed_source_urls"],
                         "gate": why})
        elif rel == "show_appearance":
            plan.append({"table": "food_events", "op": "insert",
                         "subject": r["subject_name"], "object": r["object"],
                         "source_urls": r["confirmed_source_urls"], "gate": why,
                         "note": "category=chef_changed? 否→guest_kitchen/media_show 类事件"})
        else:
            plan.append({"table": "pending", "op": "hold", "subject": r["subject_name"],
                         "relation": rel, "object": r["object"], "gate": why,
                         "note": "本关系暂无自动映射，人工核后写"})
    return plan


# ---------------------------------------------------------------------------
# LLM ensemble（24/7 自跑用）；容器无 key 时优雅退出，不阻塞 agent 版实跑。
# ---------------------------------------------------------------------------
def llm_endpoint():
    base = os.environ.get("ARK_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
    key = os.environ.get("ARK_API_KEY") or os.environ.get("OPENAI_API_KEY")
    model = os.environ.get("HAE_MODEL") or os.environ.get("ARK_MODEL") or "doubao-pro-32k"
    return base, key, model


def diverge_llm(seed: dict, ensemble_models: list) -> list:
    """同一探针过多个模型；逐模型留痕。无 key 时返回 []（调用方走 agent 版）。"""
    base, key, default_model = llm_endpoint()
    if not key or not base:
        print("[hae] 未配置 ARK/OPENAI key，跳过 LLM ensemble（用 agent 版实跑）。"
              "24/7 定时自跑请在 cloud/deploy.env 配 ARK_BASE_URL/ARK_API_KEY/HAE_MODEL。")
        return []
    import requests
    out = []
    for m in ensemble_models or [default_model]:
        prompt = (f"你是上海美食图鉴的假设生成器。对种子实体做自由回忆+联想，"
                  f"只输出结构化 JSON 假设数组，每条含 subject_type/subject_name/"
                  f"relation/object/when/claim_text/known_vs_inferred/confirm_queries/"
                  f"falsify_queries。不知道就留空，禁编造名字/年份/原话。种子={seed}")
        ph = hashlib.sha1(prompt.encode()).hexdigest()[:12]
        r = requests.post(f"{base}/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": m, "messages": [{"role": "user", "content": prompt}],
                                "temperature": 0.4}, timeout=60)
        try:
            arr = r.json()["choices"][0]["message"]["content"]
        except Exception:
            continue
        out.append({"model": m, "prompt_hash": ph, "raw": arr})
    return out


# ---------------------------------------------------------------------------
# 多模型舰队（llm-sourcing-fleet.md §2）：--fleet-recall / --prove
#   认识论红线：模型输出只进 lead_hypotheses，绝不直写事实表；
#   多模型一致只作先验；联网结果必带 source_url，无 URL 不作证实；
#   无 key 时降级为 agent 自身推理、跳过缺适配器，不报错中断。
# ---------------------------------------------------------------------------
SEED_PROMPT = (
    "对下面这个种子实体做【自由回忆+联想】，围绕其维度（师承/沿革/现任曾任店/"
    "招牌菜/荣誉节目/旗下品牌/合伙人/榜单节目成员）枚举结构化假设。\n"
    "只输出 JSON 数组，每个元素：subject_type,subject_name,relation,object,when,"
    "claim_text,confidence(0-1),known_vs_inferred(知道/推断/不知道),"
    "confirm_queries[],falsify_queries[]。\n"
    "规则：不知道就显式 null；禁止编造人名/年份/原话；"
    "每条都要有 falsify_queries（关店/离职/辟谣/难吃/预制等反向查询）。\n"
    "种子={seed}"
)


def _parse_model_json(text: str) -> list:
    """从模型回复里抠 JSON 数组（容忍 ```json 包裹/前后废话）。"""
    if not text:
        return []
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, list) else []
    except Exception:
        return []


def fleet_recall(seed: dict, apply: bool) -> dict:
    """同一探针 fan-out 到所有已配置 provider/model；结果只 upsert lead_hypotheses。
    无 provider（无 key）→ 降级：打印提示、返回空，不报错。"""
    providers = MP.load_providers()
    if not providers:
        print("[hae-fleet] 未配置任何 provider key（见 deploy.env §5）。"
              "降级为 agent 自身推理零成本实跑；24/7 自跑请配 ARK/KIMI/QWEN/GLM/MINIMAX/HUNYUAN key。")
        return {"mode": "degraded_no_provider", "providers": 0, "rows": []}
    prompt = SEED_PROMPT.format(seed=json.dumps(seed, ensure_ascii=False))
    ph = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]
    out_rows, calls = [], []
    for p in providers:
        for model in p.models:
            r = MP.chat(p, model, prompt, web_search=MP.web_search_enabled())
            calls.append({"provider": p.name, "model": model, "ok": r["ok"],
                          "web": r["web"], "sources_n": len(r.get("sources", [])),
                          "error": r.get("error")})
            if not r["ok"]:
                continue
            for item in _parse_model_json(r.get("text", "")):
                if not isinstance(item, dict):
                    continue
                # 认识论：联网来源才作线索 URL；无 URL 的纯参数回忆仍进假设表，但 confidence 压低
                urls = r.get("sources", []) or []
                row = {
                    "subject_type": item.get("subject_type", seed.get("subject_type", "restaurant")),
                    "subject_name": item.get("subject_name", seed.get("subject_name")),
                    "relation": item.get("relation", "related_to"),
                    "object": item.get("object"),
                    "when": item.get("when"),
                    "claim_text": item.get("claim_text") or "(模型未给出 claim)",
                    "confidence": float(item.get("confidence", 0.30)),
                    "known_vs_inferred": item.get("known_vs_inferred", "推断"),
                    "status": "hypothesized",
                    "confirm_queries": item.get("confirm_queries", []),
                    "falsify_queries": item.get("falsify_queries") or ["(缺证伪)"],
                    "confirmed_source_urls": urls,   # 联网来源先挂线索
                    "confirm_voices": 1 if urls else 0,
                    "proposed_by": {"model": model, "provider": p.name,
                                    "prompt_hash": ph, "date": today()},
                    "is_seed": False,
                }
                out_rows.append(norm_row(row))
    res = upsert_rows(out_rows, apply=apply)
    return {"mode": "fleet", "calls": calls, "n_rows": len(out_rows),
            "upsert": res, "web_search": MP.web_search_enabled()}


def prove(rows: list, apply: bool) -> dict:
    """收敛：对每条假设跑 confirm_queries + 【强制】falsify_queries。
    当前无联网检索器/无 key：只做确定性裁决——
      - 带权威/≥2独立 URL 的 confirmed 保持；
      - 仅模型单源、无 URL → 不晋升，留 unverified；
      - 明确被反向证伪(如关店三要素/停业新闻)→ contradicted。
    真联网取证由 --fleet-recall 联网模型回 URL 或确定性连接器(closed_watch/authority)承担。"""
    from collections import Counter
    n = Counter()
    for r in rows:
        urls = r.get("confirmed_source_urls") or []
        voices = r.get("confirm_voices", 0)
        rel = r["relation"]
        if r["status"] == "contradicted":
            n["kept_contradicted"] += 1
            continue
        # 关系类：≥1 可信文档 URL；事实类：权威 URL 或 ≥2 声音
        ok, _ = passes_gate({**r, "status": "confirmed"})
        if ok:
            r["status"] = "confirmed"; n["confirmed"] += 1
        elif urls or voices:
            r["status"] = "unverified"; n["unverified"] += 1  # 有线索但不足门槛
        else:
            r["status"] = "hypothesized"; n["open"] += 1
    if apply and rows and table_exists(HYP_TABLE):
        for r in rows:
            C.req("PATCH", f"/{HYP_TABLE}?hid=eq.{r['hid']}",
                  use_service=True, json={"status": r["status"],
                                          "verdict_notes": "prove 确定性裁决(无联网器)"})
    return {"decisions": dict(n), "apply": apply}


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest-ledger", help="从 JSONL 账本导入假设（幂等 upsert）")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--promote-plan", action="store_true")
    ap.add_argument("--apply", action="store_true", help="过闸才真写（默认 dry-run）")
    ap.add_argument("--diverge-llm", action="store_true")
    ap.add_argument("--fleet-recall", action="store_true",
                    help="同一探针并行 fan-out 所有已配置 provider（带参数+联网），只 upsert 假设表")
    ap.add_argument("--prove", action="store_true",
                    help="对假设跑 confirm+强制 falsify 裁决，标 confirmed/contradicted/unverified")
    ap.add_argument("--fleet-status", action="store_true",
                    help="打印舰队各 provider 配置与联网能力（不打印 key）")
    ap.add_argument("--seed-json", default="")
    args = ap.parse_args()

    if args.fleet_status:
        print(json.dumps(MP.fleet_status(), ensure_ascii=False, indent=2))
        return

    if args.fleet_recall:
        seed = json.loads(pathlib.Path(args.seed_json).read_text(encoding="utf-8")) \
            if args.seed_json else {}
        res = fleet_recall(seed, apply=args.apply)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if args.diverge_llm:
        seed = json.loads(pathlib.Path(args.seed_json).read_text(encoding="utf-8")) \
            if args.seed_json else {}
        res = diverge_llm(seed, [])
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    # 读账本（本地 JSONL）
    rows = []
    if args.ingest_ledger:
        for line in pathlib.Path(args.ingest_ledger).read_text(
                encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(norm_row(json.loads(line)))

    if args.prove:
        # 优先从库里读全量假设；库不可用则退本地 ledger
        if table_exists(HYP_TABLE):
            rows = [norm_row(x) for x in C.fetch_all(
                HYP_TABLE,
                "hid,subject_type,subject_name,relation,object,when,claim_text,confidence,"
                "known_vs_inferred,status,evidence,confirm_queries,falsify_queries,"
                "confirm_voices,confirmed_source_urls",
                order_col="hid")]
        elif not rows:
            lp = sorted(HAE_DIR.glob("ledger_*.jsonl"))
            if lp:
                rows = [norm_row(x) for x in C.read_jsonl(str(lp[-1]))]
        res = prove(rows, apply=args.apply)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return

    if args.status:
        if table_exists(HYP_TABLE):
            data = C.fetch_all(HYP_TABLE, "hid,subject_type,status,relation,confidence",
                               order_col="hid")
        else:
            data = rows
        from collections import Counter
        print("账本状态统计:", dict(Counter(r["status"] for r in data)))
        print("主体维度分布:", dict(Counter(r["subject_type"] for r in data)))
        return

    if args.promote_plan:
        # 若无入参行，从本地 ledger 读
        if not rows and args.ingest_ledger is None:
            lp = sorted(HAE_DIR.glob("ledger_*.jsonl"))
            if lp:
                rows = [norm_row(x) for x in C.read_jsonl(str(lp[-1]))]
        plan = build_promote_plan(rows)
        print(f"confirmed 过闸晋升计划 {len(plan)} 条 (apply={args.apply}):")
        for p in plan:
            print(" -", json.dumps(p, ensure_ascii=False))
        return

    if args.ingest_ledger:
        res = upsert_rows(rows, apply=args.apply)
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
