#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cloud_bili_collect.py — B站(bilibili)美食探店采集，接入现有反软广管线。

双通道：
  通道① KOL 监控名单：统计 UP主 出现频次（≥3 次），upsert 进 food_kol_watchlist，
        后续长期监控其新视频作探店线索。
  通道② 餐厅候选：从搜索到的视频 title+简介产出 kind=discover 原始证据（每个视频一条 note），
        落盘 /app/data/discovery/raw_bili_<cat>.jsonl → admission_gate 离线裁决
        → candidate_apply --commit 收录。标题/简介只是线索不是证据：单条视频只算一条声音，
        独立声音≥2（≥2 个不同 UP主 提及同店）、口味均分≥3.5 才 admit，阈值与现有管线一致。

采集源（双通道）：
  首选 零依赖搜索 API：GET x/web-interface/search/all/v2（必须带 Referer，否则 -412）。
  兜底 bili-cli v0.6.2：API 返回非 code=0 时自动切换（上游 2026-03 停更，仅兜底）。

限流：每次请求间隔≥1s，每轮 ≤10 个搜索词（≤200 条视频）。
断点续跑：/app/data/bili_state.json 记录已搜关键词、已处理 bvid、UP主累计计数。

容器内：cloud=/app/cloud，pipeline=/app/pipeline，data=/app/data。
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import date

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = os.environ.get("FOOD_DATA_DIR", "/app/data")
sys.path.insert(0, str(HERE))
sys.path.insert(0, PIPE)

import requests  # noqa: E402
import common as C  # noqa: E402
import discovery_keywords as K  # noqa: E402
import health  # noqa: E402

DISC_DIR = pathlib.Path(DATA) / "discovery"
STATE_F = pathlib.Path(DATA) / "bili_state.json"
# 兜底 bili-cli：容器内经 PATH 查找（Dockerfile 容错安装）；也可用 BILI_CLI 环境变量覆盖
BILI_BIN = shutil.which(os.environ.get("BILI_CLI", "bili")) or os.environ.get("BILI_CLI", "bili")

SEARCH_API = "https://api.bilibili.com/x/web-interface/search/all/v2"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
API_HEADERS = {"User-Agent": UA, "Referer": "https://search.bilibili.com"}

# 每品类 6 个搜索句式（复用 discovery_keywords.CATEGORY_SPEC 的主称呼）
WORD_TEMPLATES = [
    "{city} {name} 探店", "{city} {name} 苍蝇馆子", "{city} {name} 宝藏",
    "{city} {name} 正宗", "{city} {name} 主厨", "{city} {name} 新店",
]
CITY = "上海"

# 实测已现的美食 UP主（首次运行预填监控名单）
PREFILL_KOLS = ["跟着老高吃东西", "周大猫Mc", "无所尉吃什么", "元气八眉菌",
                "一天世界的陆老师", "头五头六白相相上海", "味觉川菜"]

KOL_THRESHOLD = 3          # 在美食探店视频中出现≥3次才入监控名单
MIN_INTERVAL = 1.0         # API 请求间隔≥1秒
MAX_WORDS_PER_RUN = 10     # 硬约束：每轮不超过 10 个词


# ---------------------------------------------------------------- 词矩阵
def build_word_queue():
    """返回 [(word, category), ...]，品类按 CATEGORY_SPEC 顺序，每品类 6 句式。"""
    out = []
    for cat in K.all_categories():
        spec = K.CATEGORY_SPEC.get(cat, {})
        name = (spec.get("names") or [cat])[0]
        for tpl in WORD_TEMPLATES:
            w = re.sub(r"\s+", " ", tpl.format(city=CITY, name=name)).strip()
            out.append((w, cat))
    return out


# ---------------------------------------------------------------- 状态
def load_state():
    if STATE_F.exists():
        try:
            return json.loads(STATE_F.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"searched_words": [], "seen_bvids": [], "kol": {},
            "prefilled": False, "runs": 0}


def save_state(st):
    DISC_DIR.mkdir(parents=True, exist_ok=True)
    STATE_F.write_text(json.dumps(st, ensure_ascii=False, indent=1),
                       encoding="utf-8")


# ---------------------------------------------------------------- 采集
def strip_em(s):
    return re.sub(r"</?em[^>]*>", "", str(s or "")).strip()


