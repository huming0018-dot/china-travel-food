/* Alarm driven: each transition is durable; no long timers in a service worker. */
(function (root) {
  'use strict';
  const C = root.CrowdCore;
  class CrowdAgent {
    constructor(runtime, api) { this.r = runtime; this.api = api; this.active = null; this.generation = 0; this.recover = false; }
    async read() { return {...C.initial(), ...await this.r.storage.get('agent')}; }
    async save(s) { await this.r.storage.set('agent', s); }
    async start() {
      const generation = this.generation;
      await this.active?.catch(() => {});
      const s = await this.read();
      if (s.consent !== C.CONSENT) throw new Error('consent_required');
      const status = await this.api.rpc('status');
      if (generation !== this.generation) throw new Error('cancelled');
      if (status.participant?.status !== 'approved') throw new Error('approval_required');
      if (s.phase === 'note') s.phase = 'reopen_note';
      if (s.phase === 'search') { s.phase = 'idle'; s.search_round = 0; }
      s.enabled = true; s.last_error = null; s.page_failures = 0; s.next_at = 0; s.last_tick = this.r.now();
      await this.save(s); await this.r.schedule(this.r.now() + 1000);
    }
    async stop(reason = 'user_stopped') {
      this.generation++; this.controller?.abort();
      // Wait for the single writer before persisting the stop; prevent stale saves.
      await this.active?.catch(() => {});
      const s = await this.read(); s.enabled = false; s.last_error = reason;
      await this.save(s); await this.r.cancel(); await this.r.close();
    }
    async tick(recover = false) {
      this.recover ||= recover;
      if (this.active) return this.active;
      this.controller = new AbortController();
      const gen = this.generation;
      const alive = () => { if (gen !== this.generation || this.controller.signal.aborted) throw new Error('cancelled'); };
      this.active = this.step(alive, this.controller.signal).finally(() => { this.active = null; });
      return this.active;
    }
    async step(alive, signal) {
      let s = await this.read(); const recover = this.recover; this.recover = false;
      if (!s.enabled) return;
      if (s.consent !== C.CONSENT) { s.enabled = false; s.last_error = 'consent_required'; await this.save(s); await this.r.cancel(); return; }
      const now = this.r.now();
      const day = new Date(now + 8 * 3600000).toISOString().slice(0, 10);
      if (s.day !== day) { s.day = day; s.visits = 0; }
      try {
        alive();
        // Restore active work, never a stopped/blocked participant. A long
        // suspension must restart dwell; wake detection is an alarm-gap heuristic.
        if (recover || (s.last_tick != null && now - s.last_tick > 120000)) {
          if (s.phase === 'note') { s.phase = 'reopen_note'; s.loaded_at = null; s.scrolls = 0; }
          else if (s.phase === 'search') { s.phase = 'idle'; s.search_round = 0; }
          // Keep persisted cooldowns, quota waits and evidence retry deadlines.
        }
        s.last_tick = now; await this.save(s); alive();
        // Repair a cleared alarm before network IO can suspend this worker.
        await this.r.schedule(Math.max(s.next_at, now + 30000)); alive();
        // Delivery runs even during collection cooldown. One stable UUID per record.
        if (s.outbox.length) {
          const item = s.outbox[0];
          if ((item.retry_at || 0) > now) { await this.r.schedule(item.retry_at); return; }
          const receipt = await this.api.rpc('submit', {p_request: item.request, p_task: item.task,
            p_lease: item.lease, p_record: item.record}, signal);
          alive();
          if (receipt.error === 'daily_quota') {
            item.retry_at = now + 3600000; await this.save(s); await this.r.schedule(item.retry_at); return;
          } else if (receipt.error === 'lease_expired') {
            const renewed = await this.api.rpc('claim', {p_task: item.task}, signal); alive();
            if (renewed.error === 'daily_quota') {
              item.retry_at = now + 3600000; s.last_error = 'daily_quota';
              await this.save(s); await this.r.schedule(item.retry_at); return;
            }
            if (renewed.error) throw new Error(renewed.error);
            if (renewed.task?.id === item.task) { item.lease = renewed.task.lease_token; s.task = renewed.task; }
            else { s.rejected.push({...item, reason: 'lease_lost'}); s.outbox.shift(); s.task = null; s.phase = 'idle'; }
          } else {
            s.outbox.shift();
            if (receipt.error) s.rejected.push({...item, reason: receipt.error});
            else {
              s.received += receipt.inserted ? 1 : 0;
              s.history = [...new Set([...s.history, item.record.standard.note_id])].slice(-2000);
              if (s.task?.id === item.task) { s.task.received = receipt.task_received; if (receipt.inserted && s.task.remaining_today != null) s.task.remaining_today--; }
            }
          }
          // Failed records remain exportable; bounded by stopping, never by deleting evidence.
          if (s.rejected.length >= 20) throw new Error('review_local_rejections');
          await this.save(s); await this.r.schedule(now + 30000); return;
        }
        if (s.next_at > now) { await this.r.schedule(s.next_at); return; }
        if (s.visits >= 60) { s.next_at = now + 3600000; await this.save(s); await this.r.schedule(s.next_at); return; }
        if (!s.task || Date.parse(s.task.lease_until) < now + 180000) {
          const claimed = await this.api.rpc('claim', {p_task: s.task?.id || null}, signal); alive();
          if (claimed.error === 'daily_quota') { s.next_at = now + 3600000; await this.save(s); await this.r.schedule(s.next_at); return; }
          if (claimed.error) throw new Error(claimed.error);
          if (!claimed.task) { s.task = null; s.phase = 'idle'; s.next_at = now + 300000; }
          else { if (s.task?.id !== claimed.task.id) { s.phase = 'idle'; s.seen = []; s.candidates = []; } s.task = claimed.task; }
        }
        if (!s.task) { await this.save(s); await this.r.schedule(s.next_at); return; }
        if (s.task.received >= s.task.target || (s.phase === 'search_done' && !s.candidates.length)) {
          const finished = await this.api.rpc('finish', {p_task: s.task.id, p_lease: s.task.lease_token}, signal); alive();
          if (finished.error) s.last_error = finished.error;
          s.task = null; s.phase = 'idle'; s.next_at = now + 60000;
        } else if (s.task.remaining_today === 0) {
          s.next_at = now + 3600000;
        } else if (s.phase === 'idle') {
          await this.r.open(C.HOST + '/search_result?keyword=' + encodeURIComponent(s.task.query) + '&source=web_search_result_notes'); alive();
          s.phase = 'search'; s.page_deadline = now + 120000; s.next_at = now + 30000;
        } else if (s.phase === 'search') {
          const page = await this.r.probe('search'); alive();
          const normalize = value => String(value || '').normalize('NFC').replace(/\s+/g, ' ').trim().toLowerCase();
          if ('keyword' in page && normalize(page.keyword) !== normalize(s.task.query)) throw new Error('page_mismatch');
          this.checkPage(page, s, now);
          if (page.ready) {
            const found = new Map(s.candidates.map(url => [C.noteURL(url).id, url]));
            for (const url of page.links) { try { const note = C.noteURL(url); if (!s.seen.includes(note.id) && !s.history.includes(note.id)) found.set(note.id, note.navigation); } catch (_) {} }
            s.candidates = [...found.values()].slice(0, 80);
            s.search_round = (s.search_round || 0) + 1;
            if (s.search_round < 3) { await this.r.probe('scroll'); alive(); s.next_at = now + C.between(30000, 45000, this.r.random); }
            else { s.search_round = 0; s.phase = 'search_done'; s.next_at = now + 30000; }
          }
        } else if (s.phase === 'search_done') {
          const url = s.candidates.shift(); const id = C.noteURL(url).id;
          // Mark before navigation: crashes cannot create infinite note loops.
          s.seen.push(id); s.visits++; s.note_id = id; s.note_url = url; s.phase = 'note'; s.loaded_at = null; s.scrolls = 0;
          s.dwell_ms = C.between(45000, 90000, this.r.random); s.page_deadline = now + 180000;
          s.next_at = now + 30000; await this.save(s);
          await this.r.open(url); alive();
        } else if (s.phase === 'reopen_note') {
          if (!s.note_url) { s.phase = 'idle'; s.next_at = now + 30000; }
          else {
            await this.r.open(s.note_url); alive(); s.phase = 'note'; s.loaded_at = null; s.scrolls = 0;
            s.page_deadline = now + 180000; s.next_at = now + 30000;
          }
        } else if (s.phase === 'note') {
          const page = await this.r.probe('note'); alive(); this.checkPage(page, s, now);
          if (page.ready) {
            if (page.record.standard.note_id !== s.note_id) throw new Error('wrong_note');
            if (s.loaded_at === null) s.loaded_at = now;
            if (now - s.loaded_at < s.dwell_ms || s.scrolls < 2) {
              await this.r.probe('scroll'); alive(); s.scrolls++; s.next_at = now + C.between(30000, 45000, this.r.random);
            } else {
              C.validate(page.record);
              s.outbox.push({request: this.r.uuid(), task: s.task.id, lease: s.task.lease_token, record: page.record});
              s.page_failures = 0;
              s.phase = 'search_done'; s.notes_in_session++; s.note_url = null; s.note_id = null; s.loaded_at = null;
              s.next_at = now + (s.notes_in_session % 8 === 0 ? C.between(300000, 600000, this.r.random) : C.between(30000, 60000, this.r.random));
            }
          }
        }
        await this.save(s); await this.r.schedule(Math.max(s.next_at, now + 30000));
      } catch (err) {
        if (err.message === 'cancelled' || signal.aborted) return;
        alive(); s.last_error = err.message;
        const pageFailure = ['page_timeout', 'page_loading', 'content_unavailable', 'probe_timeout'].includes(err.message);
        if (pageFailure) {
          s.page_failures = (s.page_failures || 0) + 1;
          if (s.page_failures >= 3) {
            s.enabled = false; await this.save(s); await this.r.cancel(); return;
          }
        }
        if (['captcha', 'rate_limit', 'login_required', 'page_mismatch', 'approval_required', 'consent_required', 'review_local_rejections'].includes(err.message) || err.status === 401 || err.status === 403) {
          s.enabled = false; await this.save(s); await this.r.cancel(); return;
        }
        if (pageFailure || err.message === 'wrong_note') {
          s.phase = 'idle'; s.candidates = []; s.task = null;
        }
        s.next_at = now + 60000;
        if (s.outbox.length) { const item = s.outbox[0]; item.retries = (item.retries || 0) + 1; item.retry_at = now + Math.min(900000, 60000 * 2 ** Math.min(item.retries - 1, 4)); s.next_at = item.retry_at; }
        await this.save(s); await this.r.schedule(s.next_at);
      }
    }
    checkPage(page, s, now) {
      if (page.gate) throw new Error(page.gate);
      if (page.ready) s.last_error = null;
      if (page.reopen) { s.phase = s.phase === 'note' ? 'reopen_note' : 'idle'; s.search_round = 0; s.next_at = now + 30000; return; }
      if (!page.ready) { if (now > s.page_deadline) throw new Error(['page_loading','content_unavailable','probe_timeout'].includes(page.reason) ? page.reason : 'page_timeout'); s.next_at = now + 30000; }
    }
  }
  root.CrowdAgent = CrowdAgent;
})(globalThis);
