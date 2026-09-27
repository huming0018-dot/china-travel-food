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
except Exception:
    sys.path.insert(0, str(pathlib.Path(__file__).parent))
    import common as C
    import social_discovery as D
    import admission_gate as G
    import discovery_keywords as K

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
    def _load_or_init(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        seeds = K.build_queries(self.category, dense=self.dense)
        return {
            "category": self.category, "city": self.city, "dense": self.dense,
            "visited": [], "frontier_high": list(seeds), "frontier_low": [],
            "brands": {}, "oral": {}, "stall": 0, "processed": 0,
            "outside_brands": 0, "status": "running",
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
    def run(self, max_queries=None):
        max_queries = max_queries or self.max_per_run
        did = 0
        while did < max_queries:
            q = self._pop()
            if q is None:
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
            remaining = (len(self.state["frontier_high"])
                         + len(self.state["frontier_low"]))
            self.save()
            print(f"  [{q}] 笔记{len(notes)} 新库外店={'是' if outside_new else '否'} "
                  f"frontier剩余{remaining} stall{self.state['stall']}")
            # 饱和判据 = frontier 清空（每个发现的店名都已追查到底）。
            # stall 仅作报告、不提前终止，确保任何已发现线索都不漏查。
        if self.state["status"] != "saturated":
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
        }
