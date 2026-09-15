#!/usr/bin/env python3
"""
中餐八大菜系数据整合脚本
读取子代理输出的 JSON 候选池，清洗后写入 Supabase restaurants 表。

用法:
    python3 integrate_chinese_cuisines.py <json_dir> [--dry-run]
    python3 integrate_chinese_cuisines.py /path/to/json --dry-run
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

try:
    from supabase import create_client
except ImportError:
    print("需要安装 supabase: pip install supabase")
    sys.exit(1)

# Supabase 配置
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://bdwrhshgdeghgyzwpxnl.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# 菜系映射（JSON 中的菜系名 → 数据库中的分类名）
CUISINE_MAP = {
    "鲁菜": "鲁菜",
    "川菜": "川菜",
    "粤菜": "粤菜",
    "苏菜": "苏菜",
    "闽菜": "闽菜",
    "浙菜": "浙菜",
    "湘菜": "湘菜",
    "徽菜": "徽菜",
}

# 档位映射
TIER_MAP = {
    "高端": "高端",
    "high": "高端",
    "中端": "中端",
    "mid": "中端",
    "亲民": "亲民",
    "low": "亲民",
    "平价": "亲民",
}


def load_json_files(json_dir: str) -> list[dict]:
    """加载目录下所有 JSON 文件"""
    restaurants = []
    json_path = Path(json_dir)

    if not json_path.exists():
        print(f"错误: 目录不存在 {json_dir}")
        return restaurants

    for f in sorted(json_path.glob("*.json")):
        print(f"读取: {f.name}")
        try:
            with open(f, "r", encoding="utf-8") as fp:
                data = json.load(fp)

            # 支持多种 JSON 结构
            if isinstance(data, list):
                restaurants.extend(data)
            elif isinstance(data, dict):
                # 可能是 {cuisine: [...]} 或 {restaurants: [...]}
                if "restaurants" in data:
                    restaurants.extend(data["restaurants"])
                else:
                    for key, value in data.items():
                        if isinstance(value, list):
                            restaurants.extend(value)
        except Exception as e:
            print(f"  跳过 {f.name}: {e}")

    print(f"共加载 {len(restaurants)} 条原始记录")
    return restaurants


def normalize_restaurant(raw: dict, source_cuisine: str = "") -> dict | None:
    """将原始 JSON 记录规范化为数据库格式"""
    name = raw.get("name") or raw.get("店名") or raw.get("restaurant_name")
    if not name:
        return None

    # 菜系
    cuisine = raw.get("cuisine") or raw.get("菜系") or source_cuisine
    cuisine = CUISINE_MAP.get(cuisine, cuisine)

    # 档位
    tier_raw = raw.get("tier") or raw.get("档位") or raw.get("price_tier")
    tier = TIER_MAP.get(str(tier_raw), tier_raw or "中端")

    # 人均价格
    price_avg = raw.get("price_avg") or raw.get("人均") or raw.get("avg_price")
    if isinstance(price_avg, str):
        # 提取数字
        import re
        match = re.search(r"\d+", price_avg)
        price_avg = int(match.group()) if match else None

    # 评分
    score_total = raw.get("score_total") or raw.get("综合评分") or raw.get("score")
    if isinstance(score_total, str):
        try:
            score_total = float(score_total)
        except ValueError:
            score_total = None

    # 特色菜
    signature = raw.get("signature_dishes") or raw.get("特色菜") or raw.get("招牌菜")
    if isinstance(signature, str):
        signature = [s.strip() for s in signature.replace("，", ",").split(",") if s.strip()]

    # 地址
    address = raw.get("address") or raw.get("地址")

    # 区域
    district = raw.get("district") or raw.get("区域") or raw.get("行政区")

    # 联系方式
    phone = raw.get("phone") or raw.get("电话") or raw.get("contact")

    # 预订方式
    booking = raw.get("booking_method") or raw.get("预订方式")

    # 食客点评摘要
    review_summary = raw.get("review_summary") or raw.get("点评摘要") or raw.get("食客评价")

    return {
        "name": name.strip(),
        "name_en": raw.get("name_en") or raw.get("英文名"),
        "cuisine": cuisine,
        "tier": tier,
        "price_avg": price_avg,
        "score_total": score_total,
        "signature_dishes": signature if isinstance(signature, list) else None,
        "address": address,
        "district": district,
        "phone": phone,
        "booking_method": booking,
        "review_summary": review_summary,
        "status": "推荐",
        "data_source": "中餐八大菜系调研",
        "data_updated_at": datetime.now(timezone.utc).isoformat(),
    }


def deduplicate(restaurants: list[dict]) -> list[dict]:
    """按店名去重，保留评分更高的"""
    seen = {}
    for r in restaurants:
        key = r["name"].strip()
        if key not in seen:
            seen[key] = r
        else:
            # 保留评分更高的
            old_score = seen[key].get("score_total") or 0
            new_score = r.get("score_total") or 0
            if new_score > old_score:
                seen[key] = r
    return list(seen.values())


def upload_to_supabase(restaurants: list[dict], dry_run: bool = False):
    """上传到 Supabase"""
    if dry_run:
        print(f"\n[DRY RUN] 将上传 {len(restaurants)} 家餐厅到 Supabase")
        for r in restaurants[:5]:
            print(f"  - {r['name']} ({r['cuisine']}/{r['tier']}) ¥{r.get('price_avg', '?')}")
        if len(restaurants) > 5:
            print(f"  ... 还有 {len(restaurants) - 5} 家")
        return

    if not SUPABASE_SERVICE_ROLE_KEY:
        print("错误: 未设置 SUPABASE_SERVICE_ROLE_KEY 环境变量")
        sys.exit(1)

    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    # 先查询已存在的餐厅（按店名）
    existing_names = set()
    offset = 0
    while True:
        resp = client.from_("restaurants").select("name").range(offset, offset + 1000).execute()
        if not resp.data:
            break
        existing_names.update(r["name"] for r in resp.data)
        offset += 1000
        if len(resp.data) < 1000:
            break

    print(f"数据库已有 {len(existing_names)} 家餐厅")

    # 过滤掉已存在的
    new_restaurants = [r for r in restaurants if r["name"] not in existing_names]
    print(f"新增 {len(new_restaurants)} 家，跳过 {len(restaurants) - len(new_restaurants)} 家已存在")

    if not new_restaurants:
        print("没有新餐厅需要上传")
        return

    # 批量插入（每次最多 100 条）
    batch_size = 100
    inserted = 0
    for i in range(0, len(new_restaurants), batch_size):
        batch = new_restaurants[i : i + batch_size]
        try:
            resp = client.from_("restaurants").insert(batch).execute()
            inserted += len(resp.data) if resp.data else len(batch)
            print(f"  已插入 {inserted}/{len(new_restaurants)}")
        except Exception as e:
            print(f"  批量插入失败 (第 {i}-{i+len(batch)} 条): {e}")
            # 逐条插入
            for r in batch:
                try:
                    client.from_("restaurants").insert(r).execute()
                    inserted += 1
                except Exception as e2:
                    print(f"    跳过 {r['name']}: {e2}")

    print(f"\n完成！共插入 {inserted} 家新餐厅")


def main():
    parser = argparse.ArgumentParser(description="中餐八大菜系数据整合到 Supabase")
    parser.add_argument("json_dir", help="包含 JSON 文件的目录路径")
    parser.add_argument("--dry-run", action="store_true", help="只预览不上传")
    args = parser.parse_args()

    print("=" * 60)
    print("中餐八大菜系数据整合")
    print("=" * 60)

    # 1. 加载 JSON
    raw_restaurants = load_json_files(args.json_dir)
    if not raw_restaurants:
        print("没有找到任何餐厅数据")
        return

    # 2. 规范化
    normalized = []
    for raw in raw_restaurants:
        r = normalize_restaurant(raw)
        if r:
            normalized.append(r)
    print(f"规范化后 {len(normalized)} 条")

    # 3. 去重
    deduped = deduplicate(normalized)
    print(f"去重后 {len(deduped)} 条")

    # 4. 统计
    cuisine_stats = {}
    tier_stats = {}
    for r in deduped:
        cuisine_stats[r["cuisine"]] = cuisine_stats.get(r["cuisine"], 0) + 1
        tier_stats[r["tier"]] = tier_stats.get(r["tier"], 0) + 1

    print("\n菜系分布:")
    for c, count in sorted(cuisine_stats.items()):
        print(f"  {c}: {count} 家")

    print("\n档位分布:")
    for t, count in sorted(tier_stats.items()):
        print(f"  {t}: {count} 家")

    # 5. 上传
    upload_to_supabase(deduped, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
