#!/usr/bin/env python3
"""
数据修复脚本：
1. 清理 restaurants 表中的重复记录（按店名去重，保留 id 最小的）
2. 重建 restaurant_cuisines 关联表
3. 修复 district 字段（从地址提取）
4. 修复 score_total 字段（从各维度分数计算）
"""

import os
import re
from collections import Counter, defaultdict
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://bdwrhshgdeghgyzwpxnl.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# 八大菜系名称（与 cuisines 表中的实际名称匹配）
CHINESE_CUISINES = ["鲁菜(山东)", "川菜(四川/重庆)", "粤菜(广东)", "苏菜(江苏/淮扬)", "闽菜(福建)", "浙菜(浙江)", "湘菜(湖南)", "徽菜(安徽)"]

# evidence 前缀到 cuisines 表名称的映射
EVIDENCE_TO_CUISINE = {
    "鲁菜": "鲁菜(山东)",
    "川菜": "川菜(四川/重庆)",
    "粤菜": "粤菜(广东)",
    "苏菜": "苏菜(江苏/淮扬)",
    "闽菜": "闽菜(福建)",
    "浙菜": "浙菜(浙江)",
    "湘菜": "湘菜(湖南)",
    "徽菜": "徽菜(安徽)",
}

# 日料品类映射（根据店名/evidence_summary 判断）
JAPANESE_CATEGORY_KEYWORDS = {
    "寿司": ["寿司", "sushi", "鮨", "omakase", "割烹"],
    "烧鸟": ["烧鸟", "yakitori", "鸟"],
    "烧肉": ["烧肉", "yakiniku", "烤肉"],
    "拉面": ["拉面", "ramen", "面"],
    "咖喱": ["咖喱", "curry", "カレー"],
    "天妇罗": ["天妇罗", "天麸罗", "tempura"],
    "鳗鱼饭": ["鳗", "うなぎ", "eel"],
    "寿喜烧": ["寿喜烧", "sukiyaki", "すき焼き"],
    "铁板烧": ["铁板烧", "teppanyaki", "鉄板"],
    "炉端烧": ["炉端", "robatayaki", "炉"],
    "居酒屋": ["居酒屋", "izakaya", "酒場"],
    "洋食": ["洋食", "西餐", "日式西餐"],
    "甜品": ["甜品", "抹茶", "松饼", "和果子", "雪葩"],
    "怀石": ["怀石", "懐石", "kaiseki"],
}

# 上海区域映射
DISTRICTS = ["黄浦", "徐汇", "长宁", "静安", "普陀", "虹口", "杨浦", "闵行", "宝山", "嘉定", "浦东", "金山", "松江", "青浦", "奉贤", "崇明"]


def extract_district(address: str) -> str | None:
    """从地址提取区域"""
    if not address:
        return None
    for d in DISTRICTS:
        if d in address:
            return d + "区"
    return None


def extract_cuisine_from_evidence(evidence: str) -> str | None:
    """从 evidence_summary 前缀提取菜系，如 [鲁菜] xxx"""
    if not evidence:
        return None
    match = re.match(r"\[([^\]]+)\]", evidence)
    if match:
        cuisine = match.group(1).strip()
        # 映射到 cuisines 表中的实际名称
        if cuisine in EVIDENCE_TO_CUISINE:
            return EVIDENCE_TO_CUISINE[cuisine]
        # 日料品类
        for cat, keywords in JAPANESE_CATEGORY_KEYWORDS.items():
            if cuisine == cat or any(k in cuisine for k in keywords):
                return cat
    return None


def detect_japanese_category(name: str, evidence: str = "") -> str | None:
    """根据店名和 evidence 判断日料品类"""
    text = (name or "") + " " + (evidence or "")
    for cat, keywords in JAPANESE_CATEGORY_KEYWORDS.items():
        if any(k.lower() in text.lower() for k in keywords):
            return cat
    return "日料其他"


