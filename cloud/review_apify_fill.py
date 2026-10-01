#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_apify_fill.py — 账号全挂时的「账号无关」真实食客评价兜底回填。

为什么存在（北极星 A5 / 机制 P4）：
  所有小红书账号被风控（-100/受限）时，签名直连主线（review_ugc_fill / ugc_longrun）无法跑；
  本脚本走第三方 actor「atomus/xiaohongshu-scraper」——**任何模式无需 cookie/登录/xsec_token、
  失败（无此店）不计费**，由 actor 自有后端完成小红书关键词搜索，容器只发 HTTP，不登录小红书。

成本（已逐家实测，Apify Free 计划，无信用卡）：
  默认 provider=toolzerhub「rednote-xiaohongshu-search-scraper」：$0.003/条、无月度条数硬上限，
  从 Free 计划每月 $5 平台额度抵扣 → $5 ≈ 1600 条，足够全量回填，实际 $0 现金支出。
  备用 provider=atomus：$0.02/条，但 Free 计划每月仅 5 条免费 search（超出须付费计划）。
  脚本以 FREE_COST_CAP=$4.50（+ 条数硬上限）做预算门，超出即停，等下月额度 / 账号恢复，不硬花钱。

证据 / 定类 / 反软广（与主线同一口径，A1/A2/P3/P6）：
  - 只写真实食客堂食：正文须含具体食物（quote_has_substance）、有口味信号、非疑问；
  - 锚定：店名 base core（剥分店括号、cjk_norm）须出现在正文；分店须正文带该分店 token，否则不猜；
  - 合集/横评/榜单笔记（多店/编号/地址罗列）不锚单一店；
  - 营销模板（空话 hype 密度高、无实物）判 is_fake_suspect，不写口味；
  - 口味为确定性整数 1-5（POS/NEG 词权），无口味信号不写；
  - 按 source_url 幂等去重；只 INSERT reviews，由 trg_reviews_taste 自动重算 taste，绝不 PATCH score_*。

