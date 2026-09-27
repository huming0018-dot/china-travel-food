#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chef_tracker.py — 主厨动向长期跟踪脚本

功能：
1. 拉取所有 chefs 记录，检查 last_tracked_at 时效性
2. 标记需要跟踪的主厨（按优先级：有 group_id 的集团老板 > 米其林星厨 > 其他）
3. 扫描 food_events 表中关联 chef_id 的事件
4. 输出需要人工/AI 跟进的主厨清单
5. 更新 last_tracked_at

设计原则：
- 不进20分钟高频cron，建议每周跑一次（云端 cron: 0 9 * * 1 周一早9点）
- 本脚本只做状态管理和清单输出，不自动爬社交媒体（避免反爬/封号）
- 社交媒体/新闻发现走 social_discovery.py 管线或人工+AI agent 定期检索
- 宁空不假：没有新动向就不写 food_events

用法:
  python3 chef_tracker.py              # 输出待跟踪清单
  python3 chef_tracker.py --update     # 更新已处理主厨的 last_tracked_at
  python3 chef_tracker.py --priority   # 只输出高优先级主厨
"""
import sys, datetime, json
sys.path.insert(0, "/Users/hubowen/Library/Application Support/Doubao/Default/.doubao/agent_mode/workspace/.user_skills/city-food-guide/scripts/food_pipeline")
import common as C

TODAY = datetime.date.today().isoformat()
WARN_DAYS = 14   # 超过14天未跟踪 = 黄色
ALERT_DAYS = 30  # 超过30天未跟踪 = 红色

# 高优先级主厨：集团创始人/米其林星厨（按 chef id 或名字匹配）
HIGH_PRIORITY_KEYWORDS = [
    "Paul Pairet", "Umberto Bombana", "董振祥", "大董", "张勇", "翁拥军",
    "卢怿明", "杜建青", "吴嵘", "江振诚", "侯新庆", "许文杰", "谭仕业",
    "段誉", "方元", "Joël Robuchon", "Pierre Gagnaire",
]


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def main():
    update = "--update" in sys.argv
    priority_only = "--priority" in sys.argv

    # Pull all chefs
    chefs = C.fetch_all("chefs", "id,name,name_en,title,last_tracked_at,group_id,reputation",
                        order_col="id")
    print(f"=== Chefs in DB: {len(chefs)} ===\n")

    # Pull food_events with chef_id
    events = C.fetch_all("food_events", "id,title,event_date,chef_id,category",
                         order_col="id")
    chef_event_count = {}
    for e in events:
        cid = e.get("chef_id")
        if cid:
            chef_event_count[cid] = chef_event_count.get(cid, 0) + 1

    # Categorize
    red, yellow, green, no_date = [], [], [], []
    for c in chefs:
        name = c["name"]
        lt = parse_date(c.get("last_tracked_at"))
        is_high = any(kw in name for kw in HIGH_PRIORITY_KEYWORDS) or c.get("group_id")

        if not lt:
            no_date.append((c, is_high))
        else:
            days = (datetime.date.today() - lt).days
            entry = (c, is_high, days)
            if days > ALERT_DAYS:
                red.append(entry)
            elif days > WARN_DAYS:
                yellow.append(entry)
            else:
                green.append(entry)

    print(f"已跟踪(<{WARN_DAYS}天): {len(green)}")
    print(f"需关注({WARN_DAYS}-{ALERT_DAYS}天): {len(yellow)}")
    print(f"需立即跟踪(>{ALERT_DAYS}天): {len(red)}")
    print(f"从未跟踪: {len(no_date)}")
    print()

    # Output priority list
    todo = []
    for c, high, days in red + yellow + [(c, h, -1) for c, h in no_date]:
        if priority_only and not high:
            continue
        events_count = chef_event_count.get(c["id"], 0)
        todo.append({
            "id": c["id"], "name": c["name"],
            "title": c.get("title", "")[:60],
            "days_since_tracked": days,
            "is_high_priority": high,
            "group_id": c.get("group_id"),
            "events_count": events_count,
        })

    # Sort: high priority first, then by days desc
    todo.sort(key=lambda x: (not x["is_high_priority"], -max(x["days_since_tracked"], 0)))

    print(f"=== 待跟踪主厨清单 ({len(todo)}) ===")
    for t in todo:
        flag = "🔴" if t["is_high_priority"] else "🟡"
        days_str = f"{t['days_since_tracked']}天前" if t["days_since_tracked"] >= 0 else "从未"
        print(f"  {flag} [{t['id']}] {t['name']} | {days_str} | events={t['events_count']} | {t['title']}")

    if update:
        print(f"\n[--update] Marking {len(todo)} chefs as tracked today...")
        import requests
        H = {**C.headers(), "Prefer": "return=representation"}
        for t in todo:
            r = requests.patch(C.BASE + f"/chefs?id=eq.{t['id']}",
                              headers=H, json={"last_tracked_at": TODAY}, timeout=30)
            if r.status_code == 200:
                print(f"  Updated chef {t['id']} {t['name']}")
            else:
                print(f"  ERROR {r.status_code}: {r.text[:200]}")

    # Cloud cron instructions
    print(f"""
=== 云端工作流接入建议 ===
1. 本脚本建议每周一早9点跑一次（不进20分钟高频cron）：
   0 9 * * 1  cd {C.DEFAULT_APP}/.. && python3 chef_tracker.py
   
2. 发现新动向时（主厨离职/新店/获奖/飞行厨房）：
   - 在 food_events 表插入事件，关联 chef_id
   - category 可选：new_restaurant / departure / award / guest_chef / relocation / menu_change
   
3. 社交媒体监控建议：
   - 高优先级主厨（集团创始人/米其林星厨）每周人工+AI检索一次
   - 小红书/抖音/微博搜索主厨名 + 新店/离职/获奖关键词
   - 结果写入 food_events，关联 chef_id
   
4. 下次全量刷新 chefs 资料：每季度跑一次 build_chefs.py（补充新主厨+更新背景）
""")


if __name__ == "__main__":
    main()
