#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""production_model_probe.py — 出餐方式二次校验探针（LLM agentic 取证 + 确定性仲裁）。

为什么存在：二次校验要分辨 真实连锁 / 商业化预制 / 资本化 / 大型连锁 及【出餐方式】。
旧机制把 central_kitchen/premade_risk 当零散硬负面，无法回答“菜怎么到盘里”。
本模块把【所有权 chain_type】与【出餐方式 production_model】作为两个正交维度：

  1) LLM（ARK/豆包）以 function-calling 驱动，自主决定检索词；
  2) web_search 由【keyless SERP】(serp_producer: 360/搜狗/bing，无配额) 真实执行，
     把标题/URL/摘要回喂 LLM，多轮取证（含反向：料理包/复热/预制）；
  3) LLM 只输出【结构化信号】（线索，不直写事实表）；
  4) 确定性仲裁 adjudicate() 按 docs/production-model-verification.md §4 规则、
     以独立源数 n_ind 决定 production_model / central_kitchen / premade_risk；
  5) 结论经 ingest 幂等写 findings，再由 gate_apply --apply 写库（n_ind≥2 才挂）。

红线：LLM 不写事实表；宁空不假；连锁本身不下架；不改非目标字段。

用法（容器内，. /app/cloud/env.sh）：
  python3 production_model_probe.py --calibrate                 # 校准集，只报告判定 vs 预期
  python3 production_model_probe.py --brands 小菜园,新荣记 --ingest   # 计算并写 findings
  python3 production_model_probe.py --all --limit 40            # 全品牌（先连锁后高口碑），不写
  随后：python3 gate_apply.py --apply
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")
import common_core as core          # noqa: E402
import ingest                       # noqa: E402
import model_providers as MP        # noqa: E402

try:
    import serp_producer as SP      # noqa: E402  keyless 搜索
except Exception:
    SP = None

DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
REPORT_DIR = DATA / "post_record"

PRODUCTION_LABELS = [
    "现炒现做", "门店现制·标准化", "中央厨房·门店加工",
    "中央厨房·门店复热", "预制料理包·复热", "外购成品·无堂食厨房"]

# 校准集：(品牌匹配 key, 预期 production_model) —— 已知 ground truth，验证机制区分力。
CALIBRATE = [
    ("小菜园", "预制料理包·复热"),
    ("味千拉面", "中央厨房·门店复热"),
    ("真功夫", "中央厨房·门店复热"),
    ("海底捞", "中央厨房·门店加工"),
    ("老乡鸡", "中央厨房·门店加工"),
    ("外婆家", "中央厨房·门店加工"),
    ("杨国福", "中央厨房·门店加工"),
    ("新荣记", "现炒现做"),
    ("老吴家川菜", "现炒现做"),
    ("鸟鸟炒菜店", "现炒现做"),
    ("FASCINO", "门店现制·标准化"),
    ("BAsdBAN", "门店现制·标准化"),
]

REG_DOMAINS = ("qcc.com", "tianyancha.com", "aiqicha.baidu.com", "gsxt.gov.cn",
               "qixin.com", "企查查", "天眼查")
RE_DOM = re.compile(r"https?://([^/]+)")


def domain(url):
    m = RE_DOM.match(url or "")
    return m.group(1) if m else "?"


def brand_core(name):
    s = re.split(r"[（(]", name or "")[0]
    s = re.sub(r"(总店|首店|旗舰店|专卖店|直营店)$", "", s)
    s = re.sub(r"(新徽菜|本帮菜|江浙菜|家常菜|地方菜|连锁餐饮|餐饮连锁|餐饮|连锁)$", "", s)
    s2 = re.sub(r"[\u4e00-\u9fa5]{1,2}菜$", "", s)
    if len(s2.strip()) >= 2:
        s = s2
    s = re.sub(r"新$", "", s)  # 去掉显式新徽菜后可能残留的尾字（不影响"新荣记"）
    return s.strip(" ·・•&")


# ---------------------------------------------------------------------------
# 真实 URL 校验 + SearXNG 就绪（防杜撰来源 / 冷启动 0 源）
# ---------------------------------------------------------------------------
RE_URL = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.I)


def is_real_url(u):
    """来源 URL 必须是真实可定位的 http(s) 地址：有 scheme + 点分主机，
    且不含省略号/空白/截断尾巴。用于剔除模型杜撰的来源（曾出现
    "post.smzdm.com/2026年春节前夕..." 这种残缺串）。"""
    if not isinstance(u, str):
        return False
    u = u.strip()
    if not RE_URL.match(u) or "..." in u or "…" in u or " " in u:
        return False
    host = u.split("://", 1)[-1].split("/", 1)[0].split("?", 1)[0]
    return ("." in host) and host[-1].isalnum()


def _searxng_base():
    return os.environ.get("SEARX_URL", "http://searxng:8080")


def searxng_ready():
    try:
        with urllib.request.urlopen(_searxng_base() + "/healthz", timeout=6) as r:
            if r.status == 200:
                return True
    except Exception:
        pass
    try:
        with urllib.request.urlopen(
                _searxng_base() + "/search?q=test&format=json", timeout=8) as r:
            return r.status == 200
    except Exception:
        return False


