#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backfill_cuisine.py — 餐厅菜系标签补全工具

基于餐厅名称、signature_dishes、semantic_description中的关键词，
自动匹配cuisines表中的菜系标签并写入restaurant_cuisines。

用法：
  python3 backfill_cuisine.py --dry-run    # 预览，不写库
  python3 backfill_cuisine.py --apply      # 实际写入

注意：当前菜系标签覆盖率已100%，此脚本主要用于新增餐厅后的补全。
"""
import sys, os, argparse, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'vendor', 'pipeline'))
import common as C

# 关键词 → 菜系名映射（可扩展）
KEYWORD_MAP = {
    '寿司': '寿司', 'sushi': '寿司', '鮨': '寿司',
    '拉面': '拉面', 'ramen': '拉面',
    '烧鸟': '烧鸟', 'yakitori': '烧鸟', '串烧': '烧鸟',
    '天妇罗': '天妇罗', 'tempura': '天妇罗',
    '鳗鱼': '鳗鱼饭', '鳗重': '鳗鱼饭', 'unagi': '鳗鱼饭',
    '咖喱': '咖喱', 'curry': '咖喱',
    '火锅': '火锅', 'hotpot': '火锅', '串串': '火锅',
    '烧烤': '烧烤/烤串', '烤串': '烧烤/烤串', 'bbq': '烧烤/烤串',
    '川菜': '川菜', '麻辣': '川菜', '川味': '川菜',
    '粤菜': '粤菜', '点心': '粤菜', '茶餐厅': '粤菜',
    '湘菜': '湘菜', '湘味': '湘菜',
    '鲁菜': '鲁菜',
    '淮扬': '淮扬菜', '扬州': '淮扬菜',
    '江浙': '江浙菜', '杭州': '江浙菜', '宁波': '江浙菜',
    '闽南': '闽菜', '潮汕': '潮汕菜', '潮州': '潮汕菜',
    '北京': '京菜', '烤鸭': '京菜',
    '东北': '东北菜',
    '新疆': '新疆菜', '大盘鸡': '新疆菜',
    '云南': '云南菜', '过桥米线': '云南菜',
    '贵州': '贵州菜', '酸汤': '贵州菜',
    '泰国': '泰国菜', '冬阴功': '泰国菜', 'thai': '泰国菜',
    '越南': '越南菜', 'pho': '越南菜', '河粉': '越南菜',
    '韩国': '韩国料理', '烤肉': '韩国料理', 'korean': '韩国料理',
    '日本': '日料/日本料理', '日料': '日料/日本料理', 'japanese': '日料/日本料理',
    '意大利': '意大利菜', 'pizza': '意大利菜', '意面': '意大利菜',
    '法国': '法国菜', 'french': '法国菜', '法餐': '法国菜',
    '西班牙': '西班牙菜', 'tapas': '西班牙菜',
    '德国': '德国菜', '香肠': '德国菜',
    '美国': '美国菜', '汉堡': '美国菜', 'burger': '美国菜',
    '墨西哥': '墨西哥菜', 'taco': '墨西哥菜',
    '中东': '中东菜', 'kebab': '中东菜',
    '印度': '印度菜', 'curry': '印度菜',
    '咖啡': '咖啡', 'cafe': '咖啡', 'coffee': '咖啡',
    '面包': '面包', 'bakery': '面包', '可颂': '面包',
    '甜品': '甜品', '蛋糕': '甜品', 'dessert': '甜品',
    '酒吧': '酒吧', 'bar': '酒吧', '鸡尾酒': '酒吧',
    '茶饮': '茶饮', '奶茶': '茶饮',
    'omakase': 'Omakase 板前', '板前': 'Omakase 板前',
    'finedining': 'Finedining', 'fine dining': 'Finedining',
    '小笼包': '小笼包', '生煎': '生煎',
    '饺子': '饺子', '馄饨': '馄饨',
}

def extract_keywords(text):
    if not text: return []
    text = str(text).lower()
    found = []
    for kw, cuisine in KEYWORD_MAP.items():
        if kw.lower() in text:
            found.append(cuisine)
    return list(set(found))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='实际写入（默认dry-run）')
    args = ap.parse_args()

    rests = C.fetch_all('restaurants', 'id,name,signature_dishes,semantic_description,status', order_col='id')
    active = [r for r in rests if r.get('status') == 'active']
    cuisines = C.fetch_all('cuisines', 'id,name,dimension', order_col='id')
    cuisine_by_name = {c['name']: c['id'] for c in cuisines if c['dimension'] == '菜系'}

    existing = {}
    rc = C.fetch_all('restaurant_cuisines', 'restaurant_id,cuisine_id', order_col='restaurant_id')
    for link in rc:
        existing.setdefault(link['restaurant_id'], set()).add(link['cuisine_id'])

    to_add = []
    for r in active:
        text = ' '.join(filter(None, [
            r.get('name'),
            str(r.get('signature_dishes') or ''),
            r.get('semantic_description') or ''
        ]))
        matched = extract_keywords(text)
        for cuisine_name in matched:
            cid = cuisine_by_name.get(cuisine_name)
            if cid and cid not in existing.get(r['id'], set()):
                to_add.append((r['id'], r['name'], cuisine_name, cid))

    print(f"在营餐厅: {len(active)}")
    print(f"待补全系标签: {len(to_add)} 条")
    if to_add:
        print("\n前10条:")
        for rid, name, cuisine, cid in to_add[:10]:
            print(f"  #{rid} {name} → {cuisine} (cid={cid})")

    if args.apply and to_add:
        for rid, name, cuisine, cid in to_add:
            r = C.req('POST', '/restaurant_cuisines',
                      json={'restaurant_id': rid, 'cuisine_id': cid, 'is_primary': False})
            if r.status_code not in (200, 201):
                print(f"  写入失败 #{rid}: {r.status_code} {r.text[:80]}")
        print(f"\n已写入 {len(to_add)} 条菜系标签")
    elif not args.apply:
        print("\n[dry-run] 未写库。加 --apply 执行写入。")

if __name__ == '__main__':
    main()