def main():
    if not SUPABASE_SERVICE_ROLE_KEY:
        print("错误: 未设置 SUPABASE_SERVICE_ROLE_KEY")
        return

    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    # ========== Step 1: 清理重复记录 ==========
    print("=" * 60)
    print("Step 1: 清理重复记录")
    print("=" * 60)

    resp = client.from_("restaurants").select("id,name").order("id").execute()
    all_records = resp.data
    print(f"当前总记录数: {len(all_records)}")

    # 按店名分组，保留 id 最小的
    name_groups = defaultdict(list)
    for r in all_records:
        name_groups[r["name"]].append(r["id"])

    duplicates_to_delete = []
    for name, ids in name_groups.items():
        if len(ids) > 1:
            # 保留最小的 id，删除其余
            keep_id = min(ids)
            delete_ids = [i for i in ids if i != keep_id]
            duplicates_to_delete.extend(delete_ids)

    print(f"重复店名数: {sum(1 for ids in name_groups.values() if len(ids) > 1)}")
    print(f"待删除记录数: {len(duplicates_to_delete)}")

    if duplicates_to_delete:
        # 批量删除（每次 100 条）
        deleted = 0
        for i in range(0, len(duplicates_to_delete), 100):
            batch = duplicates_to_delete[i : i + 100]
            client.from_("restaurants").delete().in_("id", batch).execute()
            deleted += len(batch)
            print(f"  已删除 {deleted}/{len(duplicates_to_delete)}")

    # 验证
    resp2 = client.from_("restaurants").select("id", count="exact").execute()
    print(f"清理后总记录数: {resp2.count}")

    # ========== Step 2: 重建 restaurant_cuisines 关联 ==========
    print("\n" + "=" * 60)
    print("Step 2: 重建 restaurant_cuisines 关联")
    print("=" * 60)

    # 清空旧关联（用 restaurant_id 条件删除，因为表没有 id 列）
    client.from_("restaurant_cuisines").delete().gte("restaurant_id", 0).execute()
    print("已清空旧关联")

    # 获取所有 cuisines
    resp3 = client.from_("cuisines").select("id,name,dimension").execute()
    cuisine_map = {}  # name -> id
    for c in resp3.data:
        cuisine_map[c["name"]] = c["id"]

    print(f"分类总数: {len(cuisine_map)}")
    print(f"中餐分类: {[c for c in CHINESE_CUISINES if c in cuisine_map]}")

    # 获取所有餐厅（清理后）
    resp4 = client.from_("restaurants").select("id,name,evidence_summary,address,district,score_objective,score_diner,score_taste,score_endorsement,score_total").execute()
    restaurants = resp4.data
    print(f"餐厅数: {len(restaurants)}")

    # 建立关联
    associations = []
    district_updates = []
    score_updates = []

    for r in restaurants:
        rid = r["id"]
        name = r["name"]
        evidence = r.get("evidence_summary") or ""

        # 提取菜系
        cuisine = extract_cuisine_from_evidence(evidence)

        if cuisine and cuisine in cuisine_map:
            # 中餐或已识别的日料品类
            associations.append({"restaurant_id": rid, "cuisine_id": cuisine_map[cuisine]})
        else:
            # 尝试从店名判断日料品类
            cat = detect_japanese_category(name, evidence)
            if cat in cuisine_map:
                associations.append({"restaurant_id": rid, "cuisine_id": cuisine_map[cat]})
            elif "日料" in cuisine_map:
                associations.append({"restaurant_id": rid, "cuisine_id": cuisine_map["日料"]})

        # 修复 district
        if not r.get("district"):
            district = extract_district(r.get("address") or "")
            if district:
                district_updates.append({"id": rid, "district": district})

        # 修复 score_total
        if not r.get("score_total"):
            obj = r.get("score_objective") or 0
            diner = r.get("score_diner") or 0
            taste = r.get("score_taste") or 0
            endorsement = r.get("score_endorsement") or 0
            total = obj + diner + taste + endorsement
            if total > 0:
                score_updates.append({"id": rid, "score_total": round(total, 1)})

    print(f"待建立关联数: {len(associations)}")
    print(f"待修复 district 数: {len(district_updates)}")
    print(f"待修复 score_total 数: {len(score_updates)}")

    # 批量插入关联
    if associations:
        inserted = 0
        for i in range(0, len(associations), 100):
            batch = associations[i : i + 100]
            client.from_("restaurant_cuisines").insert(batch).execute()
            inserted += len(batch)
        print(f"已插入关联: {inserted}")

    # 批量更新 district
    if district_updates:
        for update in district_updates:
            client.from_("restaurants").update({"district": update["district"]}).eq("id", update["id"]).execute()
        print(f"已修复 district: {len(district_updates)}")

    # 批量更新 score_total
    if score_updates:
        for update in score_updates:
            client.from_("restaurants").update({"score_total": update["score_total"]}).eq("id", update["id"]).execute()
        print(f"已修复 score_total: {len(score_updates)}")

    # ========== Step 3: 最终验证 ==========
    print("\n" + "=" * 60)
    print("Step 3: 最终验证")
    print("=" * 60)

    resp5 = client.from_("restaurants").select("id", count="exact").execute()
    print(f"餐厅总数: {resp5.count}")

    resp6 = client.from_("restaurant_cuisines").select("restaurant_id", count="exact").execute()
    print(f"关联总数: {resp6.count}")

    # 按菜系统计
    resp7 = client.from_("restaurant_cuisines").select("cuisine_id").execute()
    cuisine_count = Counter()
    for rc in resp7.data:
        cid = rc["cuisine_id"]
        for name, cid2 in cuisine_map.items():
            if cid == cid2:
                cuisine_count[name] += 1
                break

    print("\n按菜系分布:")
    for c, n in sorted(cuisine_count.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n}")

    # 检查无关联的餐厅
    resp8 = client.from_("restaurants").select("id,name").execute()
    all_ids = set(r["id"] for r in resp8.data)
    resp9 = client.from_("restaurant_cuisines").select("restaurant_id").execute()
    linked_ids = set(r["restaurant_id"] for r in resp9.data)
    unlinked = all_ids - linked_ids
    print(f"\n无关联餐厅数: {len(unlinked)}")
    if unlinked:
        for uid in list(unlinked)[:5]:
            r = next((x for x in resp8.data if x["id"] == uid), None)
            if r:
                print(f"  - {r['name']}")

    print("\n数据修复完成！")


if __name__ == "__main__":
    main()
