import os
import signal
import time

targets = []
for p in os.listdir("/proc"):
    if not p.isdigit():
        continue
    try:
        c = open(f"/proc/{p}/cmdline", "rb").read().replace(b"\x00", b" ").decode()
    except Exception:
        continue
    # 只杀 python 跑的 pool/runner；排除本脚本自身
    if ("gap_pool.py" in c or "gap_runner.py" in c) and "python" in c:
        targets.append(int(p))

# 先杀 worker 再杀 pool
workers = [t for t in targets]
for pid in sorted(set(targets), reverse=True):
    try:
        os.kill(pid, signal.SIGTERM)
        print("TERM", pid)
    except ProcessLookupError:
        pass
    except Exception as e:
        print("ERR", pid, e)

time.sleep(4)
for pid in set(targets):
    if os.path.exists(f"/proc/{pid}"):
        try:
            os.kill(pid, signal.SIGKILL)
            print("KILL", pid)
        except Exception:
            pass

pres = "/app/data/POOL_RUNNING"
if os.path.exists(pres):
    os.remove(pres)
    print("removed presence")
print("stopped. targets were", sorted(set(targets)))
