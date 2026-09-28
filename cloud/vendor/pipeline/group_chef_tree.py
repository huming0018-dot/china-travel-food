#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""group_chef_tree.py — F3「集团 / 品牌 / 主厨树」自上而下抽样框（确定性、可复跑）。

为什么存在：名店很多以集团/主厨品牌矩阵扩张（新荣记、甬府、大董、Paul Pairet…），
只靠关键词自下而上会漏掉同集团的其他品牌。本模块把已登记的品牌名解析成真实店铺并对账：

  1) chefs.restaurants_owned 存的是品牌【名字符串】→ 解析到在营 restaurant（高置信唯一才认）；
  2) chefs.group_id 缺失但 group.founder 命中 → 自动补集团归属；
  3) 集团 expected brands = 成员 brand_name + 同集团主厨 owned + 描述里“旗下：A/B/C”；
     逐一对账：linked 已挂成员 / new 店在库却未挂成员（--apply 补挂）/
     missing 无此店（写 group_missing_brands.json 喂发现，绝不臆造）/ ambiguous。

默认 dry-run；--apply 才 PATCH chefs.group_id、补插 restaurant_group_members、写缺口文件。
"""
import argparse
import json
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, "/app/cloud")
sys.path.insert(0, "/app/pipeline")

import common as C          # noqa: E402

COVDIR = pathlib.Path("/app/data/coverage")
MISS_F = COVDIR / "group_missing_brands.json"
STATUS_F = COVDIR / "group_brand_status.json"


def key(s):
    """归一比较键：CJK 归一 + 拉丁小写 + 去空格/标点。"""
    s = C.cjk_norm(str(s or ""))
    return re.sub(r"[\s\W_]+", "", s, flags=re.UNICODE).lower()


def parse_desc_brands(desc):
    """从描述提取品牌：『旗下：A/B/C』『含A、B』；去括号注释。"""
    out = []
    for m in re.finditer(r"(?:旗下[:：]|含)([^。；]+)", str(desc or "")):
        seg = m.group(1)
        seg = re.sub(r"[（(].*?[)）]", "", seg)
        for b in re.split(r"[/、,，]", seg):
            b = re.split(r"等", b)[0].strip()   # 去“等/等等”列举尾巴
            if b and not re.search(r"(米其林|星|创始人|年|生于|创立)$", b):
                out.append(b)
    return out


def load_brand_status():
    """品牌状态注册表（外部时效/关店/外地核验写入，带 source_url）。
    返回 key(brand) -> {status: closed|out_of_market, city, closed_date, source_url}。"""
    if not STATUS_F.exists():
        return {}
    d = json.loads(STATUS_F.read_text(encoding="utf-8"))
    out = {}
    for b in d.get("brands", []):
        if b.get("brand"):
            out[key(b["brand"])] = b
    return out


class Index:
    def __init__(self, rests):
        self.rids = []
        self.by_k = {}      # active key -> [rid...]
        self.closed_k = {}  # closed key -> [rid...]
        for r in rests:
            bucket = self.by_k if r.get("status") == "active" else self.closed_k
            if r.get("status") == "active":
                self.rids.append(r["id"])
            for nm in (r["name"], r.get("name_en")):
                if nm:
                    bucket.setdefault(key(nm), []).append(r["id"])

    def _closed_match(self, k):
        if k in self.closed_k:
            return sorted(set(self.closed_k[k]))
        hits = set()
        for nk, rids in self.closed_k.items():
            if k and (k in nk or nk in k):
                hits.update(rids)
        return sorted(hits)

    def resolve(self, token):
        """返回 (rids, conf)。exact/strong 唯一在营；ambiguous；closed 仅关店；none。"""
        k = key(token)
        if not k:
            return [], "none"
        if k in self.by_k:
            rids = sorted(set(self.by_k[k]))
            return rids, "exact"
        # 包含匹配（品牌名 vs 店名）
        hits = set()
        for nk, rids in self.by_k.items():
            if k and (k in nk or nk in k):
                hits.update(rids)
        if len(hits) == 1:
            return list(hits), "strong"
        if len(hits) > 1:
            return sorted(hits), "ambiguous"
        closed = self._closed_match(k)
        if closed:
            return closed, "closed"
        return [], "none"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    groups = C.fetch_all("restaurant_groups", order_col="id")
    members = C.fetch_all("restaurant_group_members", order_col="group_id")
    chefs = C.fetch_all("chefs", order_col="id")
    rests = C.fetch_all("restaurants", select="id,name,name_en,status", order_col="id")
    rid_name = {r["id"]: r["name"] for r in rests}
    idx = Index(rests)

    # 成员按集团分组
    mem_by_g = {}
    rid_groups = {}
    for m in members:
        mem_by_g.setdefault(m["group_id"], {})[m["restaurant_id"]] = m
        rid_groups.setdefault(m["restaurant_id"], set()).add(m["group_id"])

    def is_founder(ch, g):
        f = str(g.get("founder") or "")
        return bool(f) and (f == ch["name"] or ch["name"] in f or f in ch["name"])

    # 主厨集团归属（founder 命中；保守，仅当当前无 group_id）
    chef_group_patch = {}
    for ch in chefs:
        if ch.get("group_id"):
            continue
        for g in groups:
            if is_founder(ch, g):
                chef_group_patch[ch["id"]] = g["id"]
                break

    # ---- 逐集团对账品牌组合 ----
    tree = {}
    all_missing = []
    new_links = []   # (gid, rid, brand_name)
    cross_skipped = []
    brand_status = load_brand_status()
    for g in groups:
        gid = g["id"]
        have_rids = set((mem_by_g.get(gid) or {}))
        # 期望品牌名：①既有成员 brand_name；②集团描述“旗下/含”（curated，可信）
        brand_tokens = []   # (token, trusted)
        for mm in (mem_by_g.get(gid) or {}).values():
            if mm.get("brand_name"):
                brand_tokens.append((mm["brand_name"], True))
        for t in parse_desc_brands(g.get("description")):
            brand_tokens.append((t, True))
        # ③仅“创始人主厨”的 owned 品牌（untrusted，需过跨集团守卫）
        for ch in chefs:
            if ch.get("group_id") == gid and is_founder(ch, g):
                for t in (ch.get("restaurants_owned") or []):
                    brand_tokens.append((t, False))
        # 去重保序
        seen, tokens = set(), []
        for t, trusted in brand_tokens:
            kk = key(t)
            if kk and kk not in seen:
                seen.add(kk); tokens.append((t, trusted))

        linked, new, ambiguous, missing, closedb, oob = [], [], [], [], [], []
        for t, trusted in tokens:
            rids, conf = idx.resolve(t)
            if conf in ("exact", "strong"):
                # 跨集团守卫：解析到的店全部已属【其他集团】且本集团没有 → 是雇主品牌，跳过
                other = all((rid in rid_groups and gid not in rid_groups[rid])
                            for rid in rids)
                if other and not any(rid in have_rids for rid in rids):
                    cross_skipped.append((gid, g["name"], t, rids))
                    continue
                for rid in rids:
                    if rid in have_rids:
                        linked.append((t, rid))
                    else:
                        new.append((t, rid))
                        new_links.append((gid, rid, t))
            elif conf == "ambiguous":
                ambiguous.append((t, rids))
            elif conf == "closed":
                closedb.append((t, rids))   # 品牌已关店，不补、不标缺口
            elif trusted:
                st = brand_status.get(key(t))
                if st and st.get("status") == "closed":
                    closedb.append((t, []))
                elif st and st.get("status") == "out_of_market":
                    oob.append((t, st.get("city")))   # 外地品牌，非上海缺口
                else:
                    missing.append(t)   # 未知：真·待核缺口
                    all_missing.append({"group_id": gid, "group_name": g["name"], "brand": t})
            # 创始人 owned 但解析不到 → 不硬标缺失（可能是雇主/外地品牌）
        tree[gid] = {"name": g["name"], "members": len(have_rids),
                      "linked": len(linked), "new": new, "ambiguous": ambiguous,
                      "missing": missing, "closed": closedb, "oob": oob}

    # ---- 报告 ----
    print(f"集团 {len(groups)}；主厨 {len(chefs)}；待补主厨 group_id {len(chef_group_patch)}")
    for gid, t in tree.items():
        print(f"\n[{gid}] {t['name']}：成员 {t['members']}，已解析挂名 {t['linked']}")
        for tok, rid in t["new"]:
            print(f"   + 未挂成员：{tok} → rid {rid}（{rid_name.get(rid)}）")
        for tok, rids in t["ambiguous"]:
            print(f"   ? 歧义：{tok} → {rids}")
        for tok, rids in t.get("closed", []):
            print(f"   ◼ 已关店：{tok} → {rids}")
        for tok, city in t.get("oob", []):
            print(f"   ◇ 外地品牌（非上海）：{tok}（{city}）")
        for tok in t["missing"]:
            print(f"   ✗ 组合缺口（无此店）：{tok}")

    print(f"\n汇总：待补挂成员 {len(new_links)}；组合缺口品牌 {len(all_missing)}；"
          f"待补主厨集团 {len(chef_group_patch)}；跨集团守卫跳过 {len(cross_skipped)}")
    for gid, gname, tok, rids in cross_skipped:
        print(f"   ↳ 守卫跳过：[{gid}]{gname} 的「{tok}」已属其他集团 {sorted(rids)}")

    if args.apply:
        # 1) 主厨 group_id
        for cid, gid in chef_group_patch.items():
            C.req("PATCH", f"/chefs?id=eq.{cid}", json={"group_id": gid}, use_service=True)
            time.sleep(0.05)
        # 2) 补挂成员（幂等：先查后插；按 (gid,rid) 去重）
        seen_pair = set()
        for gid, rid, brand in new_links:
            if (gid, rid) in seen_pair:
                continue
            seen_pair.add((gid, rid))
            payload = {"group_id": gid, "restaurant_id": rid, "brand_name": brand,
                       "is_current": True}
            C.req("POST", "/restaurant_group_members", json=payload, use_service=True)
            time.sleep(0.05)
        # 3) 缺口文件喂发现
        COVDIR.mkdir(parents=True, exist_ok=True)
        MISS_F.write_text(json.dumps(all_missing, ensure_ascii=False, indent=1),
                          encoding="utf-8")
        print(f"\nAPPLIED：主厨集团 {len(chef_group_patch)}，补挂成员 {len(new_links)}，"
              f"缺口 -> {MISS_F}（{len(all_missing)}）")
    else:
        print("\n(dry-run；--apply 才写库)")


if __name__ == "__main__":
    main()
