#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
semantic_profile_generator.py — 为全库餐厅生成 semantic_description（50-150字）

原则（寿司方法论回滚）：
- 基于招牌菜 / 真实评价 / 荣誉提炼，不写空话（"环境优雅""服务周到"不算）
- 不使用软广话术（"必吃""天花板""yyds""绝绝子"）
- 突出独特性：菜系定位、招牌单品、主厨特色、价格定位
- 宁空不假：证据不足时生成基础简介但标记低置信度，不编造

用法：
  python3 semantic_profile_generator.py                # dry-run，打印样本+统计
  python3 semantic_profile_generator.py --commit       # 写库（每批50家，写后回读验证）
  python3 semantic_profile_generator.py --commit --high-score  # 只处理 score_total>70
"""
import argparse
import collections
import json
import re
import sys
import time
from collections import defaultdict

import common as C

# ---------------------------------------------------------------- 过滤词典
# 这些 tag 是"形式/时段/设施"标签，不是菜系，不进简介
_GENERIC_TAGS = {
    "午餐", "晚餐", "早午餐", "Casual Dining", "Finedining", "Fine Dining",
    "可预订", "包间", "团购优惠", "露台", "户外座位", "吸烟区",
    "快餐/简餐", "Bistro/小酒馆", "Bistro", "小酒馆",
    "晚餐", "午餐", "Brunch", "下午茶", "夜宵",
}
# 软广 / 空话词（出现在生成结果里要剔除）
_HYPE_WORDS = [
    "必吃", "天花板", "yyds", "YYDS", "封神", "宝藏", "不踩雷", "闭眼冲",
    "巨好吃", "超好吃", "绝绝子", "yyds", "网红", "打卡", "出片",
    "环境优雅", "服务周到", "服务一流", "高端大气", "上档次", "氛围感",
    "强烈推荐", "值得一试", "不容错过", "首屈一指",
]
# 价位描述映射
_TIER_PRICE_WORD = {
    "经济": "人均五十元档",
    "平价": "百元内",
    "中档": "百元档",
    "高档": "人均两三百元",
    "奢华": "高端价位",
}


def parse_evidence(ev_raw):
    """解析 evidence_summary JSON，返回 (quotes, negatives, soft_ad)。"""
    if not ev_raw:
        return [], [], []
    try:
        j = json.loads(ev_raw) if isinstance(ev_raw, str) else ev_raw
        return j.get("quotes", []), j.get("negative", []), j.get("soft_ad", [])
    except (json.JSONDecodeError, TypeError, AttributeError):
        return [], [], []


def clean_text(s):
    """清理文本：去除软广词，压缩空白。"""
    if not s:
        return ""
    s = str(s)
    for w in _HYPE_WORDS:
        s = s.replace(w, "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_cuisine_label(cuisine_names):
    """从关联标签中提取真正的菜系名（去掉形式/时段标签）。"""
    if not cuisine_names:
        return ""
    # 优先选带地域/烹饪形式的标签
    cuisine_tags = [c for c in cuisine_names if c not in _GENERIC_TAGS
                   and not re.match(r"^(午餐|晚餐|早午餐|夜宵|下午茶)", c)]
    # 去重保序
    seen, out = set(), []
    for c in cuisine_tags:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def extract_facts_from_quotes(quotes, name):
    """从评价引用中提取可用于简介的事实片段（只提取干净短语，不抓整句片段）。"""
    facts = {
        "history": "",       # 创于XX年 / 老字号
        "award": "",         # 米其林/黑珍珠
        "format": "",        # omakase/板前/露台/私房/居民楼
        "chef": "",          # 主厨名/背景
        "price_hint": "",    # 人均/价格
    }
    for q in quotes:
        text = q.get("quote", "") if isinstance(q, dict) else str(q)
        if not text or len(text) < 5:
            continue
        # 历史：创于XX年
        m = re.search(r"(创于|创立于|始建于|开业于|始于)\s*(\d{4})年?", text)
        if m and not facts["history"]:
            facts["history"] = f"{m.group(1)}{m.group(2)}年"
            continue
        # 老字号/百年
        if re.search(r"老字号|百年老店|百年历史|光绪|民国", text) and not facts["history"]:
            if "老字号" in text:
                facts["history"] = "老字号"
            elif "百年" in text:
                facts["history"] = "百年老店"
            continue
        # 米其林
        if re.search(r"米其林(指南|一星|二星|三星)", text) and not facts["award"]:
            m2 = re.search(r"米其林(指南|一星|二星|三星)", text)
            if m2:
                facts["award"] = f"米其林{m2.group(1)}"
            continue
        # 黑珍珠
        if re.search(r"黑珍珠(一钻|二钻|三钻|餐厅)", text) and not facts["award"]:
            m2 = re.search(r"黑珍珠(一钻|二钻|三钻)", text)
            if m2:
                facts["award"] = f"黑珍珠{m2.group(1)}"
            else:
                facts["award"] = "黑珍珠"
            continue
        # 店型
        if not facts["format"]:
            for kw in ["omakase", "Omakase", "板前", "露台", "私房菜", "居民楼",
                        "主厨餐桌", "怀石", "会席", "放题", "大排档", "江景"]:
                if kw in text:
                    facts["format"] = kw.lower() if kw in ("omakase","Omakase") else kw
                    break
        # 主厨：匹配"XX师傅"，XX 应为2-3字中文名（排除带"的/着/了/是/在/看"等虚词）
        if not facts["chef"]:
            m2 = re.search(r"(?<![\u4e00-\u9fa5])([\u4e00-\u9fa5]{2,3})师傅", text)
            if m2:
                name_p = m2.group(1)
                # 排除含虚词的匹配
                if not re.search(r"[的着了是在看和都也就很被把让对从向到]$", name_p) \
                   and not re.search(r"^(老|小|大|新|这|那|我|你|他)", name_p):
                    facts["chef"] = f"{name_p}师傅主理"
    return facts


def build_description(rest, cuisine_tags, awards):
    """为单家餐厅构建 semantic_description。返回 (text, confidence)。
    结构：[菜系/店型]，[位置]，[荣誉/历史]，招牌[菜品]，人均[价格]。
    不抓整句评价片段，只用确定性提取的事实。"""
    name = rest.get("name", "")
    district = rest.get("district", "") or ""
    area = rest.get("business_area", "") or ""
    price = rest.get("price_avg")
    tier = rest.get("tier", "") or ""
    dishes = rest.get("signature_dishes", []) or []
    score = rest.get("score_total") or 0

    quotes, negatives, soft_ad = parse_evidence(rest.get("evidence_summary"))
    facts = extract_facts_from_quotes(quotes, name)

    parts = []
    confidence = "high"

    # --- 菜系标签（取最具体的一个）---
    preferred = [c for c in cuisine_tags
                 if re.search(r"(菜|料理|寿司|烧肉|烧鸟|天妇罗|怀石|拉面|咖喱|火锅|烧烤|咖啡|甜品|面包|鳗鱼|面|饭)", c)]
    cuisine_label = preferred[0] if preferred else (cuisine_tags[0] if cuisine_tags else "")

    # --- 第1段：菜系 + 店型 ---
    opener_parts = []
    if cuisine_label:
        opener_parts.append(cuisine_label)
    if facts["format"]:
        opener_parts.append(facts["format"])
    opener = "".join(opener_parts)
    if opener:
        parts.append(opener)

    # --- 位置 ---
    loc = area if area else district
    if loc:
        parts.append(f"位于{loc}")

    # --- 荣誉（优先 awards 表，其次 quote 提取）---
    award_str = ""
    if awards:
        award_names = []
        for a in awards[:2]:
            atype = a.get("award_type", "")
            level = a.get("level", "")
            if "michelin" in atype:
                award_names.append(f"米其林{level}" if level else "米其林指南")
            elif "black_pearl" in atype:
                award_names.append(f"黑珍珠{level}" if level else "黑珍珠")
        award_str = "、".join(award_names)
    elif facts["award"]:
        award_str = facts["award"]
    if award_str:
        parts.append(award_str)

    # --- 历史 ---
    if facts["history"]:
        parts.append(facts["history"])

    # --- 主厨 ---
    if facts["chef"]:
        parts.append(facts["chef"])

    # --- 招牌菜 ---
    if dishes:
        clean_dishes = []
        seen = set()
        for d in dishes[:4]:
            d_clean = re.sub(r"[（(].*?[)）]", "", d).strip()
            if d_clean and d_clean not in seen and len(d_clean) <= 15:
                seen.add(d_clean)
                clean_dishes.append(d_clean)
        if clean_dishes:
            parts.append(f"招牌{'、'.join(clean_dishes[:3])}")

    # --- 价格 ---
    if price and isinstance(price, (int, float)):
        p = int(price)
        if p < 50:
            parts.append("人均五十元以内")
        elif p < 100:
            parts.append("百元内人均")
        elif p < 200:
            parts.append("人均百元档")
        else:
            parts.append(f"人均{p}元")

    # --- 拼接 ---
    desc = "，".join(p for p in parts if p)
    desc = clean_text(desc)
    desc = re.sub(r"^[，。、\s]+", "", desc)
    desc = re.sub(r"，+", "，", desc)

    # 置信度：基于证据质量，不基于长度
    if not dishes or len(quotes) == 0:
        confidence = "low"
    elif len(quotes) < 2:
        confidence = "medium"
    else:
        confidence = "high"

    # 长度控制：目标 50-150 字
    if len(desc) < 40:
        # 补更多菜品（不补 district，避免和 area 重复）
        if len(dishes) > 3:
            extra = []
            seen = set(clean_dishes) if dishes else set()
            for d in dishes[3:6]:
                d_clean = re.sub(r"[（(].*?[)）]", "", d).strip()
                if d_clean and d_clean not in seen and len(d_clean) <= 15:
                    seen.add(d_clean)
                    extra.append(d_clean)
            if extra:
                desc += f"，另有{'、'.join(extra)}"

    if len(desc) > 150:
        desc = desc[:148].rstrip("，、") + "…"

    if len(desc) < 20:
        desc = f"{cuisine_label or '餐厅'}"
        if loc:
            desc += f"，位于{loc}"
        confidence = "low"

    return desc, confidence


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="写库（默认 dry-run）")
    ap.add_argument("--high-score", action="store_true", help="只处理 score_total>70")
    ap.add_argument("--limit", type=int, default=0, help="限制处理数量（调试用）")
    args = ap.parse_args()

    print("拉取全量餐厅...", file=sys.stderr)
    rests = C.fetch_all("restaurants", order_col="id")
    cuis = C.fetch_all("cuisines", "id,name", order_col="id")
    rc = C.fetch_all("restaurant_cuisines", "restaurant_id,cuisine_id", order_col="restaurant_id")
    awards_rows = C.fetch_all("restaurant_awards", "restaurant_id,award_type,level,year,is_current",
                              order_col="restaurant_id")

    cmap = {c["id"]: c["name"] for c in cuis}
    rest_cuisines = defaultdict(list)
    for x in rc:
        if x["cuisine_id"] in cmap:
            rest_cuisines[x["restaurant_id"]].append(cmap[x["cuisine_id"]])
    rest_awards = defaultdict(list)
    for a in awards_rows:
        if a.get("is_current", True):
            rest_awards[a["restaurant_id"]].append(a)

    # 过滤目标
    targets = []
    for r in rests:
        if r.get("semantic_description"):
            continue  # 已有简介跳过
        if args.high_score and (r.get("score_total") or 0) <= 70:
            continue
        targets.append(r)

    if args.limit:
        targets = targets[:args.limit]

    print(f"待生成: {len(targets)} 家", file=sys.stderr)

    # 生成
    results = []
    conf_counter = collections.Counter()
    for r in targets:
        rid = r["id"]
        ct = rest_cuisines.get(rid, [])
        aw = rest_awards.get(rid, [])
        desc, conf = build_description(r, ct, aw)
        results.append({
            "id": rid,
            "name": r["name"],
            "semantic_description": desc,
            "_confidence": conf,
            "_score": r.get("score_total") or 0,
        })
        conf_counter[conf] += 1

    # 打印样本
    print(f"\n=== 生成样本（前20条）===")
    for x in results[:20]:
        print(f"  [id={x['id']}] [{x['_confidence']}] score={x['_score']}")
        print(f"    {x['name']}: {x['semantic_description']}")
        print()

    print(f"\n=== 置信度分布 ===")
    for k, v in conf_counter.most_common():
        print(f"  {k}: {v}")
    print(f"  总: {len(results)}")

    # 长度统计
    lens = [len(x["semantic_description"]) for x in results]
    print(f"\n=== 长度统计 ===")
    print(f"  min={min(lens)} max={max(lens)} avg={sum(lens)/len(lens):.0f}")
    under50 = sum(1 for l in lens if l < 50)
    over150 = sum(1 for l in lens if l > 150)
    print(f"  <50字: {under50}, >150字: {over150}")

    # 写库
    if not args.commit:
        print("\n[DRY-RUN] 加 --commit 写库", file=sys.stderr)
        return

    # 备份
    import pathlib
    backup_dir = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/backups")
    backup_dir.mkdir(exist_ok=True)
    backup_file = backup_dir / f"semantic_desc_backup_{C.today()}.jsonl"
    old_vals = {r["id"]: r.get("semantic_description") for r in rests}
    C.write_jsonl(str(backup_file), [
        {"id": k, "semantic_description": v} for k, v in old_vals.items()
    ])
    print(f"备份已写入 {backup_file}", file=sys.stderr)

    # 批量 PATCH，每批50
    BATCH = 50
    ok, fail = 0, 0
    for i in range(0, len(results), BATCH):
        batch = results[i:i+BATCH]
        # 逐条 PATCH（PostgREST 不支持批量 update by filter with different values）
        for item in batch:
            rid = item["id"]
            payload = {"semantic_description": item["semantic_description"]}
            try:
                r = C.req("PATCH", f"/restaurants?id=eq.{rid}", json=payload)
                if r.status_code in (200, 204):
                    ok += 1
                else:
                    fail += 1
                    print(f"  [FAIL] id={rid}: {r.status_code} {r.text[:100]}", file=sys.stderr)
            except Exception as e:
                fail += 1
                print(f"  [ERR] id={rid}: {e}", file=sys.stderr)
            time.sleep(0.05)

        # 回读验证本批
        ids = [str(x["id"]) for x in batch]
        try:
            rv = C.req("GET", f"/restaurants?select=id,semantic_description&id=in.({','.join(ids)})")
            if rv.status_code == 200:
                checked = {row["id"]: row.get("semantic_description") for row in rv.json()}
                verified = sum(1 for x in batch
                               if checked.get(x["id"]) == x["semantic_description"])
                print(f"  批次 {i//BATCH+1}: PATCH {len(batch)} 条, 回读验证 {verified}/{len(batch)}",
                      file=sys.stderr)
        except Exception as e:
            print(f"  回读异常: {e}", file=sys.stderr)

    print(f"\n完成: 成功 {ok}, 失败 {fail}", file=sys.stderr)


if __name__ == "__main__":
    main()