_READY_DONE = {"v": False}


def ensure_search_ready(force=False):
    """容器刚重建后的前几十秒，food-cloud→searxng 的网络/DNS 可能尚未就绪；
    首轮取证前先等待，避免整批 0 源。"""
    if _READY_DONE["v"] and not force:
        return True
    for _ in range(6):
        if searxng_ready():
            _READY_DONE["v"] = True
            return True
        time.sleep(5)
    return False


# ---------------------------------------------------------------------------
# LLM 原始调用（支持 tools / tool_calls；MP.chat 不处理工具，故在此实现）
# ---------------------------------------------------------------------------
def chat_raw(provider, model, messages, tools=None, timeout=30, retries=2, hard_cap=60,
             max_tokens=None):
    """OpenAI 兼容 chat completion；使用 SSE 流式累积，避免大输出在读上空闲超时。
    返回 message 形态 dict（content / tool_calls）。
    timeout=单次读空闲上限；hard_cap=整次请求墙钟硬上限（服务端挂起不返回时快速失败）。
    max_tokens=输出上限（封顶计费，防止冗长 JSON 失控）。"""
    body = {"model": model, "messages": messages, "temperature": 0.2, "stream": True}
    if max_tokens:
        body["max_tokens"] = int(max_tokens)
    if tools:
        body["tools"] = tools
        body["stream"] = False  # 工具调用路径不流式（当前主流程不用）
    waits = [8, 16, 30, 60]
    net_waits = [10, 20, 30]
    last = None
    for i in range(retries):
        content_parts, tool_calls = [], []
        t_start = time.time()
        try:
            req = urllib.request.Request(
                provider.base_url + "/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json",
                         "Authorization": f"Bearer {provider.api_key}"}, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                if not body["stream"]:
                    d = json.loads(r.read().decode("utf-8"))
                    return d["choices"][0]["message"]
                for raw in r:
                    if time.time() - t_start > hard_cap:
                        raise TimeoutError("hard_cap")
                    line = raw.decode("utf-8", "ignore").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta") or {}
                    if delta.get("content"):
                        content_parts.append(delta["content"])
                    if delta.get("tool_calls"):
                        tool_calls += delta["tool_calls"]
            if not content_parts and not tool_calls:
                raise TimeoutError("empty_stream")
            return {"role": "assistant", "content": "".join(content_parts),
                    "tool_calls": tool_calls or None}
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                wait = waits[i] if i < len(waits) else 60
                print("    [429] backoff", wait, "s")
                time.sleep(wait)
                continue
            raise
        except (TimeoutError, urllib.error.URLError) as e:
            last = e
            if i >= len(net_waits):
                raise TimeoutError("service_stall")
            wait = net_waits[i]
            print("    [net]", type(e).__name__, "retry in", wait)
            time.sleep(wait)
    raise last if last else TimeoutError("service_stall")


WEB_SEARCH_TOOL = [{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "联网网页搜索，返回多条结果的标题/URL/摘要",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string",
                                        "description": "搜索词，可含品牌名+中央厨房/料理包/现炒/供应链等"}},
                       "required": ["query"]}}}]

SIGNALS_FIELDS = [
    "license_hot_cook", "license_packaged_only", "central_kitchen_license",
    "factory_sc", "central_delivery_evidence", "reheat_evidence",
    "premade_packet_evidence", "fresh_wok_evidence", "onsite_prep_evidence",
    "retail_packaged_products",
    "direct_franchise", "financing", "n_locations", "production_guess",
    "confidence", "supply_chain_entity"]

SYSTEM = (
    "你是上海美食图鉴的【出餐方式】调查员。目标：用证据判断一个餐饮品牌的菜是怎么做出来、"
    "怎么到盘里。需要事实时必须调用 web_search；要同时找【正向现做】(明厨/现炒/锅气/现包/现切) "
    "与【反向复热】(中央厨房/料理包/预制/复热/供应链工厂) 两类证据，优先官方/年报/工商许可/媒体。\n"
    "检索 2–3 次、证据足够后立即输出，不要反复搜索。\n"
    "取证后只输出一个 JSON 对象，字段：" + ", ".join(SIGNALS_FIELDS) + "。\n"
    "其中 *_evidence 与 supply_chain_entity 为数组，元素含 {quote(原文短句),url,kind(reg/news/ugc)}；"
    "布尔许可字段用 true/false/未知null；financing=上市/VC融资/无/未知；"
    "production_guess 取 " + "/".join(PRODUCTION_LABELS) + "；confidence 0-1。\n"
    "规则：无证据就 null，禁止编造引文/URL/名字；不要输出 JSON 以外的话。")


def _keyless_search(q):
    if SP is None:
        return [], "no_sp"
    try:
        return SP.search_with_failover(q)
    except Exception as e:
        return [], f"err {e}"


