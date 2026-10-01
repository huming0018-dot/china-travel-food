#!/usr/bin/env python3
# shard_s12_submit.py — S12 本地提交包装器
# 复用 cloud/findings_extractor.py 的确定性校验（冻结标准件），
# 仅把落盘目标重定向到本分片 findings_s12.jsonl，并 append 断点。
# 用法: echo '<payload json>' | python3 shard_s12_submit.py
#   或:  python3 shard_s12_submit.py --file payload.json
import sys, os, json, pathlib, argparse

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "cloud"))
import findings_extractor as fe

# 重定向本分片输出
LEDGER = ROOT / "research" / "post_record"
LEDGER.mkdir(parents=True, exist_ok=True)
fe.FINDINGS = LEDGER / "findings_s12.jsonl"

DONE = LEDGER / "shards" / "s12.done"
FAILED = LEDGER / "shards" / "s12.failed"
DONE.parent.mkdir(parents=True, exist_ok=True)


def submit(payload: dict):
    kept = fe.validate(payload, apply=True)
    rid = payload.get("restaurant_id")
    # 无论有无 findings，只要跑完即记 done
    with DONE.open("a", encoding="utf-8") as fh:
        fh.write(str(rid) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    return kept


def mark_failed(rid, why=""):
    with FAILED.open("a", encoding="utf-8") as fh:
        fh.write(f"{rid}\t{why}\n")
        fh.flush()
        os.fsync(fh.fileno())
    with DONE.open("a", encoding="utf-8") as fh:
        fh.write(str(rid) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    a = ap.parse_args()
    if a.file:
        payload = json.loads(pathlib.Path(a.file).read_text(encoding="utf-8"))
    else:
        payload = json.loads(sys.stdin.read())
    submit(payload)
