#!/usr/bin/env python3
"""
汇总4个子代理的菜系调研JSON结果，写入飞书工作簿《上海中餐八大菜系》

用法:
  python consolidate_cuisine_data.py --json-dir <dir> [--dry-run]
  python consolidate_cuisine_data.py --files file1.json file2.json ... [--dry-run]

依赖: lark-cli (已在环境中)
"""

import argparse
import csv
import io
import json
import os
import subprocess
import sys
from pathlib import Path

# 飞书工作簿配置
SPREADSHEET_TOKEN = "Vqg7shWEYhk7Q8t5gIZc4mWhnbm"
SHEET_01_ID = "5d3fec"   # 01 档次推荐
SHEET_02_ID = "cPQfTZ"   # 02 候选池总表

# Sheet 01 表头（顺序即列顺序）
SHEET01_HEADERS = [
    "菜系", "档位", "推荐店", "实测人均(元)", "客观评分(40)",
    "食客证据摘要", "特色菜", "地址", "联系方式", "预订方式"
]

# Sheet 02 表头
SHEET02_HEADERS = [
    "菜系", "档位", "店名", "实测人均(元)", "客观评分(40)",
    "食客评分(30)", "口味评分(20)", "背书(10)", "自然流量(+5)",
    "软广嫌疑(-)", "综合分", "食客证据摘要", "差评信号", "特色菜",
    "地址", "联系方式", "预订方式", "数据采集日期", "结论"
]

# 菜系顺序（用于排序输出）
CUISINE_ORDER = ["鲁菜", "川菜", "粤菜", "苏菜", "闽菜", "浙菜", "湘菜", "徽菜"]
TIER_ORDER = ["亲民", "中端", "高端"]


def log(msg, level="INFO"):
    print(f"[{level}] {msg}", flush=True)


def load_json_files(file_paths):
    """加载多个JSON文件，返回合并后的cuisines列表"""
    all_cuisines = {}
    for fp in file_paths:
        if not os.path.exists(fp):
            log(f"文件不存在，跳过: {fp}", "WARN")
            continue
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        for c in data.get("cuisines", []):
            name = c.get("cuisine", "")
            if name:
                # 归一化档位值
                for r in c.get("recommendations", []):
                    normalize_row(r)
                for r in c.get("candidate_pool", []):
                    normalize_row(r)
                if name in all_cuisines:
                    log(f"菜系重复，合并: {name}", "WARN")
                    all_cuisines[name]["recommendations"].extend(c.get("recommendations", []))
                    all_cuisines[name]["candidate_pool"].extend(c.get("candidate_pool", []))
                else:
                    all_cuisines[name] = c
    return all_cuisines


def normalize_tier(tier):
    """归一化档位值：亲民(<100) -> 亲民，中端(100-300) -> 中端，高端(>300) -> 高端"""
    if not tier:
        return tier
    tier = str(tier).strip()
    for t in TIER_ORDER:
        if tier.startswith(t):
            return t
    return tier


def normalize_row(row):
    """归一化单行数据的档位字段"""
    if "档位" in row:
        row["档位"] = normalize_tier(row["档位"])
    return row


def row_to_csv_row(row, headers):
    """将dict按headers顺序转为CSV行值列表"""
    return [str(row.get(h, "")).strip() for h in headers]