def standard_queries(brand):
    """标准地毯搜索词根：复热向（品牌加引号，强制精确、压制行业泛文）/
    手艺现做向 / 资本规模向（不加引号以保召回）。结果再经品牌命中过滤（双重保险）。"""
    return [
        f'"{brand}" 中央厨房 料理包 预制菜 复热 供应链',
        f'{brand} 招牌菜 现炒 现做 厨师 明厨亮灶 锅气',
        f'{brand} 门店 直营 加盟 上市 集团 公司',
    ]


def brand_terms(brand):
    """品牌的显著词（用于"必须真在讲该品牌"过滤）：CJK 整段+二元组，拉丁整词。"""
    terms = set()
    for raw in re.split(r"[\s·・•&]+", brand):
        raw = raw.strip("'\"()（）")
        if not raw:
            continue
        if re.fullmatch(r"[A-Za-z0-9.'+\-]+", raw):
            if len(raw) >= 3:
                terms.add(raw.lower())
            continue
        for run in re.findall(r"[\u4e00-\u9fa5]+", raw):
            if len(run) >= 2:
                terms.add(run)
            for i in range(len(run) - 1):
                terms.add(run[i:i + 2])
    return terms


def _mentions_brand(doc, bterms):
    blob = (doc.get("source_title", "") + " " + doc.get("snippet", "") + " "
            + doc.get("source_url", "") + " " + doc.get("source_host", ""))
    blob_l = blob.lower()
    return any(t in (blob_l if t.isascii() else blob) for t in bterms)


def evidence_url_set(evidence):
    s = set()
    for e in evidence:
        for d in e.get("results", []):
            u = d.get("source_url")
            if u:
                s.add(u)
    return {u for u in s if is_real_url(u)}


def gather_evidence(brand, n_queries=3, _retry=1):
    bterms = brand_terms(brand)

    def _once():
        ev = []
        for q in standard_queries(brand)[:n_queries]:
            res, eng = _keyless_search(q)
            kept = [d for d in res if _mentions_brand(d, bterms)]
            ev.append({"query": q, "engine": eng, "raw": len(res), "results": kept})
            time.sleep(2)
        return ev

    ev = _once()
    if _retry and not any(e["results"] for e in ev):
        # 冷启动/上游瞬态导致 0 源：等待就绪后整轮重取一次，不产出空轮
        ensure_search_ready(force=True)
        time.sleep(12)
        ev = _once()
    return ev


def _evidence_brief(evidence, top=5, snip=170):
    """跨查询按 source_url 去重（同一篇常被多个词命中，避免重复喂给 LLM 浪费输入 token）。"""
    lines = []
    seen = set()
    for e in evidence:
        lines.append(f"【搜索】{e['query']}（引擎 {e['engine']}）")
        n = 0
        for d in e["results"]:
            key = d.get("source_url") or (d.get("source_host", "") + d.get("source_title", ""))
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- {d.get('source_host')} | {d.get('source_title','')[:60]}\n  {(d.get('snippet') or '')[:snip]}")
            n += 1
            if n >= top:
                break
    return "\n".join(lines)


def extract_signals_once(provider, model, brand, locations, evidence, retries=2):
    brief = _evidence_brief(evidence)
    prompt = (
        f"品牌：{brand}\n库内分店：{locations}\n"
        f"以下是已检索到的网页证据（可能含无关或营销内容，需甄别）：\n{brief}\n\n"
        "任务：从证据中摘录与该品牌【出餐方式/供应链/资本规模】最关键的原文句子。\n"
        "必须同时收集两类（裁决由后续程序做；每类只留信息量最高的 ≤6 条，引文 ≤40 字，不要长篇照抄）：\n"
        "(A) 复热/工业化：中央厨房、料理包、预制菜、复热、统一配送、供应链公司、工厂、SC许可、门店只做加热；\n"
        "(B) 现做/门店制作：明厨亮灶、现炒、锅气、现包、现切、现烤、现擀、门店后厨、厨师现场制作。\n"
        "关键区分（极易误判，务必遵守）：若证据是品牌【售卖/推出】预制菜、年夜饭/年货礼盒、"
        "伴手礼、电商旗舰店或到家速冻产品（语境为 推出/上线/开售/礼盒/年货/电商/购买/包邮），"
        "一律放进 retail_packaged_products，绝不能作为堂食出餐方式证据；"
        "只有明确描述【门店/堂食/到店食客】吃到的是料理包复热、统一配送、门店仅做加热"
        "（语境 后厨/上菜/堂食/到店/门店只做加热），才可计入 (A) 类。\n"
        "并提取：是否上市/股票代码、融资、门店总数、直营/加盟、背后餐饮或供应链公司。\n"
        "字段映射（出现即填，不得留空）：证据含 IPO/上市/港交所/深交所/上交所/股票代码/招股书 → financing=上市；"
        "含“共N家门店/N家直营/直营店N家” → n_locations=N（整数）；含 VC/天使/融资轮 → financing=VC融资；"
        "提到的供应链/母公司/集团名放进 supply_chain_entity。\n"
        "只输出一个 JSON 对象，字段：" + ", ".join(SIGNALS_FIELDS) + "。\n"
        "*_evidence、retail_packaged_products 与 supply_chain_entity 为数组，元素 {quote(原文短句,尽量保留关键事实),url,kind(reg/news/ugc)}；"
        "只把最关键的相关句子放进对应数组（每类≤6条）并保留其 URL；"
        "布尔许可字段 true/false/null；financing=上市/VC融资/无/未知；n_locations 为整数或null；"
        "production_guess 取 " + "/".join(PRODUCTION_LABELS) + "；confidence 0-1。\n"
        "只能引用上面真实出现的引文和 URL，禁止编造；完全无据的字段填 null；不要输出 JSON 以外的话。")
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt}]
    msg = chat_raw(provider, model, messages, timeout=30, retries=retries,
                   max_tokens=2200)  # 单次、无工具；封顶输出
    return _parse_signals(msg.get("content") or "")


