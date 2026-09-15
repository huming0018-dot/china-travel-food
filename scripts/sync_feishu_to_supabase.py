#!/usr/bin/env python3
"""
飞书表格 → Supabase 数据同步脚本

用法:
  python sync_feishu_to_supabase.py --full              # 全量同步所有表
  python sync_feishu_to_supabase.py --table cuisines    # 只同步分类字典
  python sync_feishu_to_supabase.py --dry-run           # 试运行，不写入
  python sync_feishu_to_supabase.py --list              # 列出可同步的表

依赖: pip install requests
飞书 CLI: lark-cli (已在环境中)
"""

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ============================================================
# 配置 — 从环境变量读取，或修改下方默认值
# ============================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# 飞书表格配置: (spreadsheet_token, sheet_id, 目标数据库表, 维度标签)
FEISHU_SOURCES = {
    # ===== cuisines 表: 三个 sheet 合并 =====
    "cuisines": [
        {
            "token": "AEIBs4TpohU42HtSTk0cnyIPn0d",
            "sheet_id": "b12bca",
            "sheet_name": "菜系·风味",
            "dimension": "菜系",
            "field_map": {
                "name": "二级菜系",
                "parent_category": "一级分类",
                "flavor_profile": "风味特征",
                "signature_dishes": "代表菜/招牌",
                "price_low": "亲民档(人均)",
                "price_mid": "中端档(人均)",
                "price_high": "高端档(人均)",
                "shanghai_format": "上海典型形态",
                "decision_maker": "决策人特征",
                "negotiation_anchor": "议价锚点",
            },
        },
        {
            "token": "AEIBs4TpohU42HtSTk0cnyIPn0d",
            "sheet_id": "xvRYI1",
            "sheet_name": "食材·品类垂直",
            "dimension": "食材",
            "field_map": {
                "name": "食材分类",
                "parent_category": "子类/细分",
                "flavor_profile": "代表品类/招牌",
                "price_low": "亲民档(人均)",
                "price_mid": "中端档(人均)",
                "price_high": "高端档(人均)",
                "shanghai_format": "上海典型形态",
                "decision_maker": "决策人特征",
                "negotiation_anchor": "议价锚点",
            },
        },
        {
            "token": "AEIBs4TpohU42HtSTk0cnyIPn0d",
            "sheet_id": "Fi7txp",
            "sheet_name": "形式·场景垂直",
            "dimension": "形式",
            "field_map": {
                "name": "形式分类",
                "parent_category": "特征/定义",
                "flavor_profile": "适用菜系",
                "price_low": "亲民档(人均)",
                "price_mid": "中端档(人均)",
                "price_high": "高端档(人均)",
                "shanghai_format": "上海典型形态",
                "decision_maker": "决策人特征",
                "negotiation_anchor": "议价锚点",
            },
        },
    ],
    # ===== restaurants 表: 从日料全品类 + 中餐八大菜系提取 =====
    "restaurants": [
        {
            "token": "ZGeRsybPDhxXBZtK4AlcrurJn2c",
            "sheet_id": "y1CaHe",
            "sheet_name": "日料-01 档次推荐",
            "cuisine_prefix": None,
            "field_map": {
                "name": "推荐店",
                "tier": "档位",
                "price_avg": "实测人均(元)",
                "address": "联系方式",
                "signature_dishes": "特色菜",
                "score_objective": "客观评分(40)",
                "evidence_summary": "综合判定",
            },
        },
        {
            "token": "Vqg7shWEYhk7Q8t5gIZc4mWhnbm",
            "sheet_id": "5d3fec",
            "sheet_name": "中餐-01 档次推荐",
            "cuisine_prefix": "菜系",
            "field_map": {
                "name": "推荐店",
                "tier": "档位",
                "price_avg": "实测人均(元)",
                "score_objective": "客观评分(40)",
                "evidence_summary": "食客证据摘要",
                "signature_dishes": "特色菜",
                "address": "地址",
                "phone": "联系方式",
                "booking_method": "预订方式",
            },
        },
    ],
}


