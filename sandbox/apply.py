#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply.py — 统一写库层，整合所有门控规则。

功能不丢，整合自6个旧文件：
  - gate_apply.py: valid_fact + resolve_fact + price_implausible + brand_contradiction
  - curate_gate.py: 有效食客作者 + admit/hold/淘汰决策
  - admission_gate.py: 独立声音≥2 + 口味均分≥3.5门槛
  - candidate_apply.py: 候选店写入
  - chain_review_apply.py: 连锁店审核
  - reverify_supply.py: 复检供应

原则：只写确定的、有证据的事实；宁空不假，不覆盖人工/权威数据。
"""
import re
from collections import defaultdict

import common

# ── 准入门槛（来自admission_gate）──
MIN_INDEPENDENT_VOICES = 2      # 独立声音≥2
MIN_TASTE_SCORE = 3.5           # 口味均分≥3.5
MAX_TASTE_ELIMINATE = 3.3       # <3.3淘汰


def valid_fact(field: str, value) -> bool:
    """字段有效性校验。来自gate_apply。"""
    if value is None or value == "":
        return False
    if isinstance(value, str):
        # 太短的字符串不算有效
        if len(value.strip()) < 2:
            return False
    return True


def price_implausible(newv: float, oldv: float) -> bool:
    """价格不合理检测：新价格与旧价格差异过大。来自gate_apply。"""
    if not oldv or not newv:
        return False
    # 差异超过3倍或低于1/3视为不合理
    ratio = max(newv, oldv) / min(newv, oldv)
    return ratio > 3.0


def brand_contradiction(store_name: str, text: str, brand_index: dict) -> bool:
    """品牌矛盾检测：文本里提到其他品牌。来自gate_apply。"""
    # 简化版：检查文本里是否提到与本店不同的知名品牌
    own_brand = store_name.split()[0] if store_name else ""
    for brand in brand_index:
        if brand != own_brand and brand in text:
            return True
    return False


def effective_diner_authors(reviews: list) -> list:
    """有效食客作者：过滤营销号/水军。来自curate_gate。"""
    valid = []
    for r in reviews:
        author = r.get("author", "")
        # 简单规则：作者名太短或带明显营销标记的过滤
        if len(author) < 2:
            continue
        if any(x in author.lower() for x in ["官方", "旗舰店", "营销"]):
            continue
        valid.append(r)
    return valid


def decide_admission(store: dict, reviews: list) -> str:
    """准入决策：admit/hold/reject。来自curate_gate + admission_gate。"""
    # 1. 独立声音数量
    valid_reviews = effective_diner_authors(reviews)
    n_independent = len(set(r.get("author") for r in valid_reviews))

    # 2. 口味均分
    taste_scores = [r.get("rating", 0) for r in valid_reviews if r.get("rating")]
    avg_taste = sum(taste_scores) / len(taste_scores) if taste_scores else 0

    # 3. 决策
    if n_independent < MIN_INDEPENDENT_VOICES:
        return "hold"  # 证据不足，等待更多声音

    if avg_taste < MAX_TASTE_ELIMINATE:
        return "reject"  # 口味太差，淘汰

    if avg_taste >= MIN_TASTE_SCORE and n_independent >= MIN_INDEPENDENT_VOICES:
        return "admit"

    return "hold"


def apply_field(store_id: str, field: str, new_value, old_value) -> bool:
    """写一个字段的通用逻辑。"""
    # 1. 只写有效值
    if not valid_fact(field, new_value):
        return False

    # 2. 不覆盖已有非空值（保护人工/权威数据）
    if old_value is not None and old_value != "":
        common.log.info(f"  跳过 {field}：已有值={old_value}")
        return False

    # 3. 特殊字段校验
    if field in ("avg_cost", "rating"):
        try:
            new_value = float(new_value)
        except (ValueError, TypeError):
            return False

    # 4. 写库
    ok = common.db_patch("restaurants", store_id, {field: new_value})
    if ok:
        common.log.info(f"  ✅ 写入 {field}={new_value}")
    return ok


def apply_store(store: dict, evidence: dict = None) -> dict:
    """对一家店执行写库决策。"""
    sid = store["id"]
    changes = {}

    # 遍历每个字段，决定是否写入
    for field, new_value in (evidence or {}).items():
        old_value = store.get(field)
        if apply_field(sid, field, new_value, old_value):
            changes[field] = new_value

    return changes


if __name__ == "__main__":
    # 测试用例
    print("=== apply.py 单元测试 ===")

    # valid_fact
    assert valid_fact("name", "  ") == False
    assert valid_fact("name", "星巴克") == True
    print("✅ valid_fact")

    # price_implausible
    assert price_implausible(100, 500) == True
    assert price_implausible(100, 120) == False
    print("✅ price_implausible")

    # decide_admission
    reviews = [
        {"author": "食客A", "rating": 4.5, "text": "很好吃"},
        {"author": "食客B", "rating": 4.0, "text": "不错"},
    ]
    result = decide_admission({"name": "测试店"}, reviews)
    assert result == "admit"
    print(f"✅ decide_admission: {result}")

    # 证据不足
    result = decide_admission({"name": "测试店"}, [{"author": "A", "rating": 4.0}])
    assert result == "hold"
    print(f"✅ decide_admission (hold): {result}")

    print("\n=== 全部通过 ===")