# 模型池状态：记录已被「安心体验」暂停（SetLimitExceeded）的模型，
# 避免每个品牌都对死模型空打一遍；状态持久化，跨 cron 生效。
_POOL_STATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "model_pool_state.json")


def _load_pool_state():
    try:
        with open(_POOL_STATE_PATH, encoding="utf-8") as f:
            return {"dead": set(json.load(f).get("dead", []))}
    except Exception:
        return {"dead": set()}


_POOL = _load_pool_state()


def _save_pool_state():
    try:
        tmp = _POOL_STATE_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"dead": sorted(_POOL["dead"])}, f, ensure_ascii=False)
        os.replace(tmp, _POOL_STATE_PATH)
    except Exception:
        pass


def mark_model_dead(model):
    if model not in _POOL["dead"]:
        _POOL["dead"].add(model)
        _save_pool_state()


def clear_model_dead(model):
    if model in _POOL["dead"]:
        _POOL["dead"].discard(model)
        _save_pool_state()


def candidate_models(provider):
    """候选顺序：PROD_MODEL 指定优先；否则【最便宜的存活模型优先】，把一个模型的免费
    额度用完再用下一个。已暂停(dead)模型不参与（仅当全部暂停才返回全部用于恢复探测）。"""
    models = list(provider.models)
    want = os.environ.get("PROD_MODEL", "")
    live = [m for m in models if m not in _POOL["dead"]]
    order = list(live if live else models)
    if want and want in models:
        order = [want] + [m for m in order if m != want]
    return order


def probe_brand(provider, model, brand, locations, n_queries=3):
    """model 可为单个模型或候选列表；自动在 429 时轮换模型。
    返回 (sig, evidence, status)；status ∈ ok / no_evidence / llm_ratelimit / llm_error。"""
    ensure_search_ready()
    evidence = gather_evidence(brand, n_queries=n_queries)
    candidates = [model] if isinstance(model, str) else list(model or [])
    if not candidates:
        candidates = candidate_models(provider)
    fail_codes = []
    stalls = 0
    for m in candidates:
        try:
            sig = extract_signals_once(provider, m, brand, locations, evidence)
            if sig:
                # 证据接地到真实检索结果，剔除模型杜撰来源
                sig = filter_signals_by_evidence(sig, evidence)
                clear_model_dead(m)
                print(f"    [model] {m}")
                return sig, evidence, "ok"
            fail_codes.append("empty")
        except urllib.error.HTTPError as e:
            body_txt = ""
            try:
                body_txt = e.read().decode("utf-8", "ignore")
            except Exception:
                pass
            if e.code == 429 and "SetLimitExceeded" in body_txt:
                # 该模型免费额度耗尽并暂停：记入 dead，本进程后续不再空打，继续试下一个模型
                mark_model_dead(m)
                print(f"    [model-paused] {m} -> 免费额度耗尽，换下一个")
                fail_codes.append("quota")
            else:
                print(f"    [model-skip] {m} -> HTTPError {e.code}")
                fail_codes.append("429" if e.code == 429 else f"http{e.code}")
            continue
        except TimeoutError:
            # 服务端挂起/排队到近乎零吞吐：记 stall，但仍试完所有候选再判定
            stalls += 1
            print(f"    [model-skip] {m} -> service stall")
            fail_codes.append("stall")
            continue
        except Exception as e:
            print(f"    [model-skip] {m} -> {type(e).__name__}")
            fail_codes.append(type(e).__name__)
            continue
    has_kept = any(e.get("results") for e in evidence)
    if not has_kept:
        return None, evidence, "no_evidence"
    if fail_codes and all(c in ("quota", "429", "stall") for c in fail_codes):
        return None, evidence, "llm_ratelimit"
    return None, evidence, "llm_error"


def _parse_signals(text):
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        v = json.loads(m.group(0))
        return v if isinstance(v, dict) else None
    except Exception:
        return None


