#!/usr/bin/env python3
"""Optional visible-page Dianping adapter; no cookie export or automatic login."""
import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit
from zoneinfo import ZoneInfo


def profile_path(root, surface, actor):
    if not surface or not actor:
        raise ValueError("trusted surface and actor are required")
    key = hashlib.sha256(json.dumps([surface, actor], ensure_ascii=False).encode()).hexdigest()
    return Path(root) / "profiles" / key / "dianping"


def shop_url(value):
    u = urlsplit(urljoin("https://www.dianping.com", value))
    if u.scheme != "https" or u.hostname != "www.dianping.com" or u.username or u.password or u.port:
        raise ValueError("only canonical Dianping shop URLs are accepted")
    m = re.fullmatch(r"/shop/([A-Za-z0-9]+)/?", u.path)
    if not m:
        raise ValueError("not a Dianping shop URL")
    return "https://www.dianping.com/shop/" + m[1]


def parse_detail(text, html=None):
    # Deliberately do not scan hidden HTML, scripts or unlabeled numbers.
    patterns = {
        "score": r"^\s*([0-5]\.\d)\s*分数\s*$",
        "price": r"^\s*人均\s*[:：]?\s*[¥￥]\s*(\d+(?:\.\d+)?)",
        "review_count": r"^\s*(\d+)\s*条评价\s*$",
        "address": r"^\s*地址\s*[:：]\s*([^\n]+)",
        "open_time": r"^\s*营业时间\s*[:：]\s*([^\n]+)",
    }
    result = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.M)
        result[key] = match[1].strip() if match else None
    for key in ("score", "price"):
        if result[key] is not None:
            result[key] = float(result[key])
    if result["score"] is not None and result["score"] > 5:
        result["score"] = None
    if result["review_count"] is not None:
        result["review_count"] = int(result["review_count"])
    result.update(parser="visible-labelled-text-v2", requires_visual_verification=True)
    return result


async def parse_detail_dom(page):
    """DOM 优先解析。**每个字段独立校验形状**，不合形状即丢弃。

    2026-10-18 实测（真实点评页）：DOM 选择器命中 2/5（score、address），
    文本锚定命中 0/5；而宽松选择器 `[class*=comment]` 曾把"38人推荐"
    当成评价数——这正是"智能兜底变静默造假"。故：
      · 数值字段必须有形状校验（分数 0–5、评价数为纯数字）
      · 形状不符一律丢弃，不"就近取值"
      · DOM 全失败时由调用方回退 parse_detail(text)
    返回值固定带 requires_visual_verification=True。
    """
    async def pick(sels):
        for s in sels:
            try:
                n = await page.query_selector(s)
            except Exception:
                continue
            if n:
                try:
                    v = (await n.inner_text()).strip()
                except Exception:
                    continue
                if v:
                    return v
        return None

    out = {}

    raw = await pick(["#comment_score .score", ".comment-score .score", "h1 ~ div [class*=score]"])
    if raw:
        m = re.fullmatch(r"([0-5](?:\.\d)?)", raw)
        if m:                      # 形状不符（如"38人推荐"）直接丢弃
            out["score"] = float(m.group(1))
        else:
            out["score"] = None

    raw = await pick(["#reviewCount", "[class*=comment] .review-num", ".review-num"])
    if raw:
        m = re.fullmatch(r"(\d+)\s*条?", raw)
        if m:
            out["review_count"] = int(m.group(1))
        else:
            out["review_count"] = None

    raw = await pick(["#addressTxt", ".address"])
    if raw and re.search(r"(路|街|道|大道)\s*\d+\s*[号弄]", raw):
        out["address"] = raw
    else:
        out["address"] = None

    raw = await pick(["[class*=avgPrice]", ".avg-price-title", "[class*=commentMean]"])
    if raw:
        m = re.search(r"(\d+(?:\.\d+)?)", raw)
        if m and 0 < float(m.group(1)) < 100000:
            out["price"] = float(m.group(1))
        else:
            out["price"] = None

    for k in ("name", "score", "price", "review_count", "address", "open_time"):
        out.setdefault(k, None)
    out["parser"] = "dom-strict-v1"
    out["requires_visual_verification"] = True
    return out


def merge_detail(dom, text_parsed):
    """DOM 优先，缺失字段回退文本锚定解析。两边都没有就留None。"""
    merged = {}
    for k in ("name", "score", "price", "review_count", "address", "open_time"):
        v = dom.get(k)
        if v is None:
            v = text_parsed.get(k)
        merged[k] = v
    merged["parser"] = dom.get("parser") if any(
        dom.get(k) is not None for k in ("score", "address", "price")) else text_parsed.get("parser")
    merged["requires_visual_verification"] = True
    return merged


def parse_recommended(text):
    """解析「网友推荐」菜名与推荐人数。只读可见文本，不扫隐藏内容。

    点评该区块是两列布局：可见文本会先读完所有"N人推荐"，再读完所有菜名，
    逐行配对会错位（把"16人推荐"当成菜名）。因此分派三种布局：
      A1 同行："17人推荐 玛德琳"
      A2 竖排相邻：votes 在上一行、菜名在下一行
      B  两列：先全部 votes，再全部菜名
    注意：配对正则里必须用 [ \\t]* 而非 \\s*，否则 \\s 会吃掉换行造成跨行误配。
    """
    paired = re.findall(r"(\d+)\s*人推荐[ \t]*([^\n]{1,20}?)[ \t]*$", text, re.M)
    paired = [(v, n) for v, n in paired if "人推荐" not in n]
    if len(paired) >= 2:
        return [{"name": n.strip(), "votes": int(v)} for v, n in paired]

    stacked = re.findall(r"(\d+)\s*人推荐\n([^\n]{1,24}?)[ \t]*$", text, re.M)
    stacked = [(v, n) for v, n in stacked if "人推荐" not in n]
    if len(stacked) >= 2:
        return [{"name": n.strip(), "votes": int(v)} for v, n in stacked]

    votes = [int(x) for x in re.findall(r"(\d+)\s*人推荐", text)]
    if not votes:
        return []
    tail = re.split(r"\d+\s*人推荐", text)[-1]
    tail = re.split(r"(查看全部|去大众点评App|查看更多)", tail)[0]
    names = [ln.strip() for ln in tail.split("\n") if ln.strip()]
    names = [n for n in names if 2 <= len(n) <= 24 and not n.isdigit() and "人推荐" not in n]
    return [{"name": names[i], "votes": votes[i]} for i in range(min(len(names), len(votes)))]


