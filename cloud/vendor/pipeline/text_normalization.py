"""Deterministic CJK/name/address matching helpers. No project config or database imports.

OpenCC t2s remains optional; Japanese character mappings and punctuation policy
are inherited matching conventions, not universal linguistic normalization.
"""
import re

def norm_name(name: str) -> str:
    """归一店名用于去重匹配：小写、去空白与常见标点；保留中文/字母/数字。
    注意：不剥离分店名（连锁分店需保留为不同实体），仅做字符归一。"""
    s = (name or "").lower()
    s = re.sub(r"[\s·・•\-—_–'‘’\"“”`（）()【】\[\]]+", "", s)
    return s


# ---------------------------------------------------------------- CJK 跨字形统一归一
# 治"和菓子↔和果子、本舖↔本铺、寛↔宽、沢↔泽"等繁简/日文汉字造成的错锚。
# OpenCC 负责繁体中文(t2s)；下表补 OpenCC 不管的日文和制字 / 日文新字体。
_t2s = None
try:
    from opencc import OpenCC
    _t2s = OpenCC("t2s")
except Exception:
    _t2s = None

_JP2CN = str.maketrans({
    # 日文和制字 / 新字体（OpenCC 不转）
    "菓": "果", "舖": "铺", "寛": "宽", "沢": "泽", "竜": "龙", "黒": "黑",
    "桜": "樱", "麺": "面", "鶏": "鸡", "焼": "烧", "気": "气", "関": "关",
    "発": "发", "戸": "户", "斎": "斋", "酔": "醉", "剣": "剑", "続": "续",
    "豊": "丰", "栄": "荣", "駅": "驿", "銭": "钱", "舎": "舍", "実": "实",
    "塩": "盐", "弾": "弹", "麹": "曲", "亀": "龟", "働": "动", "枠": "框",
    "鰹": "鲣", "鱈": "鳕", "鯛": "鲷", "鮪": "鲔",
})


def cjk_unify(s) -> str:
    """繁体中文 + 日文汉字 → 简体中文（确定性、幂等）。"""
    s = str(s or "")
    if _t2s is not None:
        s = _t2s.convert(s)
    return s.translate(_JP2CN)


def cjk_norm(s) -> str:
    """跨字形统一归一：cjk_unify + 小写 + 去标点空白。店名/正文/招牌匹配统一用它。"""
    s = cjk_unify(s).lower()
    return re.sub(r"[\s·・•\-—_–'‘’\"“”`（）()【】\[\]+&]+", "", s)


def addr_core(addr: str) -> str:
    """抽取'XX路/街/村 NNN弄 NNN号'主干，用于同址判定。"""
    if not addr:
        return ""
    s = str(addr)
    m = re.search(r"([\u4e00-\u9fa5A-Za-z0-9]+(?:路|街|道|村|公路)\d*[\u4e00-\u9fa5A-Za-z0-9]*?(?:\d+弄)?\d*号?)", s)
    core = m.group(1) if m else re.sub(r"[（(].*?[)）]", "", s)
    return re.sub(r"\s", "", core)