def agent_gather(provider, model, brand, locations, max_rounds=4, max_searches=3,
                 time_budget=150):
    user = (f"品牌：{brand}\n库内分店/地址：{locations}\n"
            "请判断它的出餐方式：先多检索（含 中央厨房/料理包/预制/复热 与 明厨/现炒/锅气 两个方向），"
            "再输出最终 JSON 信号对象。")
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": user}]
    evidence, n_searches = [], 0
    t0 = time.time()
    for rnd in range(max_rounds):
        if time.time() - t0 > time_budget:
            break
        try:
            msg = chat_raw(provider, model, messages, tools=WEB_SEARCH_TOOL)
        except Exception as e:
            print("    [llm]", type(e).__name__, str(e)[:80])
            time.sleep(3)
            continue
        tcs = msg.get("tool_calls")
        if tcs and n_searches < max_searches and time.time() - t0 <= time_budget:
            messages.append({"role": "assistant", "content": msg.get("content") or "",
                             "tool_calls": tcs})
            for tc in tcs:
                if n_searches >= max_searches or time.time() - t0 > time_budget:
                    # 仍须为每个 tool_call 回一条，保持会话合法
                    messages.append({"role": "tool", "tool_call_id": tc.get("id"),
                                     "name": "web_search", "content": "[]"})
                    continue
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                    q = args.get("query")
                except Exception:
                    q = brand + " 中央厨房 料理包"
                if not q:
                    messages.append({"role": "tool", "tool_call_id": tc.get("id"),
                                     "name": "web_search", "content": "[]"})
                    continue
                res, eng = _keyless_search(q)
                n_searches += 1
                evidence.append({"query": q, "engine": eng, "results": res})
                compact = [{"title": d.get("source_title", "")[:80],
                            "url": d.get("source_url", ""),
                            "snippet": (d.get("snippet") or "")[:280]} for d in res[:6]]
                messages.append({"role": "tool", "tool_call_id": tc.get("id"),
                                 "name": "web_search",
                                 "content": json.dumps(compact, ensure_ascii=False)})
                time.sleep(1)
            continue
        # 无可用工具（已达搜索上限/超时）：先把可能存在的 tool_calls 补占位
        if tcs:
            messages.append({"role": "assistant", "content": msg.get("content") or "",
                             "tool_calls": tcs})
            for tc in tcs:
                messages.append({"role": "tool", "tool_call_id": tc.get("id"),
                                 "name": "web_search", "content": "[]"})
        sig = _parse_signals(msg.get("content") or "")
        if sig:
            return sig, evidence
        messages.append({"role": "assistant", "content": msg.get("content") or ""})
        messages.append({"role": "user", "content":
            "请直接输出最终 JSON 信号对象（不要解释）。"})

    # 强制收口：不再给工具，模型必须基于已检索信息输出最终 JSON
    messages.append({"role": "user", "content":
        "证据收集已达上限。请基于以上检索到的信息立即输出最终 JSON 信号对象；"
        "没有证据的字段一律填 null，不要解释、不要调用工具。"})
    try:
        msg = chat_raw(provider, model, messages, timeout=150)  # 不传 tools
        sig = _parse_signals(msg.get("content") or "")
        if sig:
            return sig, evidence
    except Exception as e:
        print("    [llm-final]", type(e).__name__, str(e)[:80])
    return None, evidence


# ---------------------------------------------------------------------------
# 证据独立源计数
# ---------------------------------------------------------------------------
def _ev_rows(sig, key):
    out = []
    for it in sig.get(key) or []:
        if isinstance(it, dict) and it.get("url"):
            out.append(it)
    return out


def n_independent_ev(items):
    doms, cls = set(), set()
    for it in items:
        u, k = it.get("url", ""), it.get("kind", "")
        dm = domain(u)
        doms.add(dm)
        if k:
            cls.add(k)
        if any(r in (u + dm) for r in REG_DOMAINS):
            cls.add("reg")
    return max(len(doms), len(cls)), sorted(doms)


def _as_bool(v):
    if v is True:
        return True
    if v is False:
        return False
    return None


# ---------------------------------------------------------------------------
# 真实 URL 白名单过滤 + 严判强模型复核
# ---------------------------------------------------------------------------
_EV_KEYS = ["central_delivery_evidence", "reheat_evidence",
            "premade_packet_evidence", "fresh_wok_evidence",
            "onsite_prep_evidence", "retail_packaged_products"]


def _norm_u(u):
    u = (u or "").strip().lower().split("#", 1)[0]
    if "://" in u:
        u = u.split("://", 1)[1]
    return u.replace("www.", "").rstrip("/")


def _norm_text(t):
    return re.sub(r"\s+", "", (t or ""))


def _ground_index(evidence):
    """真实取证的接地索引：归一 URL → 真实 URL；主机 → [(真实URL, 标题+摘要归一文本)]。"""
    by_url, by_host = {}, {}
    for e in evidence:
        for d in e.get("results", []):
            u = d.get("source_url", "")
            if not is_real_url(u):
                continue
            by_url[_norm_u(u)] = u
            host = domain(u).lower().replace("www.", "")
            txt = _norm_text(d.get("source_title", "") + d.get("snippet", ""))
            by_host.setdefault(host, []).append((u, txt))
    return by_url, by_host


