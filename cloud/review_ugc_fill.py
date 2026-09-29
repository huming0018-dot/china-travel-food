#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""review_ugc_fill.py — Phase 2 真实食客评价扩量（已在库、口味证据不足的餐厅）。

目标：为 active 但 0 真实 UGC 食客评价的餐厅（优先高端店）扩充「真实食客堂食笔记」证据。
证据单位：小红书单店笔记（note），正文含具体菜品 + 堂食细节，作者=笔记作者本人。
  - 与 cloud_review_fill.py（高德聚合分，trust=low，不计 taste）互补：本脚本只写 trust=mid/high 的真实 UGC。
  - 写库仅 INSERT reviews 行（review_kind=diner, is_verified_diner=true），
    由 DB 触发器 trg_reviews_taste 自动重算 score_taste/review_count（本脚本绝不 PATCH restaurants.score_*/review_count）。

通道与边界（A5）：
  - 小红书签名直连 HTTP（cloud/xhs_api.py），两账号轮替、account_b 走广州代理。
  - gap_pool 正后台并发用号 → 本脚本保守 pacing（搜索间隔 SEARCH_GAP=60s，min_gap=4s），不硬刷。
  - B站 UP主探店为 KOL 声音（常半商业），不直接当食客评价写（A1），本脚本不写 B站。

反软广（P6）：
  - 无具体菜名/食物词 → 直接丢弃（空话不计口味证据）。
  - 营销模板（hype 套话占比高、emoji  bullet 广告结构）→ 标记 is_fake_suspect=true 留痕但不计口味，计入「软广拦截」。
  - 真堂食笔记（≥1 菜名 + 具体体验）→ is_fake_suspect=false, trust=mid/high。
  - 宁空不假：锚定不上正确餐厅/分店 → 不绑。

实体锚定：
  - core = 店名剥括号分店后归一（common.cjk_norm）。core 在库内唯一 → 高置信。
  - core 对应多家（连锁多分店）→ 仅当笔记正文出现该分店 token（括号内地名）时才绑，否则跳过（不猜分店）。
  - 笔记 title+desc 归一后必须包含 core，否则视为讲别家，跳过。

幂等：按 source_url 去重；已存在的笔记不重复写。

用法：
  python3 review_ugc_fill.py                 # dry-run（默认，只打印计划）
  python3 review_ugc_fill.py --apply          # 真实写入
  --batch N      本轮处理几家店（默认 25）
  --min-price N 只处理人均>=N 的店（默认 500，高端优先）
  --max-notes N 每家店最多深取几篇笔记（默认 4）
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

import requests  # noqa: E402
import common as C  # noqa: E402
import xhs_api  # noqa: E402

PROXY_F = pathlib.Path(DATA) / "account_proxies.json"

# 保守 pacing（与后台 gap_pool 共存）
SEARCH_GAP = float(os.environ.get("UGC_SEARCH_GAP", "60"))   # 本脚本两次搜索之间 >=60s
MIN_GAP = float(os.environ.get("UGC_MIN_GAP", "4.0"))

# 营销套话 / 空话（P6 软广信号）
HYPE_RE = re.compile(r"(绝绝子|天花板|yyds|YYDS|封神|宝藏|闭眼冲|不踩雷|必吃|必打卡|码住|收藏|"
                     r"家人们|谁懂啊|太绝了|绝了|爱了|冲鸭|姐妹|打卡|网红|排队王|yyds)")
# emoji bullet 广告结构（✅🌸📍💰🚇🚨 密集）
AD_BULLET_RE = re.compile(r"[✅🌸📍💰🚇🚨🈶🉐✨💯🔥👍😍🤩🥰]")

POS_WORDS = ["好吃", "惊艳", "鲜嫩", "入味", "酥脆", "正宗", "推荐", "值得", "必点", "招牌",
             "满足", "惊喜", "细腻", "平衡", "层次", "干净", "地道", "扎实", "饱满", "弹牙",
             "二刷", "顶", "牛逼", "超值", "封神", "喜欢", "满意", "精致", "会再来", "回不去"]
NEG_WORDS = ["难吃", "失望", "踩雷", "翻车", "太咸", "腥", "发柴", "太腻", "不值", "后悔",
             "不推荐", "一般般", "避雷", "不推荐", "敷衍", "冤种", "不会再去", "走掉",
             "sorry", "踩", "寡淡", "失望"]

# 作者身份拦截（P6）：代订/招商/场地/婚庆/营销/品牌自营号 ≠ 真实食客
AUTHOR_INTERCEPT_RE = re.compile(
    r"(预定|代订|订座|预约|订位|场地|云看场|招商|策划|推广|管家|预订|排号|留位|"
    r"婚庆|婚宴|婚礼|朵蕴|招募|体验官|礼遇|携程|黑钻|礼遇官)")
