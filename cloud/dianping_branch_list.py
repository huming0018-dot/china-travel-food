#!/usr/bin/env python3
# dianping_branch_list.py — 模块B·chain 维度 TRUSTED 源
# 用途：给定品牌名，经大众点评搜索/商户分店列表页，返回真实分店清单。
# 设计：
#   - 礼貌低频（每次调用内部 sleep 2-4s）；失败优雅降级返回 []，不抛异常；
#   - cookie 从本地 .dianping_cookies.json 读，绝不打印/不外发 cookie 值；
#   - 仅作 chain_type 判定的第 2 独立 TRUSTED 源；预制/集团口径不借本 helper。
#
# 2026-10-01 修复（S03 实测验证）：
#   1) _load_cookie_str 兼容三种 cookie 形态：dict{k:v}、{"cookies":[{name,value}]}、
#      list[{name,value}] / ["k=v", ...] / ["k","v",...] 交替；cookie 文件在
#      FOOD_CLOUD_DIR、/app/cloud、/app/data 三处依次查找（FOOD_CLOUD_DIR 优先）。
#   2) search_branches 改用点评改版后真实结构：店名锚点 data-click-name="shop_title_click"
#      的 href + 店名，并尽量抽取相邻地址；旧的 class="...shopname..." 正则已失效。
import argparse, json, pathlib, time, os, sys, re

CLOUD = pathlib.Path(os.environ.get("FOOD_CLOUD_DIR", "/app/cloud"))

# cookie 候选路径：FOOD_CLOUD_DIR 优先，其次 /app/cloud，最后 /app/data
def _cookie_candidates():
    cands = []
    if os.environ.get("FOOD_CLOUD_DIR"):
        cands.append(pathlib.Path(os.environ["FOOD_CLOUD_DIR"]) / ".dianping_cookies.json")
    cands.append(CLOUD / ".dianping_cookies.json")
    cands.append(pathlib.Path("/app/data/.dianping_cookies.json"))
    # 去重保序
    seen, out = set(), []
    for p in cands:
        rp = str(p)
        if rp not in seen:
            seen.add(rp); out.append(p)
    return out

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _join_pairs(pairs):
    """pairs: iterable of (k, v) -> 'k=v; ...'。空值跳过。"""
    parts = ["%s=%s" % (k, v) for k, v in pairs if k not in (None, "") and v not in (None, "")]
    return "; ".join(parts)


def _load_cookie_str() -> str:
    """按三种形态解析 cookie 文件，绝不返回空以外的异常。绝不打印值。"""
    for path in _cookie_candidates():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        pairs = []
        if isinstance(data, dict):
            if isinstance(data.get("cookies"), list):
                # {"cookies": [{name,value}, ...]}
                for c in data["cookies"]:
                    if isinstance(c, dict):
                        pairs.append((c.get("name"), c.get("value")))
            else:
                # dict{k:v}
                pairs = list(data.items())
        elif isinstance(data, list):
            if data and isinstance(data[0], dict):
                # [{name,value}, ...]
                for c in data:
                    if isinstance(c, dict):
                        pairs.append((c.get("name"), c.get("value")))
            else:
                # list[str]：可能是 ["k=v", ...]，也可能是 ["k","v",...] 交替
                strs = [str(x) for x in data]
                joined = [s for s in strs if "=" in s]
                if joined:
                    return "; ".join(joined)
                # 交替 ["k","v", ...]
                pairs = [(strs[i], strs[i + 1]) for i in range(0, len(strs) - 1, 2)]
        s = _join_pairs(pairs)
        if s:
            return s
    return ""


def search_branches(brand: str, limit: int = 20):
    """返回 [{branch_name, branch_url, address, district}]。失败返回 []。"""
    import requests
    cookie = _load_cookie_str()
    if not cookie:
        print("[dianping] cookie missing/empty -> []", file=sys.stderr)
        return []
    headers = {"User-Agent": UA, "Cookie": cookie, "Referer": "https://www.dianping.com/"}
    out = []
    try:
        url = "https://www.dianping.com/search/keyword/1/0_" + requests.utils.quote(brand)
        time.sleep(2.5)
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print("[dianping] search http %s -> []" % r.status_code, file=sys.stderr)
            return []
        html = r.text
        # 店名锚点：data-click-name="shop_title_click"，href 为独立分店页
        pairs = re.findall(
            r'<a[^>]*data-click-name="shop_title_click"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html, re.S)
        # 地址：尽量抽取（不同页面结构略有差异），抽不到则留空，不影响 chain 判定
        addrs = re.findall(
            r'<span[^>]*class="[^"]*addr[^"]*"[^>]*>([^<]+)</span>', html)
        seen_urls = set()
        for i, (href, txt) in enumerate(pairs[:limit]):
            name = re.sub(r"<[^>]+>", "", txt).strip()
            if not name or href in seen_urls:
                continue
            seen_urls.add(href)
            addr = addrs[i].strip() if i < len(addrs) else ""
            out.append({"branch_name": name, "branch_url": href,
                        "address": addr, "district": ""})
    except Exception as e:
        print("[dianping] error %s -> []" % type(e).__name__, file=sys.stderr)
    return out


def chain_signal(brand: str) -> dict:
    """供 extractor 调用：返回 {is_chain, n_branches, branches, source_url}。
    ≥2 个独立分店页（不同 branch_url）即视为 chain 信号；地址可用时按地址去重。"""
    branches = search_branches(brand)
    if not branches:
        n = 0
    else:
        addrs = {b.get("address") for b in branches if b.get("address")}
        urls = {b.get("branch_url") for b in branches if b.get("branch_url")}
        # 有地址按地址，否则按独立分店 URL
        n = len(addrs) if len(addrs) >= 2 else len(urls)
    return {
        "brand": brand,
        "is_chain": n >= 2,
        "n_branches": n,
        "branches": branches,
        "source_url": "https://www.dianping.com/search/keyword/1/" + brand,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("brand")
    a = ap.parse_args()
    print(json.dumps(chain_signal(a.brand), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
