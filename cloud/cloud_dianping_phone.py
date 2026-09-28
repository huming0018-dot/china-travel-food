#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_dianping_phone.py — 大众点评电话连接器（默认 dry-run、确定性、可复跑、幂等）。

目的：为库里 phone 为空的 active 店，按店名+城市在大众点评检索，锚定唯一正确门店
（记录点评 shop uuid/URL），并尝试取该店公开电话。

铁律（对齐宪法 A2 宁空不假 / A5 账号兜底）：
  - 大众点评网页版门店页**默认不渲染电话**（电话为 App 深链）。因此本连接器：
      * 锚定门店身份（shop uuid/URL/地址）作为证据；
      * 仅当门店页 HTML 里出现**结构化、可确证属于本店**的号码才采纳；
      * 查不到公开号码 → 留空，绝不编造、绝不用同名他店/错分店号码。
  - 只 PATCH restaurants.phone 一个字段；其余字段一律不动。
  - 号码必须过 common.clean_phone；且必须排除假阳性：poiId 碎片、点评客服 4003101100、
    URL 里的长数字串。
  - 仅当「high 置信名称匹配 + 地址/分店证据 + clean_phone 通过」三者同时满足才采纳。
  - 礼貌限速（每店间隔）、可复跑、幂等（已写过 phone 的店自动跳过）。

凭据：cookie 从 /app/data/.dianping_cookies.json 读取（gitignored，600），禁止入库/外发。

用法：
  python3 cloud_dianping_phone.py                # dry-run，出取证报告，不写库
  python3 cloud_dianping_phone.py --apply        # 自检确认后才真写
  python3 cloud_dianping_phone.py --limit 20     # 本轮最多处理 N 家
  python3 cloud_dianping_phone.py --only-named  # 只跑点名回归店
