#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_amap_fill.py — 高德 POI 全字段采集（一次 place/text 补多字段）。

为什么取代 cloud_review_fill：
  高德 place/text extensions=all 的同一条响应里同时含
  biz_ext.rating（聚合评分）、biz_ext.cost（人均）、tel（电话）、
  biz_ext.opentime2/open_time（营业时间）、location（坐标）、keytag（菜系标签）。
  一次调用补全所有缺字段，配额最省（日 5000，约一天可覆盖全库）。

铁律：
  - 高德 Web 服务只需 key，**不带 sig**（sig 是腾讯概念；多余 sig 虽多被忽略，一律不加）。
  - 只补"空字段"，绝不覆盖已有非空值（保护人工/权威数据）。
  - 电话必须过 clean_phone；坐标必须 in_shanghai；宁空不假、绝不用错分店号码
    （pick_best 以店名 0.6 + 地址 0.4 高阈值锁定同一家，外地同名店直接排除）。
  - 评分 → reviews 表（幂等，source_platform=高德地图）；其余字段 → restaurants。
  - keytag/tag 仅入缓存作线索，不自动改菜系分类（分类走专门引擎，避免误改）。

模式：
  默认 dry-run：只采集 + 写缓存 + 打印每店将写入的 patch，不写库。
  --apply    ：真正写库。
  --limit N  ：本轮最多"新调用"N 家（默认 100）。