# 店名线索提取：从 title+简介抓带店铺后缀的片段，合成结构化锚点喂给 admission_gate。
# 标题只是线索不是证据——即便合成锚点，gate 仍要求独立声音≥2、均分≥3.5 才 admit。
SHOP_SUFFIX = "店馆坊屋舍堂楼轩居铺室家行记苑阁"
# 纯品类词 / 通用词（命中即丢弃，不当店名）
GENERIC_HINT = re.compile(
    r"(面包店|面包|咖啡店|咖啡馆|咖啡|甜品店|甜品|蛋糕|酒吧|清吧|茶馆|茶室|寿司|寿司店|"
    r"拉面|烧鸟|烧肉|烤肉|居酒屋|天妇罗|怀石|咖喱|川菜|四川菜|粤菜|广东菜|苏菜|鲁菜|"
    r"浙菜|闽菜|湘菜|徽菜|本帮菜|上海菜|京菜|泰餐|越南菜|韩餐|火锅|私房菜|私宴|"
    r"餐厅|饭店|饭馆|馆子|小馆|店铺|门店|美食|好吃的|这家店|那家店|这家|那家|什么|哪里|"
    r"菜市场|菜场|小吃|快餐|自助|大餐|便饭|便所|厕所|书店|花店|药店|酒店|旅馆|"
    r"小卖部|超市|便利店|理发店|健身房|网吧|KTV|酒吧街|美食街|夜市)"
)
_RE_SHOP = re.compile(r"([一-龥A-Za-z][一-龥A-Za-z&·]{1,7}?[" + SHOP_SUFFIX + r"])")
_LEAD_STOP = set("这那我你他她它其每某本各另")


def extract_shop_leads(*texts):
    """从多段文本里提取候选店名（去重、保序）。排除纯品类词与语气词开头。"""
    out, seen = [], set()
    for t in texts:
        for m in _RE_SHOP.findall(t or ""):
            name = m.strip(" ：:，。、！？!?,./～~·-")
            if not name or name[0] in _LEAD_STOP:
                continue
            if len(name) < 3:
                continue
            if GENERIC_HINT.search(name) and len(name) <= 4:
                continue
            # 含品类词整词（如"川菜馆""面包店"）不单独成店
            if re.fullmatch(r".{0,3}(面包|咖啡|甜品|寿司|拉面|川菜|粤菜|火锅|烤肉|烧烤|餐厅|饭店|馆子|小馆)", name):
                continue
            k = C.cjk_norm(name)
            if k and k not in seen:
                seen.add(k)
                out.append(name)
    return out


def _normalize_desc(desc):
    """把 B站简介里全角竖线/竖杠统一成冒号，让 admission_gate 的 RE_DASH('店名:详情')能接住。
    （不改 gate 本身，仅在采集侧归一化；📍/编号锚点 gate 原生支持。）"""
    d = (desc or "").strip()
    if d in ("-", "—"):
        return ""
    # 全角｜│｜ → 半角竖线 → 冒号（保留 📍 emoji 行原样）
    d = re.sub(r"[｜│丨]", "：", d)
    return d


def build_note_desc(title, desc):
    """保留原简介（归一化后自带📍/店名:详情锚点），再为标题里抽到的店名补 '店名: 标题' 锚点行。"""
    lines = []
    nd = _normalize_desc(desc)
    if nd:
        lines.append(nd)
    for lead in extract_shop_leads(title, desc):
        snippet = title[:80]
        lines.append(f"{lead}：{snippet}")
    return "\n".join(lines)


def _norm_video(v):
    """API / CLI 两种来源统一成 dict。"""
    return {
        "bvid": v.get("bvid") or "",
        "author": (v.get("author") or v.get("uname") or "").strip(),
        "mid": v.get("mid") or v.get("uid") or 0,
        "play": C.to_int(v.get("play")) or 0,
        "title": strip_em(v.get("title")),
        "desc": (v.get("desc") or v.get("description") or "").strip(),
        "duration": str(v.get("duration") or "").strip(),
    }


def search_api(keyword):
    """首选：零依赖搜索 API。返回 list[dict] 或 None（失败/风控）。"""
    params = {"keyword": keyword, "page": 1}
    try:
        r = requests.get(SEARCH_API, params=params, headers=API_HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"  [API] HTTP {r.status_code} for {keyword!r}")
            return None
        j = r.json()
    except Exception as e:
        print(f"  [API] 异常 {e} for {keyword!r}")
        return None
    if j.get("code") != 0:
        print(f"  [API] code={j.get('code')} msg={j.get('message')} for {keyword!r}（触发风控，切 CLI）")
        return None
    vids = []
    for blk in j.get("data", {}).get("result", []):
        if blk.get("result_type") == "video":
            for v in blk.get("data", []):
                nv = _norm_video(v)
                if nv["bvid"]:
                    vids.append(nv)
    return vids