# 作者名里的个人化后缀（命中则不像品牌官方号）
PERSONAL_MARKER = re.compile(r"(的|呀|呢|哈|啦|日记|笔记|吃货|吃|喝|喵|酱|子|er|爱)")


def _is_hotel_official(author):
    """作者名像酒店/餐厅官方号（含'酒店/饭店/公馆/会所'且无个人后缀）。"""
    if re.search(r"(酒店|大饭店|公馆|会所|餐饮管理|餐饮文化)", author) and not PERSONAL_MARKER.search(author):
        return True
    return False


def proxies_for(account):
    if not account or not PROXY_F.exists():
        return None
    try:
        url = json.loads(PROXY_F.read_text(encoding="utf-8")).get(account)
    except Exception:
        return None
    return {"http": url, "https": url} if url else None


class CoexistXhs(xhs_api.XhsApi):
    """两账号轮替 + 每账号独立出口 + 更保守节奏。"""

    def _send(self, method, uri, *, params=None, payload=None, _retried=False):
        acc = self.accounts[self.idx % len(self.accounts)]
        self.proxies = proxies_for(acc["name"])
        return super()._send(method, uri, params=params, payload=payload, _retried=_retried)


# ---------------------------------------------------------------- 文本判定
def strip_branch(name):
    """剥掉分店括号：荣府宴(南阳路店) -> (core='荣府宴', branch='南阳路店')。"""
    m = re.match(r"^\s*(.+?)\s*[（(]([^（）()]*)[）)]\s*$", name or "")
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return (name or "").strip(), ""


def dish_hits(text):
    """统计正文中出现的具体菜品/食物词命中数。"""
    hits = [w for w in C.DISH_WORDS if w and w in text]
    # 常见泛菜名也计入（地锅鸡/叉烧/菠萝油 等）——用 dishes_list 词表兜底
    try:
        for w in C.dishes_list(text) or []:
            if w and w not in hits and len(w) >= 2:
                hits.append(w)
    except Exception:
        pass
    return hits


def sentiment_taste(text):
    pos = sum(text.count(w) for w in POS_WORDS)
    neg = sum(text.count(w) for w in NEG_WORDS)
    if neg > pos and neg >= 1:
        return 2 if pos == 0 else 3
    if pos >= 3 and neg == 0:
        return 5
    if pos >= 1 and neg == 0:
        return 4
    return 3


def classify_note(text):
    """返回 (verdict, reason, dish_n)。
    verdict: 'accept' | 'fake' | 'drop' """
    dish = dish_hits(text)
    dish_n = len(set(dish))
    hype_n = len(HYPE_RE.findall(text))
    ad_bullets = len(AD_BULLET_RE.findall(text))
    has_substance = C.quote_has_substance(text) or dish_n >= 1
    if not has_substance:
        return "drop", "no_substance", dish_n
    # 软广模板：套话密集 + emoji广告结构 + 菜品稀薄
    if hype_n >= 4 and dish_n <= 1:
        return "fake", f"template_hype(hype={hype_n},dish={dish_n},bullet={ad_bullets})", dish_n
    if ad_bullets >= 8 and dish_n <= 1:
        return "fake", f"ad_bullet(bullet={ad_bullets},dish={dish_n})", dish_n
    if dish_n >= 1:
        return "accept", f"dish={dish_n},hype={hype_n}", dish_n
    return "drop", "thin", dish_n


def author_intercept(author, core):
    """返回拦截原因或 None。代订/招商号直接拦；品牌官方号（作者名即店名、无个人后缀）也拦。"""
    if not author:
        return None
    if AUTHOR_INTERCEPT_RE.search(author):
        return f"agent_account({author})"
    if _is_hotel_official(author):
        return f"hotel_official({author})"
    n_author = C.cjk_norm(author)
    n_core = C.cjk_norm(core)
    n_core_cjk = "".join(re.findall(r"[一-鿿]", n_core))  # 只取中文核心，剥离拉丁/空格
    # 品牌自营：作者名包含核心店名，且无个人化后缀（如「鮨吉兆」=店官方号）
    if n_core_cjk and len(n_core_cjk) >= 2 and n_core_cjk in n_author and not PERSONAL_MARKER.search(author):
        return f"brand_selfpost({author})"
    # 拉丁/混合店名官方号：归一化后作者名整体含店名核心串且无个人后缀（Mr & Mrs Bund / TORIKAZE鳥かぜ）
    n_core_lat = re.sub(r"[^a-z0-9]", "", n_core)
    if len(n_core_lat) >= 6 and n_core_lat in n_author and not PERSONAL_MARKER.search(author):
        return f"brand_selfpost_latin({author})"
    return None


