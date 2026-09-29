#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""discovery_engine.py — 自驱动「图遍历」开放式发现引擎。

解决 social_discovery 的根本缺陷：只跑一张固定静态词表，不会从已捞笔记 / 评论区自动
发现新店名并继续追查，也不会判饱和。本引擎实现 systematic-sourcing 的"种子图遍历"：

    种子发现词（discovery_keywords）
        → 搜 + 开笔记 + 读评论
        → 提取【新店名】（合集结构化锚点 / 品牌词典 / 评论"真正好吃的是XX" / 未知专名）
        → 新店名自动入 frontier，下一轮按店名取证（图扩展）
        → 直到 frontier 清空（饱和）或连续 STALL 个查询零库外新品牌（提前收敛）

职责边界：
  - 本引擎在浏览器内，只做"采集 + 发现 + 饱和判断"，产出 raw_discovery.jsonl
    （kind=discover，admission_gate 可直接读）+ oral_mentions.jsonl（低置信口述）。
  - 口味 / 独立声音 / admit 裁决交给离线的 admission_gate；
  - admit 库外新店的取证 + 写库交给 cloud_discover 编排。

在 mac_computer_use_tool(plane="bu") cell 或云端 cloud_bu.CloudBrowser 上运行：
    import sys; sys.path.insert(0, PIPE)
    from discovery_engine import DiscoveryEngine
    eng = DiscoveryEngine(bu, "sichuan", work_dir)
    print(eng.run(max_queries=8))