def search_cli(keyword):
    """兜底：bili-cli v0.6.2。返回 list[dict] 或 None。"""
    binpath = shutil.which("bili") or BILI_BIN
    if not pathlib.Path(binpath).exists() and shutil.which(binpath) is None:
        print(f"  [CLI] bili 不在 PATH（{binpath}），跳过兜底")
        return None
    try:
        out = subprocess.run([binpath, "search", "--type", "video", "-n", "20",
                              "--yaml", keyword],
                             capture_output=True, text=True, timeout=60)
    except Exception as e:
        print(f"  [CLI] 异常 {e}")
        return None
    if out.returncode != 0:
        print(f"  [CLI] exit={out.returncode}: {out.stderr[:200]}")
        return None
    text = out.stdout
    try:
        import yaml  # 容器未必装，失败则走正则
        data = yaml.safe_load(text)
    except Exception:
        data = None
    vids = []
    items = data if isinstance(data, list) else (data or {}).get("videos") if isinstance(data, dict) else None
    if items is None:
        # 宽松解析：逐块找 bvid
        for block in re.split(r"\n(?=\S)", text):
            bm = re.search(r"\b(BV[0-9A-Za-z]{10})\b", block)
            if not bm:
                continue
            def grab(key):
                m = re.search(rf"{key}:\s*['\"]?([^'\"\n]+)", block)
                return m.group(1).strip() if m else ""
            vids.append(_norm_video({"bvid": bm.group(1), "author": grab("author") or grab("uname"),
                                     "title": grab("title"), "play": grab("play"),
                                     "desc": grab("desc") or grab("description")}))
        return vids or None
    for it in items:
        if isinstance(it, dict) and it.get("bvid"):
            vids.append(_norm_video(it))
    return vids or None


def search(keyword):
    vids = search_api(keyword)
    if vids is not None:
        return vids, "api"
    vids = search_cli(keyword)
    if vids is not None:
        return vids, "cli"
    return [], "failed"


# ---------------------------------------------------------------- KOL 监控
def upsert_kol(name, mid, count):
    """PostgREST upsert food_kol_watchlist（按 (name,platform) 唯一）。返回是否成功。"""
    row = {"name": name, "platform": "bilibili", "video_count": count,
           "last_seen": date.today().isoformat(), "status": "active"}
    h = dict(C.headers())
    h["Prefer"] = "resolution=merge-duplicates,return=representation"
    try:
        r = requests.post(C.BASE + "/food_kol_watchlist", headers=h, json=row, timeout=30)
        if r.status_code not in (200, 201):
            print(f"  [KOL upsert] {name} -> HTTP {r.status_code}: {r.text[:120]}")
            return False
        return True
    except Exception as e:
        print(f"  [KOL upsert] {name} 异常 {e}")
        return False


def kol_table_ready():
    """轻量探测 food_kol_watchlist 是否已建（404 PGRST205 = 未建）。"""
    try:
        r = requests.get(C.BASE + "/food_kol_watchlist?select=id&limit=1",
                         headers=C.headers(), timeout=20)
        return r.status_code == 200
    except Exception:
        return False


def prefill_kols():
    ok = 0
    for name in PREFILL_KOLS:
        if upsert_kol(name, 0, 0):
            ok += 1
        time.sleep(0.2)
    return ok


# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=int(os.environ.get("BILI_WORDS", "8")),
                    help="本轮跑几个搜索词（默认8，硬上限10）")
    ap.add_argument("--category", default="", help="只跑指定品类（调试用）")
    args = ap.parse_args()
    limit = min(args.limit, MAX_WORDS_PER_RUN)

    DISC_DIR.mkdir(parents=True, exist_ok=True)
    st = load_state()
    if not st.get("prefilled"):
        if kol_table_ready():
            print("首次运行：预填已知美食 UP主到 food_kol_watchlist ...")
            n_ok = prefill_kols()
            print(f"  预填成功 {n_ok}/{len(PREFILL_KOLS)}")
            st["prefilled"] = True
            save_state(st)
        else:
            print("[WARN] food_kol_watchlist 表未建（先在 Supabase SQL Editor 执行 db/migrations/011_bili_kol.sql）。")
            print("       本轮餐厅候选通道②照常采集；KOL 通道①跳过，建表后下轮自动补预填。")
            health.alert(
                "B站采集已部署，但 food_kol_watchlist 表尚未建。\n"
                "请在 Supabase SQL Editor 执行 db/migrations/011_bili_kol.sql，下轮自动补 KOL 预填。",
                title="上海美食图鉴·B站建表待办", key="bili_kol_table_missing", once=True)

    queue = build_word_queue()
    if args.category:
        cat = K.normalize_category(args.category)
        queue = [(w, c) for (w, c) in queue if c == cat]

    todo = [(w, c) for (w, c) in queue if w not in st["searched_words"]]
    if not todo:
        # 全部搜过一轮后，重置已搜词队列（但保留 seen_bvids / kol 计数），持续挖新视频
        print("全量词矩阵已跑完一轮，重置词队列以继续挖新视频。")
        st["searched_words"] = []
        save_state(st)
        todo = queue
    todo = todo[:limit]

    seen_bvids = set(st["seen_bvids"])
    kol = st["kol"]
    touched_cats = set()
    raw_buf = {}  # cat -> list of records (本轮新视频)

    print(f"本轮 {len(todo)} 个搜索词，每词约20条视频。")
    for i, (word, cat) in enumerate(todo):
        vids, src = search(word)
        st["searched_words"].append(word)
        new_cnt = 0
        for v in vids:
            bv = v["bvid"]
            if bv in seen_bvids:
                continue
            seen_bvids.add(bv)
            new_cnt += 1
            # KOL 计数（通道①）
            author = v["author"]
            if author:
                k = kol.get(author)
                if k is None:
                    k = {"mid": v.get("mid") or 0, "count": 0,
                         "first_seen": date.today().isoformat()}
                    kol[author] = k
                k["count"] += 1
                if v.get("mid"):
                    k["mid"] = v["mid"]
                k["last_seen"] = date.today().isoformat()
            # 餐厅候选 note（通道②）：title+简介直接交给 admission_gate 提取锚点
            note = {
                "title": v["title"],
                "desc": build_note_desc(v["title"], v["desc"]),
                "author": author,
                "url": f"https://www.bilibili.com/video/{bv}",
                "play": v["play"],
                "bvid": bv,
                "source": "bilibili",
            }
            raw_buf.setdefault(cat, []).append(
                {"kind": "discover", "category": cat, "query": word,
                 "city": CITY, "source": "bilibili", "notes": [note]})
        touched_cats.add(cat)
        print(f"  [{i+1}/{len(todo)}] {word!r} -> {len(vids)}条({src})，新视频{new_cnt}")
        time.sleep(MIN_INTERVAL)

    # 追加写 raw_bili_<cat>.jsonl（按品类累积，跨轮聚独立声音）
    for cat, recs in raw_buf.items():
        if not recs:
            continue
        rp = DISC_DIR / f"raw_bili_{cat}.jsonl"
        with rp.open("a", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  写入 {rp.name}: +{len(recs)} 条")

    # KOL ≥3 次入监控名单
    kol_new = 0
    for author, k in kol.items():
        if k["count"] >= KOL_THRESHOLD and author not in PREFILL_KOLS:
            upsert_kol(author, k.get("mid") or 0, k["count"])
            kol_new += 1
            time.sleep(0.2)
    # 预填 UP主也刷新一次计数/last_seen
    for author in PREFILL_KOLS:
        if author in kol:
            upsert_kol(author, kol[author].get("mid") or 0, kol[author]["count"])
            time.sleep(0.2)

    # 落状态
    st["seen_bvids"] = sorted(seen_bvids)
    st["kol"] = kol
    st["runs"] = st.get("runs", 0) + 1
    save_state(st)

    # 对本轮触及的品类跑裁决 + 收录（标题只是线索，阈值不变）
    admitted_total = 0
    for cat in sorted(touched_cats):
        rp = DISC_DIR / f"raw_bili_{cat}.jsonl"
        if not rp.exists():
            continue
        print(f"\n=== admission_gate 裁决 {cat}（{rp.name}）===")
        g = subprocess.run([sys.executable, f"{PIPE}/admission_gate.py",
                            "--raw", str(rp), "--category", cat],
                           capture_output=True, text=True)
        print(g.stdout[-1500:])
        if g.returncode != 0:
            print("  gate stderr:", g.stderr[-800:])
            continue
        # 产出 candidates_<cat>.jsonl（gate 默认写 raw 同目录）→ candidate_apply 收录
        print(f"=== candidate_apply 收录 {cat} ===")
        a = subprocess.run([sys.executable, str(HERE / "candidate_apply.py"),
                            "--category", cat, "--commit"],
                           capture_output=True, text=True)
        print(a.stdout[-1200:])
        if a.returncode != 0:
            print("  apply stderr:", a.stderr[-500:])
        cf = DISC_DIR / f"candidates_{cat}.jsonl"
        if cf.exists():
            for line in cf.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    p = json.loads(line)
                    if p.get("verdict", "").startswith("admit") and not p.get("in_db"):
                        admitted_total += 1

    new_videos = sum(len(v) for v in raw_buf.values())
    print(f"\n本轮完成：{len(todo)}词，新视频{new_videos}，"
          f"KOL新增{kol_new}，库外admit候选{admitted_total}。")
    if not todo:
        health.alert("B站采集词队列空，检查状态/配额。", title="上海美食图鉴·B站采集",
                     key="bili_queue_empty")


if __name__ == "__main__":
    sys.exit(main() or 0)