# ============================================================
# 工具函数
# ============================================================
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def check_env():
    """检查必要的环境变量"""
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        log(f"缺少环境变量: {', '.join(missing)}", "ERROR")
        log("请先设置: export SUPABASE_URL=... export SUPABASE_SERVICE_ROLE_KEY=...", "ERROR")
        sys.exit(1)


def export_feishu_csv(token, sheet_id):
    """用 lark-cli 导出飞书表格为 CSV，返回 list[dict]"""
    cmd = [
        "lark-cli", "sheets", "+csv-get",
        "--spreadsheet-token", token,
        "--sheet-id", sheet_id,
        "--range", "A1:Z500",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        log(f"lark-cli 失败: {result.stderr[:200]}", "ERROR")
        return []

    try:
        data = json.loads(result.stdout)
        annotated = data["data"]["annotated_csv"]
    except (json.JSONDecodeError, KeyError) as e:
        log(f"解析 lark-cli 输出失败: {e}", "ERROR")
        return []

    # 解析 annotated_csv 格式: [row=N] col1,col2,...
    rows = []
    for line in annotated.splitlines():
        if line.startswith("[row="):
            csv_line = line.split("] ", 1)[1]
            rows.append(next(csv.reader(io.StringIO(csv_line))))

    if len(rows) < 2:
        return []

    headers = rows[0]
    return [dict(zip(headers, row)) for row in rows[1:] if any(cell.strip() for cell in row)]


def clean_value(val, field_name):
    """清洗单个字段值"""
    if val is None:
        return None
    val = str(val).strip()
    if val in ("", "—", "-", "N/A", "n/a", "暂无", "待补充"):
        return None

    # 价格字段: 提取数字
    if field_name in ("price_low", "price_mid", "price_high", "price_avg"):
        import re
        nums = re.findall(r"\d+", val)
        if nums:
            # 取第一个数字（区间取下限）
            return int(nums[0])
        return None

    # 签牌菜: 转为 JSON 数组
    if field_name == "signature_dishes":
        if val:
            # 按常见分隔符拆分
            import re
            items = re.split(r"[、,，/；;]+", val)
            items = [i.strip() for i in items if i.strip()]
            return json.dumps(items, ensure_ascii=False) if items else None
        return None

    return val


def map_fields(row, field_map, extra=None):
    """将飞书行映射为数据库行"""
    record = {}
    for db_field, feishu_col in field_map.items():
        if feishu_col in row:
            val = clean_value(row[feishu_col], db_field)
            if val is not None:
                record[db_field] = val
    if extra:
        record.update(extra)
    return record


def normalize_record_keys(records):
    """统一所有记录的键集合（Supabase批量upsert要求所有对象键一致）。
    缺失的键设为None。"""
    if not records:
        return records
    all_keys = set()
    for r in records:
        all_keys.update(r.keys())
    normalized = []
    for r in records:
        nr = {k: r.get(k, None) for k in all_keys}
        normalized.append(nr)
    return normalized


def supabase_upsert(table, records, key="name"):
    """批量 upsert 到 Supabase"""
    if not records:
        return 0

    # 统一键集合
    records = normalize_record_keys(records)

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": f"resolution=merge-duplicates",
    }

    # Supabase REST API 单次最多 1000 条，分批
    batch_size = 500
    total = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        resp = requests.post(url, headers=headers, json=batch, timeout=30)
        if resp.status_code in (200, 201):
            total += len(batch)
        else:
            log(f"Supabase 写入失败 ({resp.status_code}): {resp.text[:300]}", "ERROR")
            # 尝试单条写入定位问题
            for rec in batch:
                r = requests.post(url, headers=headers, json=[rec], timeout=10)
                if r.status_code not in (200, 201):
                    log(f"  问题记录: {rec.get('name','?')} -> {r.text[:150]}", "WARN")
                else:
                    total += 1
        time.sleep(0.2)  # 避免限流

    return total


def supabase_delete_by_dimension(table, dimension):
    """删除指定 dimension 的旧数据（用于全量同步前清理）"""
    url = f"{SUPABASE_URL}/rest/v1/{table}?dimension=eq.{dimension}"
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
    }
    resp = requests.delete(url, headers=headers, timeout=30)
    if resp.status_code in (200, 204):
        log(f"  已清理 dimension={dimension} 的旧数据")
    else:
        log(f"  清理旧数据失败 ({resp.status_code}): {resp.text[:200]}", "WARN")


