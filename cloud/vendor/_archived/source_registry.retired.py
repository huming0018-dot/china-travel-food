#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""source_registry.py — 上海美食图鉴「信源注册表」（P5 信源资产化，A4 信源沉淀）。

把每一个可用源注册为长期连接器：注册信息 / 能力 / 认证层级 / 质量评分 / 淘汰条件 /
调度节奏 / 账号依赖度；并动态探测健康（连接器是否在、状态文件 mtime、账号池状态）。
默认只读打印；--save 写 /app/data/source_registry.json（数据资产，不写库、不改业务表）。

设计依据（mechanism-master-v4 P5 / north-star A4 A5）：
  - L0 公开/官方 API（地图 key、B站公开搜索）——优先；
  - L1 匿名签名直连（小红书签名 HTTP）；
  - L2 网页只读（米其林列表/海外媒体）；
  - L3 登录账号兜底（点评 cookie、小红书账号）——最后手段，池化、独立出口 IP、健康管理。
  - reliability：是否常发软广 / 可否交叉验证 / 更新频率 / 专业度；低质只作线索，高质才作证据。
  - 淘汰条件：连续 N 次失败 / 配额长期耗尽 / 账号全部过期且无替代 → health=down 并告警。

容器内：cloud=/app/cloud，data=/app/data。本脚本不采集、不写 restaurants。
"""
import argparse
import json
import pathlib
import sys
import time
from datetime import datetime, timezone

HERE = pathlib.Path("/app/cloud")
PIPE = "/app/pipeline"
DATA = pathlib.Path("/app/data")
sys.path.insert(0, str(HERE))

# ---------------------------------------------------------------------------
# 静态目录：每一条都是「真实存在/确证待建」的源，凭真实连接器文件注册，不臆造。
# auth_level: L0 公开API / L1 匿名签名 / L2 网页只读 / L3 登录账号
# frames: 该源服务哪些独立抽样框（F1地理 F2权威 F3集团树 F4社交 F5地图 F6滚雪球）
# ---------------------------------------------------------------------------
CATALOG = [
    {
        "id": "michelin_list", "name": "米其林指南·上海主列表",
        "platform": "guide.michelin.com", "kind": "official_guide",
        "auth_level": "L2", "frames": ["F2", "F6"],
        "connector_module": "cloud_michelin_collect.py",
        "output": "/app/data/michelin_shanghai.json",
        "reliability": 0.95, "refresh_cadence": "weekly",
        "account_dependency": "none",
        "covers": "米其林星级/必比登/入选 全量索引；只作『不漏』发现入口，不作口味背书",
        "retire_if": "连续 3 周抓取 <100 条，或纯 requests 返回 202 且浏览器通道失效",
        "note": "sitemap 全量召回见 authority_sitemap.py（含望庐这类主列表漏掉的店）；本连接器只翻主列表",
    },
    {
        "id": "michelin_sitemap", "name": "米其林指南·sitemap 全量索引",
        "platform": "guide.michelin.com/sitemap.xml", "kind": "official_guide",
        "auth_level": "L2", "frames": ["F2"],
        "connector_module": "authority_sitemap.py",
        "output": "research/authority/sitemap_shanghai.json",
        "reliability": 0.98, "refresh_cadence": "monthly",
        "account_dependency": "none",
        "covers": "与官方总数(156)对账的兜底；四态裁决 exact/strong/weak/none",
        "retire_if": "官方 sitemap 结构变更致连续 2 次解析 0 上海 slug",
        "note": "必须浏览器（纯 requests 202）；慢 XML 页用 cdp+Wait 法",
    },
    {
        "id": "blackpearl", "name": "黑珍珠餐厅指南·上海",
        "platform": "blackpearl.meituan.com (apimeishi.meituan.com)", "kind": "official_guide",
        "auth_level": "L2", "frames": ["F2b"],
        "connector_module": "cloud_blackpearl_collect.py",
        "output": "/app/data/blackpearl_shanghai.json",
        "reliability": 0.95, "refresh_cadence": "yearly",
        "account_dependency": "none",
        "covers": "黑珍珠上海官方全量（2026=61，3/2/1钻=3/6/52）；getSelectorList+filterList 双口径对账；"
                  "与库 make_matcher 四态比对 + 分店错配排除；在库在榜店幂等挂 160 认证标签",
        "retire_if": "源停办，或 apimeishi rank 接口连续 2 次 totalCount=0",
        "note": "官方 rank API 逆向自 blackpearl-overseas SPA home.js；上海 cityId=1；"
                "默认 dry-run，--apply-tag 才挂标；missing(17) 交 admission_gate 补录",
    },
    {
        "id": "amap_poi", "name": "高德地图 POI",
        "platform": "高德开放平台", "kind": "map",
        "auth_level": "L0", "frames": ["F1", "F5"],
        "connector_module": "map_helpers.py/cloud_amap_fill.py",
        "output": "/app/data/amap_poi_cache.jsonl",
        "reliability": 0.80, "refresh_cadence": "daily(配额制)",
        "account_dependency": "none",
        "covers": "地图 POI 枚举/坐标/电话；单平台声音只建 frontier，不直接收录",
        "retire_if": "key 全部 10007/配额长期耗尽且无替代 key",
        "note": "数字签名 SK 按 key 池轮换；只读使用，不改连接器本身",
    },
    {
        "id": "tencent_map", "name": "腾讯位置服务",
        "platform": "腾讯位置服务", "kind": "map",
        "auth_level": "L0", "frames": ["F1", "F5"],
        "connector_module": "cloud_phone_fill.py/cloud_coord_fill.py",
        "output": "/app/data/_phone_fill_state.json",
        "reliability": 0.75, "refresh_cadence": "daily(配额制)",
        "account_dependency": "none",
        "covers": "高德的备份地图通道（电话/坐标）；GCJ-02",
        "retire_if": "主 key 日量 121 超限且无新实名 key",
        "note": "真实日量偏低，已在 HANDOFF 列扩容待办",
    },
    {
        "id": "xhs_signed", "name": "小红书签名 HTTP 采集",
        "platform": "xiaohongshu", "kind": "ugc",
        "auth_level": "L1/L3", "frames": ["F4", "F6"],
        "connector_module": "xhs_api.py/gap_runner.py/discovery_engine.py",
        "output": "/app/data/discovery/",
        "reliability": 0.70, "refresh_cadence": "continuous(池常驻)",
        "account_dependency": "required(L3 账号 cookie + 独立出口IP)",
        "covers": "老饕私藏/图遍历/评论区二次溯源；证据需 admission_gate 独立声音≥2",
        "retire_if": "全部账号 -100 过期 >72h 且无新 cookie；搜索 300011 长期不恢复",
        "note": "A5 账号最后手段：池化、每账号独立代理、健康探测、不硬刷",
    },
    {
        "id": "bili_search", "name": "B 站公开搜索",
        "platform": "bilibili", "kind": "ugc",
        "auth_level": "L0", "frames": ["F4", "G"],
        "connector_module": "cloud_bili_collect.py",
        "output": "/app/data/bili_state.json",
        "reliability": 0.75, "refresh_cadence": "every_6h",
        "account_dependency": "none",
        "covers": "美食探店视频/KOL 监控名单(food_kol_watchlist)；标题简介只作线索，不直接背书",
        "retire_if": "API code!=0 连续 5 次且 bili-cli 兜底也失效",
        "note": "必须带 Referler；KOL≥3 次入监控表",
    },
    {
        "id": "kol_watchlist_monitor", "name": "KOL/美食家名单监控（帖子归档+提及锚定）",
        "platform": "bilibili/xiaohongshu/cross", "kind": "ugc",
        "auth_level": "L0(bili搜索)/L3(xhs)", "frames": ["F4", "F6"],
        "connector_module": "kol_monitor.py",
        "output": "/app/data/kol_monitor_report.json; food_kol_posts/food_kol_mentions",
        "reliability": 0.72, "refresh_cadence": "daily(增量游标)",
        "account_dependency": "bili=none(keyless搜索); xhs=required(L3,当前-100停摆)",
        "covers": "遍历 food_kol_watchlist(38)：按平台拉近期内容→归档→提及店锚定(高置信才绑restaurant_id,"
                  "连锁分店正文消歧否则留空)→新候选路由 discovery 池交 admission_gate(≥2独立声音)。提及只作线索不计口味",
        "retire_if": "bili搜索 code!=0 连续5轮且无兜底；或 watchlist 连续14天零新内容",
        "note": "Phase0-E 接线。bili space/wbi 在数据中心IP -403/-352 不可用，走 keyless 搜索按author+mid严格归属；"
                "xhs 两账号 -100 待恢复；cross(美食作家)无单渠道登记不轮询。只写 food_kol_posts/mentions，restaurants 零变化",
    },
    {
        "id": "bili_video_enrich", "name": "B站视频 enrichment（详情/字幕/评论→堂食口味信号，分KOL/食客声音）",
        "platform": "bilibili", "kind": "ugc",
        "auth_level": "L0(keyless)", "frames": ["F4", "F6"],
        "connector_module": "bili_enrich.py",
        "output": "/app/data/discovery/bili_signals.jsonl",
        "reliability": 0.65, "refresh_cadence": "daily(增量游标 done_posts)",
        "account_dependency": "none",
        "covers": "对 food_kol_posts(bilibili) 逐条补 view详情/公开字幕/评论区：KOL正文/字幕=curator半商业(trust低,权重0.6)，"
                  "评论区(排除UP主本人)=独立食客声音(keyless未验证trust=low)；只产信号落 discovery 交 admission_gate，绝不直接插 restaurants",
        "retire_if": "view/reply code!=0 连续5轮；或连续14天零新信号",
        "note": "Track1B。实测2026-09-29：view?bvid=code0补全desc(搜索常为-)；公开字幕0/104(探店视频无CC,自动字幕需登录不硬刷)；"
                "x/v2/reply Referer=视频页 code0(98/104帖拿到284条评论)。restaurants/posts/mentions 零变化",
    },
    {
        "id": "kol_cross_platform", "name": "KOL跨平台身份归一+开放平台定点采集(公众号搜狗/已含B站)",
        "platform": "wechat/bilibili(微博知乎抖音skipped)", "kind": "ugc",
        "auth_level": "L0(keyless)", "frames": ["F4", "F6"],
        "connector_module": "kol_cross.py",
        "output": "/app/data/discovery/raw_cross.jsonl; food_kol_watchlist.handles(016)",
        "reliability": 0.6, "refresh_cadence": "every_6h(内容指纹增量)",
        "account_dependency": "none(不硬闯XHS/微博/知乎/抖音)",
        "covers": "以watchlist为主实体映射跨平台handle(同名/已知mid才记,否则留空不猜)；cross美食作家经搜狗微信按名采文章，"
                  "内容指纹sha1(归一标题)去重(跨平台同款只算1独立声音)；提及归一restaurant_id(多分店留空)，"
                  "归属不确定→线索入gap pool，过admission_gate(≥2独立声音+口味≥3.5+堂食单品)才入库，KOL不回写score",
        "retire_if": "搜狗antispider连续5轮；或连续14天零新线索",
        "note": "Track1C。2026-09-29实测：bilibili mid已知39/41；9/9 cross作家公众号有公开痕迹(keyless拿不到可靠账号名→不写handles,待016列+人工确认)；"
                "微博s.weibo 0cards/知乎403/抖音JS壳=skipped不硬刷。首轮抓88篇去重87,matched3(全聚德淮海/夜上海/晟永兴外滩),线索24→gap pool。restaurants/posts/mentions零变化",
    },
    {
        "id": "dianping_identity", "name": "点评身份/电话锚定",
        "platform": "dianping", "kind": "map/identity",
        "auth_level": "L3", "frames": ["C"],
        "connector_module": "cloud_dianping_phone.py",
        "output": "/app/data/dianping_phone_report.json",
        "reliability": 0.60, "refresh_cadence": "on_demand",
        "account_dependency": "required(L3 cookie)",
        "covers": "事实层：电话/身份锚定；网页风控强，只读、遇验证码交真人",
        "retire_if": "cookie 全失效且无替代；或地图 L0 通道已覆盖全部电话需求",
        "note": "A5：L3 仅用于无替代的电话/身份，能 L0/L1 就不升 L3",
    },
    {
        "id": "media_overseas", "name": "海外双语美食媒体",
        "platform": "SmartShanghai/TimeOut/Nomfluence", "kind": "media",
        "auth_level": "L2", "frames": ["F2", "D"],
        "connector_module": "",  # 待建
        "output": "",
        "reliability": 0.80, "refresh_cadence": "monthly",
        "account_dependency": "none",
        "covers": "治软广、补 Fine Dining/Bistro/Brunch/咖啡甜品；只作 endorsement，不作 UGC",
        "retire_if": "源停更",
        "note": "【待建】公开网页只读采集器；媒体不得冒充 UGC 证据",
    },
]


def _mtime(p):
    try:
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(pathlib.Path(p).stat().st_mtime))
    except Exception:
        return None


def _probe_accounts():
    """返回 {account: status}；探测失败返回 {}（不阻塞注册）。"""
    try:
        sys.path.insert(0, str(HERE))
        import xhs_cookie_pool as pool
        s = pool.summary() or {}
        return {k: v.get("status") for k, v in s.items() if isinstance(v, dict)}
    except Exception:
        return {}


def _conn_exists(conn):
    """连接器文件可能在 /app/cloud 或 /app/pipeline（vendor/pipeline 快照）。"""
    if not conn:
        return False
    name = conn.split("/")[0]
    return (HERE / name).exists() or (pathlib.Path(PIPE) / name).exists()


def build():
    accts = _probe_accounts()
    out = []
    for s in CATALOG:
        conn = s["connector_module"]
        conn_exists = _conn_exists(conn)
        # last_polled：取 output 文件 mtime
        last = None
        if s["output"] and pathlib.Path(s["output"]).exists():
            last = _mtime(s["output"])
        # 健康裁决
        health = "ok"
        notes = []
        if not s["connector_module"]:
            health = "not_built"
            notes.append("连接器待建")
        elif not conn_exists:
            health = "missing"
            notes.append(f"连接器文件 {conn} 不在 /app/cloud")
        if s["id"] == "xhs_signed":
            alive = [a for a, st in accts.items() if st == "ok"]
            if not alive:
                health = "down"
                notes.append(f"全部账号状态={accts or '未知'}（-100/冷却），F4 当前停摆")
            else:
                notes.append(f"可用账号={alive}")
        if s["id"] == "amap_poi":
            ql = DATA / "map_quota_ledger.json"
            if ql.exists():
                try:
                    j = json.loads(ql.read_text(encoding="utf-8"))
                    notes.append(f"配额账本={json.dumps(j, ensure_ascii=False)[:120]}")
                except Exception:
                    pass
        row = dict(s)
        row.update({
            "connector_present": bool(conn and conn_exists),
            "last_polled": last,
            "health": health,
            "accounts": accts if s["account_dependency"].startswith("required") else {},
            "health_notes": notes,
            "registered_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        })
        out.append(row)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="写 /app/data/source_registry.json")
    args = ap.parse_args()

    rows = build()
    print("=" * 92)
    print("信源注册表（Source Registry）—— 长期连接器资产")
    print("=" * 92)
    hdr = f"{'id':<18}{'层级':<6}{'框':<10}{'rel':<5}{'健康':<10}{'last_polled':<18}账号依赖"
    print(hdr)
    print("-" * 92)
    for r in rows:
        fr = ",".join(r["frames"])
        acc = "账号" if r["account_dependency"].startswith("required") else "-"
        print(f"{r['id']:<18}{r['auth_level']:<6}{fr:<10}{r['reliability']:<5}"
              f"{r['health']:<10}{str(r['last_polled'] or '-'):<18}{acc}")
        for n in r["health_notes"]:
            print(f"      ↳ {n}")
    n_ok = sum(1 for r in rows if r["health"] == "ok")
    n_down = sum(1 for r in rows if r["health"] == "down")
    n_notbuilt = sum(1 for r in rows if r["health"] == "not_built")
    print("-" * 92)
    print(f"合计 {len(rows)} 个注册源：ok={n_ok} down={n_down} not_built={n_notbuilt}")
    l3 = [r['id'] for r in rows if r['auth_level'].startswith('L3')]
    print(f"L3 登录账号依赖源: {l3}（A5 最后手段，占比 {len(l3)}/{len(rows)}）")

    if args.save:
        out = DATA / "source_registry.json"
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写 {out}")
    else:
        print("\n(dry-run；加 --save 写 /app/data/source_registry.json)")


if __name__ == "__main__":
    main()