def visit_from_ms(ms):
    try:
        v = int(ms or 0)
        if v < 1_000_000_000_000:  # 无时间戳/epoch0 → 留空，不写 1970
            return None
        return time.strftime("%Y-%m-%d", time.localtime(v / 1000))
    except Exception:
        return None


# ---------------------------------------------------------------- 目标集
def build_targets(min_price, batch):
    res = C.fetch_all("/restaurants",
                      "id,name,price_avg,status",
                      order_col="id")
    act = [r for r in res if r.get("status") == "active"]
    # 已有真实 UGC 的店
    rv = C.fetch_all("/reviews",
                     "restaurant_id,source_platform,trust_level,review_kind,is_fake_suspect,is_hidden",
                     order_col="id")
    ugc = set()
    for r in rv:
        if (r.get("review_kind") == "diner"
                and r.get("trust_level") in ("mid", "high")
                and not r.get("is_fake_suspect")
                and not r.get("is_hidden")):
            ugc.add(r["restaurant_id"])
    # 已有 source_url 集合（幂等）
    existing_urls = set()
    r2 = C.fetch_all("/reviews", "source_url", order_col="id")
    for r in r2:
        if r.get("source_url"):
            existing_urls.add(r["source_url"])

    # core 索引（连锁检测）
    core_index = defaultdict(list)
    for r in act:
        core, _br = strip_branch(r["name"])
        core_index[C.cjk_norm(core)].append(r)

    todo = [r for r in act
            if r["id"] not in ugc and (r.get("price_avg") or 0) >= min_price]
    todo.sort(key=lambda r: -(r.get("price_avg") or 0))
    return todo[:batch], existing_urls, core_index


def _poi_name(nc):
    """从 feed 详情里尽量取地点/POI 名（小红书打卡定位）。"""
    for k in ("location", "poi", "poi_info", "place"):
        v = nc.get(k)
        if isinstance(v, dict):
            for kk in ("name", "title", "poi_name"):
                if v.get(kk):
                    return str(v[kk])
        elif isinstance(v, str) and v:
            return v
    return ""


