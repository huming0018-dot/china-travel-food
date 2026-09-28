#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ugc_longrun.py — 真实 UGC 扩量长跑（容器常驻、低频、礼貌、只读采集+确定性写）。

设计约束（北极星 A5/A6 + 采集宪章）：
  - 设备无关：由容器 crontab 触发，不依赖任何用户设备/豆包会话。
  - 低频礼貌：环境变量控制；默认每轮只推进 UGC_BATCH(=5) 家，搜索间隔 UGC_SEARCH_GAP(=70s)
    （≥28s、≤2 次/分）；两 XHS 账号 + account_b 广州代理轮替（review_ugc_fill 内置 CoexistXhs）。
  - 退避不硬刷：速率/软限流由 xhs_api 内置（search_gap 翻倍封顶、空页 60–180s 长冷却）；
    本 wrapper 再加单轮墙钟超时（UGC_RUN_TIMEOUT=1500s），到点安静停止、等下一轮。
  - 不重复写库：review_ugc_fill 按 source_url 幂等；0-UGC 选择本身即天然续跑
    （已获真证据的店自动从待办集剔除），无需额外账本。
  - 账号死/接口配额耗尽不硬刷：捕获 AllAccountsBlocked / -100 → 经 notifier.action 推
    TG+飞书（一次），恢复后由看门狗/下轮自愈；常规进度不刷屏（心跳由 progress_broadcast 承担）。
  - 每批后自动跑 scoring_engine.py --apply 收敛口味分（确定性、幂等）。

只写 reviews（由 DB 触发器重算 taste）；绝不 PATCH restaurants 的 score_*。
"""
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
PIPE = os.environ.get("FOOD_PIPELINE_DIR", "/app/pipeline")
DATA = pathlib.Path(os.environ.get("FOOD_DATA_DIR", "/app/data"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PIPE))

BATCH = int(os.environ.get("UGC_BATCH", "5"))
MIN_PRICE = int(os.environ.get("UGC_MIN_PRICE", "500"))
SEARCH_GAP = os.environ.get("UGC_SEARCH_GAP", "70")
RUN_TIMEOUT = int(os.environ.get("UGC_RUN_TIMEOUT", "1500"))   # 25 分钟墙钟
STATE_F = pathlib.Path(DATA) / "ugc_longrun.json"


def _env():
    e = dict(os.environ)
    e["UGC_BATCH"] = str(BATCH)
    e["UGC_MIN_PRICE"] = str(MIN_PRICE)
    e["UGC_SEARCH_GAP"] = str(SEARCH_GAP)
    e["UGC_MIN_GAP"] = os.environ.get("UGC_MIN_GAP", "4.0")
    return e


def _run(cmd, timeout):
    try:
        p = subprocess.run([sys.executable] + cmd, cwd=str(HERE), env=_env(),
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -9, "[wrapper] 单轮墙钟超时，安静停止（不硬刷，等下一轮）"


def main():
    print(f"=== ugc_longrun {time.strftime('%Y-%m-%d %H:%M:%S')} "
          f"batch={BATCH} min_price={MIN_PRICE} gap={SEARCH_GAP}s timeout={RUN_TIMEOUT}s ===",
          flush=True)
    rc, out = _run(["review_ugc_fill.py", "--apply",
                    "--batch", str(BATCH), "--min-price", str(MIN_PRICE)], RUN_TIMEOUT)
    print(out[-4000:], flush=True)

    low = out.lower()
    account_dead = ("allaccountsblocked" in low or "-100" in low
                    or "无带 web_session" in out or "无可用 xhs 账号" in out)

    # 每批后收敛口味分（幂等）
    src, sout = _run(["/app/pipeline/scoring_engine.py", "--apply"], 300)
    print("--- scoring_engine ---\n" + (sout[-1500:]), flush=True)

    # 持久状态（供 work_progress / 复盘）
    state = {"updated_at": time.strftime("%Y-%m-%d %H:%M"),
             "batch": BATCH, "min_price": MIN_PRICE, "ugc_rc": rc,
             "account_dead": account_dead, "scoring_rc": src}
    try:
        STATE_F.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[warn] 状态写入失败: {e}", flush=True)

    # 仅账号真死才 ACTION；常规进度不刷屏
    try:
        import notifier
        if account_dead:
            notifier.action(
                "UGC 扩量长跑：XHS 账号疑似全部失效(-100/AllAccountsBlocked)，"
                "本轮安静停止、未硬刷。请按 xhs-login-runbook 扫码重登。",
                key="ugc_account_dead",
                action_text="打开容器 /app/data/router.log 与 xhs 账号目录，按 SOP 扫码重登 account_a/b")
        else:
            notifier.resolve("UGC 扩量长跑：账号已恢复，本轮正常推进。",
                             key="ugc_account_dead")
    except Exception as e:
        print(f"[warn] notifier 失败: {e}", flush=True)

    return 0 if not account_dead else 0   # 不把账号死当脚本错误（cron 不重试刷屏）


if __name__ == "__main__":
    sys.exit(main() or 0)