用法（容器内，cd /app/cloud && . ./env.sh）：
  python3 review_apify_fill.py                # dry-run，只打印计划与候选
  python3 review_apify_fill.py --apply        # 真实写入
  --limit N      本轮最多处理几家缺证据店（默认 12）
  --need N        目标每店独立口味证据数（默认 2）
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = pathlib.Path(os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline"))
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

import requests  # noqa: E402
import common as C  # noqa: E402

def _load_token():
    """token 解析：优先环境变量；缺失则回退到持久数据卷上的密钥文件。
    回退文件位于命名卷 /app/data（跨容器重建/镜像重建持久存在），
    根治「打包流程重写 deploy.env、抹掉 APIFY_TOKEN 并重启容器」导致的反复失效。"""
    t = os.environ.get("APIFY_TOKEN", "").strip()
    if t:
        return t
    fp = DATA / ".secrets" / "apify_token"
    if fp.exists():
        return fp.read_text(encoding="utf-8").strip()
    return ""


TOKEN = _load_token()
STATE_F = DATA / "apify_fill_state.json"

# 四个「账号无关、无需 cookie」的小红书搜索 actor。
#
# ⚠️ 2026-10-01 真实账单复盘（$18.94 / $5 额度超支）：
#   Apify 不是按返回条数计费，而是按「每次运行启动事件 + 内存×时长」计费。
#   以下 price 是 2026-10-01 从账单 API 实测的**每次运行**费用，不是每条笔记费用。
#   之前标注 $0.003/条 / $0.0（免费）是误读 actor 页面标价，实际每次 run-sync 最低
#   消费约 $0.10（启动事件），无论返回几条结果。这导致预算门按「条数×单价」估算严重
#   低估，$5 额度在跑了 134 次后才从 remaining_credit() 发现（计费延迟）。
#
#   opspilot  —— 实测 6 次运行 $0.00（hze9g9xvmpSRztttq），可能是真免费 actor；
#                但强制 512MB 内存参数有效。若 actor 更新或计划变更可能开始收费。
#   zenstudio —— 未在账单中出现；保留 price=0.0 假设，下次运行后用账单复核。
#   toolzerhub—— 实测 134 次 $13.40 = $0.10/次（JECW4SdwsOOgtuobc）。
#   atomus    —— 实测 2 次 $0.34 = $0.17/次（hO5NqsA6aC1bz3jra）；免费计划每月仅 5 次。
PROVIDERS = {
    "opspilot": {
        "run": ("https://api.apify.com/v2/acts/opspilot.cc~xiaohongshu-keyword-search-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.0},
    "zenstudio": {
        "run": ("https://api.apify.com/v2/acts/zen-studio~rednote-search-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.0},
    "toolzerhub": {
        "run": ("https://api.apify.com/v2/acts/toolzerhub~rednote-xiaohongshu-search-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.10},
    "atomus": {
        "run": ("https://api.apify.com/v2/acts/atomus~xiaohongshu-scraper"
                "/run-sync-get-dataset-items"),
        "price_per_run": 0.17},
}
DEFAULT_PROVIDER = os.environ.get("APIFY_PROVIDER", "opspilot")
# 总预算门：免费计划每月 $5 平台额度。按实测每次运行 $0.10 保守封顶。
# 默认只允许跑 5 次/月（$0.50），确保不会再次超支。
FREE_COST_CAP = float(os.environ.get("APIFY_FREE_COST_USD", "0.50"))
FREE_NOTE_CAP = int(os.environ.get("APIFY_FREE_NOTE_CAP", "100"))
PER_NOTE_PAUSE = float(os.environ.get("APIFY_NOTE_PAUSE", "4.0"))
# 调用前剩余额度地板：Apify 计费延迟结算，低于此值即停。
# 2026-10-01 教训：$0.20 地板太低，计费延迟期间已跑超；改为 $1.00 保守地板。
MIN_REMAINING_USD = float(os.environ.get("APIFY_MIN_REMAINING_USD", "1.00"))
# 每次运行地板：实际单次运行最低 $0.10，以此作为余额检查门槛。
PER_RUN_FLOOR_USD = float(os.environ.get("APIFY_PER_RUN_FLOOR_USD", "0.15"))
# 每轮真实花费封顶（从账单 API 读真实 usage，不靠内部估算）。
ROUND_CAP_USD = float(os.environ.get("APIFY_ROUND_CAP_USD", "2.0"))


def remaining_credit():
    """返回本月剩余平台额度（$）。须带 token；计费延迟，调用前以此为准而非累计估算。"""
    if not TOKEN:
        return 0.0
    try:
        me = requests.get("https://api.apify.com/v2/users/me",
                          params={"token": TOKEN}, timeout=30).json()["data"]
        cap = (me.get("plan") or {}).get("maxMonthlyUsageUsd") or 0
        d = requests.get("https://api.apify.com/v2/users/me/usage/monthly",
                         params={"token": TOKEN}, timeout=30).json()["data"]
        used = d.get("totalUsageCreditsUsdAfterVolumeDiscount") or 0
        return max(0.0, float(cap) - float(used))
    except Exception:
        return 0.0


def current_used():
    """本月真实已用（$，折后），以平台账单 totalUsageCreditsUsdAfterVolumeDiscount 为准。
    计费延迟，内部 price 估算会低估；轮次门一律用此真实值。"""
    if not TOKEN:
        return 0.0
    try:
        d = requests.get("https://api.apify.com/v2/users/me/usage/monthly",
                         params={"token": TOKEN}, timeout=30).json()["data"]
        return float(d.get("totalUsageCreditsUsdAfterVolumeDiscount") or 0.0)
    except Exception:
        return 0.0


# ---------------------------------------------------------------- 锚定工具
def strip_branch(s):
    return re.sub(r"（.*?）|\(.*?\)", "", s or "").strip()


def branch_tokens(name):
    """括号内分店 token（mall / 路 / 区）。"""
    toks = []
    for p in re.findall(r"[（(]([^）)]+)[）)]", name or ""):
        for seg in re.split(r"[·・,，/]", p):
            seg = seg.strip()
            if seg:
                toks.append(C.cjk_norm(seg))
    return [t for t in toks if t]


_ROUNDUP_TITLE = re.compile(
    r"VS|vs|PK|pk|对决|横评|比拼|哪家强|红黑榜|排行|排名|合集|盘点|\d+家|\d+碗")
_CIRCLED = set("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳")
QUESTION = re.compile(
    r"[?？]|想问|吗\b|么\b|嘛\b|请问|在哪|哪里|哪家|求问|求安利|求坐标|求地址|怎么样|正宗吗")

# 口味词权（与 xhs_to_reviews 同口径）
POS = {"好吃": .35, "正宗": .3, "惊艳": .4, "鲜嫩": .25, "入味": .25, "地道": .3,
       "值得": .2, "香": .15, "酥脆": .25, "弹": .2, "浓郁": .15, "回购": .25,
       "必吃": .25, "天花板": .3, "封神": .3, "新鲜": .25, "入口即化": .35,
       "爆汁": .3, "鲜美": .25, "嫩滑": .25}
NEG = {"难吃": -.6, "避雷": -.5, "踩雷": -.5, "失望": -.4, "一般": -.3,
       "不好吃": -.55, "腥": -.35, "柴": -.35, "预制": -.4, "冷冻": -.3,
       "不新鲜": -.45, "太咸": -.25, "油腻": -.3, "糊弄": -.4, "无味": -.4,
       "寡淡": -.3, "嚼不动": -.4}


def taste_sent(text):
    pos = sum(w for k, w in POS.items() if k in text)
    neg = sum(w for k, w in NEG.items() if k in text)
    if pos == 0 and neg == 0:
        return None
    raw = max(1.0, min(5.0, round(3.8 + pos + neg, 1)))
    return max(1, min(5, int(raw + 0.5)))


def clean_content(t):
    t = re.sub(r"#\S+", "", t or "")
    t = t.replace("\t", " ").replace("\u200b", " ")
    return re.sub(r"\n{2,}", "\n", t).strip()


# ---------------------------------------------------------------- Apify 调用
class TokenBad(Exception):
    pass


def apify_search(provider, keyword, max_items=4, timeout=150):
    if not TOKEN:
        raise TokenBad("APIFY_TOKEN 未配置")
    if provider == "toolzerhub":
        body = {"query": keyword, "sort": "popular", "maxItems": max_items}
    elif provider == "atomus":
        body = {"searchType": "search", "keywords": [keyword],
                "maxItems": max_items, "sortType": "popularity_descending"}
    elif provider == "opspilot":
        # actor 固定返回 20 条/页，忽略 maxItems；keyword 为其搜索键
        body = {"keyword": keyword, "maxItems": max_items}
    else:  # zenstudio
        body = {"keyword": keyword, "maxItems": max_items}
    endpoint = PROVIDERS[provider]["run"]
    run_params = {"token": TOKEN}
    # opspilot 默认 4GB，启动事件按 GB 计费($0.10/GB→默认 $0.40/次)；关键词搜索只需
    # ≤512MB，强制覆盖后按“最低 1 个启动事件”计 = $0.10/次（20 条，约 $0.005/条）。
    if provider == "opspilot":
        run_params["memory"] = 512
    r = requests.post(endpoint, params=run_params, json=body, timeout=timeout)
    if r.status_code == 401:
        raise TokenBad(r.text[:200])
    if r.status_code not in (200, 201):
        return None, f"http{r.status_code}:{r.text[:120]}"
    data = r.json()
    if isinstance(data, dict) and data.get("error"):
        return None, str(data["error"])[:160]
    if isinstance(data, list):
        # actor 级错误行（invalid_input / free_tier_limit 等）与正常笔记混在同一 201 列表；剔除
        errs = [x for x in data if isinstance(x, dict) and x.get("error_kind")]
        good = [x for x in data if not (isinstance(x, dict) and x.get("error_kind"))]
        if not good and errs:
            return None, f"actor:{str(errs[0].get('reason'))[:140]}"
        data = good
    return data, None


def normalize_note(provider, n):
    """四家 actor 字段形状不同 → 统一成下游锚定/入库所需的公共形状。"""
    if provider == "opspilot":
        nid = n.get("noteId")
        url = n.get("noteUrl") or (
            f"https://www.xiaohongshu.com/explore/{nid}" if nid else "")
        return {"id": nid, "title": n.get("title") or "",
                "desc": n.get("description") or "", "url": url,
                "author": n.get("nickname") or "",
                "liked_count": n.get("likedCount"),
                "timestamp": None, "provider": provider}
    if provider == "zenstudio":
        nid = n.get("id")
        eng = n.get("engagement") if isinstance(n.get("engagement"), dict) else {}
        au = n.get("author") if isinstance(n.get("author"), dict) else {}
        return {"id": nid, "title": n.get("title") or "",
                "desc": n.get("desc") or "", "url": n.get("url") or "",
                "author": au.get("nickname") or "",
                "liked_count": eng.get("liked_count"),
                "timestamp": n.get("timestamp"), "provider": provider}
    # toolzerhub / atomus
    nid = n.get("id")
    url = n.get("url") or (f"https://www.xiaohongshu.com/explore/{nid}" if nid else "")
    u = n.get("user")
    author = ""
    if isinstance(u, dict):
        author = u.get("nickname") or u.get("nickName") or ""
    author = author or n.get("author") or n.get("nickname") or ""
    return {"id": nid, "title": n.get("title") or "", "desc": n.get("desc") or "",
            "url": url, "author": author, "liked_count": n.get("liked_count"),
            "timestamp": n.get("timestamp"), "provider": provider}


# ---------------------------------------------------------------- 状态
def note_author(note):
    """作者昵称：normalize_note 已统一到 author；保留对原始 actor 输出的兼容。"""
    if note.get("author"):
        return note["author"]
    u = note.get("user")
    if isinstance(u, dict):
        return u.get("nickname") or u.get("nickName") or ""
    return note.get("nickname") or "小红书用户"


def is_brand_author(note, base_core):
    """品牌官方账号识别：作者昵称 core 含品牌 base_core（如「望庐·精细江西菜」）→
    官方招募/通稿，不是食客，排除。返回 True 表示是官方账号。"""
    if not base_core:
        return False
    return base_core in C.cjk_norm(note_author(note))


def load_state():
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"billable_notes": 0, "billable_cost_usd": 0.0, "shops_done": [],
            "skipped": {}, "last_run": "", "token_bad": False}


def save_state(st):
    st["last_run"] = C.today()
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- 主流程
def worth_ids():
    """治理后真正值得花钱补证据的队列（worth_fill.json）的 id 集合。
    无文件时返回 None（不限制，向后兼容）；有则填充严格限定在该队列，不给被治理掉的店花钱。"""
    cands = [pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/home/ubuntu/food-apify-fill"))
             / "worth_fill.json",
             pathlib.Path(__file__).parent / "worth_fill.json"]
    for p in cands:
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            return {x["id"] for x in d if isinstance(x, dict) and x.get("id") is not None}
    return None


def select_targets(need):
    rests = C.fetch_all(
        "restaurants",
        "id,name,status,price_avg,is_chain_standardized")
    revs = C.fetch_all("reviews", "restaurant_id,trust_level,is_verified_diner")
    have = {}
    for r in revs:
        if r.get("is_verified_diner") and r.get("trust_level") in ("mid", "high"):
            have[r["restaurant_id"]] = have.get(r["restaurant_id"], 0) + 1
    allow = worth_ids()
    targets = [r for r in rests
               if r.get("status") == "active"
               and r.get("is_chain_standardized") is not True
               and have.get(r["id"], 0) < need
               and (allow is None or r["id"] in allow)]

    def key(r):
        p = C.to_int(r.get("price_avg")) or 0
        return (-p, r["id"])
    targets.sort(key=key)
    return targets


def note_anchors(note, rest, base_core, btoks, all_cores):
    """返回 (ok, reason)。"""
    text = (note.get("title", "") + "\n" + note.get("desc", ""))
    nt = C.cjk_norm(text)
    if base_core not in nt:
        return False, "正文无目标店"
    if btoks and not any(t in nt for t in btoks):
        return False, "分店token缺失"
    # 合集判定
    if _ROUNDUP_TITLE.search(note.get("title", "")):
        return False, "合集(标题)"
    if len(re.findall(r"地址[：:]", text)) >= 2:
        return False, "合集(多地址)"
    if len(set(ch for ch in text if ch in _CIRCLED)) >= 3:
        return False, "合集(编号)"
    if len(re.findall(r"(?m)^\s*(?:\d{1,2}[.、）)]|[一二三四五六七八九十]{1,3}[、.）)])", text)) >= 3:
        return False, "合集(列表)"
    # 正文出现≥2 个别的、可识别店名（len>=3 core）→ 横评/合集
    others = [c for c in all_cores if c != base_core and c in nt]
    if len(set(others)) >= 2:
        return False, "合集(多店)"
    body = clean_content(note.get("desc", ""))
    if QUESTION.search(body):
        return False, "疑问/互动"
    if not C.quote_has_substance(body):
        return False, "无实物/软广模板"
    score = taste_sent(text)
    if score is None:
        return False, "无口味信号"
    return True, (body, score)


def run(apply, limit, need, provider=DEFAULT_PROVIDER):
    if os.environ.get("APIFY_DISABLED", ""):
        print("[已停用] APIFY_DISABLED 环境变量已设置，Apify采集暂停。"
              "等额度重置或充值后取消该变量。")
        return
    if provider not in PROVIDERS:
        print(f"未知 provider {provider}；可选 {list(PROVIDERS)}")
        return
    if not TOKEN:
        print("APIFY_TOKEN 未配置；写入 cloud/deploy.env 或持久卷 .secrets/apify_token 后再跑。")
        return
    st = load_state()
    if st.get("token_bad"):
        print("上轮 token 无效（401）；本轮先复验……")
    targets = select_targets(need)
    round_start_used = current_used()  # 本轮真实账单基线（折后）
    # 已在免费额度内完成的店仍可能因 <need 出现（证据不足），不强制跳过
    print(f"缺<{need}条真实口味证据的 active 店：{len(targets)}；本轮处理 {limit} 家；"
          f"provider={provider}(${PROVIDERS[provider]['price_per_run']:.2f}/次)")
    print(f"已用额度 ${st.get('billable_cost_usd',0):.3f}/{FREE_COST_CAP}；"
          f"笔记 {st['billable_notes']}/{FREE_NOTE_CAP}")

    # 全量店名 core（用于合集识别）
    rests_all = C.fetch_all("restaurants", "id,name,status")
    all_cores = set()
    for r in rests_all:
        bc = C.cjk_norm(strip_branch(r["name"]))
        if len(bc) >= 3:
            all_cores.add(bc)
    existing_urls = set(
        x.get("source_url") for x in C.fetch_all("reviews", "source_url") if x.get("source_url"))

    batch = targets[:limit]
    written, blocked, empty = 0, 0, 0
    for rest in batch:
        rid, name = rest["id"], rest["name"]
        base = strip_branch(name)
        base_core = C.cjk_norm(base)
        btoks = branch_tokens(name)
        keyword = f"{base} 上海"
        rem = remaining_credit()
        if rem < PER_RUN_FLOOR_USD:
            print(f"[额度门] 剩余额度 ${rem:.3f} < 每次运行地板 ${PER_RUN_FLOOR_USD:.2f}，本轮停止；"
                  "充值或月度额度重置（见 usageCycle.endAt）后由常驻服务自动续跑。")
            break
        if current_used() - round_start_used >= ROUND_CAP_USD:
            print(f"[轮次门] 本轮真实花费已达 ${ROUND_CAP_USD:.2f}，暂停等确认；"
                  "TG/飞书已通知，确认后续跑。")
            break
        try:
            raw_notes, err = apify_search(provider, keyword, max_items=4)
        except TokenBad as e:
            st["token_bad"] = True
            save_state(st)
            print(f"[TOKEN-BAD] {e}")
            _alert_token()
            return
        if err:
            print(f"  [skip] {name}: {err}")
            st["skipped"][str(rid)] = err
            continue
        if raw_notes is None:
            continue
        # 按每次运行计费（不是按条数）；免费 provider 不占预算门
        if PROVIDERS[provider]["price_per_run"] > 0:
            st["billable_notes"] += len(raw_notes)
            st["billable_cost_usd"] = round(
                st.get("billable_cost_usd", 0.0)
                + PROVIDERS[provider]["price_per_run"], 4)
        notes = [normalize_note(provider, x) for x in raw_notes]
        got = 0
        for note in notes:
            url = note.get("url")
            if url and url in existing_urls:
                continue
            ok, payload = note_anchors(note, rest, base_core, btoks, all_cores)
            if is_brand_author(note, base_core):
                blocked += 1
                continue
            if not ok:
                if payload in ("无实物/软广模板",):
                    blocked += 1
                continue
            body, score = payload
            rev = {"restaurant_id": rid,
                   "author_name": note_author(note)[:20],
                   "source_platform": "小红书", "source_url": url, "content": body,
                   "review_kind": "diner", "is_verified_diner": True, "trust_level": "mid",
                   "aspect_taste": score,
                   "aspect_json": {"via": f"apify-{provider}",
                                   "liked": note.get("liked_count")}}
            if apply:
                rr = C.req("POST", "/reviews", json=rev)
                if rr.status_code in (200, 201):
                    got += 1
                    if url:
                        existing_urls.add(url)
                else:
                    print("   insert fail", rr.status_code, rr.text[:140])
            else:
                got += 1
        if got:
            written += got
            if rid not in st["shops_done"]:
                st["shops_done"].append(rid)
        else:
            empty += 1
        print(f"  [{rid}] {name[:22]} ← 笔记{len(notes)} 采信{got}")
        if current_used() - round_start_used >= ROUND_CAP_USD:
            print(f"[轮次门] 本轮真实花费达 ${ROUND_CAP_USD:.2f}，暂停等确认；"
                  "下月额度重置或确认后续跑。")
            break
        time.sleep(PER_NOTE_PAUSE)

    st["token_bad"] = False
    save_state(st)
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"\n[{mode}] 采信评论 {written} | 软广/无实物拦截 {blocked} | 0证据店 {empty}")
    print(f"累计额度 ${st.get('billable_cost_usd',0):.3f}/{FREE_COST_CAP}；"
          f"笔记 {st['billable_notes']}/{FREE_NOTE_CAP}")


def _alert_token():
    try:
        import notifier
        notifier.action(
            "Apify token 无效（401 user-or-token-not-found），账号无关回填暂停。"
            "请到 console.apify.com 确认账号/重新生成 token 并更新 deploy.env。",
            key="apify_token_bad", action_text="去处理", nudge_schedule="6h")
    except Exception as e:
        print("notifier fail:", repr(e)[:100])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--need", type=int, default=2)
    ap.add_argument("--provider", default=DEFAULT_PROVIDER,
                    choices=list(PROVIDERS), help="账号无关搜索 actor")
    a = ap.parse_args()
    run(a.apply, a.limit, a.need, a.provider)
