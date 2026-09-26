#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""authority_sitemap.py — 米其林「全量 sitemap 召回」兜底通道（确定性、可复跑）。

为什么存在（望庐漏店的根因）：
  michelin_collect 只靠"主列表 HTML 翻页"，实测上海主列表 153 家，漏掉了连续三年
  米其林的江西菜「望庐」(slug=wang-lu)；它没有和官方公布总数对账，漏了也无感知，
  authority_compare 又只在已抓到的 153 内比对，永远发现不了漏掉的店。
  米其林官网 sitemap（/sitemap.xml，全球餐厅全量索引；纯 requests 被反爬返回 202，
  必须用浏览器打开）能完整枚举上海 slug（实测 154，含 wang-lu）。

本脚本以 sitemap 为权威全量源：
  1) 解析 sitemap index，遍历全球餐厅段（ae-az / ae-du）所有页，提取上海全部 slug；
  2) 与官方公布总数（2026 上海 156）对账，不足报警、不静默；
  3) 多别名归一后与库对账：中文名（cjk_norm 繁简异体 + 中文数字→阿拉伯）、
     英文名、slug 的英文/拼音品牌前缀（解决"米泰"↔"Mi Thai"、"福一零一五"↔"福1015"）；
  4) 输出 exact/strong（在库）、weak/short（待人工）、none（真缺失，强制进补录闭环）。

慢网络执行法（实测 Clash 到米其林 TLS~5s、大 XML 完整传输 60s+，期间 CDP 忙、
navigate/wait_for_load 会超时）：
  - 用 bu.cdp("Page.navigate", url=页) 发起（立即返回；即便 Python 侧超时，后台仍加载）；
  - 用 Wait 工具等待该页传完（page1/page2 各约 60-75s）；
  - 再用轻量 js 读 loc、提取上海并落盘（每页立即写 _sitemap_cache.json，断点续跑）；
  - 全部页缓存后调 S.reconcile_cached(bu) 对账，不再导航慢页。

在 mac_computer_use_tool(plane="bu") cell 内：
    import sys; sys.path.insert(0, PIPE)
    import authority_sitemap as S
    S.run(bu, expected_total=156)                 # 网络好时一条跑完
    S.reconcile_cached(bu)                        # 慢网络、已分页采集后