# ============================================================
# 同步任务
# ============================================================
def sync_cuisines(dry_run=False):
    """同步三维分类字典（菜系50 + 食材20 + 形式14）"""
    log("=== 同步 cuisines (分类字典) ===")
    all_records = []

    for source in FEISHU_SOURCES["cuisines"]:
        log(f"  读取: {source['sheet_name']} (dimension={source['dimension']})")
        rows = export_feishu_csv(source["token"], source["sheet_id"])
        log(f"    导出 {len(rows)} 行")

        for row in rows:
            record = map_fields(row, source["field_map"], extra={"dimension": source["dimension"]})
            if record.get("name"):
                all_records.append(record)

    log(f"  合计 {len(all_records)} 条分类记录")

    if dry_run:
        log(f"  [DRY-RUN] 不写入，预览前 3 条:")
        for r in all_records[:3]:
            log(f"    {r.get('dimension')} | {r.get('name')} | {r.get('price_low')}-{r.get('price_high')}")
        return 0

    # 全量同步: 先删后写
    for dim in ["菜系", "食材", "形式"]:
        supabase_delete_by_dimension("cuisines", dim)

    count = supabase_upsert("cuisines", all_records)
    log(f"  写入完成: {count} 条")
    return count


def sync_restaurants(dry_run=False):
    """同步餐厅数据（从日料全品类 + 中餐八大菜系提取）"""
    log("=== 同步 restaurants (餐厅) ===")
    all_records = []

    for source in FEISHU_SOURCES["restaurants"]:
        log(f"  读取: {source['sheet_name']}")
        rows = export_feishu_csv(source["token"], source["sheet_id"])
        log(f"    导出 {len(rows)} 行")

        cuisine_col = source.get("cuisine_prefix")
        for row in rows:
            record = map_fields(row, source["field_map"])
            if record.get("name"):
                # 菜系前缀：中餐表将菜系信息拼入 evidence_summary
                if cuisine_col and cuisine_col in row:
                    cuisine = str(row[cuisine_col]).strip()
                    if cuisine:
                        existing = record.get("evidence_summary", "")
                        record["evidence_summary"] = f"[{cuisine}] {existing}".strip()
                record["status"] = "推荐"
                record["data_updated_at"] = "2026-09-15"
                all_records.append(record)

    log(f"  合计 {len(all_records)} 条餐厅记录")

    if dry_run:
        log(f"  [DRY-RUN] 不写入，预览前 5 条:")
        for r in all_records[:5]:
            log(f"    {r.get('name')} | {r.get('tier')} | {r.get('price_avg')} | {r.get('evidence_summary','')[:40]}")
        return 0

    count = supabase_upsert("restaurants", all_records)
    log(f"  写入完成: {count} 条")
    return count


# ============================================================
# 主入口
# ============================================================
SYNC_FUNCTIONS = {
    "cuisines": sync_cuisines,
    "restaurants": sync_restaurants,
}


def main():
    parser = argparse.ArgumentParser(description="飞书表格 → Supabase 数据同步")
    parser.add_argument("--full", action="store_true", help="全量同步所有表")
    parser.add_argument("--table", choices=SYNC_FUNCTIONS.keys(), help="只同步指定表")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不写入数据库")
    parser.add_argument("--list", action="store_true", help="列出可同步的表")
    args = parser.parse_args()

    if args.list:
        print("可同步的表:")
        for name in SYNC_FUNCTIONS:
            print(f"  - {name}")
        return

    check_env()

    if args.dry_run:
        log("=== DRY-RUN 模式（不写入）===", "WARN")

    if args.full:
        for name, func in SYNC_FUNCTIONS.items():
            func(dry_run=args.dry_run)
            print()
    elif args.table:
        SYNC_FUNCTIONS[args.table](dry_run=args.dry_run)
    else:
        parser.print_help()
        print("\n示例: python sync_feishu_to_supabase.py --full")


if __name__ == "__main__":
    main()