"""
import json
import pathlib
import re
import sys
from collections import defaultdict

try:
    import common as C
    import social_discovery as D
    import admission_gate as G
    import discovery_keywords as K
    try:
        from semantic_wordnet import build_wordnet as _build_wn
    except Exception:
        _build_wn = None
except Exception:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import common as C
    import social_discovery as D
    import admission_gate as G
    import discovery_keywords as K
    try:
        from semantic_wordnet import build_wordnet as _build_wn
    except Exception:
        _build_wn = None


def _seed_queries(category, dense=False):
    """1B-5 词网接线：优先 semantic_wordnet 四维词网，异常/空则回退 discovery_keywords 模板。
    确定性、幂等；词网为空或报错不得影响既有采集。"""
    if _build_wn:
        try:
            q = _build_wn(category, dense=dense)
            if q:
                return list(q)
        except Exception:
            pass
    return K.build_queries(category, dense=dense)

# 评论区 / 正文"明确推荐另一家"的口述店名模式（捕获店名片段）
RE_REC = [
    re.compile(r"真正好?吃的?(?:还得是|是|得去)?\s*([一-龥A-Za-z0-9'&·]{2,14})"),
    re.compile(r"(?:推荐|安利|种草)(?:大家)?(?:一家|个|去)?\s*([一-龥A-Za-z0-9'&·]{2,14})"),
    re.compile(r"另(?:一家|外一家|家)\s*([一-龥A-Za-z0-9'&·]{2,14})"),
    re.compile(r"(?:不如|比不上|秒杀|吊打)(?:去)?\s*([一-龥A-Za-z0-9'&·]{2,14})"),
    re.compile(r"(?:本地人|老饕|懂吃)(?:都|只|一般去)?\s*去?\s*([一-龥A-Za-z0-9'&·]{2,14})"),
]
# 店名片段尾部：语气词 / 夸赞词 / 连接字（连续剥除，直到露出店名/店铺后缀）
TAIL_PARTICLE = set("超很挺正赞绝棒哦呀啊吧呢嘛的了啦哟噢喔嘞太最是也就还在和跟真")
# 明显不是店名的开头 / 通用词
STOP_HEAD = set("这那个一好吃买的我你他她它啥甚很太真假些每此本该大家谁啥怎哪如何么")
GENERIC_WORDS = {
    "面包", "面包店", "咖啡", "咖啡店", "咖啡馆", "甜品", "甜点", "蛋糕", "酒吧", "清吧",
    "寿司", "拉面", "烧鸟", "烧肉", "居酒屋", "天妇罗", "怀石", "咖喱", "川菜", "四川菜",
    "粤菜", "苏菜", "鲁菜", "浙菜", "闽菜", "湘菜", "徽菜", "本帮菜", "上海菜", "京菜",
    "泰餐", "越南菜", "韩餐", "火锅", "私房菜", "私宴", "茶馆", "茶室", "大家", "指数",
    "一下", "什么", "怎么", "这家店", "那家店", "店铺", "餐厅", "饭店", "好吃的", "美食",
}
# 像"店铺"的后缀（中文未知店名，单次出现也可考虑）
SHOP_SUFFIX = ("店", "馆", "坊", "屋", "舍", "堂", "楼", "轩", "居", "室", "铺", "面包",
               "烘焙", "菓子", "果子", "料理")

# 【质量监管】非美食领域关键词黑名单：包含这些词的锚点一律不当作美食品牌/店名，
# 防止房产/政策/金融等内容污染 frontier（曾导致"架空地板""初创社保补贴"等词进入拉面采集）。
NON_FOOD_KEYWORDS = (
    # 房产/建筑/装修
    "开发商", "楼盘", "房价", "户型", "物业", "小区", "公寓", "别墅", "写字楼", "商铺",
    "厂房", "仓库", "土地", "征地", "拆迁", "装修", "建材", "地板", "空调", "车位",
    "电梯", "层高", "采光", "通风", "架空", "配套", "租金", "临港", "浦东", "静安",
    "徐汇", "虹口", "杨浦", "闵行", "松江", "青浦", "嘉定", "宝山", "奉贤", "金山",
    "崇明", "黄浦", "长宁", "普陀", "闸北",
    # 政策/补贴/金融/政务
    "补贴", "政策", "社保", "税费", "减免", "就业", "创业", "高新", "专精特新", "研发",
    "加计扣除", "招投标", "融资", "背书", "证书", "奖励", "申领", "材料", "避坑",
    "高企", "高成长", "带动就业", "初创", "个体户", "高校", "能级", "核定",
    "投资", "免责声明", "翻车", "高频", "盖章", "品牌盖章", "真高企", "伪高企",
    "促进中心", "就业促进", "社保补贴", "税费减免", "高企证书", "研发费用",
    # 招聘/教育/法律
    "招聘", "求职", "工资", "薪资", "培训", "教育", "学校", "考试", "留学", "移民",
    "签证", "律师", "法院", "诉讼", "仲裁", "调解", "公证", "登记", "注册",
    "开户", "注销", "变更", "年检", "审计", "税务", "发票", "报销", "做账",
    "会计", "财务", "出纳", "人事", "行政", "前台", "客服", "销售", "市场",
    "运营", "产品", "技术", "开发", "测试", "运维", "设计", "文案", "策划",
    # 旅游/出行/交通
    "旅游", "机票", "酒店", "景点", "门票", "线路", "攻略", "高铁", "航班", "机场",
    "火车站", "快递", "物流", "跑腿", "家政", "保洁", "维修", "安装", "搬家",
    "施工", "工程", "项目", "招标", "投标", "合同", "协议",
    # 数码/汽车/能源
    "手机", "电脑", "数码", "汽车", "车展", "新能源", "电动车", "油价", "加油站",
    "停车", "路况", "地铁", "公交", "宽带", "WiFi", "流量", "话费", "套餐",
    "充值", "缴费", "水电", "燃气", "暖气",
    # 医美/保健/保险
    "植发", "纹眉", "纹唇", "美甲", "美睫", "美容", "美体", "SPA", "按摩",
    "足疗", "修脚", "采耳", "拔罐", "刮痧", "艾灸", "针灸", "推拿", "正骨",
    "中医", "西医", "医院", "诊所", "药店", "药房", "挂号", "体检", "化验",
    "检查", "手术", "住院", "出院", "医保", "商保", "保险", "理赔", "保单",
    "投保人", "被保险人", "受益人", "保费", "保额", "免赔", "续保", "退保",
    "分红", "万能险", "投连险", "年金险", "寿险", "重疾险", "医疗险", "意外险",
    "车险", "家财险", "企财险", "责任险", "雇主险", "工伤险", "失业险", "养老险",
    "生育险", "公积金", "退休金", "养老金", "低保", "五保",
    # 穿搭/美妆/健身
    "穿搭", "美妆", "护肤", "健身", "减肥", "瑜伽", "跑步", "马拉松", "球赛",
    "演唱会", "电影", "电视剧", "综艺", "动漫", "游戏", "电竞",
    # 直播/自媒体/互联网
    "主播", "直播", "短视频", "网红", "粉丝", "点赞", "评论", "转发", "收藏",
    "关注", "私信", "群聊", "朋友圈", "公众号", "小程序", "APP", "网站", "域名",
    "服务器", "云服务", "数据库", "网络",
    # 农业/农资（非美食加工）
    "扶贫", "助农", "乡村振兴", "三农", "农产品", "化肥", "农药", "种子",
    "农机", "农具", "农田", "耕地", "宅基地", "承包地", "流转", "确权", "颁证",
    "林权证", "草原证", "水域滩涂", "养殖证", "捕捞证", "渔船", "渔港", "渔民",
    "远洋", "近海", "淡水", "海水", "水产", "养殖", "种植", "大棚", "温室",
    "无土栽培", "水培", "雾培", "基质", "营养液", "肥料", "有机肥", "无机肥",
    "复合肥", "尿素", "磷肥", "钾肥", "微肥", "菌肥", "生物肥", "叶面肥",
    "冲施肥", "滴灌", "喷灌", "渗灌", "渠灌", "井灌", "排涝", "抗旱", "防洪",
    "防汛", "防风", "防沙", "水土保持", "退耕还林", "退牧还草", "围封", "禁牧",
    "休牧", "轮牧", "舍饲", "半舍饲", "青贮", "黄贮", "氨化", "微贮", "秸秆",
    "饲草", "饲料", "添加剂", "预混料", "浓缩料", "全价料", "蛋白饲料", "能量饲料",
    "粗饲料", "青绿饲料", "多汁饲料", "糟渣", "饼粕", "糠麸", "谷实", "薯类",
    "豆类", "玉米", "小麦", "水稻", "大麦", "燕麦", "高粱", "谷子", "荞麦",
    "糜子", "青稞", "豌豆", "蚕豆", "扁豆", "鹰嘴豆", "羽扇豆", "香豌豆",
)


def _norm(s):
    return C.cjk_norm(s or "")


def load_db_forms():
    """库内店 → 归一店名 forms（品类无关，不做面包标签限定）。"""
    rests = C.fetch_all("restaurants", "id,name,status", order_col="id")
    out = []
    for r in rests:
        full = re.split(r"[（(]", r["name"])[0].strip()
        forms = {_norm(r["name"]), _norm(full)}
        for seg in re.split(r"[·・•&,，]", full):
            s = _norm(seg)
            if s and len(s) >= 2:
                forms.add(s)
        out.append({"id": r["id"], "full": full, "forms": {f for f in forms if f}})
    return out


class DiscoveryEngine:
    def __init__(self, bu, category, work_dir, city="上海", notes_per_query=4,
                 dense=False, stall=6, max_per_run=8, max_frontier=80, use_db=True):
        self.bu = bu
        self.category = K.normalize_category(category)
        self.work = pathlib.Path(work_dir)
        self.work.mkdir(parents=True, exist_ok=True)
        self.city = city
        self.npq = notes_per_query
        self.dense = dense
        self.stall_limit = stall
        self.max_per_run = max_per_run
        self.max_frontier = max_frontier

        self.alias2canon, self.short_alias = G.build_alias_map()
        self.db = load_db_forms() if use_db else []

        self.state_path = self.work / f"engine_{self.category}.json"
        self.raw_path = self.work / "raw_discovery.jsonl"
        self.oral_path = self.work / "oral_mentions.jsonl"
        self.state = self._load_or_init()

    # ------------------------------------------------------------ 状态
    # 【质量监管】连续空结果阈值：达到此数则标记 stalled，防止搜索限流时空跑至假饱和
    EMPTY_STALL_LIMIT = 3

    def _load_or_init(self):
        if self.state_path.exists():
            st = json.loads(self.state_path.read_text(encoding="utf-8"))
            # 兼容旧 state：补 empty_streak 字段
            st.setdefault("empty_streak", 0)
            return st
        seeds = _seed_queries(self.category, dense=self.dense)
        return {
            "category": self.category, "city": self.city, "dense": self.dense,
            "visited": [], "frontier_high": list(seeds), "frontier_low": [],
            "brands": {}, "oral": {}, "stall": 0, "processed": 0,
            "outside_brands": 0, "status": "running",
            # 【质量监管】连续空结果计数：搜索被限流时 notes 持续为空，
            # 达到 EMPTY_STALL_LIMIT 则标记 stalled，防止 frontier 耗尽误判 saturated
            "empty_streak": 0,
        }

    def save(self):
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=1), encoding="utf-8")

    def _append_raw(self, rec):
        with self.raw_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _append_oral(self, name, query):
        with self.oral_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"name": name, "query": query,
                                "category": self.category}, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------ 匹配
    def match_db(self, na):
        exact = [d for d in self.db if na in d["forms"]]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            return "AMBIG"
        if len(na) >= 4:
            hits = [d for d in self.db if na in _norm(d["full"]) or _norm(d["full"]) in na]
            if len(hits) == 1:
                return hits[0]
        return None

    def resolve(self, anchor):
        """锚点名 → (显示名, in_db, rid)。"""
        na = _norm(anchor)
        if not na or na in GENERIC_WORDS or len(na) < 2:
            return None
        # 【质量监管】非美食词过滤：包含房产/政策/金融等关键词的锚点不当作美食品牌
        if any(kw in na for kw in NON_FOOD_KEYWORDS):
            return None
        if na in self.alias2canon:
            canon = self.alias2canon[na]
            d = self.match_db(_norm(canon))
            if isinstance(d, dict):
                return canon, True, d["id"]
            return canon, False, None
        d = self.match_db(na)
        if isinstance(d, dict):
            return d["full"], True, d["id"]
        if d == "AMBIG":
            return None  # 多店命中，无法确认，不当作新店
        return anchor.strip(), False, None

    # ------------------------------------------------------------ frontier
    def _enqueue(self, q, level):
        q = re.sub(r"\s+", " ", q or "").strip()
        if not q or q in self.state["visited"]:
            return False
        # 【质量监管】非美食词过滤：防止房产/政策等词污染 frontier
        if any(kw in _norm(q) for kw in NON_FOOD_KEYWORDS):
            return False
        if q in self.state["frontier_high"] or q in self.state["frontier_low"]:
            return False
        if len(self.state["frontier_high"]) + len(self.state["frontier_low"]) >= self.max_frontier:
            return False
        (self.state["frontier_high"] if level == "high"
         else self.state["frontier_low"]).append(q)
        return True

    def _pop(self):
        while True:
            if self.state["frontier_high"]:
                q = self.state["frontier_high"].pop(0)
            elif self.state["frontier_low"]:
                q = self.state["frontier_low"].pop(0)
            else:
                return None
            if q not in self.state["visited"]:
                return q

    # ------------------------------------------------------------ 提取
    def _anchors_from_lines(self, desc):
        """合集结构化锚点店名（- 店名：/ 📍店名 / 店名丨 / 编号 店名）。"""
        names = []
        for line in G.split_lines(desc):
            m = G.RE_DASH.match(line)
            if m:
                names.append(G.clean_anchor(m.group(1)))
                continue
            for rx in (G.RE_PIN, G.RE_BAR, G.RE_NUM):
                for mm in rx.finditer(line):
                    names.append(G.clean_anchor(mm.group(1)))
        return [n for n in names if n]

    @staticmethod
    def _clean_oral_fragment(seg):
        s = seg.strip(" ：:，。、！？!?,.'\"")
        # 连续剥掉末尾的语气/夸赞/连接字，保留店名与店铺后缀（店馆坊屋舍堂楼…）
        while len(s) > 2 and s[-1] in TAIL_PARTICLE:
            s = s[:-1]
        return s.strip()

    def _record_brand(self, name, in_db, rid, query, outside_new):
        key = _norm(name)
        b = self.state["brands"].get(key)
        if b is None:
            b = {"name": name, "in_db": in_db, "rid": rid,
                 "mentions": 0, "from_queries": []}
            self.state["brands"][key] = b
            if not in_db:
                self.state["outside_brands"] += 1
                outside_new = True
        b["mentions"] += 1
        if query not in b["from_queries"]:
            b["from_queries"].append(query)
        return b, outside_new

    def _ingest(self, query, notes):
        """从一批笔记识别品牌、扩展 frontier。返回是否引入库外新品牌。"""
        outside_new = False
        # 英文未知专名（跨正文+评论，最长匹配）
        known = set(self.alias2canon)
        for d in self.db:
            known.update(d["forms"])
        en_leads = defaultdict(int)
        # 中文口述计数（低置信，需重复）
        oral_cnt = defaultdict(int)

        def add_resolved(anchor, level, enqueue=True):
            nonlocal outside_new
            res = self.resolve(anchor)
            if not res:
                return
            name, in_db, rid = res
            _, outside_new = self._record_brand(name, in_db, rid, query, outside_new)
            if enqueue and not in_db:
                self._enqueue(name, level)  # 库外新店 → 按店名取证

        for note in notes:
            title, desc = note.get("title", ""), note.get("desc", "")
            # 1) 合集结构化锚点（高置信）
            for a in self._anchors_from_lines(desc):
                add_resolved(a, "high")
            # 2) 正文品牌词典长别名自由匹配
            body_norm = _norm(title + desc)
            for al, canon in self.alias2canon.items():
                if len(al) >= 6 and al in body_norm:
                    add_resolved(canon, "high", enqueue=False)
            # 3) 评论区
            for c in note.get("comments") or []:
                ctext = c.get("text", "")
                if not ctext:
                    continue
                cnt = _norm(ctext)
                # 评论里的品牌词典
                hit_brand = None
                for al, canon in self.alias2canon.items():
                    if (len(al) >= 4 and al in cnt) or (al in cnt and al not in self.short_alias):
                        hit_brand = canon
                if hit_brand:
                    add_resolved(hit_brand, "high", enqueue=False)
                else:
                    d = None
                    for dd in self.db:
                        if any(len(f) >= 4 and f in cnt for f in dd["forms"]):
                            d = dd
                            break
                    if d:
                        add_resolved(d["full"], "high", enqueue=False)
                # 评论明确推荐另一家
                for rx in RE_REC:
                    for mm in rx.finditer(ctext):
                        frag = self._clean_oral_fragment(mm.group(1))
                        if not frag or frag[0] in STOP_HEAD or _norm(frag) in GENERIC_WORDS:
                            continue
                        res = self.resolve(frag)
                        if res and res[1]:
                            add_resolved(res[0], "high", enqueue=False)
                        elif res:
                            oral_cnt[_norm(frag)] += 1
                        else:
                            oral_cnt[_norm(frag)] += 1
            # 4) 英文未知专名
            alltext = title + "\n" + desc + "\n" + " ".join(
                c.get("text", "") for c in note.get("comments") or [])
            G.collect_leads(alltext, known, en_leads)

        # 英文专名：仅当被多次（≥2）独立提及时才记录并按店名取证；
        # 单次提及多为噪声/粘连，不进 brands、不耗浏览器，交离线 leads 后续锚定。
        for lead, cnt in G.merge_leads(dict(en_leads)).items():
            if lead in known:
                continue
            if cnt >= 2:
                _, outside_new = self._record_brand(lead, False, None, query, outside_new)
                self._enqueue(lead, "high")
            else:
                self.state["oral"][lead] = self.state["oral"].get(lead, 0) + cnt
                self._append_oral(lead, query)

        # 中文口述：像店名（后缀）或重复≥2 → 入 low；否则记 oral
        for frag_n, cnt in oral_cnt.items():
            frag = frag_n  # norm 后
            looks_shop = frag.endswith(SHOP_SUFFIX)
            if looks_shop or cnt >= 2:
                _, outside_new = self._record_brand(frag, False, None, query, outside_new)
                self._enqueue(frag, "low")
            else:
                self.state["oral"][frag] = self.state["oral"].get(frag, 0) + cnt
                self._append_oral(frag, query)
        return outside_new

    # ------------------------------------------------------------ 主循环
    # 假饱和重开用的加深词根（评论区/长尾/主厨/英文/排名，见 BREAD method §二）
    DEEP_WORD_SUFFIX = [
        "评论区 推荐", "评论区 真正好吃", "合集 盘点", "红黑榜",
        "本地人 私藏", "老饕 无广", "主厨 招牌 工作室",
        "预约 排队 老顾客", "正宗 排名", "宝藏小店", "踩雷 排雷",
    ]

    def reseed_deep(self, round_n=1):
        """假饱和重开：用「更密 + 评论区/长尾词根」重建 frontier（排除已访问）。

        何时由 gap_runner 调用：一轮 run 标 saturated/stalled，但覆盖账本显示该叶
        在营候选店 n_active < target_n（发现没做够）。verified 缺口归评价管线、不靠
        本方法。round_n 记入 state，达上限仍不足则由 gap_runner 标 gap_remaining。
        返回新 frontier 长度。
        """
        visited = set(self.state.get("visited", []))
        spec = K.CATEGORY_SPEC.get(self.category, {})
        cand = list(_seed_queries(self.category, dense=True))  # gather 自动加城市
        for nm in (spec.get("names") or [])[:2]:
            for suf in self.DEEP_WORD_SUFFIX:
                cand.append(f"{nm} {suf}")
        for sub in (spec.get("subs") or [])[:8]:
            cand.append(f"{sub} 评论区 推荐")
            cand.append(f"{sub} 正宗 好吃 排名")
        for en in (spec.get("ens") or [])[:3]:
            cand.append(f"best {en} shanghai review")
        out, seen = [], set()
        for q in cand:
            qq = re.sub(r"\s+", " ", q).strip()
            if not qq or qq in visited or qq in seen:
                continue
            seen.add(qq)
            out.append(qq)
        self.state["frontier_high"] = out
        self.state["frontier_low"] = []
        self.state["stall"] = 0
        self.state["empty_streak"] = 0
        self.state["deep_round"] = round_n
        self.state["status"] = "running"
        self.state.pop("stall_reason", None)
        self.save()
        return len(out)

    def run(self, max_queries=None):
        max_queries = max_queries or self.max_per_run
        did = 0
        while did < max_queries:
            q = self._pop()
            if q is None:
                # 【质量监管】frontier 耗尽前若有连续空结果，应是 stalled 而非 saturated
                if self.state.get("empty_streak", 0) >= self.EMPTY_STALL_LIMIT:
                    self.state["status"] = "stalled"
                    self.state["stall_reason"] = "frontier耗尽但连续空结果，疑似搜索限流"
                else:
                    self.state["status"] = "saturated"
                break
            notes = D._gather_one_query(self.bu, q, self.npq, self.city)
            self._append_raw({"kind": "discover", "category": self.category,
                              "query": q, "city": self.city, "notes": notes})
            outside_new = self._ingest(q, notes)
            self.state["visited"].append(q)
            self.state["processed"] += 1
            did += 1
            if outside_new:
                self.state["stall"] = 0
            else:
                self.state["stall"] += 1
            # 【质量监管】空结果检测：连续 EMPTY_STALL_LIMIT 次返回 0 篇笔记 → stalled
            if len(notes) == 0:
                self.state["empty_streak"] = self.state.get("empty_streak", 0) + 1
            else:
                self.state["empty_streak"] = 0
            remaining = (len(self.state["frontier_high"])
                         + len(self.state["frontier_low"]))
            self.save()
            print(f"  [{q}] 笔记{len(notes)} 新库外店={'是' if outside_new else '否'} "
                  f"frontier剩余{remaining} stall{self.state['stall']} "
                  f"空转{self.state['empty_streak']}")
            # 【质量监管】连续空结果达到阈值 → 立即停止，不继续跑到假饱和
            if self.state["empty_streak"] >= self.EMPTY_STALL_LIMIT:
                self.state["status"] = "stalled"
                self.state["stall_reason"] = (
                    f"连续{self.EMPTY_STALL_LIMIT}次搜索返回0篇笔记，疑似登录失效或搜索限流")
                print(f"  !! 空转检测触发：{self.state['stall_reason']}，停止本叶子采集")
                break
            # 饱和判据 = frontier 清空（每个发现的店名都已追查到底）。
            # stall 仅作报告、不提前终止，确保任何已发现线索都不漏查。
        if self.state["status"] not in ("saturated", "stalled"):
            self.state["status"] = "running"
        self.save()
        return self.report()

    def report(self):
        s = self.state
        return {
            "category": s["category"], "status": s["status"],
            "processed": s["processed"], "visited": len(s["visited"]),
            "brands": len(s["brands"]), "outside_brands": s["outside_brands"],
            "frontier_remaining": len(s["frontier_high"]) + len(s["frontier_low"]),
            "oral_pending": len(s["oral"]),
            # 【质量监管】空转计数 + 原因（如有）
            "empty_streak": s.get("empty_streak", 0),
            "stall_reason": s.get("stall_reason", ""),
        }
