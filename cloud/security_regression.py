#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
security_regression.py — 众包系统安全回归测试（每次迭代/上线前必跑）

把安全攻击审计（SECURITY_AUDIT_20261002.md）的 6 个攻击用例固化为自动化回归：
  R1  H1 日配额强制      —— quota=3 回传 5 条只收 3
  R2  H2 跨参与者伪造    —— envelope.participant_id 与调用参数不一致 → participant_id_mismatch
  R3  H3 编号枚举        —— 不存在/pending/不存在 → 统一 participant_unavailable
  R4  M1 报名XSS         —— display_name/contact 含 < > → 被 RLS 拒
  R5  M2 自定超大配额    —— quota_day=999999 → 被 RLS 拒
  R6  M3 同title去重     —— 同 title 3 个 note_id → 仅 1 条入库

退出码：0=全部通过；1=存在失败（具体失败项打印在 stdout）。
安全：测试数据自动清理（按外键依赖顺序），不触碰正式任务包 #1/#2。
用法：
  export HTTPS_PROXY=http://127.0.0.1:7897 && export FOOD_APP_DIR="$(pwd)/app"
  python3 cloud/security_regression.py
"""
import json
import pathlib
import sys
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "vendor" / "pipeline"))

import common as C  # noqa: E402

ENV = {}
for line in open(HERE.parent / "app" / ".env.local"):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        ENV[k] = v.strip()

REST = ENV["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/") + "/rest/v1"
ANON = ENV["NEXT_PUBLIC_SUPABASE_ANON_KEY"]
HEADERS = {"apikey": ANON, "Authorization": "Bearer " + ANON, "Content-Type": "application/json"}

# 测试用唯一前缀（避免与历史残留冲突）
PREFIX = "RGT"  # regression test
CLEANUP_PIDS = []
CLEANUP_TASKS = []
FAILS = []


def anon(method, path, body=None):
    req = urllib.request.Request(REST + path, method=method, headers=HEADERS,
                                 data=json.dumps(body).encode() if body else None)
    try:
        r = urllib.request.urlopen(req, timeout=30)
        txt = r.read().decode()
        try:
            return r.status, json.loads(txt) if txt else {}
        except Exception:
            return r.status, txt[:120]
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode()) if e.read else {}
        except Exception:
            return e.code, {"message": "http_error"}


def rpc(fn, body):
    return anon("POST", "/rpc/" + fn, body)


def check(name, cond, detail=""):
    mark = "✅" if cond else "❌"
    print(f"  {mark} {name}" + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def cleanup():
    """按外键依赖顺序清理：proofs → settlements → reviews → participants → tasks"""
    for pid in CLEANUP_PIDS:
        C.req("DELETE", f"/crowd_proofs?participant_id=eq.{pid}")
        C.req("DELETE", f"/crowd_reviews?participant_id=eq.{pid}")
        C.req("DELETE", f"/crowd_settlements?participant_id=eq.{pid}")
        C.req("DELETE", f"/crowd_participants?participant_id=eq.{pid}")
    for tid in CLEANUP_TASKS:
        C.req("DELETE", f"/crowd_tasks?task_id=eq.{tid}")


def main():
    print("═══ 众包安全回归测试 ═══\n")

    # ---------- 准备：高 kpi 任务包 + 测试参与者 ----------
    C.req("POST", "/crowd_tasks", json={"pack_type": "store", "pack": [PREFIX + "任务"],
                                        "target": "notes", "kpi_min": 1000,
                                        "quota_day": 20, "status": "open"})
    r = C.req("GET", "/crowd_tasks?order=task_id.desc&limit=1&select=task_id")
    tid = r.json()[0]["task_id"]
    CLEANUP_TASKS.append(tid)

    # R1 参与者 quota=3
    C.req("POST", "/crowd_participants", json={"participant_id": f"{PREFIX}-Q3", "display_name": "q3",
                                               "contact": "q3@x.com", "status": "approved", "quota_day": 3})
    CLEANUP_PIDS.append(f"{PREFIX}-Q3")
    # R2/R6 参与者 quota=50
    C.req("POST", "/crowd_participants", json={"participant_id": f"{PREFIX}-OK", "display_name": "ok",
                                               "contact": "ok@x.com", "status": "approved", "quota_day": 50})
    CLEANUP_PIDS.append(f"{PREFIX}-OK")
    # R3 pending 参与者（H3 用）
    C.req("POST", "/crowd_participants", json={"participant_id": f"{PREFIX}-PEND", "display_name": "p",
                                               "contact": "p@x.com", "status": "pending"})
    CLEANUP_PIDS.append(f"{PREFIX}-PEND")

    # ---------- R1 日配额强制 ----------
    print("R1 H1 日配额强制（quota=3 → 单批塞 8 条只收 3，次日/二次回传被拒）")
    # 单批 8 条不同 title（避开 M3 同title去重），验证逐条限流
    st, body = rpc("crowd_submit_proof", {
        "p_participant_id": f"{PREFIX}-Q3",
        "p_envelope": {"participant_id": f"{PREFIX}-Q3", "task_id": tid, "proof_seq": 1,
                       "sync_version": 1,
                       "items": [{"kind": "note", "note_id": f"{PREFIX}-r1-{i}",
                                  "note_url": "https://www.xiaohongshu.com/explore/r",
                                  "title": f"标题{i}"} for i in range(8)]}})
    got1 = body.get("accepted") if isinstance(body, dict) else None
    check("单批8条只收3条（逐条限流）", got1 == 3, f"got={got1}")
    # 第二次回传（不同 note_id/title，但当日配额已满 → 批前快速失败）
    st2, body2 = rpc("crowd_submit_proof", {
        "p_participant_id": f"{PREFIX}-Q3",
        "p_envelope": {"participant_id": f"{PREFIX}-Q3", "task_id": tid, "proof_seq": 2,
                       "sync_version": 1,
                       "items": [{"kind": "note", "note_id": f"{PREFIX}-r1b-{i}",
                                  "note_url": "https://www.xiaohongshu.com/explore/r",
                                  "title": f"标题B{i}"} for i in range(3)]}})
    check("二次回传被拒 quota_exceeded", isinstance(body2, dict) and body2.get("reason") == "quota_exceeded",
          f"got={body2}")

    # ---------- R2 跨参与者伪造 ----------
    print("R2 H2 跨参与者伪造（调用 P-RGT-OK，envelope 填 P-RGT-Q3）")
    st, body = rpc("crowd_submit_proof", {
        "p_participant_id": f"{PREFIX}-OK",
        "p_envelope": {"participant_id": f"{PREFIX}-Q3", "task_id": tid, "proof_seq": 100,
                       "sync_version": 1,
                       "items": [{"kind": "note", "note_id": f"{PREFIX}-r2",
                                  "note_url": "https://www.xiaohongshu.com/explore/r", "title": "t"}]}})
    check("伪造被拒 participant_id_mismatch",
          isinstance(body, dict) and body.get("reason") == "participant_id_mismatch", f"got={body}")

    # ---------- R3 编号枚举 ----------
    print("R3 H3 编号枚举（不存在 / pending / 不存在 → 统一 unavailable）")
    reasons = []
    for pid in [f"{PREFIX}-NOPE", f"{PREFIX}-PEND", f"{PREFIX}-NOPE2"]:
        _, b = rpc("crowd_fetch_tasks", {"p_participant_id": pid})
        reasons.append(b.get("reason") if isinstance(b, dict) else None)
    check("三种输入同文案 participant_unavailable",
          len(set(reasons)) == 1 and reasons[0] == "participant_unavailable", f"got={reasons}")

    # ---------- R4 报名XSS ----------
    print("R4 M1 报名XSS（< > 应被 RLS 拒）")
    ok_xss = True
    for payload in [
        {"participant_id": f"{PREFIX}-X1", "display_name": "<script>alert(1)</script>", "contact": "a@x.com", "status": "pending"},
        {"participant_id": f"{PREFIX}-X2", "display_name": "正常名", "contact": "<img src=x onerror=alert(2)>", "status": "pending"},
    ]:
        st, _ = anon("POST", "/crowd_participants", payload)
        if st != 401:  # 42501 RLS 拒绝（PostgREST 报 401）
            ok_xss = False
    check("XSS 报名全部被拒", ok_xss)

    # ---------- R5 自定配额 ----------
    print("R5 M2 报名自定 quota_day=999999（应被 RLS 拒）")
    st, _ = anon("POST", "/crowd_participants", {"participant_id": f"{PREFIX}-X3", "display_name": "x",
                                                 "contact": "x@x.com", "status": "pending", "quota_day": 999999})
    check("自定配额被拒", st == 401, f"st={st}")

    # ---------- R6 同title去重 ----------
    print("R6 M3 同 title 不同 note_id（应仅 1 条入库）")
    st, body = rpc("crowd_submit_proof", {
        "p_participant_id": f"{PREFIX}-OK",
        "p_envelope": {"participant_id": f"{PREFIX}-OK", "task_id": tid, "proof_seq": 200,
                       "sync_version": 1,
                       "items": [{"kind": "note", "note_id": f"{PREFIX}-d{i}",
                                  "note_url": "https://www.xiaohongshu.com/explore/r",
                                  "title": "同一篇笔记复制"} for i in range(3)]}})
    r = C.req("GET", f"/crowd_proofs?participant_id=eq.{PREFIX}-OK&note_id=like.{PREFIX}-d%&select=id")
    n = len(r.json())
    check("同 title 仅入 1 条", n == 1, f"入库 {n} 条")

    # ---------- 附加：anon 直连 5 表应被拒 ----------
    print("R7 anon 直连 5 表（RLS 零权限）")
    ok_rls = True
    for t in ["crowd_participants", "crowd_tasks", "crowd_proofs", "crowd_reviews", "crowd_settlements"]:
        st, _ = anon("GET", f"/{t}?select=*&limit=1")
        if st != 401:
            ok_rls = False
    check("anon 直连全部 401", ok_rls)

    # ---------- 收尾 ----------
    cleanup()
    print("\n═══ 结果 ═══")
    if FAILS:
        print(f"❌ 失败 {len(FAILS)} 项: {FAILS}")
        sys.exit(1)
    print("✅ 全部通过（R1-R7）")
    sys.exit(0)


if __name__ == "__main__":
    main()
