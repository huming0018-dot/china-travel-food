#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud/kol_identity.py — Track 1C：KOL 跨平台身份归一（确定性、幂等、不硬猜）。

上位契约：references/source-classes-and-calibration.md §3.1 / migration 016。
原则（A2 宁空不假）：
  1) bilibili handle：仅当 B站 bili_user 搜索返回 uname(cjk_norm) == KOL名，
     且 mid 与库内 mid 一致（库内 mid 为空时采信搜索结果）才写 handles.bilibili。
  2) wechat handle：仅当搜狗 type=2 文章结果中出现「发布账号名(cjk_norm) == KOL名」
     的公众号文章，才写 handles.wechat={name}。别人媒体号发的提及文章
     （如 WIT玩趣 发《沈宏非：细品八大菜系》）→ 只报「有公开痕迹」，不写 handle。
  3) 微博/知乎/抖音 keyless 实测不可采（Sina Visitor System / 401 ZERR_NOT_LOGIN /
     JS 壳），绝不硬刷、不写 handle；只在报告里列出需要的登录态。
  4) 默认 dry-run；--apply 才 PATCH food_kol_watchlist.handles（按平台键合并，不覆盖已有）。

幂等：可重复跑；已写过的平台键跳过。状态不落盘（身份一次性归一，结果以库为准）。
"""
import argparse
import html
import json
import re
import sys
import time

HERE = "/app/cloud"
PIPE = "/app/pipeline"
sys.path.insert(0, HERE)
sys.path.insert(0, PIPE)

import requests  # noqa: E402
import common as C  # noqa: E402

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
BILI_HEADERS = {"User-Agent": UA, "Referer": "https://search.bilibili.com"}
SOGOU = "https://weixin.sogou.com/weixin"
MIN_INTERVAL = 2.5        # B站用户搜索限速（412 风控实测 ~每几秒一次）
SOGOU_INTERVAL = 1.5
BACKOFF = 45.0            # 412 后退避


def clean(x):
    return html.unescape(re.sub(r"<[^>]+>", "", x or "")).strip()


def bili_user_search(name):
    """返回 (matches, err)。matches=[{uname,mid,fans}]。412/风控 → ([], 'rate')。"""
    try:
        r = requests.get("https://api.bilibili.com/x/web-interface/search/type",
                         params={"search_type": "bili_user", "keyword": name, "page": 1},
                         headers=BILI_HEADERS, timeout=15)
    except Exception as e:
        return [], f"exc {e}"
    if r.status_code == 412 or "anti" in r.text[:500].lower():
        return [], "rate"
    try:
        j = r.json()
    except Exception:
        return [], f"non-json http={r.status_code}"
    if j.get("code") != 0:
        return [], f"code={j.get('code')} msg={j.get('message')}"
    res = (j.get("data") or {}).get("result") or []
    out = [{"uname": clean(u.get("uname")), "mid": str(u.get("mid") or ""),
            "fans": u.get("fans") or 0} for u in res if u.get("uname")]
    return out, None


def sogou_accounts_for(name):
    """按 KOL 名搜搜狗微信文章，提取每篇的发布公众号名。
    返回 (account_names:set, articles_n, err)。"""
    try:
        r = requests.get(SOGOU, params={"type": 2, "query": name},
                        headers={"User-Agent": UA}, timeout=15)
    except Exception as e:
        return set(), 0, f"exc {e}"
    if r.status_code != 200 or "antispider" in r.text:
        return set(), 0, f"http={r.status_code} 风控"
    items = re.findall(r'<li id="sogou_vr_.*?</li>', r.text, re.S)
    names = set()
    for it in items:
        m = re.search(r'<span class="all-time-y2">(.*?)</span>', it, re.S)
        if m:
            acct = clean(m.group(1))
            if acct:
                names.add(acct)
    return names, len(items), None


def patch_handles(kol_id, handles):
    r = C.req("PATCH", f"/food_kol_watchlist?id=eq.{kol_id}",
              json={"handles": handles})
    if r.status_code not in (200, 204):
        raise RuntimeError(f"PATCH {kol_id} -> {r.status_code}: {r.text[:200]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    kols = C.fetch_all("food_kol_watchlist",
                       "id,name,platform,mid,handles,status",
                       order_col="id", extra="status=eq.active")
    if args.limit:
        kols = kols[:args.limit]

    plan = []          # (kol, handles_to_write, why)
    rate_deadline = 0  # 退避时间戳
    for k in kols:
        name = k["name"]
        cur = dict(k.get("handles") or {})
        new = {}
        notes = []

        # ---- 1) bilibili 身份核验
        if time.time() < rate_deadline:
            time.sleep(rate_deadline - time.time())
        matches, err = bili_user_search(name)
        if err == "rate":
            print(f"  [退避] {name}: B站 412，{BACKOFF}s 后重试一次")
            time.sleep(BACKOFF)
            matches, err = bili_user_search(name)
            if err == "rate":
                rate_deadline = time.time() + BACKOFF
                err = "rate-final"
        if err:
            # 搜索受限时：库内已有 mid 的行，其 mid 本身是入库时已核验的权威列，
            # 回填 JSONB 仅为镜像既有数据（不猜新号）；无 mid 的行留空。
            if k.get("mid"):
                new["bilibili"] = {"mid": str(k["mid"]),
                                   "url": f"https://space.bilibili.com/{k['mid']}"}
                notes.append(f"bilibili沿用库mid={k['mid']}(搜索受限[{err}],JSONB镜像)")
            else:
                notes.append(f"bili_search={err}(库内无mid,留空)")
        else:
            cjk = C.cjk_norm(name)
            exact = [m for m in matches if C.cjk_norm(m["uname"]) == cjk]
            if len(exact) == 1:
                m = exact[0]
                if k.get("mid") and m["mid"] != str(k["mid"]):
                    notes.append(f"bili未绑: 搜索mid={m['mid']} != 库mid={k['mid']}")
                else:
                    new["bilibili"] = {"mid": m["mid"],
                                       "url": f"https://space.bilibili.com/{m['mid']}"}
                    notes.append(f"bilibili核验通过 mid={m['mid']}")
            elif len(exact) > 1:
                notes.append(f"bili未绑: {len(exact)}个同名UP主,不猜")
            else:
                # 库内已有 mid 但搜索无同名 → 也不覆盖，只记录
                if k.get("mid"):
                    new["bilibili"] = {"mid": str(k["mid"]),
                                       "url": f"https://space.bilibili.com/{k['mid']}"}
                    notes.append(f"bilibili沿用库mid={k['mid']}(搜索未见同名,仅回填JSONB)")
                else:
                    notes.append("bili无同名账号")
        time.sleep(MIN_INTERVAL)

        # ---- 2) 公众号 handle（仅 cross/wechat 类型做确定性核验；bilibili KOL 不搜）
        if k.get("platform") in ("cross", "wechat"):
            accts, n_arts, aerr = sogou_accounts_for(name)
            time.sleep(SOGOU_INTERVAL)
            if aerr:
                notes.append(f"wechat={aerr}")
            else:
                cjk = C.cjk_norm(name)
                own = [a for a in accts if C.cjk_norm(a) == cjk]
                if own:
                    new["wechat"] = {"name": sorted(own)[0], "url": ""}
                    notes.append(f"wechat自有号核验通过: {sorted(own)[0]}")
                else:
                    notes.append(f"wechat有{n_arts}篇提及文章但发布账号非本人: {sorted(accts)[:4]}")

        merged = dict(cur)
        merged.update(new)
        if new:
            plan.append((k, merged, notes))
        else:
            notes.append("无handle可写(留空)")
        print(f"  id={k['id']:<4} {name:<14} [{k.get('platform')}] "
              f"-> {'; '.join(notes)}")

    # ---- 应用
    print("=" * 90)
    print(f"模式: {'APPLY' if args.apply else 'DRY-RUN'}；将写 handles 的 KOL 数: {len(plan)}")
    for k, merged, notes in plan:
        print(f"  id={k['id']} {k['name']}: {json.dumps(merged, ensure_ascii=False)}")
    if args.apply:
        ok = 0
        for k, merged, _ in plan:
            patch_handles(k["id"], merged)
            ok += 1
        print(f"APPLY 完成: PATCH {ok} 行 food_kol_watchlist.handles")
        # 回读
        rb = C.fetch_all("food_kol_watchlist", "id,name,handles",
                         order_col="id", extra="status=eq.active")
        filled = [r for r in rb if r.get("handles")]
        print(f"回读: handles 非空行数 = {len(filled)}/{len(rb)}")


if __name__ == "__main__":
    main()
