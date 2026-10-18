#!/usr/bin/env python3
"""Food Radar v2: local records, evidence-aware shortlists and scoped wishlists.
No network, credentials, bookings or schedulers. Python >= 3.11, standard library.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
# 宿主固定的数据根目录。db 必须直接位于其下，防止 --db 被 ../ 逃逸或指向系统路径。
# 每次构造时解析（而非 import 时），便于宿主/测试用 FOOD_RADAR_DATA_ROOT 切换到隔离目录。
def _allowed_db_root():
    return Path((os.environ.get("FOOD_RADAR_DATA_ROOT", "").strip()
                 or str(Path.home() / ".local/share/food-radar/data"))).resolve()
KINDS = {"restaurant", "event"}
FACTS = {
    "price_per_head", "menu", "ingredient_tags", "technique_tags", "flavor_tags",
    "freshness", "sourcing", "signature_dishes", "address", "opening_date",
    "business_status", "hours", "booking_status", "booking_url", "allergens",
    "chef", "service_charge", "reservation_opens_at", "cancellation_policy"
}
TAG_FIELDS = ("ingredient_tags", "technique_tags", "flavor_tags")
PROFILE_KEYS = {"liked_tags", "avoid_tags", "allergies", "novelty", "experience", "priorities"}
DEFAULT_PROFILE = {"liked_tags": [], "avoid_tags": [], "allergies": [],
                   "novelty": True, "experience": None, "priorities": []}
BASIS = {"official", "booking", "menu", "reporting", "ugc", "user"}
# Operational cache limits, not promises that a source is accurate.
TTL = {"booking_status": timedelta(minutes=15), "business_status": timedelta(days=7),
       "hours": timedelta(days=7), "menu": timedelta(days=30),
       "price_per_head": timedelta(days=30), "freshness": timedelta(days=1),
       "allergens": timedelta(days=1), "ingredient_tags": timedelta(days=30),
       "technique_tags": timedelta(days=30), "flavor_tags": timedelta(days=30),
       "signature_dishes": timedelta(days=30), "sourcing": timedelta(days=30)}

def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")

def instant(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timestamps require a timezone")
    return d.astimezone(TZ)

def boundary(value, end=False):
    if len(value) == 10:
        return datetime.combine(date.fromisoformat(value), time.max if end else time.min, TZ)
    return instant(value)

def canonical_url(value):
    p = urlsplit(value)
    if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password:
        raise ValueError("source/booking URLs must be http(s), without credentials")
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"spm", "fbclid"}]
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, urlencode(sorted(query)), ""))

def require_string(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " must be a nonempty string")

def strings(value, name):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(name + " must be a list of nonempty strings")

def sources_valid(sources, now):
    if not isinstance(sources, list):
        raise ValueError("sources must be a list")
    result = []
    seen = set()
    for s in sources:
        if not isinstance(s, dict):
            raise ValueError("invalid source")
        s = copy.deepcopy(s)
        s["url"] = canonical_url(s["url"])
        require_string(s.get("publisher"), "publisher")
        require_string(s.get("origin_id"), "origin_id")
        if instant(s["observed_at"]) > now + timedelta(minutes=5):
            raise ValueError("observation is in the future")
        published = s.get("published_at")
        if published:
            if boundary(published) > now + timedelta(minutes=5):
                raise ValueError("publication is in the future; event date belongs elsewhere")
        key = (s["url"], s["origin_id"])
        if key not in seen:
            result.append(s)
            seen.add(key)
    return result

def validate_record(record, now=None):
    now = now or datetime.now(TZ)
    r = copy.deepcopy(record)
    if r.get("schema_version") != 2:
        raise ValueError("schema_version must be 2; legacy records need explicit migration")
    for key in ("id", "name", "city"):
        require_string(r.get(key), key)
    if r.get("kind") not in KINDS:
        raise ValueError("kind must be restaurant or event")
    r["sources"] = sources_valid(r.get("sources", []), now)
    if not r["sources"]:
        raise ValueError("discovered records require a public source; personal notes use feedback")
    if r["kind"] == "restaurant":
        require_string(r.get("branch"), "branch (use explicit single-location label if applicable)")
    else:
        require_string(r.get("restaurant_id"), "restaurant_id")
        if r.get("event_type") not in {"guest_chef", "four_hands", "pop_up", "limited_menu", "other"}:
            raise ValueError("invalid event_type")
        if r.get("event_status") not in {"announced", "cancelled", "postponed", "unknown"}:
            raise ValueError("invalid event_status")
        start, end = r.get("starts_at"), r.get("ends_at")
        if bool(start) != bool(end):
            raise ValueError("provide both event boundaries or leave both unknown")
        if start and boundary(end, True) < boundary(start):
            raise ValueError("event ends before it starts")
    facts = r.setdefault("facts", {})
    if not isinstance(facts, dict) or set(facts) - FACTS:
        raise ValueError("unknown fact keys; use schema fields")
    for key, f in facts.items():
        if not isinstance(f, dict) or "value" not in f:
            raise ValueError("facts need value, basis and sources")
        if f.get("basis") not in BASIS:
            raise ValueError("invalid fact basis")
        f["sources"] = sources_valid(f.get("sources", []), now)
        if f["value"] is not None and not f["sources"]:
            raise ValueError(key + " value requires evidence")
        if key in TAG_FIELDS or key in {"allergens", "signature_dishes"}:
            if f["value"] is not None:
                strings(f["value"], key)
        if key == "price_per_head" and f["value"] is not None:
            if isinstance(f["value"], bool) or not isinstance(f["value"], (int, float)) or not 0 <= f["value"] < 1000000:
                raise ValueError("invalid price")
        if key == "booking_url" and f["value"]:
            f["value"] = canonical_url(f["value"])
        if key == "booking_status" and f["value"] not in {None, "available", "sold_out", "not_open", "unknown"}:
            raise ValueError("invalid booking status")
        if key == "business_status" and f["value"] not in {None, "open", "trial", "planned", "temporarily_closed", "closed", "unknown"}:
            raise ValueError("invalid business status")
        if key == "opening_date" and f["value"] is not None:
            date.fromisoformat(f["value"])
        if f.get("valid_until"):
            instant(f["valid_until"])
    return r

def fact_value(r, key, now):
    f = r.get("facts", {}).get(key)
    if not f or f.get("value") is None:
        return None
    src = f.get("sources", [])
    if not src:
        return None
    observed = max(instant(s["observed_at"]) for s in src)
    if observed > now + timedelta(minutes=5):
        return None
    # 永久闭店是终态：不受 valid_until 与服务商 TTL 影响（#19）。
    # 必须放在 valid_until 检查之前，否则带 valid_until 的闭店记录到期后会返回 None，
    # 让已确认闭店的餐厅重新变回候选。
    if key == "business_status" and f["value"] == "closed":
        return "closed"
    if f.get("valid_until") and now > instant(f["valid_until"]):
        return None
    if key in TTL and now - observed > TTL[key]:
        return None
    return f["value"]

def event_state(r, now):
    status = r.get("event_status", "unknown")
    if status in {"cancelled", "postponed"}:
        return status
    if not r.get("starts_at") or status == "unknown":
        return "unknown"
    if boundary(r["ends_at"], True) < now:
        return "ended"
    return "upcoming" if boundary(r["starts_at"]) > now else "active"

def semantic_hash(r):
    # Observation refresh alone is not a news item. Status/date/menu/price changes are.
    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if k not in {"observed_at", "verified_at"}}
        if isinstance(x, list):
            values = [strip(v) for v in x]
            return sorted(values, key=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True))
        return x
    return hashlib.sha256(json.dumps(strip(r), sort_keys=True, ensure_ascii=False).encode()).hexdigest()

class Radar:
    def __init__(self, db, surface, actor):
        require_string(surface, "surface")
        require_string(actor, "actor")
        self.scope = json.dumps([surface, actor], ensure_ascii=False)
        p = Path(db).expanduser()
        # 固定数据根目录：db 必须位于 root 之内，禁止 ../ 逃逸或指向任意系统路径。
        # 否则网页/聊天内容若能影响 --db 参数，就可能写到宿主私有数据目录之外。
        root = _allowed_db_root()
        if p.parent.resolve() != root:
            raise ValueError(
                "db must be directly under %s (host-fixed data root); got %s"
                % (root, p.parent))
        p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.db = sqlite3.connect(p)
        os.chmod(p, 0o600)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS records(scope TEXT,id TEXT,body TEXT,hash TEXT,PRIMARY KEY(scope,id));
        CREATE TABLE IF NOT EXISTS profiles(scope TEXT PRIMARY KEY,body TEXT);
        CREATE TABLE IF NOT EXISTS saved(scope TEXT,id TEXT,note TEXT,created_at TEXT,PRIMARY KEY(scope,id));
        CREATE TABLE IF NOT EXISTS feedback(scope TEXT,id TEXT,body TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS changes(seq INTEGER PRIMARY KEY,scope TEXT,id TEXT,change TEXT,created_at TEXT);
        """)
    def close(self):
        self.db.close()
    def profile(self, patch=None):
        row = self.db.execute("SELECT body FROM profiles WHERE scope=?", (self.scope,)).fetchone()
        value = json.loads(row[0]) if row else copy.deepcopy(DEFAULT_PROFILE)
        if patch is not None:
            if not isinstance(patch, dict) or set(patch) - PROFILE_KEYS:
                raise ValueError("unknown profile keys")
            for k in ("liked_tags", "avoid_tags", "allergies", "priorities"):
                if k in patch:
                    strings(patch[k], k)
            if "novelty" in patch and not isinstance(patch["novelty"], bool):
                raise ValueError("novelty must be boolean")
            if "experience" in patch and patch["experience"] not in {None, "casual", "experienced"}:
                raise ValueError("invalid experience")
            value.update(patch)
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO profiles VALUES(?,?)", (self.scope, json.dumps(value, ensure_ascii=False)))
        return value
    def records(self):
        return [json.loads(x[0]) for x in self.db.execute("SELECT body FROM records WHERE scope=? ORDER BY id", (self.scope,))]
    def get(self, item_id):
        row = self.db.execute("SELECT body FROM records WHERE scope=? AND id=?", (self.scope, item_id)).fetchone()
        if not row:
            raise ValueError("record not found in this scope")
        return json.loads(row[0])
    def ingest(self, records, now=None):
        if not isinstance(records, list):
            raise ValueError("input must be a JSON list")
        records = [validate_record(r, now) for r in records]
        if len({r["id"] for r in records}) != len(records):
            raise ValueError("duplicate ids in one batch; resolve sources before ingest")
        existing = {r["id"]: r for r in self.records()}
        combined = {**existing, **{r["id"]: r for r in records}}
        for r in records:
            old = existing.get(r["id"])
            if old and any(old.get(k) != r.get(k) for k in ("kind", "city", "branch", "restaurant_id")):
                raise ValueError("identity collision; do not merge branches or cities")
            if r["kind"] == "event":
                parent = combined.get(r["restaurant_id"])
                if not parent or parent["kind"] != "restaurant" or parent["city"] != r["city"]:
                    raise ValueError("event needs a same-city restaurant record")
        delta = []
        with self.db:
            for r in records:
                old = self.db.execute("SELECT hash FROM records WHERE scope=? AND id=?", (self.scope, r["id"])).fetchone()
                digest = semantic_hash(r)
                change = "new" if not old else ("updated" if old[0] != digest else "refreshed")
                self.db.execute("INSERT OR REPLACE INTO records VALUES(?,?,?,?)",
                                (self.scope, r["id"], json.dumps(r, ensure_ascii=False), digest))
                if change != "refreshed":
                    self.db.execute("INSERT INTO changes(scope,id,change,created_at) VALUES(?,?,?,?)",
                                    (self.scope, r["id"], change, now_iso()))
                delta.append({"id": r["id"], "change": change})
        return delta
    def save(self, item_id, note=""):
        self.get(item_id)
        with self.db:
            self.db.execute("INSERT INTO saved VALUES(?,?,?,?) ON CONFLICT(scope,id) DO UPDATE SET note=excluded.note",
                            (self.scope, item_id, note, now_iso()))
        return {"saved": item_id}
    def unsave(self, item_id):
        with self.db:
            self.db.execute("DELETE FROM saved WHERE scope=? AND id=?", (self.scope, item_id))
        return {"removed": item_id}
    def feedback(self, item_id, note, verdict, eaten_on):
        self.get(item_id)
        require_string(note, "note")
        date.fromisoformat(eaten_on)
        if date.fromisoformat(eaten_on) > date.today():
            raise ValueError("visit date cannot be future")
        if verdict not in {"liked", "mixed", "disliked"}:
            raise ValueError("invalid verdict")
        body = {"note": note, "verdict": verdict, "eaten_on": eaten_on}
        with self.db:
            self.db.execute("INSERT INTO feedback VALUES(?,?,?,?)", (self.scope, item_id, json.dumps(body, ensure_ascii=False), now_iso()))
        return body
    def wishlist(self):
        return [{"record": self.get(i), "note": n, "saved_at": t}
                for i, n, t in self.db.execute("SELECT id,note,created_at FROM saved WHERE scope=? ORDER BY created_at", (self.scope,))]
    def history(self, item_id):
        return sorted([json.loads(x[0]) for x in self.db.execute("SELECT body FROM feedback WHERE scope=? AND id=? ORDER BY created_at,rowid", (self.scope, item_id))], key=lambda x: x["eaten_on"])
    def changes(self, after=0):
        return [dict(zip(("cursor", "id", "change", "at"), row)) for row in self.db.execute(
            "SELECT seq,id,change,created_at FROM changes WHERE scope=? AND seq>? ORDER BY seq", (self.scope, after))]
    def shortlist(self, city, mode="now", start=None, end=None, budget=None, now=None, limit=5, required_tags=None):
        now = now or datetime.now(TZ)
        if mode not in {"now", "later", "radar"} or not 1 <= limit <= 30:
            raise ValueError("invalid mode/limit")
        if budget is not None and (not isinstance(budget, (int, float)) or not 0 <= budget < 1000000):
            raise ValueError("invalid budget")
        start = boundary(start) if start else now
        end = boundary(end, True) if end else now + timedelta(days=30)
        if end < start:
            raise ValueError("invalid query window")
        profile = self.profile()
        records = self.records()
        parents = {r["id"]: r for r in records if r["kind"] == "restaurant"}
        candidates, excluded = [], []
        for r in records:
            if r["city"] != city:
                continue
            if mode in {"now", "later"} and r["kind"] != "restaurant":
                continue
            parent = parents.get(r.get("restaurant_id"), r)
            why, needs, omit = [], [], None
            status = fact_value(parent, "business_status", now)
            if status in {"closed", "temporarily_closed"}:
                omit = "closed_or_temporarily_closed"
            opening = fact_value(parent, "opening_date", now)
            if mode == "now" and (status == "planned" or (opening and date.fromisoformat(opening) > now.date())):
                omit = "not_open_yet"
            elif mode == "later" and opening:
                # #18 later 允许尚未开业的店，但若开业时间晚于本次行程窗口结束，
                # 这趟就用不上，不能塞进候选里充数。
                try:
                    opens_on = date.fromisoformat(opening)
                except ValueError:
                    opens_on = None
                if opens_on and opens_on > end.date():
                    omit = "opens_after_window"
            if not status or status == "unknown":
                needs.append("营业状态待核实")
            state = event_state(r, now) if r["kind"] == "event" else None
            if r["kind"] == "event":
                if state in {"cancelled", "postponed", "ended", "unknown"}:
                    omit = "event_" + state
                elif boundary(r["ends_at"], True) < start or boundary(r["starts_at"]) > end:
                    omit = "outside_window"
                booking = fact_value(r, "booking_status", now)
                if booking != "available":
                    needs.append("已售罄" if booking == "sold_out" else "余位待核实；有链接不代表有位")
                else:
                    needs.append("余位仅为查询时快照，订前复核")
            elif mode == "radar":
                opening = fact_value(r, "opening_date", now)
                # Radar = new/upcoming openings in requested window, not every popular restaurant.
                if not opening or not start.date() <= date.fromisoformat(opening) <= end.date():
                    omit = "no_opening_in_window"
            tags = set()
            for k in TAG_FIELDS:
                tags.update(fact_value(r, k, now) or [])  # Guest menus cannot inherit normal-menu ingredients.
            avoid = tags.intersection(profile["avoid_tags"])
            if avoid:
                omit = "avoid_tags:" + ",".join(sorted(avoid))
            wanted = set(required_tags or [])
            if wanted - tags:
                omit = "required_ingredient_or_technique_unconfirmed"
            allergens = fact_value(r, "allergens", now)
            if profile["allergies"]:
                # Even a matching menu is not a cross-contamination guarantee.
                if allergens is None:
                    omit = "allergen_information_unconfirmed"
                elif set(profile["allergies"]).intersection(allergens):
                    omit = "allergen_conflict"
                else:
                    needs.append("已知过敏原未匹配，仍需门店确认交叉接触")
            price = fact_value(r, "price_per_head", now)
            if price is None and r["kind"] == "restaurant":
                price = fact_value(parent, "price_per_head", now)
            if budget is not None:
                if price is None:
                    needs.append("预算待确认")
                elif price > budget:
                    omit = "over_budget"
            if omit:
                excluded.append({"id": r["id"], "reason": omit})
                continue
            liked = sorted(tags.intersection(profile["liked_tags"]))
            score = len(liked) * 3
            if liked:
                why.append("符合明确偏好：" + "、".join(liked))
            visits = self.history(parent["id"])
            if r["kind"] == "event":
                visits += self.history(r["id"])
            visits.sort(key=lambda x: x["eaten_on"])
            if profile["novelty"] and not visits:
                score += 1
                why.append("没有已记录的到访，不等于你没吃过")
            if visits and visits[-1]["verdict"] == "disliked":
                score -= 3
                why.append("上次评价不喜欢，复访需要新理由")
            if not tags:
                needs.append("具体食材与技法证据不足")
            if not fact_value(r, "freshness", now):
                needs.append("食材新鲜度未独立核实")
            if r["kind"] == "restaurant":
                needs.append("营业中、当天有位、排队情况需分别确认")
            candidates.append({"id": r["id"], "name": r["name"], "kind": r["kind"],
                "score": score, "reasons": why, "needs_confirmation": list(dict.fromkeys(needs)),
                "price_per_head": price, "event_state": state, "record": r})
        candidates.sort(key=lambda x: (-x["score"], x["id"]))
        return {"city": city, "mode": mode, "as_of": now.isoformat(),
                "items": candidates[:limit], "excluded": excluded,
                "note": "候选排序辅助，不是美味评分；未执行实时联网搜索或订位"}

    def calendar(self, city, start=None, end=None, now=None):
        """未来日历视图：把活动按日期排出来，回答"什么时候会发生什么"。

        与 shortlist(--mode radar) 的区别：
          · shortlist 是**排序后的候选**，回答"去哪几家"
          · calendar 是**按日期的时间轴**，回答"哪天有什么"，含取消/延期/已结束
        取消/延期/已结束的活动**不删除**，放进 unavailable——供知悉，
        但绝不能被当作可订项呈现（data-contract §过期与冲突）。
        日期不明的活动进 undated，不进日期轴。
        """
        now = now or datetime.now(TZ)
        start = boundary(start) if start else now
        end = boundary(end, True) if end else now + timedelta(days=90)
        if end < start:
            raise ValueError("invalid query window")

        records = self.records()
        restaurants = {r["id"]: r for r in records if r["kind"] == "restaurant"}
        by_date, unavailable, undated = {}, [], []

        for r in records:
            if r["kind"] != "event" or r.get("city") != city:
                continue
            state = event_state(r, now)
            host = restaurants.get(r.get("restaurant_id"))
            chef = fact_value(r, "chef", now)
            booking = fact_value(r, "booking_status", now)
            opens_at = fact_value(r, "reservation_opens_at", now)
            entry = {
                "id": r["id"], "name": r["name"],
                "event_type": r.get("event_type"),
                "restaurant": host["name"] if host else None,
                "restaurant_id": r.get("restaurant_id"),
                "city": r.get("city"),
                "chef": chef, "booking_status": booking,
                "reservation_opens_at": opens_at,
                "price_per_head": fact_value(r, "price_per_head", now),
                "sources": [s.get("url") for s in r.get("sources", []) if s.get("url")],
            }

            if not r.get("starts_at") or not r.get("ends_at"):
                entry["reason"] = "档期不明"
                undated.append(entry)
                continue

            s_at, e_at = boundary(r["starts_at"]), boundary(r["ends_at"], True)
            if e_at < start or s_at > end:
                continue                      # 窗口外，不进日历
            if state in {"cancelled", "postponed", "ended", "unknown"}:
                entry["event_status"] = state
                if state == "ended":
                    entry["reason"] = "已结束——可作情报，不作可订项"
                elif state == "cancelled":
                    entry["reason"] = "已取消"
                elif state == "postponed":
                    entry["reason"] = "已延期，新日期未确认——维持延期状态，不改announced"
                else:
                    entry["reason"] = "档期状态未知——需主办方确认"
                unavailable.append(entry)
                continue

            key = s_at.date().isoformat()
            entry["starts_at"] = r["starts_at"]
            entry["ends_at"] = r["ends_at"]
            entry["spans_days"] = (e_at.date() - s_at.date()).days

            # #21 预订开放时间必须区分"已开放"与"将开放"。
            # 旧实现只要 reservation_opens_at 有值就写"预订刚开放"，
            # 未来时间也被说成已经开放，属于事实错误。
            if opens_at:
                o_at = boundary(opens_at)
                if o_at <= now:
                    entry["why_now"] = "预订已开放"
                else:
                    entry["why_now"] = "预订将于 %s 开放" % o_at.date().isoformat()
            elif (s_at.date() - now.date()).days <= 7:
                entry["why_now"] = "临近开始"
            else:
                entry["why_now"] = "档期已公布"

            needs = (
                [] if booking == "available" else
                ["已售罄——保留情报但不可订"] if booking == "sold_out" else
                ["余位未确认：有预订入口≠有位"])

            # #20 主办餐厅的营业状态必须核对：已确认闭店的餐厅不会照常办活动。
            host_biz = fact_value(host, "business_status", now) if host else None
            if host_biz == "closed":
                needs.append("主办餐厅已确认闭店——活动大概率不会举行，订前必须直接向主办方复核")
            elif host_biz == "temporarily_closed":
                needs.append("主办餐厅暂停营业——恢复时间未确认")
            entry["needs_confirmation"] = needs

            by_date.setdefault(key, []).append(entry)

        for items in by_date.values():
            items.sort(key=lambda e: (e["starts_at"], e["name"]))
        # #22 日期轴必须按日期排序。dict 的插入顺序取决于记录遍历顺序（约等于 ID 序），
        # 直接返回会让日历乱序，因此显式按日期键排序。
        ordered = {k: by_date[k] for k in sorted(by_date)}
        return {
            "city": city, "window": [start.date().isoformat(), end.date().isoformat()],
            "generated_at": now.isoformat(),
            "by_date": ordered,
            "unavailable": unavailable,
            "undated": undated,
            "counts": {"scheduled": sum(len(v) for v in by_date.values()),
                       "unavailable": len(unavailable), "undated": len(undated)},
            "note": "取消/延期/已结束列入 unavailable 仅供知悉，不得作为可订项；余位为查询时快照，订前须复核。",
        }


