#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crowd_admin.py — 众包参与者管控 CLI（PM 窗口使用）

灵活报名后的审核/管控入口：
  - list [--status pending|approved|suspended|blacklisted|all]  列出参与者
  - approve <P-xxx> [--quota N] [--note 备注]                     调整配额/留档（报名即用，无需批准）
  - suspend <P-xxx> [--note 备注]                                暂停（拉不到新任务）
  - blacklist <P-xxx> [--note 备注]                              拉黑（永久拒绝回传）
  - reject <P-xxx> [--note 备注]                                  驳回报名
  - stats                                                        全局统计

用法示例：
  export HTTPS_PROXY=http://127.0.0.1:7897 && export FOOD_APP_DIR="$(pwd)/app"
  python3 cloud/crowd_admin.py list --status pending
  python3 cloud/crowd_admin.py approve TMP-LX3K8A --quota 20 --note "熟人推荐，试用期1周"
  python3 cloud/crowd_admin.py stats
"""
import argparse
import html
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "vendor" / "pipeline"))

import common as C  # noqa: E402

TABLE = "/crowd_participants"
VALID_STATUS = ("pending", "approved", "suspended", "blacklisted", "rejected")


def _row_fmt(r):
    """格式化一行参与者；昵称/联系方式做 HTML 转义兜底（防审核日志被粘贴渲染成 HTML 时触发 XSS）。"""
    name = html.escape(r.get('display_name') or '')
    contact = html.escape(r.get('contact') or '')
    return (f"  {r.get('participant_id'):<14} {r.get('status'):<12} "
            f"配额{r.get('quota_day') or '-'}/日 有效{r.get('total_effective') or 0} "
            f"拒收率{(r.get('reject_rate') or 0)*100:.0f}%  "
            f"昵称:{name} 联系:{contact} "
            f"来源:{html.escape(r.get('source') or '')}")


def cmd_list(args):
    st = args.status
    url = TABLE + "?select=*" + (f"&status=eq.{st}" if st != "all" else "")
    url += "&order=applied_at.asc&limit=200"
    r = C.req("GET", url)
    if r.status_code != 200:
        sys.exit(f"查询失败: {r.status_code} {r.text[:200]}")
    rows = r.json()
    if not rows:
        print(f"（无 {st} 状态记录）")
        return
    print(f"共 {len(rows)} 条（{st}）：")
    for row in rows:
        print(_row_fmt(row))


def _get_one(pid):
    r = C.req("GET", TABLE + f"?select=*&participant_id=eq.{pid}")
    if r.status_code != 200 or not r.json():
        sys.exit(f"找不到参与者 {pid}（确认编号是否正确）")
    return r.json()[0]


def cmd_approve(args):
    row = _get_one(args.pid)
    if row["status"] not in ("pending", "rejected"):
        sys.exit(f"{args.pid} 当前状态是 {row['status']}，不可批准")
    # v3.2.1 起报名走 crowd_register RPC（服务端直接生成 P-[A-Z0-9]{8} 编号），
    # 不再存在 TMP→P 主键变更；批准 = 原地 UPDATE（一步原子，无复制/删除竞态）
    body = {
        "status": "approved",
        "quota_day": args.quota,
        "reviewed_at": "now()",
        "review_note": (args.note or ""),
    }
    r = C.req("PATCH", TABLE + f"?participant_id=eq.{args.pid}", json=body)
    if r.status_code not in (200, 204):
        sys.exit(f"批准失败: {r.status_code} {r.text[:200]}")
    print(f"✅ 已批准 {args.pid}（配额 {args.quota}/日，原地 UPDATE 原子完成）")


def cmd_suspend(args):
    _get_one(args.pid)
    body = {"status": "suspended", "review_note": args.note or ""}
    r = C.req("PATCH", TABLE + f"?participant_id=eq.{args.pid}", json=body)
    if r.status_code not in (200, 204):
        sys.exit(f"暂停失败: {r.status_code} {r.text[:200]}")
    print(f"⏸ 已暂停 {args.pid}")


def cmd_blacklist(args):
    _get_one(args.pid)
    body = {"status": "blacklisted", "review_note": args.note or ""}
    r = C.req("PATCH", TABLE + f"?participant_id=eq.{args.pid}", json=body)
    if r.status_code not in (200, 204):
        sys.exit(f"拉黑失败: {r.status_code} {r.text[:200]}")
    print(f"⛔ 已拉黑 {args.pid}")


def cmd_reject(args):
    _get_one(args.pid)
    body = {"status": "rejected", "review_note": args.note or ""}
    r = C.req("PATCH", TABLE + f"?participant_id=eq.{args.pid}", json=body)
    if r.status_code not in (200, 204):
        sys.exit(f"驳回失败: {r.status_code} {r.text[:200]}")
    print(f"❌ 已驳回 {args.pid}")


def cmd_stats(args):
    out = {}
    for st in VALID_STATUS:
        r = C.req("GET", TABLE + f"?select=participant_id&status=eq.{st}")
        if r.status_code == 200:
            out[st] = len(r.json())
        else:
            out[st] = None  # 查询失败显示故障而非 0（外部审计 #52 表格项）
    print("参与者状态统计：")
    for k, v in out.items():
        print(f"  {k:<12} {'故障' if v is None else v}")
    # 任务包进度
    r = C.req("GET", "/crowd_tasks?select=task_id,status,progress,kpi_min&limit=50")
    if r.status_code == 200:
        tasks = r.json()
        print(f"\n任务包 {len(tasks)} 个：")
        for t in tasks:
            print(f"  #{t.get('task_id')} {t.get('status')} progress={t.get('progress')}/{t.get('kpi_min')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="众包参与者管控")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list"); p_list.add_argument("--status", default="all",
                        choices=["pending", "approved", "suspended", "blacklisted", "rejected", "all"])
    p_ap = sub.add_parser("approve"); p_ap.add_argument("pid"); p_ap.add_argument("--quota", type=int, default=20); p_ap.add_argument("--note", default="")
    p_su = sub.add_parser("suspend"); p_su.add_argument("pid"); p_su.add_argument("--note", default="")
    p_bl = sub.add_parser("blacklist"); p_bl.add_argument("pid"); p_bl.add_argument("--note", default="")
    p_rj = sub.add_parser("reject"); p_rj.add_argument("pid"); p_rj.add_argument("--note", default="")
    sub.add_parser("stats")
    args = ap.parse_args()

    handlers = {"list": cmd_list, "approve": cmd_approve, "suspend": cmd_suspend,
                "blacklist": cmd_blacklist, "reject": cmd_reject, "stats": cmd_stats}
    handlers[args.cmd](args)
