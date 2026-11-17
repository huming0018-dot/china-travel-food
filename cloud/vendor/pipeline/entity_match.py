"""兼容旧 entity_match 入口；仅 get_index 首次调用或 force 时读取数据库。

纯计算消费者直接 import entity_matching；旧公开函数继续可用。
"""
from entity_matching import (
    SQ,
    strip_branch,
    brand_forms,
    head_token,
    GENERIC_WORDS,
    is_generic_name,
    head_usable,
    MALLS,
    branch_malls,
    malls_in,
    branch_addr_token,
    POS,
    NEG,
    taste_sent,
    QUESTION,
    is_question,
    clean_content,
    M,
    EntityIndex,
)

# ------------------------------------------------------------ 缓存默认索引
_INDEX = None


def get_index(force=False):
    global _INDEX
    if _INDEX is None or force:
        import common as C
        rests = C.fetch_all("restaurants", "id,name,status,district,address")
        _INDEX = EntityIndex(rests)
    return _INDEX
