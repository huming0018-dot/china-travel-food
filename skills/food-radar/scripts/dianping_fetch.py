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
    async def pick_all(sels):
        """按 selector 顺序返回**所有**非空文本，供逐个尝试解析。

        #25 旧实现 pick() 只返回第一个非空节点：该节点解析失败就整字段放弃，
        后续本来合法的 selector 永远不被尝试（反例 3）。
        """
        vals = []
        for s in sels:
            try:
                n = await page.query_selector(s)
            except Exception:
                continue
            if not n:
                continue
            try:
                v = (await n.inner_text()).strip()
            except Exception:
                continue
            if v:
                vals.append(v)
        return vals

    out = {}

    # 评分：必须是纯数字形状，且落在 0..5。
    # "5.9" 形状合法但超上限 → 拒绝；"无评分" 形状不符 → 换下一个 selector。
    out["score"] = None
    for raw in await pick_all(["#comment_score .score", ".comment-score .score",
                               "h1 ~ div [class*=score]"]):
        m = re.fullmatch(r"(\d(?:\.\d)?)", raw)
        if m:
            v = float(m.group(1))
            if 0 <= v <= 5:
                out["score"] = v
                break

    # 评价数：纯数字或「N条」
    out["review_count"] = None
    for raw in await pick_all(["#reviewCount", "[class*=comment] .review-num", ".review-num"]):
        m = re.fullmatch(r"(\d+)\s*条?", raw)
        if m:
            out["review_count"] = int(m.group(1))
            break

    # 地址：必须像地址（含路/街/道 + 门牌）
    out["address"] = None
    for raw in await pick_all(["#addressTxt", ".address"]):
        if re.search(r"(路|街|道|大道)\s*\d+\s*[号弄]", raw):
            out["address"] = raw
            break

    # 价格：必须有**明确价格语义**（含「人均」或货币符号），而不是任意数字。
    #  · "38人推荐" 只是数字 → 拒绝；
    #  · "人均￥8" 语义明确 → 接受（不能用"下限 10 元"这类门槛代替语义判断，
    #    那会把合法低价误杀，反例 2）；
    #  · `commentMean` 是评分均值，本就不作价格来源，已从 selector 列表移除。
    out["price"] = None
    for raw in await pick_all(["[class*=avgPrice]", ".avg-price-title"]):
        if not re.search(r"(人均|[¥￥])", raw):
            continue
        m = re.search(r"[¥￥]\s*(\d+(?:\.\d+)?)", raw)
        if not m:
            m = re.search(r"人均[^\d]{0,4}(\d+(?:\.\d+)?)", raw)
        if not m:
            continue
        v = float(m.group(1))
        if 0 < v < 100000:
            out["price"] = v
            break

    for k in ("name", "score", "price", "review_count", "address", "open_time"):
        out.setdefault(k, None)
    out["parser"] = "dom-strict-v1"
    out["requires_visual_verification"] = True
    return out


