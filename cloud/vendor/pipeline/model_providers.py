#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
model_providers.py — 国产大模型【知识源舰队】注册表（HAE / L0.5 配套）

方法论来源：references/llm-sourcing-fleet.md（已复制到 cloud/docs/llm-sourcing-fleet.md）。

============================================================
认识论红线（不可违反，与 north-star A2/机制 P 绑定）：
1. 模型是【线索生成器/联想记忆】，不是权威。任何模型输出【绝不直写事实表】，
   只进隔离表 lead_hypotheses；事实表写入一律走 hae_engine 的确定性晋升闸门。
2. 多模型一致 ≠ 独立证实（训练语料高度重叠），一致只抬高【先验】，
   晋升仍需外部权威 URL 或 ≥2 独立声音。
3. 每条假设必带强制 falsify_queries（不只找支持证据）。
4. 宁空不假：模型自标 知道/推断/不知道；无记忆显式 null，禁止编造人名/年份/原话。
5. key/base_url 全部从环境(deploy.env)读，禁止硬编码；缺 key/缺适配器自动跳过、不报错。
============================================================

配置（deploy.env，值勿入库；变量名严格按 llm-sourcing-fleet.md §5）：
  ARK_BASE_URL   ARK_API_KEY   HAE_MODELS_ARK=doubao-id,deepseek-id
  KIMI_BASE_URL  KIMI_API_KEY  HAE_MODELS_KIMI=moonshot-v1-...
  QWEN_BASE_URL  QWEN_API_KEY  HAE_MODELS_QWEN=qwen-...
  GLM_BASE_URL   GLM_API_KEY   HAE_MODELS_GLM=glm-...
  MINIMAX_BASE_URL MINIMAX_API_KEY HAE_MODELS_MINIMAX=...
  HUNYUAN_BASE_URL HUNYUAN_API_KEY HAE_MODELS_HUNYUAN=...
  HAE_WEB_SEARCH=1   # 1=各适配器启用联网搜索、强制回传 URL；0=纯参数回忆

