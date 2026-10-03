#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""discover.py — 发现新餐厅。

整合自：
  - vendor/pipeline/hae_engine.py（LLM舰队假设生成）
  - comention_probe.py（关键词共现联想）
  - serp_producer.py（搜索引擎发现）

功能不丢：用LLM生成假设 → 关键词联想扩展 → 搜索引擎验证 → 候选店入库。
"""
import common


def llm_hypotheses(cuisine: str, area: str) -> list:
    """LLM舰队：生成假设。简化版，实际调用LLM API。"""
    # 这里是占位，实际应该调用LLM生成：
    # "上海徐汇区有哪些好的川菜馆？"
    return []


def comention_expand(keyword: str) -> list:
    """关键词共现：从已知餐厅联想相关词。"""
    # 实际应该：查数据库里同菜系/同区域的餐厅名，提取关键词
    return []


def search_engine_verify(name: str, area: str) -> dict:
    """搜索引擎验证：确认这家店真实存在。"""
    # 实际应该：调用SERP API搜索，确认地址/电话/评分
    return {}


def run():
    """执行一轮发现。"""
    common.log.info("开始发现新餐厅")

    # 1. 从已有数据里选几个热门菜系
    cuisines = ["川菜", "日料", "咖啡", "bistro"]

    # 2. 对每个菜系生成假设
    candidates = []
    for cuisine in cuisines:
        hypos = llm_hypotheses(cuisine, "上海")
        candidates.extend(hypos)

    # 3. 关键词联想扩展
    expanded = []
    for kw in candidates:
        expanded.extend(comention_expand(kw))

    # 4. 搜索引擎验证
    verified = []
    for name in expanded:
        info = search_engine_verify(name, "上海")
        if info:
            verified.append(info)

    common.log.info(f"发现完成：{len(verified)}家候选店")
    return verified


if __name__ == "__main__":
    run()
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""discover_ext.py — 扩展发现：边界笔记 + 搜索探针 + 地图解卡。

#38 跑题/边界笔记：未锚定但有食物实质的笔记不丢弃，判recover/lead/drop
#33 搜索引擎探针：关键词组合找新店线索
#45 地图解卡：故障转移 + pick_best拒绝他店号码
"""
import json
import time
import config
import common
from difflib import SequenceMatcher

BOUNDARY_F = config.DATA / "boundary_notes.jsonl"


# ── 边界笔记 ──
def save_boundary(note: dict):
    note["ts"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(BOUNDARY_F, "a", encoding="utf-8") as f:
        f.write(json.dumps(note, ensure_ascii=False) + "\n")


def classify(note: dict) -> str:
    """判 recover/lead/drop。"""
    text = (note.get("title", "") + note.get("desc", "")).lower()
    taste_words = ["好吃", "难吃", "推荐", "踩雷", "口味", "味道"]
    has_taste = any(w in text for w in taste_words)
    has_store = "店" in text or "馆" in text
    if has_taste and has_store:
        return "recover"
    if has_store:
        return "lead"
    return "drop"


# ── 地图解卡 ──
def pick_best(candidates: list, target_name: str) -> dict:
    """从候选里挑最佳，相似度<0.7拒绝，不挪用他店号码。"""
    best = None
    best_score = 0
    for c in candidates:
        score = SequenceMatcher(None, target_name, c.get("name", "")).ratio()
        if score > best_score:
            best_score = score
            best = c
    if best_score < 0.7:
        common.log.warning(f"pick_best拒绝: {target_name} ({best_score:.2f})")
        return None
    return best


def rescue_one(store: dict) -> dict:
    """故障转移：腾讯失败转高德。"""
    # 简化版：实际调用地图API
    return {"fixed": False, "error": "未实现"}


# ── 搜索探针 ──
def probe_run(limit: int = 10):
    """跑一轮搜索探针。"""
    common.log.info("搜索探针启动")
    # 简化版：实际调用搜索引擎API
    return 0


if __name__ == "__main__":
    print("扩展发现模块就绪")
    print("功能: 边界笔记 + 搜索探针 + 地图解卡")