def merge_detail(dom, text_parsed):
    """DOM 优先，缺失字段回退文本锚定解析。两边都没有就留None。

    #26 旧实现只在 DOM 缺失时回退，**两边都有值但不一致时静默采信 DOM**，
    冲突被吞掉。现在把冲突显式记录进 `conflicts`，保留双方原值，
    让调用方知道这个字段存在歧义、需要人工/截图复核。
    """
    merged = {}
    conflicts = {}
    for k in ("name", "score", "price", "review_count", "address", "open_time"):
        dv, tv = dom.get(k), text_parsed.get(k)
        if dv is not None and tv is not None and dv != tv:
            # #26 冲突不能默认采信 DOM（DOM 也曾把"38人推荐"当价格）。
            # 数值字段冲突时宁可留空交给可视化复核，也不给一个可能错的值。
            conflicts[k] = {"dom": dv, "text": tv, "taken": None}
            merged[k] = None
            continue
        merged[k] = dv if dv is not None else tv
    merged["conflicts"] = conflicts
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

    raw_stacked = re.findall(r"(\d+)\s*人推荐\n([^\n]{1,24}?)[ \t]*$", text, re.M)
    # #23 竖排分支同样要过滤非菜名行：紧随推荐人数出现的往往就是地址、电话、
    # 营业时间等元信息，不能因为它们排在"下一行"就被当成菜名。
    stacked = [(v, n) for v, n in raw_stacked
               if "人推荐" not in n
               and not re.search(r"(路|街|道|大道|号|弄|电话|营业时间|人均|地址|评分|条评价)", n)]
    if len(stacked) >= 2:
        return [{"name": n.strip(), "votes": int(v)} for v, n in stacked]
    # 说明：曾尝试在"原始多条、过滤后仅剩一条"时返回单条，但两列布局也会命中
    # 该形态（其 raw_stacked 同样是多条、过滤后只剩菜名那一条），会截断主路径。
    # 二者仅靠正则无法区分，因此放弃该降级：竖排残缺布局返回空列表，
    # 不完整但不造假，交由人工复核。

    votes = [int(x) for x in re.findall(r"(\d+)\s*人推荐", text)]
    if not votes:
        return []
    tail = re.split(r"\d+\s*人推荐", text)[-1]
    # #23 两列布局的 tail 会一直延伸到文末，若"网友推荐"区块后面紧跟地址、电话、
    # 营业时间等段落，这些行会被当成菜名（典型症状：菜名里出现"建国西路485号"）。
    # 因此必须在区块边界处截断，而不只是截在"查看全部"。
    tail = re.split(
        r"(查看全部|去大众点评App|查看更多|地址\s*[:：]|商户地址|电话\s*[:：]|营业时间\s*[:：]"
        r"|人均\s*[:：]?|评分|条评价|商户信息|商家信息|购买须知|推荐理由|附近推荐)", tail)[0]
    names = [ln.strip() for ln in tail.split("\n") if ln.strip()]
    # #23 B 两列分支同样要过滤：推荐人数之后紧跟的可能是地址/电话等元信息，
    # 单纯的"\d+人推荐"切分不会把它们排除，必须按内容特征剔除。
    names = [n for n in names
             if 2 <= len(n) <= 24 and not n.isdigit() and "人推荐" not in n
             and not re.search(r"(路|街|道|大道|号|弄|电话|营业时间|人均|地址|评分|条评价)", n)]
    return [{"name": names[i], "votes": votes[i]} for i in range(min(len(names), len(votes)))]


def parse_group_buy(text):
    """解析团购套餐：名称与到手价。

    关键约束（2026-10-18 修复）：**价格必须来自本套餐自己的段落**。
    原实现用 `【名】[\\s\\S]{0,120}?¥(\\d+)` 全局匹配，会在上一套餐没有价格时
    吃到**下一个套餐的价格**——把 ¥2980 安到无价的套餐A 上，属于编造数据。

    现按【…】切段：每个套餐只在自己的段内（到下一个【为止）找 ¥。
    本段内无价格 → price_cny=None，明确表示"未取到"，不借用他人价格。
    """
    marks = list(re.finditer(r"【[^】]{2,40}】[^\n]{0,30}", text))
    out = []
    for i, m in enumerate(marks):
        if i + 1 < len(marks):
            end = marks[i + 1].start()
        else:
            # #24 最后一段没有"下一个【"作右界，若取到文末会把正文金额算进来
            # （原始反例：'暂无价格\n网友评论\n停车费¥50' → 误得 50）。
            rest = text[m.start():]
            cut = re.search(
                r"(商家信息|商户信息|地址\s*[:：]|电话\s*[:：]|营业时间\s*[:：]"
                r"|网友推荐|网友评论|查看全部|购买须知|人均\s*[:：]|停车费?)", rest)
            end = m.start() + cut.start() if cut else len(text)
        segment = text[m.start():end]

        # 价格语义分级（#24 反例 2：'订金¥100\n套餐价¥800' 必须取 800）。
        # 1) 明确标签优先：套餐价/现价/售价/到手价/团购价
        price = None
        for label in ("套餐价", "现价", "售价", "到手价", "团购价"):
            lm = re.search(label + r"[^\d¥￥]{0,4}[¥￥]?\s*(\d+(?:\.\d+)?)", segment)
            if lm:
                price = float(lm.group(1))
                break
        # 2) 无明确标签时，取本段内第一个「不带附加费语义前缀」的金额
        if price is None:
            for pm in re.finditer(r"([^\n]{0,10})[¥￥]\s*(\d+(?:\.\d+)?)", segment):
                if re.search(r"(订金|定金|原价|门市价|停车|押金|服务费|配送|茶位)", pm.group(1)):
                    continue
                price = float(pm.group(2))
                break
        out.append({"set": m.group(0).strip(), "price_cny": price})
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