"""
import json
import pathlib
import re
import sys
import time

try:
    import common as C
except Exception:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import common as C

PROJ = pathlib.Path(
    "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food")
AUTH = PROJ / "research" / "authority"
SITEMAP_INDEX = "https://guide.michelin.com/sitemap.xml"
LOCALE = "/sg/zh_CN"
SH_MARK = "/shanghai-municipality/shanghai/restaurant/"
GLOBAL_SEGMENTS = ("ae-az", "ae-du")

_CN_NUM = {"零": "0", "一": "1", "二": "2", "两": "2", "三": "3", "四": "4",
           "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}
_STOP1 = {"the", "la", "le", "da", "de", "yi", "new", "old", "little", "big",
          "au", "el", "al", "di", "san"}


def _locs(bu):
    return bu.js("return [...document.querySelectorAll('loc')].map(e=>e.textContent)")


def _wait_locs(bu, minimum=100, tries=10, pause=1.4):
    try:
        bu.wait_for_load(timeout=16)
    except Exception:
        pass
    locs = []
    for _ in range(tries):
        locs = _locs(bu)
        if len(locs) >= minimum:
            return locs
        bu.wait(pause)
    return locs


def _norm_digits(s):
    """连续≥2 个中文数字 → 阿拉伯（福一零一五→福1015）。"""
    return re.sub(r"[零一二两三四五六七八九]{2,}",
                  lambda m: "".join(_CN_NUM.get(ch, ch) for ch in m.group(0)), s)


def core(s):
    """去括号后缀 → cjk_norm（繁简/异体/小写/去标点）→ 中文数字归一。"""
    s = re.sub(r"[（(].*?[)）]", "", s or "")
    return _norm_digits(C.cjk_norm(s))


def _han(s):
    return "".join(ch for ch in s if "一" <= ch <= "鿿")


def _cjk_count(s):
    return len(_han(s))


def eligible(c):
    j = _cjk_count(c)
    # 2 个汉字已足够特异（唐阁/甬府/言盐）；1 汉字需总长≥3；纯拉丁需≥4（避开 pop/bar）
    return j >= 2 or (j == 1 and len(c) >= 3) or (j == 0 and len(c) >= 4)


def slug_brand_cores(slug):
    """slug 的英文/拼音品牌前缀候选（去数字 id，取前 1-3 段）。"""
    s = re.sub(r"-\d{5,}$", "", slug)
    parts = s.split("-")
    keys = set()
    for n in (1, 2, 3):
        if len(parts) >= n:
            head = parts[0]
            if n == 1 and head in _STOP1:
                continue
            keys.add(core(" ".join(parts[:n])))
    return {k for k in keys if eligible(k)}


def make_matcher(rests):
    index = {}
    for r in rests:
        for nm in (r["name"], r.get("name_en")):
            if nm:
                index.setdefault(core(nm), r)

    def match(cores):
        cores = [c for c in cores if c]
        for c in cores:
            if c in index:
                return index[c], "exact"
        strong, weak = [], []
        for c in cores:
            ch, c_han = _han(c), _han(c)
            if not eligible(c):
                # 纯拉丁短品牌（如 pop）：仅当库名以它开头且紧接非字母（汉字/数字）才 strong，
                # 避免误配 popot；这是对 eligible 门槛的必要例外。
                if not ch and len(c) >= 3:
                    for k, r in index.items():
                        nxt = k[len(c)] if len(k) > len(c) else ""
                        # 紧接字符不是 a-z 拉丁字母（汉字/数字均可），避免误配 popot
                        if k.startswith(c) and not ("a" <= nxt <= "z"):
                            strong.append(r)
                continue
            for k, r in index.items():
                k_han = _han(k)
                hit = False
                if ch and k_han and ch in k_han:
                    hit = "strong"                      # 中文专名连续包含
                elif c in k or k in c:
                    ratio = min(len(c), len(k)) / max(len(c), len(k))
                    hit = "strong" if (k.startswith(c) or ratio >= 0.6) else (
                        "weak" if ratio >= 0.35 else False)
                if hit == "strong":
                    strong.append(r)
                elif hit == "weak":
                    weak.append(r)
        # 单汉字品牌（坛/春/扒）：库内店名以该汉字开头，唯一→strong，多个→weak
        for c in cores:
            ch = _han(c)
            if len(ch) == 1:
                starts = [r for k, r in index.items() if _han(k).startswith(ch)]
                if len(starts) == 1:
                    return starts[0], "strong"
                if starts:
                    return starts[0], "weak"
        # 纯拉丁 3 字符（pop）：品牌开头且后一字符非字母（排除 popot 这类更长词）
        for c in cores:
            if _cjk_count(c) == 0 and len(c) == 3:
                heads = [r for k, r in index.items()
                         if k.startswith(c) and not k[len(c):len(c) + 1].isalpha()]
                if len(heads) == 1:
                    return heads[0], "strong"
        if strong:
            return strong[0], "strong"
        if weak:
            return weak[0], "weak"
        return None, "none"

    return match


def _index_restaurant_pages(bu, segments):
    bu.navigate(SITEMAP_INDEX)
    locs = _wait_locs(bu, minimum=100)
    out = {}
    for seg in segments:
        pages = [l for l in locs if f"/sitemap/restaurant/{seg}/page/" in l]
        pages = sorted(pages, key=lambda u: int(re.search(r"/page/(\d+)\.xml", u).group(1)))
        out[seg] = pages
    return out


def _page_shanghai_slugs(bu, page_url):
    bu.navigate(page_url)
    locs = _wait_locs(bu, minimum=2000, tries=12)
    out = {}
    for l in locs:
        if SH_MARK in l:
            slug = l.split(SH_MARK, 1)[1].strip()
            if slug:
                out[slug] = l
    return out


def _cache_p():
    return AUTH / "_sitemap_cache.json"


def _cache_load():
    p = _cache_p()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"pages": {}}


def _cache_save(c):
    _cache_p().write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")


def cached_slugs(segments=("ae-az",)):
    cache = _cache_load()
    slugs = {}
    for pu, got in cache["pages"].items():
        if any(f"/restaurant/{seg}/" in pu for seg in segments):
            slugs.update(got)
    return slugs


def collect_shanghai(bu, segments=GLOBAL_SEGMENTS, force=False):
    pages_by_seg = _index_restaurant_pages(bu, segments)
    cache = _cache_load()
    for seg, pages in pages_by_seg.items():
        for pu in pages:
            if not force and pu in cache["pages"]:
                print(f"  [缓存 {pu.rsplit('/',1)[-1]}] {len(cache['pages'][pu])}")
                continue
            got = _page_shanghai_slugs(bu, pu)
            cache["pages"][pu] = got
            _cache_save(cache)  # 每页立即落盘，超时可续跑
            print(f"  [{seg} {pu.rsplit('/',1)[-1]}] {len(got)}")
    return cached_slugs(tuple(segments))


def mainlist_slug_name():
    p = AUTH / "michelin_shanghai_153.json"
    out = {}
    if p.exists():
        for r in json.loads(p.read_text(encoding="utf-8")):
            if r.get("slug") and r.get("name"):
                out[r["slug"]] = r["name"]
    return out


def detail_name(bu, slug):
    url = ("https://guide.michelin.com" + LOCALE
           + "/shanghai-municipality/shanghai/restaurant/" + slug)
    h1js = "(()=>{const h=document.querySelector('h1');return h?h.innerText.trim():'';})()"
    ogjs = ("return (document.querySelector('meta[property='+JSON.stringify('og:title')"
            ")||{}).content||''")
    here = bu.js("return location.href") or ""
    if slug in here:                 # 已在目标详情页：直接读，不重新导航（避免慢页超时）
        nm = bu.js(h1js)
        if nm:
            return nm, url
    else:
        bu.navigate(url)
    for _ in range(10):
        nm = bu.js(h1js)
        if nm:
            return nm, url
        og = bu.js(ogjs)
        if og:
            head = re.split(r"[–-] Shanghai", og, 1)[0].strip()
            if head and "MICHELIN" not in head:
                return head, url
        bu.wait(1.5)
    return (bu.js("return document.title") or "").split(" – ")[0].strip(), url


def reconcile(bu, slugs, expected_total=156, fetch_missing_detail=True):
    print(f"sitemap 枚举上海 slug：{len(slugs)} / 官方公布 {expected_total}")
    if len(slugs) < expected_total:
        print(f"⚠ 仍差 {expected_total-len(slugs)} 家：可能在其它段/口径，需补段或核对官方名单")
    elif len(slugs) > expected_total:
        print("⚠ 多于官方口径：可能含已关/重复，需人工核对")

    slug_name = mainlist_slug_name()
    rests = C.fetch_all("restaurants", "id,name,name_en,status,district")
    matcher = make_matcher(rests)

    # 主列表没有的 slug（wang-lu）→ 抓详情页取中文名
    extra = [s for s in slugs if s not in slug_name]
    if fetch_missing_detail and extra:
        print(f"主列表未覆盖 {len(extra)} 个 slug，逐家抓详情页：{extra}")
        for s in extra:
            try:
                slug_name[s], _u = detail_name(bu, s)
                time.sleep(1.0)
            except Exception as e:
                print("  详情页失败", s, repr(e)[:80])

    rows, missing, uncertain = [], [], []
    for slug, url in sorted(slugs.items()):
        name = slug_name.get(slug, "")
        aliases = [core(name)] if name else []
        aliases += list(slug_brand_cores(slug))
        m, conf = matcher(aliases)
        if not eligible(core(name)) and conf in ("none", "weak"):
            conf = "short" if conf == "none" else conf
        row = {"slug": slug, "name": name, "url": url, "match_conf": conf,
               "matched_id": m["id"] if m else None,
               "matched_status": m["status"] if m else None}
        rows.append(row)
        if conf == "none":
            missing.append({"slug": slug, "name": name, "url": url})
        elif conf in ("weak", "short"):
            uncertain.append({"slug": slug, "name": name, "url": url, "reason": conf,
                              "candidate_id": m["id"] if m else None,
                              "candidate_name": m["name"] if m else None})

    (AUTH / "sitemap_shanghai.json").write_text(
        json.dumps({"expected_total": expected_total, "collected_total": len(slugs),
                    "restaurants": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    (AUTH / "authority_sitemap_missing.json").write_text(
        json.dumps({"missing": missing, "uncertain": uncertain},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    n_hit = len(rows) - len(missing) - len(uncertain)
    print(f"\n=== 对账结果 ===")
    print(f"sitemap 全量 {len(slugs)}；在库 {n_hit}；待确认 {len(uncertain)}；真缺失 {len(missing)}")
    for x in uncertain:
        cand = f"~ 候选 {x['candidate_name']}" if x.get("candidate_name") else "（短名/无候选）"
        print(f"  待确认：{x['name']}（{x['slug']}）{cand}")
    for x in missing:
        print(f"  缺：{x['name']}（{x['slug']}）")
    print("\n已写 sitemap_shanghai.json / authority_sitemap_missing.json")
    print("下一步：missing 强制进补录闭环（按 slug 详情取证 → 够门槛入库）；uncertain 人工裁定。")
    return {"total": len(slugs), "missing": missing, "uncertain": uncertain}


def run(bu, expected_total=156, segments=GLOBAL_SEGMENTS, fetch_missing_detail=True):
    print("=== sitemap 全量召回（上海）===")
    slugs = collect_shanghai(bu, segments)
    return reconcile(bu, slugs, expected_total, fetch_missing_detail)


def reconcile_cached(bu, expected_total=156, segments=("ae-az",), fetch_missing_detail=True):
    """直接用已落盘缓存对账，不再导航慢的 sitemap index / 大页。"""
    slugs = cached_slugs(segments)
    print(f"=== 用缓存对账（segments={segments}）===")
    return reconcile(bu, slugs, expected_total, fetch_missing_detail)


if __name__ == "__main__":
    raise SystemExit("本脚本需在浏览器 cell 内调用 S.run(bu)，不能纯命令行运行。")