def parse_group_buy(text):
    """解析团购套餐：名称与到手价。

    套餐名与其价格通常**不在同一行**（中间夹有效期/退款说明），
    且 ¥ 与数字本身也可能被拆成两行（真实页面："¥\\n2980"）。
    因此允许跨行但限定 120 字符，¥ 后允许空白，取套餐名后第一个 ¥。
    只认可见文本中的「【…】」+ ¥数字。
    """
    out = []
    pat = r"(【[^】]{2,40}】[^\n]{0,30})[\s\S]{0,120}?¥\s*(\d+(?:\.\d+)?)"
    for name, price in re.findall(pat, text):
        out.append({"set": name.strip(), "price_cny": float(price)})
    return out


async def search(page, keyword, city_id, limit=10):
    if city_id < 1 or not 1 <= limit <= 10:
        raise ValueError("city_id must be positive and limit 1..10")
    url = "https://www.dianping.com/search/keyword/%d/0_%s" % (city_id, quote(keyword, safe=""))
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    links = page.locator('a[href*="/shop/"]')
    try:
        await links.first.wait_for(state="attached", timeout=12000)
        raw = await links.evaluate_all("(els) => els.slice(0,100).map(e => ({name:e.innerText.trim(),url:e.href}))")
    except Exception:
        return {"status": "channel_unverified", "reason": "login, challenge, layout or network; not proof of zero shops", "query_url": url, "results": []}
    result, seen = [], set()
    for row in raw:
        try:
            target = shop_url(row.get("url", ""))
        except ValueError:
            continue
        name = str(row.get("name", "")).strip()
        if name and target not in seen:
            result.append({"name": name, "url": target})
            seen.add(target)
        if len(result) == limit:
            break
    return {"status": "observed" if result else "channel_unverified", "query_url": url, "results": result, "reason": None if result else "no usable visible shop links; not proof of zero shops"}


async def run(args):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {"status": "dependency_missing", "fallback": "use host public search; optional Playwright adapter unavailable"}
    profile = profile_path(args.data_dir, args.surface, args.actor)
    profile.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(profile, 0o700)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(str(profile), headless=False, locale="zh-CN", viewport={"width":1280,"height":900})
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            if args.login:
                await page.goto("https://www.dianping.com", wait_until="domcontentloaded")
                print("请在独立浏览器窗口手动登录；完成后在此按回车。不会导出 Cookie。", file=sys.stderr)
                await asyncio.to_thread(input)
                result = {"status": "login_window_closed", "session_validity": "not_verified"}
            elif args.shop_url:
                url = shop_url(args.shop_url)
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                try:
                    same = shop_url(page.url) == url
                except ValueError:
                    same = False
                if same:
                    body_text = await page.locator("body").inner_text()
                    dom = await parse_detail_dom(page)
                    detail = merge_detail(dom, parse_detail(body_text))
                    detail["dom_fields"] = sorted(k for k in ("name","score","price","review_count","address","open_time")
                                                 if dom.get(k) is not None)
                    detail["recommended_dishes"] = parse_recommended(body_text)
                    detail["group_buy"] = parse_group_buy(body_text)
                    detail["dish_layout"] = (
                        "two_column" if len(detail["recommended_dishes"]) > 2 else "unknown")
                    usable = any(detail[k] is not None for k in ("score","price","address","open_time"))
                    result = {"status": "observed" if usable else "channel_unverified", "url": url, "detail": detail}
                else:
                    result = {"status": "channel_unverified", "url": url, "reason": "redirect/login/challenge; not closure evidence"}
            else:
                result = await search(page, args.keyword, args.city_id, args.limit)
            result["observed_at"] = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
            return result
        finally:
            await context.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("data-dir","surface","actor"):
        p.add_argument("--"+key, required=True)
    choice = p.add_mutually_exclusive_group(required=True)
    choice.add_argument("--keyword")
    choice.add_argument("--shop-url")
    choice.add_argument("--login", action="store_true")
    p.add_argument("--city-id", type=int)
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--out")
    args = p.parse_args()
    if args.keyword and (not args.city_id or args.city_id < 1):
        p.error("search requires a verified positive --city-id; never silently assumes Shanghai")
    if not 1 <= args.limit <= 10:
        p.error("--limit must be 1..10")
    try:
        result = asyncio.run(run(args))
    except Exception as e:
        result = {"status":"channel_unverified","error_type":type(e).__name__,"fallback":"host public search"}
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        path = Path(args.out)
        with os.fdopen(os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600), "w") as f:
            f.write(output+"\n")
        os.chmod(path, 0o600)
    print(output)
    return 0 if result["status"] in ("observed","login_window_closed") else 2


if __name__ == "__main__":
    raise SystemExit(main())
