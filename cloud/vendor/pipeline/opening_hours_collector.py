#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
opening_hours_collector.py — 从 evidence_summary 提取营业时间，写入 opening_hours(jsonb) + open_days(text)

原则：宁空不假。只提取有明确时间模式的文本；提取不到不臆造。
- opening_hours: {"周一":"11:00-22:00", "周二":"11:00-22:00", ...}
- open_days: "周一至周日" / "周二休" / "仅周末" 等

用法：
  python3 opening_hours_collector.py                # dry-run
  python3 opening_hours_collector.py --commit       # 写库
  python3 opening_hours_collector.py --commit --high-priority  # 只处理 score>75 / 米其林 / 有评价
"""
import argparse
import collections
import json
import re
import sys
import time
from collections import defaultdict

import common as C

DAYS_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
DAYS_SHORT = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def parse_evidence_quotes(ev_raw):
    """提取 evidence_summary 中所有引用文本拼接成一段，便于正则匹配。"""
    if not ev_raw:
        return ""
    try:
        j = json.loads(ev_raw) if isinstance(ev_raw, str) else ev_raw
        texts = []
        for q in j.get("quotes", []):
            if isinstance(q, dict):
                texts.append(q.get("quote", ""))
            else:
                texts.append(str(q))
        return " ".join(texts)
    except (json.JSONDecodeError, TypeError, AttributeError):
        return str(ev_raw) if ev_raw else ""


def extract_time_ranges(text):
    """从文本提取营业时间区间。返回 list of (start, end, period_note)。
    匹配: 11:00-22:00 / 11:00~22:00 / 11:00—22:00 / 11点到22点 / 11:00-14:00,17:00-22:00"""
    ranges = []
    # 标准 HH:MM-HH:MM
    for m in re.finditer(r"(\d{1,2}[:：]\d{2})\s*[-~—–至到]\s*(\d{1,2}[:：]\d{2})", text):
        s, e = m.group(1).replace("：", ":"), m.group(2).replace("：", ":")
        # 规范化 HH:MM
        def norm(t):
            h, m = t.split(":")
            return f"{int(h):02d}:{m}"
        try:
            s, e = norm(s), norm(e)
            ranges.append((s, e))
        except Exception:
            pass
    # "11点到22点" / "11点至22点"
    if not ranges:
        for m in re.finditer(r"(\d{1,2})点\s*[-~—–至到]\s*(\d{1,2})点", text):
            s, e = int(m.group(1)), int(m.group(2))
            if 5 <= s <= 23 and 6 <= e <= 24:
                ranges.append((f"{s:02d}:00", f"{e:02d}:00"))
    return ranges


def extract_closed_day(text):
    """提取休息日。返回 '周一'..'周日' 或 None。"""
    patterns = [
        r"(周[一二三四五六日天])\s*(休息|休业|定休|店休|闭店)",
        r"每周\s*(周[一二三四五六日天])",
        r"((?:周一|周二|周三|周四|周五|周六|周日))\s*休",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            day = m.group(1).replace("天", "日")
            return day
    return None


def extract_day_range(text):
    """提取营业日范围。返回 (start_day_idx, end_day_idx) 或 None。
    支持: 周一至周日 / 周一到周五 / 周二至周六 / 周末 / 工作日"""
    # 周一至周日
    m = re.search(r"(周[一二三四五六日天])\s*[-至到—–]\s*(周[一二三四五六日天])", text)
    if m:
        s_day = m.group(1).replace("天", "日")
        e_day = m.group(2).replace("天", "日")
        s_idx = DAYS_CN.index(s_day) if s_day in DAYS_CN else None
        e_idx = DAYS_CN.index(e_day) if e_day in DAYS_CN else None
        if s_idx is not None and e_idx is not None:
            return (s_idx, e_idx)
    if re.search(r"周末", text):
        return (5, 6)  # 周六日
    if re.search(r"工作日", text):
        return (0, 4)  # 周一至周五
    return None


def build_opening_hours(text):
    """从文本提取营业时间。返回 (opening_hours_dict, open_days_str, confidence)。
    confidence: high=明确提取到 / low=仅部分信息 / none=未提取到"""
    if not text:
        return None, None, "none"

    ranges = extract_time_ranges(text)
    closed_day = extract_closed_day(text)
    day_range = extract_day_range(text)

    if not ranges and not closed_day:
        return None, None, "none"

    # 构建 open_days 描述
    open_days_parts = []
    if day_range:
        s_idx, e_idx = day_range
        if s_idx == 0 and e_idx == 6:
            open_days_str = "周一至周日"
        elif s_idx == 5 and e_idx == 6:
            open_days_str = "仅周末"
        elif s_idx == 0 and e_idx == 4:
            open_days_str = "周一至周五"
        else:
            open_days_str = f"{DAYS_CN[s_idx]}至{DAYS_CN[e_idx]}"
    elif closed_day:
        open_days_str = f"{closed_day}休"
    else:
        open_days_str = "周一至周日"  # 默认每天

    # 构建 opening_hours dict
    opening_hours = {}
    if ranges:
        # 如果只有一个时间段，应用到所有营业日
        if len(ranges) == 1:
            s, e = ranges[0]
            time_str = f"{s}-{e}"
            # 确定哪些天营业
            if day_range:
                s_idx, e_idx = day_range
                days = []
                i = s_idx
                while True:
                    days.append(i)
                    if i == e_idx:
                        break
                    i = (i + 1) % 7
            elif closed_day:
                closed_idx = DAYS_CN.index(closed_day)
                days = [i for i in range(7) if i != closed_idx]
            else:
                days = list(range(7))
            for i in days:
                opening_hours[DAYS_CN[i]] = time_str
        else:
            # 多个时间段（午晚市），合并
            time_str = "; ".join(f"{s}-{e}" for s, e in ranges)
            if day_range:
                s_idx, e_idx = day_range
                days = []
                i = s_idx
                while True:
                    days.append(i)
                    if i == e_idx:
                        break
                    i = (i + 1) % 7
            elif closed_day:
                closed_idx = DAYS_CN.index(closed_day)
                days = [i for i in range(7) if i != closed_idx]
            else:
                days = list(range(7))
            for i in days:
                opening_hours[DAYS_CN[i]] = time_str

    confidence = "high" if opening_hours else "low"
    return opening_hours, open_days_str, confidence


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--high-priority", action="store_true",
                    help="只处理 score_total>75 / 米其林黑珍珠 / review_count>0")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    print("拉取餐厅...", file=sys.stderr)
    rests = C.fetch_all("restaurants", order_col="id")
    awards = C.fetch_all("restaurant_awards",
                         "restaurant_id,award_type,is_current",
                         order_col="restaurant_id")
    award_rids = {a["restaurant_id"] for a in awards if a.get("is_current", True)}

    # 筛选目标
    targets = []
    for r in rests:
        if r.get("opening_hours"):
            continue
        if args.high_priority:
            score = r.get("score_total") or 0
            if score <= 75 and r["id"] not in award_rids and (r.get("review_count") or 0) == 0:
                continue
        targets.append(r)

    if args.limit:
        targets = targets[:args.limit]

    print(f"待处理: {len(targets)} 家", file=sys.stderr)

    results = []
    conf_counter = collections.Counter()
    for r in targets:
        text = parse_evidence_quotes(r.get("evidence_summary"))
        oh, od, conf = build_opening_hours(text)
        results.append({
            "id": r["id"],
            "name": r["name"],
            "opening_hours": oh,
            "open_days": od,
            "_confidence": conf,
            "_score": r.get("score_total") or 0,
        })
        conf_counter[conf] += 1

    # 打印样本
    print(f"\n=== 提取成功样本（前20条 high confidence）===")
    shown = 0
    for x in results:
        if x["_confidence"] == "high" and shown < 20:
            print(f"  [id={x['id']}] {x['name']}")
            print(f"    open_days: {x['open_days']}")
            print(f"    opening_hours: {json.dumps(x['opening_hours'], ensure_ascii=False)}")
            shown += 1
            print()

    print(f"\n=== 置信度分布 ===")
    for k, v in conf_counter.most_common():
        print(f"  {k}: {v}")

    high_n = conf_counter.get("high", 0)
    print(f"\n高置信提取率: {high_n}/{len(results)} = {high_n/max(len(results),1):.0%}")

    if not args.commit:
        print("\n[DRY-RUN] 加 --commit 写库", file=sys.stderr)
        return

    # 备份
    import pathlib
    backup_dir = pathlib.Path("/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/backups")
    backup_dir.mkdir(exist_ok=True)
    backup_file = backup_dir / f"opening_hours_backup_{C.today()}.jsonl"
    old = {r["id"]: {"opening_hours": r.get("opening_hours"),
                      "open_days": r.get("open_days")} for r in rests}
    C.write_jsonl(str(backup_file), [{"id": k, **v} for k, v in old.items()])
    print(f"备份: {backup_file}", file=sys.stderr)

    # 只写 high confidence 的
    to_write = [x for x in results if x["_confidence"] == "high" and x["opening_hours"]]
    print(f"写入 {len(to_write)} 家高置信营业时间", file=sys.stderr)

    BATCH = 50
    ok, fail = 0, 0
    for i in range(0, len(to_write), BATCH):
        batch = to_write[i:i+BATCH]
        for item in batch:
            rid = item["id"]
            payload = {
                "opening_hours": item["opening_hours"],
                "open_days": item["open_days"],
            }
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

        # 回读验证
        ids = [str(x["id"]) for x in batch]
        try:
            rv = C.req("GET",
                       f"/restaurants?select=id,opening_hours,open_days&id=in.({','.join(ids)})")
            if rv.status_code == 200:
                checked = {row["id"]: row for row in rv.json()}
                verified = sum(1 for x in batch
                               if checked.get(x["id"], {}).get("opening_hours") == x["opening_hours"])
                print(f"  批次 {i//BATCH+1}: 写入{len(batch)}, 回读验证 {verified}/{len(batch)}",
                      file=sys.stderr)
        except Exception as e:
            print(f"  回读异常: {e}", file=sys.stderr)

    print(f"\n完成: 成功 {ok}, 失败 {fail}", file=sys.stderr)


if __name__ == "__main__":
    main()
