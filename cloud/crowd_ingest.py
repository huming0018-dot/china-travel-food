#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crowd_ingest.py — 众包插件回传服务端校验与落库（PM窗口自承接，#50）

对齐 CROWD-CONTRACT-001（crowd_extension/CROWD_CONTRACT.md）：
  - 信封字段：participant_id / task_id / proof_seq / captured_at / sync_version / items
  - proof 字段：kind / note_id / note_url / title / excerpt / author / rating /
                rating_reason / matched_store / anchor_score / raw_query / client_ip_salt
  - sync_version 不符 → 409 拒绝
  - (participant_id, task_id, proof_seq) 幂等去重
  - gate_status 唯一权威：accepted 计酬 / pending 不结算 / rejected 记录原因

用法：
  python3 crowd_ingest.py --dry-run proof.jsonl          # 只校验不落库
  python3 crowd_ingest.py --ingest proof.jsonl            # 校验+落库+状态回写
  # 或作为 HTTP 服务被插件 POST（见底部示例）
"""
import argparse
import hashlib
import json
import pathlib
import sys
import uuid

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "vendor" / "pipeline"))

import common as C  # noqa: E402
import data_gate as G  # noqa: E402

SYNC_VERSION = 1
RATING_MIN_REASON_LEN = 8
UNIT_PRICE = {"note": 0.5, "rating": 1.0}  # 试点价（元/条）

# ---------------------------------------------------------------- 校验
def _envelope_schema():
    return {
        "required": ["participant_id", "task_id", "proof_seq", "captured_at", "sync_version", "items"],
        "fields": {
            "participant_id": {"type": "str", "min_length": 8, "max_length": 64},
            "task_id": {"type": "int", "min": 1},
            "proof_seq": {"type": "int", "min": 0},
            "sync_version": {"type": "int", "enum": [SYNC_VERSION]},
            "captured_at": {"type": "str", "min_length": 19},
            "items": {"type": "list", "min_length": 1, "max_length": 50},
        },
    }


def _item_schema():
    return {
        "required": ["kind", "note_id", "note_url", "raw_query"],
        "fields": {
            "kind": {"type": "str", "enum": ["note", "rating"]},
            "note_id": {"type": "str", "min_length": 6, "max_length": 40},
            "note_url": {"type": "str", "url": True, "max_length": 512},
            "title": {"type": "str", "max_length": 200},
            "excerpt": {"type": "str", "max_length": 300},
            "author": {"type": "str", "max_length": 80},
            "rating": {"type": "number", "min": 1, "max": 5},
            "rating_reason": {"type": "str", "max_length": 300},
            "matched_store": {"type": "str", "max_length": 80},
            "anchor_score": {"type": "number", "min": 0, "max": 1},
            "raw_query": {"type": "str", "min_length": 1, "max_length": 80},
            "client_ip_salt": {"type": "str", "min_length": 6, "max_length": 64},
        },
    }


def _dedupe_key(item):
    """指纹：cjk_norm(title) + note_id，防同篇笔记重复计酬。"""
    name = C.cjk_norm(item.get("title") or "")
    return hashlib.md5((name + "|" + item.get("note_id", "")).encode("utf-8")).hexdigest()


def validate_envelope(envelope):
    """返回 (issues, envelope)。信封级校验，sync_version 不符直接 409。"""
    issues = G.validate(envelope, _envelope_schema())
    if envelope.get("sync_version") != SYNC_VERSION:
        issues.append({"level": G.ERROR, "rule": "sync_version", "field": "sync_version",
                       "detail": f"契约版本不符：期望 {SYNC_VERSION}，实得 {envelope.get('sync_version')}"})
    return issues, envelope


def validate_items(items):
    """逐条 proof 校验：schema + 评分理由长度 + URL 域名。"""
    out, rejected = [], []
    for it in items:
        iss = G.validate(it, _item_schema())
        # URL 域名必须 xiaohongshu.com
        url = it.get("note_url") or ""
        if "xiaohongshu.com" not in url:
            iss.append({"level": G.ERROR, "rule": "url", "field": "note_url", "detail": "非小红书域名"})
        # rating 必须有理由且≥8字
        if it.get("kind") == "rating":
            reason = it.get("rating_reason") or ""
            if len(reason) < RATING_MIN_REASON_LEN:
                iss.append({"level": G.ERROR, "rule": "rating_reason", "field": "rating_reason",
                            "detail": f"评分理由需≥{RATING_MIN_REASON_LEN}字，实得{len(reason)}字"})
        if any(x["level"] == G.ERROR for x in iss):
            it["_reject"] = "; ".join(f"{x['field']}:{x['detail']}" for x in iss if x["level"] == G.ERROR)
            rejected.append(it)
        else:
            out.append(it)
    return out, rejected


def _fmt_ewkt(lng, lat):
    return f"SRID=4326;POINT({lng} {lat})" if lng and lat else None


def _check_participant(pid):
    """管控闸门：参与者必须 approved 才能回传（suspended/blacklisted/rejected/pending 一律拒）。

    返回 (ok, reason)。
    """
    if not pid:
        return False, "participant_id 为空"
    r = C.req("GET", f"/crowd_participants?select=participant_id,status,quota_day,total_effective&participant_id=eq.{pid}")
    if r.status_code != 200:
        return False, f"参与者状态查询失败 {r.status_code}"
    rows = r.json()
    if not rows:
        return False, "参与者不存在（未报名或编号错误）"
    st = rows[0].get("status")
    if st != "approved":
        return False, f"参与者状态为 {st}，非 approved（被暂停/驳回/拉黑或未通过审核）"
    return True, ""


def ingest(envelope, dry_run=False):
    """主流程：管控闸门 → 校验 → 幂等查重 → 落库 → 状态回写。返回结果 dict。"""
    env_issues, _ = validate_envelope(envelope)
    hard_reject = [x for x in env_issues if x["level"] == G.ERROR]
    if hard_reject:
        return {"status": "rejected", "reason": "; ".join(x["detail"] for x in hard_reject),
                "rejected_items": 0, "accepted_items": 0}

    pid = envelope["participant_id"]
    tid = envelope["task_id"]
    seq = envelope["proof_seq"]

    # 管控闸门：非 approved 参与者直接拒收（服务端兜底，插件侧也有前置拦截）
    ok, reason = _check_participant(pid)
    if not ok:
        return {"status": "rejected", "reason": f"参与者管控拦截: {reason}",
                "rejected_items": 0, "accepted_items": 0}

    # 幂等：同 (participant_id, task_id, proof_seq) 已存在 → 直接忽略
    dup = C.req("GET", f"/crowd_proofs?select=id&participant_id=eq.{pid}&task_id=eq.{tid}&proof_seq=eq.{seq}")
    if dup.status_code == 200 and dup.json():
        return {"status": "duplicate", "reason": "proof_seq 幂等忽略", "rejected_items": 0, "accepted_items": 0}

    items, rejected = validate_items(envelope.get("items") or [])

    if dry_run:
        return {"status": "dry_run", "rejected_items": len(rejected), "accepted_items": len(items),
                "reject_reasons": [i["_reject"] for i in rejected]}

    rows, accepted = [], 0
    for it in items:
        dk = _dedupe_key(it)
        # 全库去重（同指纹已 accepted → 拒收）
        ddup = C.req("GET", f"/crowd_proofs?select=id&dedupe_key=eq.{dk}&gate_status=eq.accepted")
        if ddup.status_code == 200 and ddup.json():
            it["_reject"] = "同篇笔记已收录（dedupe_key 重复）"
            rejected.append(it)
            continue
        row = {
            "participant_id": pid, "task_id": tid, "proof_seq": seq,
            "captured_at": envelope.get("captured_at"), "sync_version": SYNC_VERSION,
            "kind": it.get("kind"), "note_id": it.get("note_id"), "note_url": it.get("note_url"),
            "title": it.get("title"), "excerpt": it.get("excerpt"),
            "author": _mask_author(it.get("author") or ""),  # 入库脱敏
            "rating": it.get("rating"), "rating_reason": it.get("rating_reason"),
            "matched_store": it.get("matched_store"), "anchor_score": it.get("anchor_score"),
            "raw_query": it.get("raw_query"), "client_ip_salt": it.get("client_ip_salt"),
            "gate_status": "accepted", "dedupe_key": dk,
        }
        r = C.req("POST", "/crowd_proofs", json=row)
        if r.status_code in (200, 201):
            accepted += 1
            # rating → crowd_reviews
            if it.get("kind") == "rating" and it.get("rating") is not None:
                _write_review(pid, tid, it, row)
        else:
            it["_reject"] = f"落库失败 {r.status_code}"
            rejected.append(it)

    # 状态回写：crowd_tasks.progress 累计
    _update_task_progress(tid, accepted)
    # 参与者累计有效条数回写
    if accepted:
        _update_participant_stats(pid, accepted)

    return {"status": "ok", "rejected_items": len(rejected), "accepted_items": accepted,
            "reject_reasons": [i["_reject"] for i in rejected][:10]}


def _update_participant_stats(pid, accepted):
    """累计参与者有效条数（settlements 计酬依据之一）。"""
    r = C.req("GET", f"/crowd_participants?select=total_effective&participant_id=eq.{pid}")
    if r.status_code == 200 and r.json():
        cur = (r.json()[0].get("total_effective") or 0) + accepted
        C.req("PATCH", f"/crowd_participants?participant_id=eq.{pid}",
              json={"total_effective": cur, "last_active_at": "now()"})


def _mask_author(name):
    """作者昵称脱敏：仅保留首尾字符，中间打码。"""
    if not name:
        return ""
    if len(name) <= 2:
        return name[0] + "*"
    return name[0] + "*" * (len(name) - 2) + name[-1]


def _write_review(pid, tid, item, proof_row):
    """rating 类 proof 落 crowd_reviews（锚定店由 entity_match 二次解析，此处存 matched_store 原文）。"""
    review = {
        "participant_id": pid, "task_id": tid,
        "store_name": item.get("matched_store") or "",
        "rating": item.get("rating"), "rating_reason": item.get("rating_reason"),
        "note_id": item.get("note_id"), "captured_at": proof_row.get("captured_at"),
        "trust_level": "crowd_single",
    }
    r = C.req("POST", "/crowd_reviews", json=review)
    if r.status_code not in (200, 201):
        print(f"[crowd] review 落库失败: {r.status_code}")


def _update_task_progress(tid, accepted):
    if accepted <= 0:
        return
    # 读取当前进度并累加（crowd_tasks 表；不存在则忽略，等待 dev/PM 建表后生效）
    cur = C.req("GET", f"/crowd_tasks?select=progress,status&task_id=eq.{tid}")
    if cur.status_code == 200 and cur.json():
        row = cur.json()[0]
        new_progress = (row.get("progress") or 0) + accepted
        new_status = "fulfilled" if new_progress >= (row.get("kpi_min") or 5) else "in_progress"
        C.req("PATCH", f"/crowd_tasks?task_id=eq.{tid}",
              json={"progress": new_progress, "status": new_status})


def _read_input(path):
    p = pathlib.Path(path)
    if not p.exists():
        sys.exit(f"找不到输入: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest", metavar="FILE", help="校验并落库")
    ap.add_argument("--dry-run", metavar="FILE", help="只校验不落库")
    a = ap.parse_args()

    target = a.ingest or a.dry_run
    if not target:
        ap.print_help()
        sys.exit(0)
    env = _read_input(target)
    # 兼容：直接传 envelope 或 {envelope: {...}}
    if "envelope" in env and "items" not in env:
        env = env["envelope"]
    dry = a.dry_run is not None
    res = ingest(env, dry_run=dry)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res["status"] in ("ok", "dry_run", "duplicate") else 1)
