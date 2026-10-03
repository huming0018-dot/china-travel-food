#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""container_closure_audit.py — docker 生产容器依赖闭包审计（治理工具）

从全部生产入口（容器 crontab.txt + 宿主 /etc/cron.d + 宿主 crontab sh）出发，
AST 静态递归 import，得到"活代码闭包"，与 cloud 全量 py 对比 → 真正孤儿清单。

用法：python3 cloud/container_closure_audit.py [--json /tmp/closure.json]
注意：静态分析对动态 import（importlib/字符串加载）会漏，孤儿清单需人工再甄别。
"""
import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent  # 仓库根
CLOUD = ROOT / "cloud"

# 宿主侧入口（容器 crontab.txt 之外；来自 /etc/cron.d food_*、宿主 crontab sh、food_production/boundary）
HOST_ENTRIES = [
    # /etc/cron.d food_indep / food_parallel
    "national_count", "brand_chain_normalize", "gate_apply", "chain_review_apply",
    "signature_cuisine_link", "name_cuisine_link", "dietary_trait_link", "curate_gate",
    "gate_apify_brief", "cuisine_plane_audit", "probe_parallel", "production_runner",
    # 宿主 crontab 5 sh / food_production / boundary / relay
    "candidate_verify", "xhs_to_reviews", "atlas_write", "boundary_revalidate",
    "review_apify_fill", "ab_compare", "crowd_tracking", "crowd_settlement",
    "crowd_store_ingest", "notify_cli",
    # 人工管理/运维工具（不在 cron 但属活工具，保守纳入）
    "crowd_admin", "crowd_scale", "crowd_build", "crowd_smoke_monitor", "pm_dispatch",
    "entrypoint", "fix_paths", "code_audit",
]


def build_index():
    """basename(去.py) -> [相对路径...]（cloud 全量，含 vendor/pipeline）。"""
    idx = {}
    for p in CLOUD.rglob("*.py"):
        rel = p.relative_to(ROOT)
        idx.setdefault(p.stem, []).append(str(rel))
    return idx


def parse_crontab_entries():
    """从 cloud/crontab.txt 提取引用的 py 模块名。"""
    cf = CLOUD / "crontab.txt"
    names = set()
    if cf.exists():
        for tok in cf.read_text(encoding="utf-8").split():
            if tok.endswith(".py"):
                names.add(pathlib.Path(tok).stem)
    return names


def imports_of(path):
    """返回一个 py 文件 import 的顶层模块名集合（本地候选）。"""
    out = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                out.add(n.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.add(node.module.split(".")[0])
    return out


def resolve(mod, idx):
    """模块名 → 本地文件相对路径列表（命中索引才是本地模块）。"""
    return idx.get(mod, [])


def main():
    idx = build_index()
    seeds = parse_crontab_entries() | set(HOST_ENTRIES)

    alive = set()       # 相对路径集合
    queue = []
    missing_seeds = []
    for s in sorted(seeds):
        paths = resolve(s, idx)
        if not paths:
            missing_seeds.append(s)
        for p in paths:
            if p not in alive:
                alive.add(p)
                queue.append(p)

    # BFS 递归闭包
    while queue:
        rel = queue.pop()
        for mod in imports_of(ROOT / rel):
            for p in resolve(mod, idx):
                if p not in alive:
                    alive.add(p)
                    queue.append(p)

    all_py = {str(p.relative_to(ROOT)) for p in CLOUD.rglob("*.py")}
    orphans = sorted(all_py - alive)

    print(f"生产入口种子: {len(seeds)} 个（其中 {len(missing_seeds)} 个在 cloud 无对应文件）")
    if missing_seeds:
        print("  无对应文件的种子（可能在别处/命名差异）:", ", ".join(sorted(missing_seeds)))
    print(f"活代码闭包: {len(alive)} 个 py")
    print(f"cloud 全量: {len(all_py)} 个 py")
    print(f"=== 疑似孤儿: {len(orphans)} 个 ===")
    for o in orphans:
        print(" ", o)

    if "--json" in sys.argv:
        i = sys.argv.index("--json")
        out_f = sys.argv[i + 1]
        pathlib.Path(out_f).write_text(json.dumps(
            {"seeds": sorted(seeds), "missing_seeds": sorted(missing_seeds),
             "alive": sorted(alive), "orphans": orphans}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\n[json] 已写 {out_f}")


if __name__ == "__main__":
    main()