def _ground_item(it, by_url, by_host):
    """把一条 LLM 证据接地到真实来源：
    ①归一 URL 精确命中；②同主机且引文能在该真实页标题/摘要中找到连续片段
    （容忍模型返回 canonical/协议/www 差异），并把 URL 重锚为真实地址；
    两者都不满足 = 杜撰，丢弃。"""
    u = it.get("url", "")
    if not is_real_url(u):
        return None
    nu = _norm_u(u)
    if nu in by_url:
        return dict(it, url=by_url[nu])
    host = domain(u).lower().replace("www.", "")
    q = _norm_text(it.get("quote", ""))
    if q:
        L = min(len(q), 12)

        def _in(real_txt):
            if len(q) <= 12:
                return q in real_txt
            return any(q[i:i + L] in real_txt
                       for i in range(0, len(q) - L + 1))

        for real_u, txt in by_host.get(host, []):
            if _in(txt):
                return dict(it, url=real_u)
    return None


def filter_signals_by_evidence(sig, evidence):
    """每条证据必须接地到真实检索结果（URL/主机+引文），杜撰来源一律剔除；其余字段保留。"""
    if not sig:
        return sig
    by_url, by_host = _ground_index(evidence)
    out = dict(sig)
    for k in _EV_KEYS:
        kept = []
        for it in (out.get(k) or []):
            if isinstance(it, dict):
                g = _ground_item(it, by_url, by_host)
                if g:
                    kept.append(g)
        out[k] = kept
    sce = []
    for it in (out.get("supply_chain_entity") or []):
        if isinstance(it, dict):
            g = _ground_item(it, by_url, by_host)
            if g:
                sce.append(g)
    out["supply_chain_entity"] = sce
    return out


SEVERE_MODELS = {"预制料理包·复热", "中央厨房·门店复热"}


def _confirm_model(provider, exclude=""):
    """选更强的存活模型做严判复核：优先 pro / glm-5-2 / turbo，否则取候选中最强。"""
    want = os.environ.get("CONFIRM_MODEL", "")
    cands = candidate_models(provider)
    if want and want in cands:
        return want
    prefs = [m for m in cands
             if ("pro" in m or "glm-5-2" in m or "turbo" in m) and m != exclude]
    pool = prefs or [m for m in cands if m != exclude]
    return pool[-1] if pool else None


def _hold(verdict, why, v2=None):
    out = dict(verdict)
    out["production_model"] = None
    out["central_kitchen"] = (v2 or {}).get("central_kitchen")
    out["premade_risk"] = (v2 or {}).get("premade_risk")
    out["rationale"] = why
    return out


def confirm_if_severe(provider, brand, locations, evidence, verdict):
    """对触发下架的最严两档，用更强模型、同一证据复核一次；一致才保留，
    不一致/无法复核 → 置空 hold（进复校），避免弱模型误杀好店。"""
    if not verdict or verdict.get("production_model") not in SEVERE_MODELS:
        return verdict
    cm = _confirm_model(provider)
    if not cm:
        return _hold(verdict, verdict["rationale"] + "；无更强模型复核，严判暂缓")
    try:
        sig2 = extract_signals_once(provider, cm, brand, locations, evidence, retries=1)
    except Exception as e:  # noqa: BLE001
        return _hold(verdict, verdict["rationale"] + f"；复核失败({type(e).__name__})，暂缓")
    if not sig2:
        return _hold(verdict, verdict["rationale"] + "；复核无信号，暂缓")
    sig2 = filter_signals_by_evidence(sig2, evidence)
    v2 = adjudicate(sig2)
    if v2.get("production_model") in SEVERE_MODELS:
        v2["rationale"] = verdict["rationale"] + f"；强模型({cm})复核一致"
        v2["sources"] = list({*(verdict.get("sources") or []),
                              *(v2.get("sources") or [])})
        return v2
    return _hold(verdict,
                 f"弱模型判[{verdict['production_model']}]，强模型({cm})复核为"
                 f"[{v2.get('production_model')}]，不一致→暂缓", v2)