"""
import argparse
import json
import os
import pathlib
import re
import sys
import time
from difflib import SequenceMatcher
from urllib.parse import quote

import requests

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import common as C  # noqa: E402

COOKIE_F = pathlib.Path(os.environ.get("DIANPING_COOKIE_FILE",
                                       str(pathlib.Path(DATA) / ".dianping_cookies.json")))
REPORT_F = pathlib.Path(DATA) / "dianping_phone_report.json"
STATE_F = pathlib.Path(DATA) / "_dianping_phone_state.json"

# 机制排查结论（2026-09-28 实测，多店+连锁均验证）：
#   点评 web（www/m 门店页 + 桌面搜索页）均为 H5 shell，desc-phone 为空 CSS 图标/App 深链，
#   HTML 内嵌 JSON（shopConfig/__NEXT_DATA__）无 tel 字段；wxmapi/mapi 详情接口 404 或仅返回
#   服务能力标志；poi-bundle JS 无电话 API 路径。电话为 App-only。
#   故本连接器：锚定门店身份（uuid/URL/地址）作证据；仅当页面 HTML 真出现结构化号码才采纳，
#   否则留空并记录已验证入口。
CHECKED_ENTRIES = "www店页HTML+m店页HTML+wxmapi shopservice+内嵌JSON+poi-bundle JS 均无电话字段（App-only）"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
CITY_ID = 1  # 上海
SEARCH_URL = "https://www.dianping.com/search/keyword/{cid}/0_{kw}"

# 点名回归店（以库里 id 为准，优先处理）
NAMED_IDS = [1931, 1391, 1841, 1929, 1846, 1930, 1898, 1412,
             1386, 1895, 1923, 1926, 1905, 1390]

# 点评自家客服/测试号，绝不可当门店电话
DP_SERVICE_NUMS = {"4003101100", "4001091008", "10100000"}

SLEEP_PER_SHOP = float(os.environ.get("DP_PHONE_SLEEP", "4.0"))  # 礼貌限速


# ---------------------------------------------------------------- cookie / session
def load_session():
    if not COOKIE_F.exists():
        raise SystemExit(f"缺少点评凭据 {COOKIE_F}（gitignored），请先完成扫码登录")
    cookies = json.loads(COOKIE_F.read_text(encoding="utf-8"))
    s = requests.Session()
    for c in cookies:
        s.cookies.set(c["name"], c["value"], domain=c["domain"].lstrip("."))
    s.headers.update({
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return s


# ---------------------------------------------------------------- 名称/地址匹配
def _norm_name(s):
    return C.cjk_norm(s)


def name_sim(a, b):
    return SequenceMatcher(None, _norm_name(a), _norm_name(b)).ratio()


def addr_overlap(db_addr, dp_addr):
    """地址核心重合度：取 db 地址核心是否出现在点评地址里，反之亦然。"""
    a = C.addr_core(db_addr or "")
    b = C.addr_core(dp_addr or "")
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------- 搜索
def search_shops(sess, kw):
    """返回 [{uuid, name, addr, url}]。点评搜索结果店名在
    <a data-click-name="shop_title_click" data-shopid="UUID" title="店名" href="..."> 里。"""
    url = SEARCH_URL.format(cid=CITY_ID, kw=quote(kw))
    r = sess.get(url, timeout=25)
    body = r.text
    out = []
    for m in re.finditer(
            r'data-click-name="shop_title_click"[^>]*data-shopid="([A-Za-z0-9]{10,24})"[^>]*'
            r'title="([^"]{1,80})"', body):
        uuid, nm = m.group(1), m.group(2).strip()
        out.append({"uuid": uuid, "name": nm, "addr": "",
                    "url": f"https://www.dianping.com/shop/{uuid}"})
    # 兜底：若上面没匹配到（页面结构变体），退而用 href+title
    if not out:
        for m in re.finditer(
                r'href="(?:https?:)?//www\.dianping\.com/shop/([A-Za-z0-9]{10,24})"[^>]*'
                r'title="([^"]{1,80})"', body):
            out.append({"uuid": m.group(1), "name": m.group(2).strip(), "addr": "",
                        "url": f"https://www.dianping.com/shop/{m.group(1)}"})
    seen, uniq = set(), []
    for o in out:
        if o["uuid"] in seen:
            continue
        seen.add(o["uuid"])
        uniq.append(o)
    return uniq, body


# ---------------------------------------------------------------- 电话提取
# 只在门店页 HTML 里找；必须排除长数字串（poiId/URL）里误命中的号码。
_RE_LAND = re.compile(r"(?<![\d])(0\d{2,3}-?\d{7,8})(?![\d])")
_RE_MOBILE = re.compile(r"(?<![\d])(1[3-9]\d{9})(?![\d])")
_RE_400 = re.compile(r"(?<![\d])(400[-\s]?\d{3}[-\s]?\d{4})(?![\d])")


def extract_phones(body):
    """从门店页 HTML 提取候选电话（已排除 poiId/URL 碎片）。返回 [raw_str]。"""
    # 去掉所有 URL / poiId / deep-link 段，避免把长数字串里的子串当号码
    cleaned = re.sub(r'https?://\S+', ' ', body)
    cleaned = re.sub(r'poiId[=%:]\d+', ' ', cleaned)
    cleaned = re.sub(r'%\d+', ' ', cleaned)
    cands = []
    for pat in (_RE_400, _RE_LAND, _RE_MOBILE):
        for m in pat.finditer(cleaned):
            cands.append(m.group(1))
    # 去重 + 剔除点评客服号
    out = []
    for c in cands:
        digits = re.sub(r"\D", "", c)
        if digits in DP_SERVICE_NUMS:
            continue
        out.append(c)
    return list(dict.fromkeys(out))


def fetch_shop_page(sess, uuid):
    url = f"https://www.dianping.com/shop/{uuid}"
    r = sess.get(url, timeout=25)
    return r.text, url


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=int(os.environ.get("DP_PHONE_LIMIT", "0")))
    ap.add_argument("--only-named", action="store_true")
    args = ap.parse_args()

    sess = load_session()

    # 拉全量缺号 active 店
    rows = C.fetch_all("restaurants",
                       select="id,name,address,district,business_area,phone,status",
                       order_col="id",
                       extra="phone=is.null&status=eq.active")
    print(f"缺号 active 店共 {len(rows)} 家")

    # 点名店优先，其余按 id
    order = {rid: i for i, rid in enumerate(NAMED_IDS)}
    rows.sort(key=lambda r: (order.get(r["id"], 9999), r["id"]))
    if args.only_named:
        rows = [r for r in rows if r["id"] in order]
    if args.limit > 0:
        rows = rows[:args.limit]

    report = []
    adopted = 0
    for r in rows:
        rid, name, addr = r["id"], r["name"], r.get("address", "") or ""
        entry = {"id": rid, "name": name, "db_address": addr,
                 "dp_shop_uuid": None, "dp_url": None, "dp_name": None,
                 "dp_addr": None, "candidates": [], "confidence": None,
                 "decision": None, "reason": None}

        try:
            results, _ = search_shops(sess, name)
        except Exception as e:
            entry["decision"] = "error"
            entry["reason"] = f"search_exception: {e}"
            report.append(entry)
            print(f"[{rid}] {name} -> search error {e}")
            time.sleep(SLEEP_PER_SHOP)
            continue

        if not results:
            entry["decision"] = "leave_empty"
            entry["reason"] = "dianping 搜索无结果"
            report.append(entry)
            print(f"[{rid}] {name} -> 点评无搜索结果，留空")
            time.sleep(SLEEP_PER_SHOP)
            continue

        # 选最佳匹配：名称相似度 + 地址证据
        best, best_score = None, -1.0
        for res in results[:8]:
            ns = name_sim(name, res["name"])
            # 地址从搜索摘要里拿不到，先靠名称；进店页再核地址
            score = ns
            if score > best_score:
                best, best_score = res, ns

        if best is None:
            entry["decision"] = "leave_empty"
            entry["reason"] = "搜索结果无可用名称"
            report.append(entry)
            print(f"[{rid}] {name} -> 搜索结果无名称，留空")
            time.sleep(SLEEP_PER_SHOP)
            continue

        entry["dp_shop_uuid"] = best["uuid"]
        entry["dp_url"] = best["url"]
        entry["dp_name"] = best["name"]

        # 名称阈值：低于 0.6 视为不确定，不锚定
        if best_score < 0.60:
            entry["confidence"] = "low"
            entry["decision"] = "leave_empty"
            entry["reason"] = f"名称相似度 {best_score:.2f}<0.60，无法确证分店归属，留空"
            report.append(entry)
            print(f"[{rid}] {name} -> 名称不匹配({best_score:.2f} vs {best['name']})，留空")
            time.sleep(SLEEP_PER_SHOP)
            continue

        # 进店页
        try:
            body, page_url = fetch_shop_page(sess, best["uuid"])
        except Exception as e:
            entry["decision"] = "error"
            entry["reason"] = f"shop_page_exception: {e}"
            report.append(entry)
            time.sleep(SLEEP_PER_SHOP)
            continue

        # 从门店页地址核对分店
        m_addr = re.search(r'"(?:address|addr)"\s*:\s*"([^"]{4,80})"', body)
        dp_addr = m_addr.group(1) if m_addr else ""
        if not dp_addr:
            m2 = re.search(r'class="addressText[^"]*"[^>]*>\s*([^<]{4,80})', body)
            dp_addr = m2.group(1).strip() if m2 else ""
        entry["dp_addr"] = dp_addr
        aov = addr_overlap(addr, dp_addr)

        # 提取电话候选
        cands = extract_phones(body)
        entry["candidates"] = cands

        # 判定
        name_ok = best_score >= 0.75
        addr_ok = aov >= 0.5 or (not addr and best_score >= 0.85)
        if not cands:
            entry["confidence"] = "high" if (name_ok and addr_ok) else "medium"
            entry["decision"] = "leave_empty"
            entry["reason"] = (f"已锚定门店 {best['name']}（名称{best_score:.2f}/地址重合{aov:.2f}），"
                               f"但点评网页未公开电话 → 留空")
            report.append(entry)
            print(f"[{rid}] {name} -> 锚定 {best['name']} 但无公开电话，留空")
        else:
            # 有候选号码：逐个过 clean_phone
            chosen = None
            for c in cands:
                cleaned, issues, note = C.clean_phone(c)
                if cleaned and "phone_missing" not in issues and "phone_unparseable" not in issues:
                    chosen = cleaned
                    break
            if chosen and name_ok and addr_ok:
                entry["confidence"] = "high"
                entry["chosen_phone"] = chosen
                entry["decision"] = "adopt"
                entry["reason"] = (f"名称{best_score:.2f}+地址{aov:.2f} 确证本店；"
                                   f"号码 {chosen} 通过 clean_phone")
                adopted += 1
                print(f"[{rid}] {name} -> ✓ 采纳电话 {chosen}（{best['name']}）")
            else:
                entry["confidence"] = "low"
                entry["decision"] = "leave_empty"
                why = "clean_phone 未过" if not chosen else f"名称/地址证据不足(ns={best_score:.2f},addr={aov:.2f})"
                entry["reason"] = f"候选{cands} 但 {why}，宁空不假"
                print(f"[{rid}] {name} -> 候选号码证据不足，留空")

        report.append(entry)
        time.sleep(SLEEP_PER_SHOP)

    # 汇总
    adopt_n = sum(1 for e in report if e["decision"] == "adopt")
    empty_n = sum(1 for e in report if e["decision"] == "leave_empty")
    err_n = sum(1 for e in report if e["decision"] == "error")
    summary = {
        "mode": "apply" if args.apply else "dry-run",
        "processed": len(report), "adopt": adopt_n, "leave_empty": empty_n, "error": err_n,
        "report": report,
    }
    REPORT_F.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== 汇总（{summary['mode']}）===")
    print(f"处理 {len(report)} | 拟采纳 {adopt_n} | 留空 {empty_n} | 错误 {err_n}")
    print(f"取证报告: {REPORT_F}")

    if args.apply:
        written = 0
        for e in report:
            if e["decision"] != "adopt":
                continue
            pr = C.req("PATCH", f"/restaurants?id=eq.{e['id']}",
                       json={"phone": e["chosen_phone"]})
            if pr.status_code in (200, 204):
                written += 1
                print(f"  PATCHED [{e['id']}] {e['name']} = {e['chosen_phone']}")
            else:
                print(f"  PATCH FAIL [{e['id']}] {pr.status_code}")
        print(f"实际写入 {written} 条 phone")
        summary["written"] = written
        REPORT_F.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