统一 OpenAI 兼容 POST {base_url}/chat/completions。
联网搜索为各家工具/插件语法，封装在 _web_search_extra()。
"""
import json
import os
import pathlib
import re
import time
import urllib.request
import urllib.error

COST_DIR = pathlib.Path(os.environ.get("HAE_COST_DIR", "/app/data/cost"))
COST_LEDGER = COST_DIR / "model_usage.jsonl"

# ---------------------------------------------------------------------------
# 各 provider 规格：base_url 默认值（可被 env 覆盖）、联网搜索支持、注入语法
# ---------------------------------------------------------------------------
# 每个 web_search 注入为「额外 body 字段」（OpenAI 兼容约定）。
# 注意：各家联网搜索参数仍在演进，首次配 key 时请按返回报错微调 _web_search_extra。
PROVIDER_SPECS = {
    "ark": {
        "label": "火山方舟 ARK（豆包 Doubao + DeepSeek）",
        "base_url_env": "ARK_BASE_URL",
        "key_env": "ARK_API_KEY",
        "models_env": "HAE_MODELS_ARK",
        "default_base": "https://ark.cn-beijing.volces.com/api/v3",
        "supports_web": True,
        # ARK/豆包内置联网：tools 里声明 web_search 工具；DeepSeek 经 ARK 一般不支持联网
        "web_search_kind": "ark_tools",
    },
    "kimi": {
        "label": "Moonshot（Kimi）",
        "base_url_env": "KIMI_BASE_URL",
        "key_env": "KIMI_API_KEY",
        "models_env": "HAE_MODELS_KIMI",
        "default_base": "https://api.moonshot.cn/v1",
        "supports_web": True,
        "web_search_kind": "kimi_builtin",
    },
    "qwen": {
        "label": "DashScope 兼容模式（通义 Qwen）",
        "base_url_env": "QWEN_BASE_URL",
        "key_env": "QWEN_API_KEY",
        "models_env": "HAE_MODELS_QWEN",
        "default_base": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "supports_web": True,
        "web_search_kind": "qwen_enable_search",
    },
    "glm": {
        "label": "智谱（GLM）",
        "base_url_env": "GLM_BASE_URL",
        "key_env": "GLM_API_KEY",
        "models_env": "HAE_MODELS_GLM",
        "default_base": "https://open.bigmodel.cn/api/paas/v4",
        "supports_web": True,
        "web_search_kind": "glm_tools",
    },
    "minimax": {
        "label": "MiniMax",
        "base_url_env": "MINIMAX_BASE_URL",
        "key_env": "MINIMAX_API_KEY",
        "models_env": "HAE_MODELS_MINIMAX",
        "default_base": "https://api.minimaxi.com/v1",
        "supports_web": True,
        "web_search_kind": "minimax_tools",
    },
    "hunyuan": {
        "label": "混元 Hunyuan",
        "base_url_env": "HUNYUAN_BASE_URL",
        "key_env": "HUNYUAN_API_KEY",
        "models_env": "HAE_MODELS_HUNYUAN",
        "default_base": "https://api.hunyuan.cloud.tencent.com/v1",
        "supports_web": True,
        "web_search_kind": "hunyuan_websearch",
    },
}


def web_search_enabled() -> bool:
    return os.environ.get("HAE_WEB_SEARCH", "0").strip() not in ("0", "", "false", "False")


class Provider:
    """一个已配置的 provider：可能有多个 model_id。"""
    def __init__(self, name, spec, base_url, api_key, models):
        self.name = name
        self.spec = spec
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.models = models  # list[str]
        self.supports_web = spec["supports_web"]

    def __repr__(self):
        return f"<Provider {self.name} models={self.models} web={self.supports_web}>"


def load_providers() -> list:
    """读 env，返回【已配置（有 key 且声明了 models）】的 provider 列表。
    缺 key / 未声明 models 的 provider 自动跳过，绝不报错中断。

    多账号：优先读复数键 <KEY_ENV>S（逗号分隔的多把 key，如 ARK_API_KEYS=k1,k2），
    每把 key 生成一个独立 Provider（name=ark / ark2 / ark3…），各自独立 RPM/配额；
    未配复数键则回退到单数键 <KEY_ENV>（如 ARK_API_KEY）。"""
    out = []
    for name, spec in PROVIDER_SPECS.items():
        plural = os.environ.get(spec["key_env"] + "S", "").strip()
        single = os.environ.get(spec["key_env"], "").strip()
        if plural:
            keys = [k.strip() for k in plural.split(",") if k.strip()]
        else:
            keys = [single] if single else []
        models_raw = os.environ.get(spec["models_env"], "").strip()
        base = os.environ.get(spec["base_url_env"], "").strip() or spec["default_base"]
        if not keys or not models_raw:
            continue  # 未配置 → 静默跳过
        models = [m.strip() for m in models_raw.split(",") if m.strip()]
        for i, key in enumerate(keys):
            pname = name if i == 0 else f"{name}{i + 1}"
            out.append(Provider(pname, spec, base, key, models))
    return out


# ---------------------------------------------------------------------------
# 联网搜索注入：各家把「启用联网+回传来源」的参数塞进 OpenAI 兼容 body
# ---------------------------------------------------------------------------
def _web_search_extra(kind: str, model: str) -> dict:
    """返回要 merge 进 chat/completions body 的联网搜索参数。"""
    if kind == "ark_tools":
        # 豆包联网（当前 ARK chat/completions：仅需 {"type":"web_search"}；
        # 嵌套 web_search.enable 会 400 MissingParameter tools.function）。
        # DeepSeek 经 ARK 不支持联网，调用方应跳过。
        if "doubao" not in model:
            return {}
        return {"tools": [{"type": "web_search"}]}
    if kind == "kimi_builtin":
        return {"tools": [{"type": "builtin_function",
                           "function": {"name": "$web_search"}}]}
    if kind == "qwen_enable_search":
        # DashScope OpenAI 兼容模式：extra_body.enable_search 触发联网
        return {"enable_search": True, "include_search_results": True}
    if kind == "glm_tools":
        return {"tools": [{"type": "web_search", "web_search": {}}]}
    if kind == "minimax_tools":
        return {"tools": [{"type": "web_search"}] }
    if kind == "hunyuan_websearch":
        return {"web_search": {"enable": True, "search_result": True}}
    return {}


_URL_RE = re.compile(r"https?://[^\s)\]\"'<>，。；]+")


def _extract_sources(data: dict, text: str) -> list:
    """best-effort 从联网响应里抽取来源 URL。各家位置不一：
    - message.annotations / message.references / 顶层 citations；
    - 兜底：从正文正则抓 URL。去重保序。"""
    srcs = []
    msg = (data.get("choices") or [{}])[0].get("message", {}) or {}
    for field in ("annotations", "references", "search_results"):
        v = msg.get(field)
        if isinstance(v, list):
            for it in v:
                if isinstance(it, dict):
                    u = it.get("url") or it.get("link") or it.get("site_name")
                    if u and str(u).startswith("http"):
                        srcs.append(u)
    for u in _URL_RE.findall(text or ""):
        srcs.append(u)
    # 去重保序
    seen, out = set(), []
    for u in srcs:
        u = u.rstrip(".,;，。；")
        if u not in seen:
            seen.add(u); out.append(u)
    return out


def chat(provider: Provider, model: str, prompt: str,
         web_search: bool = True, timeout: int = 60) -> dict:
    """统一 OpenAI 兼容调用。返回 {ok, text, sources, model, provider, error}。
    绝不抛异常打断整舰队；失败记 error 继续其他模型。"""
    use_web = bool(web_search and provider.supports_web and web_search_enabled())
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content":
             "你是上海城市美食图鉴的事实线索引擎。只输出结构化 JSON 数组，不要客套。"
             "不知道就显式 null；禁止编造人名/年份/原话。每条 claim 带 "
             "claim_text/confidence/known_vs_inferred/confirm_queries/falsify_queries。"},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    if use_web:
        body.update(_web_search_extra(provider.spec["web_search_kind"], model))
    req = urllib.request.Request(
        provider.base_url + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {provider.api_key}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage") or {}
        return {"ok": True, "text": text, "sources": _extract_sources(data, text),
                "model": model, "provider": provider.name, "web": use_web,
                "usage": {"prompt": usage.get("prompt_tokens", 0),
                          "completion": usage.get("completion_tokens", 0),
                          "total": usage.get("total_tokens", 0)}}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:200]
        return {"ok": False, "text": "", "sources": [], "model": model,
                "provider": provider.name, "web": use_web, "usage": {},
                "error": f"HTTP {e.code}: {detail}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "text": "", "sources": [], "model": model,
                "provider": provider.name, "web": use_web, "usage": {},
                "error": str(e)[:200]}


def responses_chat(provider: Provider, model: str, prompt: str,
                   tools=None, timeout: int = 90) -> dict:
    """走【Responses API】(/responses + input)：当前 ARK 内置 web_search 仅在此可用，
    chat/completions 传 web_search 会 400 MissingParameter tools.function。
    返回与 chat() 同形：{ok,text,sources,model,provider,web,usage,error}。"""
    tools = tools or [{"type": "web_search"}]
    body = {
        "model": model,
        "input": [{"role": "user",
                   "content": [{"type": "input_text", "text": prompt}]}],
        "tools": tools,
        "stream": False,
    }
    req = urllib.request.Request(
        provider.base_url + "/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {provider.api_key}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        texts, srcs = [], []
        for item in data.get("output", []) or []:
            if item.get("type") == "message":
                for c in item.get("content", []) or []:
                    if c.get("type") == "output_text" and c.get("text"):
                        texts.append(c["text"])
                    for a in c.get("annotations", []) or []:
                        u = a.get("url") or a.get("link")
                        if u and str(u).startswith("http"):
                            srcs.append(u)
            if item.get("type") == "web_search_call":
                act = item.get("action") or {}
                for u in (act.get("urls") or []):
                    if str(u).startswith("http"):
                        srcs.append(u)
        text = "\n".join(texts)
        for u in _URL_RE.findall(text or ""):
            srcs.append(u)
        # 去重保序
        seen, out_s = set(), []
        for u in srcs:
            u = u.rstrip(".,;，。；")
            if u not in seen:
                seen.add(u); out_s.append(u)
        usage = data.get("usage") or {}
        return {"ok": True, "text": text, "sources": out_s, "model": model,
                "provider": provider.name, "web": True,
                "usage": {"prompt": usage.get("input_tokens", 0),
                          "completion": usage.get("output_tokens", 0),
                          "total": usage.get("total_tokens", 0)}}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:200]
        return {"ok": False, "text": "", "sources": [], "model": model,
                "provider": provider.name, "web": True, "usage": {},
                "error": f"HTTP {e.code}: {detail}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "text": "", "sources": [], "model": model,
                "provider": provider.name, "web": True, "usage": {},
                "error": str(e)[:200]}


def log_usage(task: str, result: dict) -> None:
    """把一次调用的 token 用量追加到成本账本（best-effort，失败不影响主流程）。"""
    u = result.get("usage") or {}
    if not u:
        return
    # 兼容归一化键(prompt/completion/total)与各家原始键(*_tokens)
    def pick(a, b):
        v = u.get(a)
        return v if v is not None else u.get(b, 0)
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "task": task,
           "provider": result.get("provider"), "model": result.get("model"),
           "prompt": pick("prompt", "prompt_tokens"),
           "completion": pick("completion", "completion_tokens"),
           "total": pick("total", "total_tokens")}
    try:
        COST_DIR.mkdir(parents=True, exist_ok=True)
        with COST_LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def cost_summary(days: int = 1) -> dict:
    """汇总成本账本：按模型/任务统计 token（默认当天，UTC+8 自然日）。"""
    import collections
    today = time.strftime("%Y-%m-%d")
    by_model = collections.defaultdict(lambda: [0, 0, 0, 0])
    by_task = collections.defaultdict(int)
    n_calls = 0
    if COST_LEDGER.exists():
        for line in COST_LEDGER.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not r.get("ts", "").startswith(today):
                continue
            n_calls += 1
            key = f"{r.get('provider')}/{r.get('model')}"
            m = by_model[key]
            m[0] += r.get("prompt", 0)
            m[1] += r.get("completion", 0)
            m[2] += r.get("total", 0)
            m[3] += 1
            by_task[r.get("task", "?")] += r.get("total", 0)
    return {
        "date": today, "calls": n_calls,
        "by_model": {k: {"prompt": v[0], "completion": v[1], "total": v[2], "calls": v[3]}
                     for k, v in sorted(by_model.items(), key=lambda x: -x[1][2])},
        "by_task": dict(sorted(by_task.items(), key=lambda x: -x[1])),
    }


def fleet_status() -> dict:
    """供 --status / 诊断用：列出各 provider 配置与联网能力（不打印 key）。"""
    out = []
    for name, spec in PROVIDER_SPECS.items():
        key = os.environ.get(spec["key_env"], "").strip()
        models = os.environ.get(spec["models_env"], "").strip()
        out.append({
            "provider": name, "label": spec["label"],
            "configured": bool(key and models),
            "supports_web_search": spec["supports_web"],
            "models_env": spec["models_env"],
            "has_key": bool(key),
        })
    return {"web_search_flag": web_search_enabled(), "providers": out}


if __name__ == "__main__":
    # 自测：打印舰队配置状态（不发请求、不打印 key）
    print(json.dumps(fleet_status(), ensure_ascii=False, indent=2))
    ps = load_providers()
    print(f"\n已配置 provider 数: {len(ps)}")
    for p in ps:
        print(" ", p)