def query_plan(city, mode, start, end, categories=None, tags=None):
    require_string(city, "city")
    a, b = boundary(start), boundary(end, True)
    if b < a or (b - a).days > 366:
        raise ValueError("query window must be 0..366 days")
    months = []
    d = a.date().replace(day=1)
    while d <= b.date():
        months.append(d.strftime("%Y年%m月"))
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    context = " ".join([city] + (categories or []) + (tags or []))
    events = ["新开 试营业 即将开业", "飞行厨房 客座 四手联弹", "快闪 限定菜单 预订"]
    searches = [context + " " + month + " " + e for month in months for e in events]
    if mode != "radar":
        searches = [context + " 菜单 食材 产地 技法", context + " 近期 食客 评价",
                    context + " 营业 订位"] + searches
    return {"city": city, "mode": mode, "window": [start, end], "queries": searches,
            "channels": [{"name": "public_web", "required": True},
                         {"name": "official_restaurant_or_chef", "required": False},
                         {"name": "dianping", "required": False},
                         {"name": "xiaohongshu_or_wechat", "required": False}],
            "note": "把 queries 交给宿主的搜索工具；脚本不会联网，也不要求全部渠道就绪"}

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--city", required=True)
    p.add_argument("--mode", choices=["now", "later", "radar"], default="now")
    p.add_argument("--from", dest="start", required=True)
    p.add_argument("--to", dest="end", required=True)
    p.add_argument("--category", action="append", default=[])
    p.add_argument("--tag", action="append", default=[])
    for name in ("ingest", "profile", "shortlist", "calendar", "save", "unsave", "wishlist", "feedback", "history", "changes"):
        p = sub.add_parser(name)
        p.add_argument("--db", required=True)
        p.add_argument("--surface", required=True, help="trusted host conversation scope")
        p.add_argument("--actor", required=True, help="trusted host user scope, never display-name inference")
        if name in {"ingest", "profile"}:
            p.add_argument("--input", required=(name == "ingest"))
        if name in {"save", "unsave", "feedback", "history"}:
            p.add_argument("--id", required=True)
        if name in {"save", "feedback"}:
            p.add_argument("--note", required=(name == "feedback"), default="")
        if name == "feedback":
            p.add_argument("--verdict", choices=["liked", "mixed", "disliked"], required=True)
            p.add_argument("--eaten-on", required=True)
        if name == "shortlist":
            p.add_argument("--city", required=True)
            p.add_argument("--mode", choices=["now", "later", "radar"], default="now")
            p.add_argument("--from", dest="start")
            p.add_argument("--to", dest="end")
            p.add_argument("--budget", type=float)
            p.add_argument("--at")
            p.add_argument("--limit", type=int, default=5)
            p.add_argument("--require-tag", action="append", default=[])
        if name == "changes":
            p.add_argument("--after", type=int, default=0)
        if name == "calendar":
            p.add_argument("--city", required=True)
            p.add_argument("--from", dest="start")
            p.add_argument("--to", dest="end")
            p.add_argument("--at")
    a = ap.parse_args(argv)
    radar = None
    try:
        if a.cmd == "plan":
            result = query_plan(a.city, a.mode, a.start, a.end, a.category, a.tag)
        else:
            radar = Radar(a.db, a.surface, a.actor)
            if a.cmd == "ingest":
                result = radar.ingest(json.loads(Path(a.input).read_text(encoding="utf-8")))
            elif a.cmd == "profile":
                patch = json.loads(Path(a.input).read_text(encoding="utf-8")) if a.input else None
                result = radar.profile(patch)
            elif a.cmd == "shortlist":
                if a.limit < 1 or a.limit > 30 or (a.budget is not None and a.budget < 0):
                    raise ValueError("invalid limit/budget")
                result = radar.shortlist(a.city, a.mode, a.start, a.end, a.budget,
                    instant(a.at) if a.at else None, a.limit, a.require_tag)
            elif a.cmd == "save": result = radar.save(a.id, a.note)
            elif a.cmd == "unsave": result = radar.unsave(a.id)
            elif a.cmd == "wishlist": result = radar.wishlist()
            elif a.cmd == "feedback": result = radar.feedback(a.id, a.note, a.verdict, a.eaten_on)
            elif a.cmd == "history": result = radar.history(a.id)
            elif a.cmd == "changes": result = radar.changes(a.after)
            elif a.cmd == "calendar":
                result = radar.calendar(a.city, a.start, a.end, instant(a.at) if a.at else None)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if radar: radar.close()

if __name__ == "__main__":
    raise SystemExit(main())