def generate_csv(rows, headers):
    """生成CSV字符串"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row_to_csv_row(row, headers))
    return output.getvalue()


def sort_rows(rows, cuisine_key="菜系", tier_key="档位"):
    """按菜系顺序+档位顺序排序"""
    def sort_key(r):
        c = r.get(cuisine_key, "")
        t = r.get(tier_key, "")
        ci = CUISINE_ORDER.index(c) if c in CUISINE_ORDER else 99
        ti = TIER_ORDER.index(t) if t in TIER_ORDER else 99
        return (ci, ti)
    return sorted(rows, key=sort_key)


def write_to_feishu(csv_content, sheet_id, start_cell="A1"):
    """用lark-cli将CSV写入飞书表格"""
    # 先清空目标区域（A2:Z500，保留表头）
    clear_cmd = [
        "lark-cli", "sheets", "+cells-clear",
        "--spreadsheet-token", SPREADSHEET_TOKEN,
        "--sheet-id", sheet_id,
        "--range", "A2:Z500",
    ]
    result = subprocess.run(clear_cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        log(f"清空区域失败（可能无数据）: {result.stderr[:100]}", "WARN")

    # 写入CSV（从A2开始，覆盖表头行的下一行）
    # 先用csv-put写入完整CSV（含表头），从A1开始覆盖
    cmd = [
        "lark-cli", "sheets", "+csv-put",
        "--spreadsheet-token", SPREADSHEET_TOKEN,
        "--sheet-id", sheet_id,
        "--start-cell", start_cell,
        "--csv", csv_content,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        log(f"写入飞书失败: {result.stderr[:200]}", "ERROR")
        return False
    log(f"写入成功: sheet_id={sheet_id}")
    return True


def validate_data(all_cuisines):
    """校验数据完整性"""
    issues = []
    for name in CUISINE_ORDER:
        if name not in all_cuisines:
            issues.append(f"缺少菜系: {name}")
            continue
        c = all_cuisines[name]
        recs = c.get("recommendations", [])
        pool = c.get("candidate_pool", [])

        if len(recs) != 15:
            issues.append(f"{name}: 推荐店数量={len(recs)}（期望15）")
        if len(pool) < 20:
            issues.append(f"{name}: 候选池数量={len(pool)}（期望≥20）")

        # 检查每档5家
        for tier in TIER_ORDER:
            tier_recs = [r for r in recs if r.get("档位") == tier]
            if len(tier_recs) != 5:
                issues.append(f"{name}-{tier}: 推荐店={len(tier_recs)}家（期望5）")

        # 检查地址/联系方式非空
        for r in recs:
            if not r.get("地址", "").strip():
                issues.append(f"{name}-{r.get('推荐店','?')}: 地址为空")
            if not r.get("联系方式", "").strip():
                issues.append(f"{name}-{r.get('推荐店','?')}: 联系方式为空")

    return issues


def main():
    parser = argparse.ArgumentParser(description="汇总菜系调研数据并写入飞书")
    parser.add_argument("--json-dir", help="包含4个JSON文件的目录")
    parser.add_argument("--files", nargs="+", help="指定JSON文件路径列表")
    parser.add_argument("--dry-run", action="store_true", help="只生成CSV不写入飞书")
    parser.add_argument("--output-dir", default="/tmp", help="CSV输出目录（dry-run时）")
    args = parser.parse_args()

    # 收集JSON文件
    if args.files:
        json_files = args.files
    elif args.json_dir:
        json_files = sorted(Path(args.json_dir).glob("cuisine_research_*.json"))
        json_files = [str(f) for f in json_files]
    else:
        # 默认搜索常见路径
        search_dirs = [
            ".",
            os.path.expanduser("~/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/data"),
        ]
        json_files = []
        for d in search_dirs:
            json_files.extend(str(f) for f in Path(d).glob("cuisine_research_*.json"))
        json_files = sorted(set(json_files))

    if not json_files:
        log("未找到任何JSON文件", "ERROR")
        sys.exit(1)

    log(f"找到 {len(json_files)} 个JSON文件:")
    for f in json_files:
        log(f"  - {f}")

    # 加载数据
    all_cuisines = load_json_files(json_files)
    log(f"加载到 {len(all_cuisines)} 个菜系: {', '.join(sorted(all_cuisines.keys()))}")

    # 校验
    issues = validate_data(all_cuisines)
    if issues:
        log(f"数据校验发现 {len(issues)} 个问题:", "WARN")
        for issue in issues[:20]:
            log(f"  - {issue}", "WARN")
        if len(issues) > 20:
            log(f"  ... 还有 {len(issues)-20} 个问题", "WARN")
    else:
        log("数据校验通过 ✓")

    # 汇总推荐店（Sheet 01）
    all_recs = []
    for name in CUISINE_ORDER:
        if name in all_cuisines:
            all_recs.extend(all_cuisines[name].get("recommendations", []))
    all_recs = sort_rows(all_recs)
    log(f"Sheet 01 推荐店合计: {len(all_recs)} 家")

    # 汇总候选池（Sheet 02）
    all_pool = []
    for name in CUISINE_ORDER:
        if name in all_cuisines:
            all_pool.extend(all_cuisines[name].get("candidate_pool", []))
    all_pool = sort_rows(all_pool)
    log(f"Sheet 02 候选池合计: {len(all_pool)} 家")

    # 生成CSV
    csv01 = generate_csv(all_recs, SHEET01_HEADERS)
    csv02 = generate_csv(all_pool, SHEET02_HEADERS)

    if args.dry_run:
        out01 = os.path.join(args.output_dir, "sheet01_recommendations.csv")
        out02 = os.path.join(args.output_dir, "sheet02_candidate_pool.csv")
        with open(out01, "w", encoding="utf-8") as f:
            f.write(csv01)
        with open(out02, "w", encoding="utf-8") as f:
            f.write(csv02)
        log(f"[DRY-RUN] CSV已保存: {out01}, {out02}")
        log(f"[DRY-RUN] Sheet01 行数: {len(all_recs)}, Sheet02 行数: {len(all_pool)}")
        return

    # 写入飞书
    log("写入飞书工作簿...")
    ok1 = write_to_feishu(csv01, SHEET_01_ID)
    ok2 = write_to_feishu(csv02, SHEET_02_ID)

    if ok1 and ok2:
        log("全部写入成功 ✓")
        log(f"工作簿链接: https://bpn58hiwlt.feishu.cn/sheets/{SPREADSHEET_TOKEN}")
    else:
        log("部分写入失败", "ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
