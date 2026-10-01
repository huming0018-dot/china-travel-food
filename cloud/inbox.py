#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inbox.py — 多窗口异步对话信箱（Git内）

让四个窗口（pm/dev/collector/qa）之间直接留言，不需要用户传话：
  - 任何窗口可向其他窗口留言（写入 INBOX/<收件人>.md）
  - 开工时 sync.sh 自动显示是否有新留言
  - 留言带时间戳+发件人，收件人读完可回复

用法：
  python3 cloud/inbox.py post <收件人> "留言内容"    # 给某窗口留言
  python3 cloud/inbox.py read <角色>                # 读给自己的留言（全部）
  python3 cloud/inbox.py list                       # 看所有留言
  python3 cloud/inbox.py clear <角色>               # 清空已读留言（收件人自己确认后）
"""
import sys, pathlib, datetime

HERE = pathlib.Path(__file__).resolve().parent
INBOX_DIR = HERE.parent / "INBOX"
ROLES = {"pm", "dev", "collector", "qa"}
CN = {"pm": "PM", "dev": "开发", "collector": "采集", "qa": "QA"}


def _f(role):
    return INBOX_DIR / f"{role}.md"


def post(to, msg):
    if to not in ROLES:
        print(f"❌ 收件人必须是: {sorted(ROLES)}")
        return
    now = datetime.datetime.now().strftime("%m-%d %H:%M")
    from_role = "qa"  # 默认发件人，可改进为环境变量
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    with open(_f(to), "a", encoding="utf-8") as f:
        f.write(f"\n--- {now} 来自[{from_role}] ---\n{msg}\n")
    print(f"✅ 已留言给 {CN.get(to,to)} (INBOX/{to}.md)")


def read(role):
    f = _f(role)
    if not f.exists():
        print(f"（{CN.get(role,role)}信箱为空）")
        return
    txt = f.read_text(encoding="utf-8").strip()
    if not txt:
        print(f"（{CN.get(role,role)}信箱为空）")
        return
    print(f"=== {CN.get(role,role)}信箱 ===")
    print(txt)


def list_all():
    for r in sorted(ROLES):
        f = _f(r)
        if f.exists() and f.read_text(encoding="utf-8").strip():
            print(f"📬 {CN.get(r,r)}: {f.read_text(encoding='utf-8').count('--- ')}条留言")


def clear(role):
    f = _f(role)
    if f.exists():
        f.write_text("", encoding="utf-8")
        print(f"✅ {CN.get(role,role)}信箱已清空")
    else:
        print("（无信箱文件）")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "post" and len(sys.argv) >= 4:
        post(sys.argv[2], " ".join(sys.argv[3:]))
    elif cmd == "read" and len(sys.argv) >= 3:
        read(sys.argv[2])
    elif cmd == "list":
        list_all()
    elif cmd == "clear" and len(sys.argv) >= 3:
        clear(sys.argv[2])
    else:
        print(__doc__)