"""
import json
import os
import pathlib
import re
import sys
import time
from difflib import SequenceMatcher
from urllib.parse import quote

import requests

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import common as C          # noqa: E402
import map_helpers as M     # noqa: E402  仅复用 pick_best/cjk_sim/addr_core_sim
import health               # noqa: E402

STATE_F = pathlib.Path(DATA) / "_amap_fill_state.json"
CACHE_F = pathlib.Path(DATA) / "amap_poi_cache.jsonl"
STATS_F = pathlib.Path(DATA) / "fill_stats.json"

AMAP_KEY = os.environ.get("AMAP_KEY", "").strip()
AMAP_BASE = "https://restapi.amap.com"
AMAP_DAILY_QUOTA = int(os.environ.get("AMAP_DAILY_QUOTA", "5000"))


# ------------------------------------------------------------ 工具
def _to_float(v):
    if v is None or v == "" or v == "[]":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _read_state():
    try:
        return json.loads(STATE_F.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(st):
    STATE_F.parent.mkdir(parents=True, exist_ok=True)
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_cache():
    """返回 {rid: {"date":..., "poi":...}}。"""
    out = {}
    if CACHE_F.exists():
        for line in CACHE_F.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                out[row["rid"]] = {"date": row.get("date", ""), "poi": row.get("poi", {})}
            except (json.JSONDecodeError, KeyError):
                continue
    return out


def _append_cache(rid, poi):
    CACHE_F.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_F.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"rid": rid, "date": C.today(), "poi": poi},
                           ensure_ascii=False) + "\n")


# ------------------------------------------------------------ 高德请求（无 sig）
def _parse_poi(p):
    loc = p.get("location", "")
    lng = lat = None
    if loc and loc != "[]":
        parts = loc.split(",")
        try:
            lng, lat = float(parts[0]), float(parts[1])
        except (ValueError, IndexError):
            pass
    biz = p.get("biz_ext") or {}
    hours = biz.get("opentime2") or biz.get("open_time") or ""
    if hours == "[]":
        hours = ""
    return {
        "poi_id": p.get("id", ""),
        "title": p.get("name", "") or "",
        "address": p.get("address", "") or "",
        "tel": (p.get("tel", "") or ""),
        "lng": lng,
        "lat": lat,
        "rating": _to_float(biz.get("rating")),
        "cost": _to_float(biz.get("cost")),
        "hours": hours,
        "keytag": p.get("keytag", "") or "",
        "tag": p.get("tag", "") or "",
        "typecode": p.get("typecode", "") or "",
        "biz_type": p.get("biz_type", "") or "",
    }


# —— 判定以高德 keytag 语义为主、typecode 为辅（实测酒吧=080304、部分蛋糕=0803xx，
#    大类前缀会误杀，故不硬编码大类；typecode 仅保留作线索）。
# 明确非餐饮（keytag 命中即排除，优先级最高）
_NON_DINING_KT = ["地名地址信息", "热点地名", "住宅区", "住宅", "商圈", "公园", "绿地",
                  "滨江", "交通", "车站", "机场", "码头", "美甲", "美睫", "美容", "美发",
                  "按摩", "足浴", "酒店", "宾馆", "旅馆", "住宿", "学校", "学院", "幼儿园",
                  "培训", "医院", "诊所", "药店", "银行", "保险", "公司", "企业", "写字楼",
                  "政府", "机关", "法院", "加油", "停车", "商场", "超市", "便利店", "服装",
                  "百货", "建材", "家具", "数码", "眼镜", "珠宝", "花店", "宠物", "洗衣",
                  "快递", "地产", "楼盘", "景区", "景点", "市场"]
# 明确餐饮（keytag 命中即接受）
_DINING_KT = ["料理", "餐厅", "中餐", "西餐", "快餐", "咖啡", "面包", "烘焙", "糕点",
              "蛋糕", "西点", "甜品", "甜点", "茶饮", "奶茶", "茶叶", "茶艺", "茶馆",
              "茶楼", "茶空间", "酒吧", "清吧", "酒馆", "酒场", "居酒屋", "饮品",
              "冷热饮", "冰淇淋", "冰激凌", "烧烤", "烤肉", "火锅", "面馆", "小吃",
              "熟食", "豆制品", "饮食", "餐饮", "菜"]
# tag 里的强餐饮词（keytag 未明确时兜底）
_STRONG_FOOD = ["料理", "咖啡", "面包", "烘焙", "蛋糕", "甜品", "甜点", "酒吧", "清吧",
                "火锅", "烧烤", "餐厅", "奶茶", "茶饮", "糕点", "冰淇淋", "烤肉", "寿司",
                "拉面", "咖喱", "海鲜"]


def is_dining_poi(poi):
    """只接受餐饮类 POI；硬排除地名/住宅/美甲/住宿/购物等（治'北外滩'地名错配）。"""
    kt = poi.get("keytag") or ""
    tg = poi.get("tag") or ""
    tc = poi.get("typecode") or ""
    biz = poi.get("biz_type") or ""
    if any(k in kt for k in _NON_DINING_KT):
        return False
    if biz == "diner":
        return True
    if any(w in kt.lower() for w in [x.lower() for x in _DINING_KT]):
        return True
    hay_all = (kt + " " + tg + " " + (poi.get("title") or "")).lower()
    if any(w in hay_all for w in _STRONG_FOOD):
        return True
    if tc.startswith("05") or tc.startswith("0803"):
        return True
    return False


def amap_text(name, offset=8):
    """place/text extensions=all，返回 [餐饮poi...] / [] / 'QUOTA'。不带 sig。
    限流感知：status!=1（QPS/并发超限）指数退避重试；status=1 空 pois 重试 1 次防限流空响应。"""
    if not AMAP_KEY:
        return []
    params = {
        "keywords": name, "city": "上海", "citylimit": "true",
        "offset": offset, "extensions": "all", "key": AMAP_KEY,
    }
    qs = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    url = f"{AMAP_BASE}/v3/place/text?{qs}"
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=15)
            j = r.json()
        except Exception as e:
            print(f"  [高德异常] {e}", file=sys.stderr)
            time.sleep(1.2 * (attempt + 1))
            continue
        code = j.get("infocode")
        if code == "10003":          # 日配额耗尽，立即终止
            return "QUOTA"
        if j.get("status") == "1":
            raw = j.get("pois", [])
            if not raw and attempt < 1:    # 空结果可能是限流，重试 1 次
                time.sleep(1.2)
                continue
            return [_parse_poi(p) for p in raw]
        # status!=1：QPS/并发/瞬时错误，退避重试
        time.sleep(1.2 * (attempt + 1))
    return []


# ------------------------------------------------------------ 增强匹配引擎
CHEF_HINT = ["师傅", "主厨", "主理"]
# cjk_unify 未覆盖的日文异体 / 同义词（本地匹配层补，不改 skill 的 common）
_LOCAL_VAR = {"晩": "晚", "壱": "壹", "弐": "贰", "斉": "齐", "藤": "藤"}


def split_name(s):
    """拆 '主名' + [括号内容...]（库名括号常是主厨注释，高德括号是分店名）。"""
    s = s or ""
    brackets = re.findall(r"[（(]([^（）()]*)[）)]", s)
    main = re.sub(r"[（(][^（）()]*[）)]", "", s)
    return main.strip(), brackets


def core_norm(s):
    """主名归一：CJK 统一 + 本地异体 + 同义词 + 去标点。"""
    s = C.cjk_unify(s)
    for k, v in _LOCAL_VAR.items():
        s = s.replace(k, v)
    s = s.lower().replace("ramen", "拉面")
    return re.sub(r"[\s·・•\-—_–'‘’\"“”`（）()【】\[\]&]+", "", s)


# 商场 / 地标词：库地址只写到地标（"中山公园龙之梦"）时，用地标做锚点
LANDMARKS = ["龙之梦", "恒隆", "来福士", "大悦城", "环宇城", "太古汇", "太古里",
             "新天地", "国金", "环贸", "万象城", "印象城", "万达", "百联", "世纪汇",
             "港汇", "正大", "嘉里中心", "前滩太古里", "晶耀", "世博天地", "今潮8弄",
             "丰盛里", "合生汇", "领展", "万科", "K11", "IAPM", "IFC", "BFC",
             "恒基", "保利", "静安寺", "中山公园"]


def concrete_addr(addr):
    """库地址是否可定位：路/街/道 + 号/弄，或含明确地标。"""
    core = C.addr_core(addr)
    if re.search(r"(路|街|道|村)", core) and re.search(r"\d", core):
        return True
    return any(lm in (addr or "") for lm in LANDMARKS)


def landmark_hit(db_addr, c):
    for lm in LANDMARKS:
        if lm in (db_addr or "") and lm in (c.get("address", "") + c.get("title", "")):
            return 0.9
    return 0.0


_DISTRICT_PREFIX = ["浦东新区", "黄浦", "徐汇", "长宁", "静安", "虹口", "杨浦", "普陀",
                    "闵行", "宝山", "嘉定", "松江", "青浦", "奉贤", "金山", "崇明", "浦东"]


def road_number(addr):
    """返回 (门牌号紧邻的路名, 号段数字)。
    先去开头行政区；枚举所有路名，对每个门牌号取其前方、间隙≤4且不跨越路名的最近路名。
    治'江苏路街道凯旋路1398'→凯旋路（而非江苏路街道凯旋路）。"""
    s = str(addr or "")
    for d in sorted(_DISTRICT_PREFIX, key=len, reverse=True):
        if s.startswith(d):
            s = s[len(d):]
            if s.startswith("区"):
                s = s[1:]
            break
    road_spans = [(m.start(), m.end(), m.group(1)) for m in
                  re.finditer(r"([\u4e00-\u9fa5A-Za-z0-9]{1,12}?[路街道])", s)]
    road, nums = "", []
    for m in re.finditer(r"(\d[\d\-~至]*)", s):
        pos = m.start()
        for rs, re_, rn in reversed(road_spans):
            gap = s[re_:pos]
            if re_ <= pos and len(gap) <= 4 and not re.search(r"[路街道\d]", gap):
                road = rn
                nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
                break
    return road, nums


def addr_anchor(db_addr, c_addr):
    """强同址判定，返回 (confirmed, score)。
    同路名（归一）且 门牌号交集 / 号段范围重叠 / 原始 sim≥0.8 → confirmed，score≥0.9；
    路名不同（错分店，如广元西路 vs 耀体路）→ 不确认，给原始 sim。"""
    sim = M.addr_core_sim(db_addr, c_addr)
    ra, na = road_number(db_addr)
    rb, nb = road_number(c_addr)
    if not ra or not rb or C.cjk_norm(ra) != C.cjk_norm(rb):
        return False, sim
    if set(na) & set(nb):
        return True, max(sim, 0.95)
    if na and nb:
        if not (max(na) < min(nb) or max(nb) < min(na)):   # 号段范围重叠
            return True, max(sim, 0.9)
    if sim >= 0.8:
        return True, max(sim, 0.9)
    return False, sim


def match_poi(cands, db_name, db_address):
    """地址锚定优先，返回 (poi, score)。
    - 库有具体地址/地标，或库名锁分店：候选必须地址/分店/地标一致（confirm≥0.9），
      主名基本相似即可，业态过滤可被地址佐证放宽（高德常把餐厅归到生活服务）；
    - 库只有泛区域地址（"古北地区"）：靠主名 + 业态，候选更泛的品牌一律不采。
    地名/热点地名永远排除。"""
    if not cands:
        return None, 0.0
    db_main, db_brackets = split_name(db_name)
    dbn = core_norm(db_main)
    db_branch = [core_norm(b) for b in db_brackets if not any(h in b for h in CHEF_HINT)]
    locked = concrete_addr(db_address) or len(db_branch) > 0
    best, bs = None, -1.0

    for c in cands:
        kt = c.get("keytag", "")
        if any(k in kt for k in ["地名地址信息", "热点地名"]):
            continue
        c_main, c_brackets = split_name(c.get("title", ""))
        cn = core_norm(c_main)
        if not dbn or not cn:
            continue
        ratio = SequenceMatcher(None, dbn, cn).ratio()
        db_in_c, c_in_db = dbn in cn, cn in dbn
        if db_in_c or c_in_db:
            ratio = max(ratio, 0.9)
        _addr_ok, addr_s = addr_anchor(db_address, c.get("address", ""))
        branch_s = 0.0
        for cb in c_brackets:
            cbn = core_norm(cb)
            for dbb in db_branch:
                if dbb and cbn and (dbb in cbn or cbn in dbb):
                    branch_s = 0.95
        confirm = max(addr_s, branch_s, landmark_hit(db_address, c))

        if locked:
            # 地址/分店/地标必须一致；强确认(号交集0.95)时店名语序差异可放宽 ratio
            if confirm < 0.9:
                continue
            rmin = 0.4 if confirm >= 0.95 else 0.55
            if ratio < rmin:
                continue
            score = 0.45 * ratio + 0.55 * confirm
        else:
            # 泛地址：必须是餐饮业态，靠主名；更泛品牌（c_in_db）不采
            if not is_dining_poi(c):
                continue
            if db_in_c and ratio >= 0.82:
                score = 0.8 * ratio
            elif ratio >= 0.9:
                score = ratio
            else:
                continue
        if score > bs:
            best, bs = c, score
    return best, bs


# ------------------------------------------------------------ 评分 → reviews
def rating_to_taste(r):
    if r >= 4.5:
        return 5
    if r >= 4.0:
        return 4
    if r >= 3.0:
        return 3
    if r >= 2.0:
        return 2
    return 1


def review_exists(rid):
    q = f"/reviews?restaurant_id=eq.{rid}&source_platform=eq.{quote('高德地图')}&select=id"
    r = C.req("GET", q)
    return r.status_code == 200 and len(r.json()) > 0


def write_review(rid, poi):
    rating = poi["rating"]
    poi_url = f"https://www.amap.com/detail/{poi['poi_id']}" if poi.get("poi_id") else ""
    payload = {
        "restaurant_id": rid,
        "author_name": "高德地图用户",
        "source_platform": "高德地图",
        "source_url": poi_url,
        "content": f"高德地图聚合食客评分 {rating}/5.0",
        "review_kind": "diner",
        "is_verified_diner": False,
        "trust_level": "low",
        "aspect_taste": rating_to_taste(rating),
        "aspect_json": {"amap_rating": rating, "source": "amap_biz_ext"},
        "is_fake_suspect": False,
        "is_hidden": False,
    }
    h = dict(C.headers())
    h["Prefer"] = "return=representation"
    r = requests.post(C.BASE + "/reviews", headers=h, json=payload, timeout=30)
    return r.status_code in (200, 201)


# ------------------------------------------------------------ 计算 patch（只补空）
def build_patch(rest, poi):
    """根据库内现状与高德 POI，返回 (patch, actions[list], will_review:bool)。"""
    patch, actions = {}, []

    # 人均（tier 由 DB 触发器按 price_avg 自动算）
    if rest.get("price_avg") is None and poi.get("cost"):
        patch["price_avg"] = int(poi["cost"])
        actions.append(f"人均={patch['price_avg']}")

    # 电话（过 clean_phone）
    if not (rest.get("phone") or "").strip() and poi.get("tel"):
        clean, _issues, _note = C.clean_phone(poi["tel"])
        if clean:
            patch["phone"] = clean
            actions.append(f"电话={clean}")

    # 营业时间
    if rest.get("opening_hours") is None and poi.get("hours"):
        patch["opening_hours"] = {"raw": poi["hours"]}
        actions.append("营业时间")

    # 坐标（仅当为空且在上海）
    if rest.get("location") is None and poi.get("lng") is not None and poi.get("lat") is not None:
        if C.in_shanghai(poi["lng"], poi["lat"]):
            patch["location"] = C.point_ewkt(poi["lng"], poi["lat"])
            actions.append("坐标")

    # 评分 → reviews（单独处理）
    will_review = bool(poi.get("rating")) and not review_exists(rest["id"])
    if will_review:
        actions.append(f"评分={poi['rating']}")

    return patch, actions, will_review


def _apply_patch(rid, patch):
    r = requests.patch(C.BASE + f"/restaurants?id=eq.{rid}",
                       headers=C.headers(), json=patch, timeout=30)
    return r.status_code in (200, 204)


# ------------------------------------------------------------ 主流程
def main():
    apply = "--apply" in sys.argv
    limit = 100
    if "--limit" in sys.argv:
        i = sys.argv.index("--limit")
        limit = int(sys.argv[i + 1])

    if not AMAP_KEY:
        print("AMAP_KEY 未配置，高德采集跳过（在 deploy.env 配置 AMAP_KEY 后自动生效）。")
        return 0

    today = C.today()
    state = _read_state()
    if state.get("quota_date") != today:
        state = {"quota_date": today, "amap_used": state.get("amap_used", 0) if False else 0}
    cache = _load_cache()

    # 拉全部营业店（含判定缺失所需字段）
    rows = C.fetch_all(
        "restaurants",
        "id,name,address,phone,price_avg,opening_hours,location,review_count",
        extra="status=eq.active", order_col="id",
    )

    def missing_count(r):
        n = 0
        if not (r.get("review_count") or 0):
            n += 1
        if not (r.get("phone") or "").strip():
            n += 1
        if r.get("price_avg") is None:
            n += 1
        if r.get("opening_hours") is None:
            n += 1
        if r.get("location") is None:
            n += 1
        return n

    # 缺字段越多越优先；当天已缓存的不重新调用
    rows = [r for r in rows if missing_count(r) > 0]
    rows.sort(key=lambda r: (-missing_count(r), r["id"]))

    stats = {"candidates": len(rows), "called": 0, "from_cache": 0,
             "fields": 0, "reviews": 0, "no_match": 0, "quota_stopped": False}

    def call_amap(kw):
        c = amap_text(kw)
        state["amap_used"] = state.get("amap_used", 0) + 1
        stats["called"] += 1
        return c

    def resolve(name, addr):
        """主搜 → match_poi → 三级降级模糊召回；返回 (poi|None, quota_bool)。"""
        c = call_amap(name)
        if c == "QUOTA":
            return None, True
        poi, _s = match_poi(c, name, addr)
        if poi:
            return poi, False
        db_main, _ = split_name(name)
        zh_full = re.sub(r"[぀-ゟ゠-ヿー·・]+", "", db_main).strip()
        tries = []
        if db_main.strip() != name:
            tries.append(db_main.strip())
        if zh_full and zh_full != db_main.strip():
            tries.append(zh_full)
        zh_only = re.sub(r"[^\u4e00-\u9fa5]", "", db_main)
        if len(zh_only) >= 4:
            tries.append(zh_only[-2:])
        for t in dict.fromkeys(tries):
            if stats["called"] >= limit or state.get("amap_used", 0) >= AMAP_DAILY_QUOTA:
                return None, False
            c2 = call_amap(t)
            if c2 == "QUOTA":
                return None, True
            p2, _s = match_poi(c2, name, addr)
            if p2:
                return p2, False
            time.sleep(0.3)
        return None, False

    for rest in rows:
        rid = rest["id"]
        name, addr = rest["name"], rest.get("address", "") or ""

        # ① 取 POI：当天缓存优先，否则主搜+降级
        cached = cache.get(rid)
        if cached and cached.get("date") == today and cached.get("poi"):
            poi = cached["poi"]
            stats["from_cache"] += 1
        else:
            if stats["called"] >= limit or state.get("amap_used", 0) >= AMAP_DAILY_QUOTA:
                break
            poi, quota = resolve(name, addr)
            if quota:
                stats["quota_stopped"] = True
                health.alert("高德日配额耗尽，全字段采集暂停至明天。",
                             title="上海美食图鉴·配额告警", key="amap_quota")
                break
            if not poi:
                stats["no_match"] += 1
                time.sleep(0.3)
                continue
            _append_cache(rid, poi)
            time.sleep(0.4)

        # ② 计算将写入的内容
        patch, actions, will_review = build_patch(rest, poi)
        if not actions:
            continue

        if apply:
            ok = True
            if patch:
                ok = _apply_patch(rid, patch)
            if ok and will_review:
                if write_review(rid, poi):
                    stats["reviews"] += 1
            if ok:
                stats["fields"] += len(patch)
        else:
            stats["fields"] += len(patch)
            if will_review:
                stats["reviews"] += 1
        print(f"  [{rid}] {name} → {'; '.join(actions)}"
              f"{'' if apply else '  (dry-run)'}")

    _write_state(state)

    try:
        existing = json.loads(STATS_F.read_text(encoding="utf-8"))
    except Exception:
        existing = {}
    existing["amap_fill"] = {"last_run": time.strftime("%Y-%m-%d %H:%M:%S"),
                             "mode": "apply" if apply else "dry-run", **stats,
                             "amap_used": state.get("amap_used", 0)}
    STATS_F.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 高德全字段采集本轮统计 ===")
    print(f"  模式: {'APPLY' if apply else 'DRY-RUN'}  待补候选: {stats['candidates']}")
    print(f"  新调用: {stats['called']}  用缓存: {stats['from_cache']}  "
          f"未匹配: {stats['no_match']}")
    print(f"  回填字段: {stats['fields']}  评分评价: {stats['reviews']}  "
          f"高德已用: {state.get('amap_used', 0)}/{AMAP_DAILY_QUOTA}")
    if stats["quota_stopped"]:
        print("  ⚠ 配额超限，本轮提前终止")
    return 0


if __name__ == "__main__":
    sys.exit(main())