# ---------------------------------------------------------------------------
# 确定性仲裁（docs §4）
# ---------------------------------------------------------------------------
def adjudicate(sig):
    """返回 dict: production_model, central_kitchen, premade_risk, sources, rationale。"""
    hot = _as_bool(sig.get("license_hot_cook"))
    packaged_only = _as_bool(sig.get("license_packaged_only"))
    ck_license = _as_bool(sig.get("central_kitchen_license"))
    factory = _as_bool(sig.get("factory_sc"))

    premade = _ev_rows(sig, "premade_packet_evidence")
    reheat = _ev_rows(sig, "reheat_evidence")
    central = _ev_rows(sig, "central_delivery_evidence")
    fresh = _ev_rows(sig, "fresh_wok_evidence")
    onsite = _ev_rows(sig, "onsite_prep_evidence")

    n_premade, dom_premade = n_independent_ev(premade)
    n_reheat, dom_reheat = n_independent_ev(reheat)
    n_central, dom_central = n_independent_ev(central + reheat)
    n_fresh, dom_fresh = n_independent_ev(fresh)
    n_onsite, dom_onsite = n_independent_ev(onsite)

    ck_confirmed = bool(ck_license or factory) or n_central >= 2
    # reg 类供应链/工厂实体也算央厨确认
    for ent in sig.get("supply_chain_entity") or []:
        if isinstance(ent, dict) and ent.get("url") and ent.get("kind") == "reg":
            ck_confirmed = True

    out = {"central_kitchen": None, "premade_risk": None,
           "production_model": None, "sources": [], "rationale": ""}

    # 1) 仅预包装销售、无热食制售
    if packaged_only and not hot:
        out.update(central_kitchen="无", premade_risk="无",
                   production_model="外购成品·无堂食厨房",
                   rationale="许可仅预包装/散装销售、无热食制售")
        return out

    # 2) 料理包
    reg_premade = any(r in (it.get("url", "") + domain(it.get("url", "")))
                      for it in premade for r in REG_DOMAINS)
    if n_premade >= 2 or (reg_premade and n_premade >= 1):
        srcs = list({it["url"] for it in premade})
        out.update(central_kitchen="确认" if ck_confirmed else "疑似",
                   premade_risk="高", production_model="预制料理包·复热",
                   sources=srcs, rationale=f"料理包证据 {n_premade} 独立源")
        return out
    if n_premade == 1:
        out["premade_risk"] = "疑似"  # 单源挂疑似，标签暂不写

    # 3) 中央厨房
    if ck_confirmed:
        srcs = list({it["url"] for it in (central + reheat + premade)})
        if hot and (n_fresh >= 1 or n_onsite >= 1 or hot):
            model = "中央厨房·门店加工"
        elif n_reheat >= 1 and n_fresh == 0 and not hot:
            model = "中央厨房·门店复热"
        elif hot:
            model = "中央厨房·门店加工"
        else:
            model = "中央厨房·门店复热"
        out.update(central_kitchen="确认", production_model=model, sources=srcs,
                   rationale=f"央厨确认(许可/工厂/≥2源)、门店热食制售={hot}、复热证据{n_reheat}/现炒{n_fresh}")
        if out["premade_risk"] is None:
            out["premade_risk"] = "无"
        return out
    if n_central == 1:
        out["central_kitchen"] = "疑似"

    # 4) 现做（合并现炒与门店现制证据，模型 production_guess 作为同档先验）
    n_craft, dom_craft = n_independent_ev(fresh + onsite)
    guess = sig.get("production_guess") or ""
    no_industrial = (n_premade + n_reheat + n_central) == 0 and not ck_confirmed
    if n_craft >= 2 and no_industrial:
        # 有明确现炒/锅气/家烧引据，或模型判现炒且至少 1 条现炒引据 → 现炒现做
        if n_fresh >= 1 and (guess in ("", "现炒现做") or "现炒" in guess):
            srcs = list({it["url"] for it in (fresh + onsite)})
            out.update(central_kitchen="无",
                       premade_risk=out["premade_risk"] or "无",
                       production_model="现炒现做", sources=srcs,
                       rationale=f"现炒/手艺证据 {n_craft} 独立源(现炒{n_fresh})、无工业化信号")
            return out
        # 仅门店现制（烘焙/组装/标准化），无现炒引据
        srcs = list({it["url"] for it in onsite})
        out.update(central_kitchen="无",
                   premade_risk=out["premade_risk"] or "无",
                   production_model="门店现制·标准化", sources=srcs,
                   rationale=f"门店现制证据 {n_onsite} 独立源、无现炒引据")
        return out
    if n_fresh >= 2 or (hot and n_fresh >= 1):
        srcs = list({it["url"] for it in fresh})
        out.update(central_kitchen="无",
                   premade_risk=out["premade_risk"] or "无",
                   production_model="现炒现做", sources=srcs,
                   rationale=f"现炒/锅气证据 {n_fresh} 独立源、热食制售={hot}")
        return out
    if n_onsite >= 1:
        srcs = list({it["url"] for it in onsite})
        out.update(central_kitchen="无",
                   premade_risk=out["premade_risk"] or "无",
                   production_model="门店现制·标准化", sources=srcs,
                   rationale=f"门店现制(现烤/现切/现擀)证据 {n_onsite} 独立源")
        return out

    # 5) 不足
    out["central_kitchen"] = out["central_kitchen"]  # may be 疑似
    out["premade_risk"] = out["premade_risk"]
    out["rationale"] = (f"证据不足：料理包{n_premade}/央厨{n_central}/复热{n_reheat}/"
                        f"现炒{n_fresh}/现制{n_onsite}，宁空不假")
    return out


# ---------------------------------------------------------------------------
# 写 findings（结论每独立源一条；reason 带证据类关键词供 gate 计 n_ind）
# ---------------------------------------------------------------------------
def _class_reason(url, base_reason):
    u = (url or "")
    if any(r in u for r in REG_DOMAINS):
        cls = "工商许可/注册主体"
    elif any(k in u for k in ("weixin", "mp.weixin", "news", "thepaper", "people.com")):
        cls = "新闻报道/公众号"
    else:
        cls = "门店/连锁/测评"
    return f"{cls}：{base_reason}"


