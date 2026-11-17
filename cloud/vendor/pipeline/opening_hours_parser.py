"""Pure Chinese opening-hours text parsing; no database or collector imports.

Preserves the existing parser behavior, including confidence/default-day rules.
This is not a complete opening-hours standard or a validation guarantee.
"""
import json
import re

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


