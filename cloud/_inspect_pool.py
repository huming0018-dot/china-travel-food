import os
rows = []
for p in os.listdir("/proc"):
    if not p.isdigit():
        continue
    try:
        c = open(f"/proc/{p}/cmdline", "rb").read().replace(b"\x00", b" ").decode().strip()
    except Exception:
        continue
    if "gap_pool.py" in c or "gap_runner.py" in c:
        try:
            st = open(f"/proc/{p}/stat").read().split()
            start = st[21]
        except Exception:
            start = "?"
        rows.append((int(p), start, c))
for pid, start, c in sorted(rows):
    print(pid, "startclk", start, "|", c)
print("POOL_COUNT:", sum("gap_pool" in c for _, _, c in rows))
print("WORKER_COUNT:", sum("gap_runner" in c for _, _, c in rows))