def write_findings(brand, rids, verdict):
    model = verdict["production_model"]
    srcs = verdict.get("sources") or []
    n_add = 0
    for rid in rids:
        # 本轮取证取代该店上一轮探针结论（仅 production_probe 来源），
        # 最新可溯源证据为准；随后只 append 本轮仍成立的结论
        ingest.supersede(rid, ["production_model", "central_kitchen", "premade_risk"])
        # 出餐方式标签：每独立源一条（需 ≥2 才会被 gate 挂）
        if model:
            for u in srcs:
                if ingest.append_finding(
                        rid, "production_model", model, 0.9,
                        _class_reason(u, f"{brand}出餐方式为{model}；{verdict['rationale']}"),
                        source_url=u, source_platform="production_probe"):
                    n_add += 1
        # 央厨 / 预制 支撑字段
        ck = verdict.get("central_kitchen")
        pr = verdict.get("premade_risk")
        for field, val in (("central_kitchen", ck), ("premade_risk", pr)):
            if not val:
                continue
            for u in (srcs or ["https://www.sogou.com/web?query=" + brand]):
                if ingest.append_finding(
                        rid, field, val, 0.85,
                        _class_reason(u, f"{brand}{field}={val}；{verdict['rationale']}"),
                        source_url=u, source_platform="production_probe"):
                    n_add += 1
    return n_add


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def pick_provider_model():
    ps = MP.load_providers()
    if not ps:
        return None, None
    p = ps[0]
    want = os.environ.get("PROD_MODEL", "")
    model = want if (want and want in p.models) else (
        p.models[1] if len(p.models) > 1 else p.models[0])
    return p, model


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--brands", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--ingest", action="store_true", help="写 findings（默认只报告）")
    args = ap.parse_args()

    rests = core.fetch_all(
        "restaurants", "id,name,status,chain_type,review_count", order_col="id")
    brands = {}
    for r in rests:
        if r.get("status") == "closed":
            continue
        brands.setdefault(brand_core(r["name"]), []).append(r)

    # 目标品牌
    targets = []
    if args.calibrate:
        for key, expect in CALIBRATE:
            hit = next((b for b in brands if key in b), None)
            targets.append((hit or key, expect))
    elif args.brands:
        for key in [x.strip() for x in args.brands.split(",") if x.strip()]:
            hit = next((b for b in brands if key in b), None)
            targets.append((hit or key, None))
    else:
        def rank(b):
            rs = brands[b]
            chain = 0 if all(r.get("chain_type") == "独立店" for r in rs) else 1
            return (chain, max(r.get("review_count") or 0 for r in rs))
        names = sorted(brands, key=lambda b: rank(b), reverse=True)
        targets = [(b, None) for b in names[:args.limit]]

    p, model = pick_provider_model()
    if not p:
        print("未配置 LLM provider（ARK），退出。")
        return
    print(f"LLM: {p.name}/{model}；目标品牌 {len(targets)} 个；ingest={args.ingest}\n")

    report, n_add = [], 0
    for bname, expect in targets:
        rs = brands.get(bname)
        if not rs:
            print(f"⚠ 未在库匹配：{bname}")
            continue
        rids = [r["id"] for r in rs]
        locs = "; ".join(f"{r['name']}" for r in rs[:6])
        print(f"● {bname} | 分店 {rids}")
        sig, evidence, _status = probe_brand(p, candidate_models(p), bname, locs)
        if not sig:
            print("    取证失败/无信号（不写）\n")
            report.append({"brand": bname, "rids": rids, "verdict": None,
                           "searches": len(evidence)})
            continue
        verdict = adjudicate(sig)
        verdict = confirm_if_severe(p, bname, locs, evidence, verdict)
        mark = ""
        if expect:
            mark = "  ✅符合预期" if verdict["production_model"] == expect else (
                f"  ❌预期[{expect}]")
        print(f"    => {verdict['production_model']} | 央厨={verdict['central_kitchen']} "
              f"预制={verdict['premade_risk']} | 源{len(verdict['sources'])}{mark}")
        print(f"       {verdict['rationale']}")
        if args.ingest:
            n_add += write_findings(bname, rids, verdict)
        report.append({"brand": bname, "rids": rids, "expected": expect,
                       "verdict": verdict, "signals": sig,
                       "searches": len(evidence)})
        print()
        gap = int(os.environ.get("BRAND_GAP", "15"))
        if gap:
            time.sleep(gap)

    rp = REPORT_DIR / f"production_probe_{datetime.date.today()}.json"
    rp.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"报告：{rp}")
    if args.ingest:
        print(f"新增 findings {n_add} 条；下一步：python3 gate_apply.py --apply")
    if args.calibrate:
        ok = sum(1 for x in report if x.get("expected") and
                 x["verdict"] and x["verdict"]["production_model"] == x["expected"])
        tot = sum(1 for x in report if x.get("expected") and x["verdict"])
        print(f"校准符合 {ok}/{tot}")


if __name__ == "__main__":
    run()