def note_matches_restaurant(note_text, rest_row, core_index, poi=""):
    """实体锚定：返回 (ok, reason)。
    锚定来源优先级：①正文/标题含店名；②笔记 POI 打卡定位名含店名（正文没写店名但定位在本店）。
    连锁多分店仍要求正文或 POI 命中分店 token。"""
    core, branch = strip_branch(rest_row["name"])
    ncore = C.cjk_norm(core)
    nt = C.cjk_norm(note_text)
    npoi = C.cjk_norm(poi or "")
    in_body = ncore in nt
    in_poi = bool(npoi) and ncore in npoi
    if not in_body and not in_poi:
        return False, "core_not_in_note"
    # 连锁多分店：必须命中分店 token（正文或 POI 任一命中即可）
    cands = core_index.get(ncore, [])
    if len(cands) > 1 and branch:
        if branch not in note_text and branch not in (poi or ""):
            return False, f"branch_ambiguous({branch})"
    return True, "ok" + ("+poi" if (in_poi and not in_body) else "")


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--from-plan", default="", help="离线处理已有计划 JSON（不再请求 XHS）")
    ap.add_argument("--batch", type=int, default=int(os.environ.get("UGC_BATCH", "25")))
    ap.add_argument("--min-price", type=int, default=int(os.environ.get("UGC_MIN_PRICE", "500")))
    ap.add_argument("--max-notes", type=int, default=int(os.environ.get("UGC_MAX_NOTES", "4")))
    args = ap.parse_args()

    # ---------- --from-plan：离线重过滤已采集候选（不请求 XHS） ----------
    if args.from_plan:
        plan_in = json.loads(pathlib.Path(args.from_plan).read_text(encoding="utf-8"))["plan"]
        # rid -> name（用于品牌号拦截）
        rmap = {r["id"]: r["name"] for r in C.fetch_all("/restaurants", "id,name", order_col="id")}
        # DB 已有 source_url（幂等：复跑不重复写）
        existing_urls = set(x["source_url"] for x in C.fetch_all("/reviews", "source_url", order_col="id") if x.get("source_url"))
        out = []
        n_int = n_keep = n_dup = 0
        for row in plan_in:
            if row.get("source_url") in existing_urls:
                n_dup += 1
                continue
            core, _ = strip_branch(rmap.get(row["restaurant_id"], ""))
            aint = author_intercept(row["author_name"], core)
            # 重算口味分（用改进词表）
            new_taste = sentiment_taste(row.get("content", "") + (row.get("aspect_json", {}).get("note_title") or ""))
            row["aspect_taste"] = new_taste
            if aint or row.get("is_fake_suspect"):
                row["is_fake_suspect"] = True
                row["is_verified_diner"] = False
                row["trust_level"] = "low"
                row.setdefault("aspect_json", {})["intercept"] = aint or row["aspect_json"].get("intercept", "template")
                n_int += 1
            else:
                n_keep += 1
            out.append(row)
        print(f"[from-plan] 候选 {len(out)}：保留真证据 {n_keep}，软广/非食客留痕 {n_int}，DB已存在跳过 {n_dup}")
        for r in out:
            tag = "拦截" if r["is_fake_suspect"] else "保留"
            print(f"  [{tag}] rid={r['restaurant_id']} {r['author_name']} | taste={r['aspect_taste']} | {r['aspect_json'].get('intercept','')}")
        if not args.apply:
            print("[DRY-RUN] --from-plan 未写库。")
            return 0
        h = dict(C.headers()); h["Prefer"] = "return=representation"
        written = 0
        for row in out:
            try:
                rr = requests.post(C.BASE + "/reviews", headers=h, json=row, timeout=30)
                if rr.status_code in (200, 201): written += 1
                else: print(f"  [写入失败 {rr.status_code}] rid={row['restaurant_id']} {rr.text[:120]}")
            except Exception as e:
                print(f"  [写入异常] {e}")
            time.sleep(1.0)
        print(f"[APPLY from-plan] 写入 {written}/{len(out)} 行。")
        return 0

    targets, existing_urls, core_index = build_targets(args.min_price, args.batch)
    print(f"目标：人均>={args.min_price} 且 0 真实UGC 的 active 店，取前 {len(targets)} 家")
    print(f"模式：{'APPLY（写库）' if args.apply else 'DRY-RUN（只计划）'}")
    print(f"已有 source_url {len(existing_urls)} 条（幂等去重）")

    api = CoexistXhs(min_gap=MIN_GAP, city="上海")
    api.search_gap = SEARCH_GAP
    print(f"账号：{[a['name'] for a in api.accounts]}；搜索节奏 {api.search_gap:.0f}s/次")
    if not api.accounts:
        print("无可用 XHS 账号，退出。")
        return 1

    plan = []   # 拟写 reviews 行
    stat = {"searched": 0, "notes_fetched": 0, "anchored": 0,
            "accept": 0, "fake": 0, "drop": 0, "dup": 0, "blocked_pace": 0}

    for ti, rest in enumerate(targets):
        rid = rest["id"]
        name = rest["name"]
        core, branch = strip_branch(name)
        kw = core if "上海" in core else f"{core} 上海"
        print(f"\n[{ti+1}/{len(targets)}] rid={rid} {name} (¥{rest.get('price_avg')})")
        try:
            items = api.search(kw)
        except Exception as e:
            print(f"  search异常 {e}")
            continue
        stat["searched"] += 1
        if not items:
            print("  无搜索结果")
            continue

        # 取数优先级：标题/摘要直接点名本店的笔记排前面（榜单合集/泛菜系帖靠后），
        # 避免把有限 feed 配额浪费在不含店名的合集上。
        _ncore = C.cjk_norm(core)
        def _hit_title(it):
            sc = it.get("note_card") or {}
            t = C.cjk_norm((sc.get("display_title") or "") + " "
                           + str(sc.get("desc") or ""))
            return _ncore in t
        items = sorted(items, key=lambda it: not _hit_title(it))

        accepted_here = 0
        for it in items[: args.max_notes]:
            nid, tok = it.get("id"), it.get("xsec_token")
            if not nid or not tok:
                continue
            try:
                sc = it.get("note_card") or {}
                nc = api.feed(nid, tok) or sc
            except Exception as e:
                print(f"  feed异常 {e}")
                continue
            stat["notes_fetched"] += 1
            title = nc.get("title") or sc.get("display_title") or ""
            desc = nc.get("desc") or ""
            text = f"{title}\n{desc}"
            poi = _poi_name(nc) or _poi_name(sc)
            author = ((nc.get("user") or {}).get("nickname")
                       or (sc.get("user") or {}).get("nickname") or "")
            t_ms = nc.get("time") or 0
            url = (f"https://www.xiaohongshu.com/explore/{nid}"
                   f"?xsec_token={tok}&xsec_source=pc_search")

            # 锚定正确餐厅/分店（正文或 POI 打卡定位命中店名）
            ok, why = note_matches_restaurant(text, rest, core_index, poi=poi)
            if not ok:
                print(f"  [跳过-锚定] {why} | {title[:24]}")
                continue
            stat["anchored"] += 1

            # 作者身份拦截：代订/招商/品牌自营号不计真实食客证据（留痕 is_fake_suspect=true）
            aint = author_intercept(author, core)
            if aint:
                stat["fake"] += 1
                if url not in existing_urls:
                    taste = sentiment_taste(text)
                    plan.append({
                        "restaurant_id": rid,
                        "author_name": author or "小红书食客",
                        "source_platform": "小红书",
                        "source_url": url,
                        "content": desc[:2000] or title[:500],
                        "review_kind": "diner",
                        "is_verified_diner": False,
                        "trust_level": "low",
                        "aspect_taste": taste,
                        "visit_date": visit_from_ms(t_ms),
                        "is_fake_suspect": True,
                        "is_hidden": False,
                        "aspect_json": {"note_title": title[:120], "intercept": aint,
                                        "channel": "xhs_signed_http"},
                    })
                    existing_urls.add(url)
                print(f"  [作者拦截-{aint}] {author} | {title[:24]}")
                continue

            verdict, reason, dish_n = classify_note(text)
            if url in existing_urls:
                stat["dup"] += 1
                print(f"  [重复] {title[:24]}")
                continue
            if verdict == "drop":
                stat["drop"] += 1
                print(f"  [丢弃-{reason}] {title[:24]}")
                continue

            taste = sentiment_taste(text)
            trust = "high" if dish_n >= 2 else "mid"
            row = {
                "restaurant_id": rid,
                "author_name": author or "小红书食客",
                "source_platform": "小红书",
                "source_url": url,
                "content": desc[:2000] or title[:500],
                "review_kind": "diner",
                "is_verified_diner": True,
                "trust_level": trust,
                "aspect_taste": taste,
                "visit_date": visit_from_ms(t_ms),
                "is_fake_suspect": (verdict == "fake"),
                "is_hidden": False,
                "aspect_json": {"note_title": title[:120], "dish_hits": dish_n,
                                "classify": reason, "channel": "xhs_signed_http"},
            }
            plan.append(row)
            existing_urls.add(url)
            if verdict == "fake":
                stat["fake"] += 1
                print(f"  [软广拦截-{reason}] {author} | {title[:24]}")
            else:
                stat["accept"] += 1
                accepted_here += 1
                print(f"  [采纳 taste={taste} trust={trust}] {author} | {title[:24]}")

    # ---------------- dry-run / apply ----------------
    print("\n=== 本轮采集统计 ===")
    print(json.dumps(stat, ensure_ascii=False, indent=2))
    print(f"拟写 reviews 行：{len(plan)}（其中真证据 {stat['accept']}，软广留痕 {stat['fake']}）")

    # 按餐厅聚合，看 evidence 提升
    by_rest = defaultdict(lambda: {"accept": 0, "fake": 0})
    for row in plan:
        key = "accept" if not row["is_fake_suspect"] else "fake"
        by_rest[row["restaurant_id"]][key] += 1
    gain1 = sum(1 for k, v in by_rest.items() if v["accept"] >= 1)
    gain3 = sum(1 for k, v in by_rest.items() if v["accept"] >= 3)
    print(f"获 >=1 条真证据的餐厅：{gain1}；获 >=3 条真证据：{gain3}")

    if not args.apply:
        print("\n[DRY-RUN] 未写库。加 --apply 写入。")
        # 落盘计划供核对
        out = pathlib.Path(DATA) / "ugc_fill_plan.json"
        out.write_text(json.dumps({"stat": stat, "plan": plan,
                                   "gain_ge1": gain1, "gain_ge3": gain3},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"计划已落盘 {out}")
        return 0

    # apply：仅 POST /reviews，绝不 PATCH restaurants
    written = 0
    h = dict(C.headers())
    h["Prefer"] = "return=representation"
    for row in plan:
        try:
            r = requests.post(C.BASE + "/reviews", headers=h, json=row, timeout=30)
            if r.status_code in (200, 201):
                written += 1
            else:
                print(f"  [写入失败 {r.status_code}] rid={row['restaurant_id']} {r.text[:120]}")
        except Exception as e:
            print(f"  [写入异常] {e}")
        time.sleep(1.0)
    print(f"\n[APPLY] 实际写入 reviews {written}/{len(plan)} 行。")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
