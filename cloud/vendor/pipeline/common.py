#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
common.py — 上海美食图鉴数据管线共享层（采集 / 清洗 / 入库 / 审计 各阶段共用）

铁律：
1. service role key 只从前端项目 app/.env.local 读取，禁止硬编码进任何脚本、产物、截图、提交记录。
2. 机械环节（清洗 / 校验 / 去重 / 地理编码 / 幂等写 / 回验）一律走本文件，不靠模型临场手拼。
3. 模型只负责"发现 + 判断"，产出符合 raw_place.schema.json 的原始证据 JSONL；其余交给脚本质量门。

仅依赖 requests（环境已装）+ 标准库。
"""
import os
import re
import sys
import json
import time
import struct
import binascii
import pathlib
import datetime

import requests

# ---------------------------------------------------------------- 连接
DEFAULT_APP = os.environ.get(
    "FOOD_APP_DIR",
    "/Users/hubowen/Desktop/桌面 - 胡博文的MacBook Pro/china-travel-food/app",
)


def load_env(app_dir: str = DEFAULT_APP) -> dict:
    env = dict(os.environ)
    p = pathlib.Path(app_dir) / ".env.local"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = load_env()
BASE = ENV.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/") + "/rest/v1"
SERVICE = ENV.get("SUPABASE_SERVICE_ROLE_KEY", "")
ANON = ENV.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")


def headers(use_service: bool = True) -> dict:
    k = SERVICE if use_service else ANON
    if not k:
        sys.exit("缺少密钥：检查 app/.env.local 的 SUPABASE_SERVICE_ROLE_KEY / NEXT_PUBLIC_SUPABASE_ANON_KEY，或设 FOOD_APP_DIR")
    return {"apikey": k, "Authorization": f"Bearer {k}", "Content-Type": "application/json"}


def req(method: str, path: str, use_service: bool = True, retries: int = 6, **kw) -> requests.Response:
    """带指数退避的 HTTP；429/5xx 自动重试。"""
    url = BASE + path
    last = None
    for i in range(retries):
        try:
            r = requests.request(method, url, headers=headers(use_service), timeout=45, **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                last = r
                time.sleep(min(2 ** i, 15))
                continue
            return r
        except requests.RequestException as e:  # DNS/连接抖动
            last = e
            time.sleep(min(2 ** i, 15))
    raise RuntimeError(f"{method} {path} 连续失败: {last}")


def fetch_all(table: str, select: str = "*", page: int = 1000,
              use_service: bool = True, order_col: str = "id", extra: str = "") -> list:
    """分页拉全表（PostgREST 单页上限 1000）。restaurant_cuisines 用 order_col='restaurant_id'。"""
    out, off = [], 0
    while True:
        path = f"/{table}?select={select}&limit={page}&offset={off}&order={order_col}"
        if extra:
            path += "&" + extra
        r = req("GET", path, use_service=use_service)
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        out.extend(rows)
        if len(rows) < page:
            break
        off += page
        time.sleep(0.12)
    return out


# ---------------------------------------------------------------- 枚举 / 阈值
DISTRICTS = {
    "黄浦区", "徐汇区", "静安区", "长宁区", "浦东新区", "闵行区", "杨浦区",
    "虹口区", "普陀区", "嘉定区", "宝山区", "松江区", "青浦区", "奉贤区",
    "金山区", "崇明区",
}
TIERS = ["经济", "平价", "中档", "高档", "奢华"]
# 营业态统一口径（与库/前端现状对齐：active=营业中，closed=关店）。质量结论由 score_* 表达。
STATUS_OPEN = "active"
STATUS_CLOSED = "closed"
VALID_STATUS = {STATUS_OPEN, STATUS_CLOSED}
# 历史值 → 统一值的归一映射（推荐/备选/可试/保留 均为营业态，质量由分数体现）
STATUS_ALIAS = {
    "active": STATUS_OPEN, "推荐": STATUS_OPEN, "备选": STATUS_OPEN,
    "可试": STATUS_OPEN, "保留": STATUS_OPEN, "保留(已入库)": STATUS_OPEN,
    "营业": STATUS_OPEN, "open": STATUS_OPEN,
    "关店": STATUS_CLOSED, "closed": STATUS_CLOSED,
    "已闭店": STATUS_CLOSED, "停业": STATUS_CLOSED, "已关店": STATUS_CLOSED,
    "已停业": STATUS_CLOSED,
}
# 保鲜周期（天）：新店 / 高端 / 平价连锁
FRESH_DAYS_NEW, FRESH_DAYS_HIGH, FRESH_DAYS_MASS = 30, 180, 90

# 上海行政范围粗略包围盒（用于剔除明显错误坐标）
SH_BBOX = (120.80, 30.65, 122.20, 31.95)  # min_lng, min_lat, max_lng, max_lat


def tier_from_price(price) -> str:
    p = to_int(price)
    if p is None:
        return ""
    if p < 50:
        return "经济"
    if p < 100:
        return "平价"
    if p < 200:
        return "中档"
    if p < 500:
        return "高档"
    return "奢华"


# ---------------------------------------------------------------- 基础清洗
def to_int(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d+", str(v).replace(",", ""))
    return int(m.group()) if m else None


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
    # 繁体 / 日文兜底（OpenCC 多会转，重复映射无害）
    "葉": "叶", "長": "长", "岡": "冈", "見": "见", "鳥": "鸟", "陽": "阳",
    "師": "师", "島": "岛", "風": "风", "魚": "鱼", "貝": "贝", "華": "华",
    "雲": "云", "夢": "梦", "緣": "缘", "嶋": "岛", "鶴": "鹤", "鰻": "鳗",
    "鮑": "鲍", "鵝": "鹅", "鳩": "鸠", "鶉": "鹑", "檸": "柠", "藍": "蓝",
    "倉": "仓", "賓": "宾", "鈴": "铃", "蘭": "兰",
    "鹽": "盐", "醬": "酱", "滷": "卤", "燉": "炖", "燜": "焖", "饅": "馒",
    "饃": "馍", "餛": "馄", "飩": "饨", "餃": "饺", "糰": "团", "麵": "面",
    "銷": "销", "價": "价", "貴": "贵", "購": "购", "貨": "货", "國": "国",
    "慶": "庆", "龍": "龙", "橋": "桥", "頭": "头", "條": "条", "線": "线",
    "總": "总", "監": "监", "測": "测", "員": "员", "驗": "验", "證": "证",
    "碼": "码", "點": "点", "廣": "广", "腸": "肠", "賣": "卖", "鍋": "锅",
    "貼": "贴", "湯": "汤", "圓": "圆", "團": "团", "凍": "冻", "裡": "里",
    "裏": "里", "來": "来", "時": "时", "說": "说", "個": "个", "麼": "么",
    "麽": "么", "評": "评", "粵": "粤", "鮮": "鲜", "漿": "浆", "醃": "腌",
    "腦": "脑", "腳": "脚", "膽": "胆", "腎": "肾", "臟": "脏", "髒": "脏",
    "當": "当", "盤": "盘", "爾": "尔", "礙": "碍", "稅": "税", "窩": "窝",
    "筍": "笋", "節": "节", "約": "约", "紅": "红", "紙": "纸", "級": "级",
    "納": "纳", "細": "细", "終": "终", "結": "结", "絕": "绝", "經": "经",
    "統": "统", "絲": "丝", "鋼": "钢", "鐵": "铁", "針": "针", "鉛": "铅",
    "銘": "铭", "銳": "锐", "鋒": "锋", "鋪": "铺", "錦": "锦", "鍛": "锻",
    "鍾": "钟", "鍵": "键", "鎂": "镁", "鎊": "镑", "鎖": "锁", "鎘": "镉",
    "鎳": "镍", "鎬": "镐", "鎮": "镇", "鏈": "链", "鏡": "镜", "鏢": "镖",
    "鐮": "镰", "鐳": "镭", "鑄": "铸", "鑑": "鉴", "鑠": "铄", "鑣": "镳",
    "鑥": "镥", "鑪": "炉", "鑭": "镧", "鑰": "钥", "鑲": "镶", "鑷": "镊",
    "鑼": "锣", "鑽": "钻", "鑾": "銮", "飨": "飨", "鹌": "鹌", "鹧": "鹧",
    "鸪": "鸪", "鸵": "鸵", "鳳": "凤", "鳴": "鸣", "鴻": "鸿", "鵲": "鹊",
    "鶯": "莺", "鷗": "鸥", "鴿": "鸽", "鵬": "鹏", "獻": "献", "瑪": "玛",
    "瓊": "琼", "琺": "珐", "璽": "玺", "盧": "卢", "矯": "矫", "礦": "矿",
    "禱": "祷", "穀": "谷", "籃": "篮", "釘": "钉", "釣": "钓", "鈔": "钞",
    "鈕": "钮", "鉢": "钵", "鉗": "钳", "鉤": "钩", "鉸": "铰", "鉻": "铬",
    "鋅": "锌", "鋇": "钡", "鋤": "锄", "錘": "锤", "錐": "锥", "錠": "锭",
    "錨": "锚", "錚": "铮", "錳": "锰", "錶": "表", "鍍": "镀", "鍬": "锹",
    "鍶": "锶", "鍺": "锗", "鎔": "熔", "鎗": "枪", "鎛": "镈", "鎢": "钨",
    "鏜": "镗", "鏟": "铲", "鏤": "镂", "鐐": "镣", "鐓": "镦", "鑊": "镬",
    "鑌": "镔", "鑔": "镲", "鑞": "镴",
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


# 合法号码：400 / 全国座机（区号0xx，021+8位=11位数字，不能按"11位=手机"误判）/ 手机号
_RE_MOBILE = re.compile(r"1[3-9]\d{9}")
_RE_LAND = re.compile(r"0\d{2,3}-?\d{7,8}")
_RE_400 = re.compile(r"400[-\s]?\d{3}[-\s]?\d{4}")


# 公开测试/占位号（常被填进假数据），判为不可用
_TEST_NUMBERS = {"13800001380", "13800007777", "13800008888", "13800000000",
                 "10000000000", "12345678901"}


def _classify_number(seg: str):
    """从一段文本识别一个号码，返回纯数字或 None。座机优先（0 开头），避免座机被手机规则误判。"""
    t = seg.replace(" ", "").replace("-", "")
    d0 = re.sub(r"\D", "", t)
    if d0 in _TEST_NUMBERS:
        return None
    m = _RE_400.search(t)
    if m:
        return re.sub(r"\D", "", m.group())
    m = _RE_LAND.search(t)
    if m:
        return re.sub(r"\D", "", m.group())
    m = _RE_MOBILE.search(t)
    if m:
        return m.group()
    d = re.sub(r"\D", "", t)
    if re.fullmatch(r"1[3-9]\d{9}", d):
        return d
    if re.fullmatch(r"0\d{9,11}", d):  # 无分隔符座机：021+8=11 / 0571+7~8=11~12
        return d
    return None


def clean_phone(raw):
    """返回 (clean|None, issues[list], note)。宁空不假：解析不出合法号码就返回 None。
    issue 类型：phone_missing（无号码）/ phone_unparseable（有数字但非法，疑似造假）/
    phone_switchboard（总机/分机/转接，号码可拨但非直线，属警告）。
    脱敏 xx、纯转接描述 → 不作为可拨号码，原文迁入 note 给 booking_method。"""
    issues, note = [], ""
    if raw is None or str(raw).strip() == "":
        return None, ["phone_missing"], note
    s = str(raw).strip()
    switchboard = bool(re.search(r"转接|总机|前台|分机", s))
    masked = bool(re.search(r"[xX*]{2,}|脱敏", s))
    if switchboard or masked:
        note = s
    # 只按多号分隔符拆；号码内部空格/短横（如 139 1234 5678、021 6333 9066）交给 _classify 归一
    parts = re.split(r"[/／、,，;；]+", re.sub(r"[()（）]", " ", s))
    found = []
    for seg in parts:
        if not seg.strip():
            continue
        cand = _classify_number(seg)
        if cand:
            found.append(cand)
    seen, uniq = set(), []
    for x in found:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    if not uniq:
        if re.search(r"\d", s):
            issues.append("phone_unparseable")
        else:
            issues.append("phone_missing")
        return None, issues, note
    if switchboard:
        issues.append("phone_switchboard")
    return " / ".join(uniq), issues, note


def dishes_list(v):
    """招牌菜统一为去重后的 list[str]；兼容 jsonb 数组 / 顿号逗号分隔字符串。"""
    if v is None:
        return []
    if isinstance(v, list):
        items = [str(x).strip() for x in v]
    else:
        items = re.split(r"[、,，/；;]", str(v))
    out, seen = [], set()
    for x in items:
        x = x.strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def in_shanghai(lng, lat) -> bool:
    try:
        lng, lat = float(lng), float(lat)
    except (TypeError, ValueError):
        return False
    x0, y0, x1, y1 = SH_BBOX
    return x0 <= lng <= x1 and y0 <= lat <= y1


def point_geojson(lng, lat):
    """GeoJSON Point（导出/前端用），坐标顺序 [经度, 纬度]。"""
    return {"type": "Point", "coordinates": [round(float(lng), 6), round(float(lat), 6)]}


def point_ewkt(lng, lat):
    """location 列**写入**格式：实测本库只接受 EWKT 字符串（GeoJSON 对象 PATCH 会 500）。
    PostGIS 坐标顺序 POINT(经度 纬度)，SRID=4326。写中文/非 Point 文本必 500。"""
    return f"SRID=4326;POINT({round(float(lng), 6)} {round(float(lat), 6)})"


_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_WKT_RE = re.compile(r"POINT\s*\(\s*([-+]?\d[\d.]*)[\s,]+([-+]?\d[\d.]*)\s*\)", re.I)


def _parse_ewkb_hex(h: str):
    """解析 PostGIS geography 经 REST 默认返回的 EWKB hex，返回 (lng,lat)。"""
    b = binascii.unhexlify(h)
    en = "<" if b[0] == 1 else ">"
    gtype = struct.unpack_from(en + "I", b, 1)[0]
    off = 5
    if gtype & 0x20000000:  # 带 SRID
        off += 4
    x, y = struct.unpack_from(en + "dd", b, off)  # lng, lat
    return float(x), float(y)


def parse_location(loc):
    """读取 location，返回 (lng,lat) 或 None。兼容：EWKB hex（REST 默认）/ EWKT、WKT 字符串 /
    GeoJSON Point / {lng,lat} / [lng,lat]。"""
    if not loc:
        return None
    try:
        if isinstance(loc, dict):
            if loc.get("type") == "Point" and loc.get("coordinates"):
                return float(loc["coordinates"][0]), float(loc["coordinates"][1])
            lng = loc.get("lng") or loc.get("lon") or loc.get("longitude")
            lat = loc.get("lat") or loc.get("latitude")
            if lng is not None and lat is not None:
                return float(lng), float(lat)
        if isinstance(loc, (list, tuple)) and len(loc) >= 2:
            return float(loc[0]), float(loc[1])
        if isinstance(loc, str):
            s = loc.strip()
            if _HEX_RE.match(s) and len(s) >= 18:
                try:
                    return _parse_ewkb_hex(s)
                except (struct.error, binascii.Error, ValueError):
                    pass
            m = _WKT_RE.search(s)
            if m:
                return float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError, IndexError):
        return None
    return None


def today() -> str:
    return datetime.date.today().isoformat()


def read_jsonl(path: str) -> list:
    rows = []
    p = pathlib.Path(path)
    if not p.exists():
        sys.exit(f"找不到输入文件: {path}")
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            sys.exit(f"第 {i} 行不是合法 JSON: {e}")
    return rows


def write_jsonl(path: str, rows: list):
    pathlib.Path(path).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


# 空话 / 软广话术信号（命中且无具体菜品名 = 不算堂食证据）
EMPTY_HYPE = ["绝绝子", "天花板", "必吃", "yyds", "YYDS", "封神", "宝藏", "不踩雷", "闭眼冲", "巨好吃", "超好吃"]


def quote_has_substance(quote: str) -> bool:
    """一条食客点评是否'有实物证据'：含具体菜品/做法/食材词，而非纯情绪词。"""
    q = quote or ""
    if len(q) < 8:
        return False
    hype = sum(1 for w in EMPTY_HYPE if w in q)
    # 含具体名词信号：菜/肉/面/饭/汤/烤/煎/炖/酱汁/口感词，或出现引号菜名
    concrete = re.search(
        r"[菜肉面饭汤粉粿饺包饼锅烤煎炖煮蒸炒拌烧腊鱼虾蟹牛羊鸡猪鸭鹅鹅肝和牛意面披萨咖喱寿司拉面糕蛋茶酒奶果串丸肠饮糖饼]"
        r"|口感|火候|调味|嫩|脆|鲜|入口|层次|甜点|甜品|蛋糕|咖啡|调酒|鸡尾酒|精酿|手冲|风味|烘焙|面包|可颂|贝果|巴斯克|提拉米苏|奶咖|拿铁|美式|气泡|发酵",
        q)
    return concrete is not None or (len(q) >= 25 and hype <= 1)


# ---------------------------------------------------------------- 来源性质分类
# 治"媒体/官方/榜单通稿冒充食客堂食点评"。按来源文本+URL 域名确定性判定，不信模型自填 type。
_UGC_SRC = [
    "xiaohongshu.com", "xhslink", "小红书", "dianping.com", "大众点评",
    "douyin.com", "iesdouyin", "抖音", "ctrip.com", "携程", "mafengwo.cn", "马蜂窝",
    "qyer.com", "穷游", "zhihu.com", "知乎", "douban.com", "豆瓣", "weibo.com", "微博",
    "bilibili.com", "b站", "tripadvisor", "trip.com", "google.com/maps", "maps.google", "谷歌地图",
]
_GUIDE_SRC = ["guide.michelin", "michelin", "米其林", "blackpearl", "黑珍珠",
              "theworlds50best", "50best", "asias50best", "gaultmillau"]
_MAP_SRC = ["amap.com", "高德", "map.baidu", "baidu.com/map", "百度地图", "lbs.qq",
            "腾讯地图", "电话邦", "dianbo", "qcc.com", "企查查", "tianyancha", "天眼查",
            "city8", "城市吧", "本地宝", "bendibao"]
_MEDIA_SRC = [
    "news.cn", "新华网", "thepaper", "澎湃", "whb.cn", "文汇", "jfdaily", "上观",
    "people.cn", "人民网", "timeout", "smartshanghai", "nomfluence", "thatsmags",
    "eater.com", "sohu.com", "163.com", "sina.com", "sina.cn", "jiemian", "界面",
    "toutiao", "头条", "网易", "新浪", "chinanews", "中新网", "huanqiu", "guancha",
    "36kr", "qq.com/",
]
_BRAND_HINT = ["官方", "官网", "小程序", "品牌", "集团", "旗舰店", "official",
               "brand", "连锁", "总部", "公司"]


def source_kind(text="", url="") -> str:
    """返回 ugc / official_guide / map / media / brand / other。
    个人微信公众号(mp.weixin)的美食探店写作按 ugc；机构/品牌/媒体号按 brand/media。"""
    t = (str(text) + " " + str(url)).lower()
    if any(k.lower() in t for k in _UGC_SRC):
        return "ugc"
    if any(k.lower() in t for k in _GUIDE_SRC):
        return "official_guide"
    if any(k.lower() in t for k in _MAP_SRC):
        return "map"
    if "mp.weixin.qq.com" in t:
        if any(k.lower() in t for k in ["官方", "集团", "品牌", "传媒", "新闻", "日报", "周刊", "融媒体", "公众号"]):
            return "brand"
        return "ugc"
    if any(k.lower() in t for k in _MEDIA_SRC):
        return "media"
    if any(k.lower() in t for k in _BRAND_HINT):
        return "brand"
    return "other"
