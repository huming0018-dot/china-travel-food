"""Transport- and project-independent notification cadence policy.

Extracted unchanged from the food consumer. The caller owns persistence,
rendering, delivery, clock and digest. No credentials, I/O or business defaults.
Not a scheduler or transactional outbox; existing persistence semantics remain.
"""
INFO, WARN, ACTION, RESOLVED = "INFO", "WARN", "ACTION", "RESOLVED"


class NotificationPolicy:
    def __init__(self, *, load, save, deliver, render, render_nudge, clock, digest):
        self.load, self.save, self.deliver = load, save, deliver
        self.render, self.clock, self.digest = render, clock, digest
        self.render_nudge = render_nudge

    def _record(self, L, key, level, full, **extra):
        rec = L.get(key, {})
        rec.update({"level": level, "last_ts": int(self.clock()),
                    "last_hash": self.digest(full), "count": rec.get("count", 0) + 1})
        rec.update(extra)
        L[key] = rec
        return rec


    # ────────────────────── 对外 API ──────────────────────
    def info(self, body, key, cadence, footer=None):
        """例行心跳：仅当距上次 ≥ cadence 才推。"""
        header, full = self.render(INFO, body, footer=footer)
        L = self.load()
        rec = L.get(key)
        if rec and int(self.clock()) - int(rec.get("last_ts", 0)) < cadence:
            return False
        ok = self.deliver(header, full)
        if ok:
            self._record(L, key, INFO, full)
            self.save(L)
        return ok


    def warn(self, body, key, cooldown, header_title=None):
        """自动处理中的问题：同 key 按 cooldown 折叠，不重复刷屏。
        内容变化也不再触发新告警，避免动态数字导致冷却失效。"""
        header, full = self.render(WARN, body)
        L = self.load()
        rec = L.get(key)
        # 只要key相同且在冷却期内，不管内容怎么变都不发
        if rec and int(self.clock()) - int(rec.get("last_ts", 0)) < cooldown:
            return False
        ok = self.deliver(header, full)
        if ok:
            self._record(L, key, WARN, full, state="open")
            self.save(L)
        return ok


    def action(self, body, key, action_text, nudge_schedule, footer=None):
        """需要用户处理：首次立即推；之后按 nudge_schedule 有界提醒；用尽不刷屏。
        若用户已处理（调用方应改走 resolve），不重复。"""
        header, full = self.render(ACTION, body, action=action_text, footer=footer)
        L = self.load()
        rec = L.get(key)
        now_i = int(self.clock())
        if rec and rec.get("state") == "resolved":
            return False
        if not rec:
            ok = self.deliver(header, full)
            if ok:
                self._record(L, key, ACTION, full, state="open", nudges=0, opened=now_i)
                self.save(L)
            return ok
        # 已开过单：按计划决定是否提醒
        nudges = int(rec.get("nudges", 0))
        if nudges >= len(nudge_schedule):
            return False
        due_at = int(rec.get("last_ts", 0)) + int(nudge_schedule[nudges])
        if now_i < due_at:
            return False
        ok = self.deliver(header, self.render_nudge(full, nudges + 1, len(nudge_schedule)))
        if ok:
            rec.update({"last_ts": now_i, "nudges": nudges + 1, "last_hash": self.digest(full)})
            L[key] = rec
            self.save(L)
        return ok


    def resolve(self, body, key, footer=None):
        """问题解决：每个 key 只推一条收尾；未开过单不推。"""
        L = self.load()
        rec = L.get(key)
        if not rec or rec.get("state") == "resolved":
            return False
        header, full = self.render(RESOLVED, body, footer=footer)
        ok = self.deliver(header, full)
        if ok:
            rec.update({"state": "resolved", "level": RESOLVED,
                        "last_ts": int(self.clock()), "last_hash": self.digest(full)})
            L[key] = rec
            self.save(L)
        return ok
