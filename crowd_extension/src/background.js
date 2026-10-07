/* Windows/macOS Chrome & Edge MV3. No automatic start on installation. */
if (typeof importScripts === 'function') importScripts('config.js', 'core.js', 'api.js', 'agent.js', 'join.js');
const storage = CrowdCore.accountStorage({
  async get(key) { return (await chrome.storage.local.get(key))[key]; },
  async set(key, value) { await chrome.storage.local.set({[key]: value}); }
});
if (chrome.storage.local.setAccessLevel) chrome.storage.local.setAccessLevel({accessLevel: 'TRUSTED_CONTEXTS'}).catch(console.error);
const runtime = {
  storage, now: Date.now, random: Math.random, uuid: () => crypto.randomUUID(),
  schedule: when => chrome.alarms.create('crowd_tick', {when: Math.max(when, Date.now() + 30000)}),
  cancel: () => chrome.alarms.clear('crowd_tick'),
  async open(url) {
    CrowdCore.navigationURL(url);
    const id = await storage.get('work_tab');
    if (id) { try { await chrome.tabs.update(id, {url, active: false}); return; } catch (_) {} }
    const tab = await chrome.tabs.create({url, active: false}); await storage.set('work_tab', tab.id);
  },
  async probe(action) {
    const id = await storage.get('work_tab');
    if (!id) return {ready: false};
    try { return await chrome.tabs.sendMessage(id, {type: 'crowd_probe', action}); }
    catch (_) { return {ready: false}; }
  },
  async close() {
    const id = await storage.get('work_tab');
    if (id) { try { await chrome.tabs.remove(id); } catch (_) {} await storage.set('work_tab', null); }
  }
};
const api = new CrowdAPI(CROWD_CONFIG, storage), agent = new CrowdAgent(runtime, api);
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (sender.id !== chrome.runtime.id) return;
  if (message.type === 'page_ready') {
    storage.get('work_tab').then(id => { if (id === sender.tab?.id) return agent.tick(); }).catch(console.error); return;
  }
  const allowed = [chrome.runtime.getURL('src/controller.html')];
  if (!allowed.includes(sender.url) || sender.tab?.url?.startsWith(CrowdCore.HOST)) return;
  (async () => {
    switch (message.type) {
      case 'state': return {agent: await agent.read(), session: !!(await storage.get('session')), invited: !!await storage.get('pending_invite'), status: await api.rpc('status').catch(e => ({error: e.message}))};
      case 'receive_invite': await storage.set('pending_invite', CrowdJoin.invite(message.invite, CROWD_CONFIG.portal)); return {};
      case 'join': {
        if (message.consent !== CrowdCore.CONSENT) throw new Error('consent_required');
        await agent.stop(); const generation = agent.generation;
        await CrowdJoin.join(api, storage, await storage.get('pending_invite'));
        if (generation !== agent.generation) throw new Error('cancelled');
        const s = await agent.read(); s.consent = CrowdCore.CONSENT; await agent.save(s);
        if (generation !== agent.generation) throw new Error('cancelled');
        await agent.start(); return {};
      }
      case 'login': await agent.stop(); return api.login(message.email, message.password, message.signup);
      case 'consent': {
        await agent.stop(); await api.rpc('register', {p_consent: CrowdCore.CONSENT});
        const s = await agent.read(); s.consent = CrowdCore.CONSENT; await agent.save(s); return {};
      }
      case 'start': await agent.start(); return {};
      case 'stop': await agent.stop(); return {};
      case 'logout': await agent.stop('logged_out'); await api.logout(); return {};
      case 'export': { const s = await agent.read(); return {outbox: s.outbox, rejected: s.rejected}; }
      case 'open_login': await agent.stop('login_required'); await chrome.tabs.create({url: CrowdCore.HOST, active: true}); return {};
      default: throw new Error('unknown_command');
    }
  })().then(data => reply({ok: true, data}), e => reply({ok: false, error: e.message}));
  return true;
});
chrome.runtime.onMessageExternal?.addListener((message, sender, reply) => {
  try {
    const u = new URL(sender.url), portal = new URL(CROWD_CONFIG.portal);
    if (u.origin !== portal.origin || u.pathname !== '/crowd' || message.type !== 'connect') return;
    const value = CrowdJoin.invite(message.invite, CROWD_CONFIG.portal);
    storage.set('pending_invite', value).then(() => chrome.tabs.create({url: chrome.runtime.getURL('src/controller.html'), active: true}))
      .then(() => reply({ok: true}), () => reply({ok: false}));
    return true;
  } catch (_) { return; }
});
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'crowd_tick') agent.tick().catch(console.error); });
chrome.runtime.onStartup.addListener(() => agent.tick().catch(console.error));
chrome.runtime.onInstalled.addListener((details = {reason: 'install'}) => {
  (async () => {
    if (details.reason === 'install') {
      // A private trial kit supplies an invitation, never consent or a session.
      if (/^[a-f0-9]{64}$/.test(CROWD_CONFIG.trialInvite || '') && !await storage.get('pending_invite') && !await storage.get('session'))
        await storage.set('pending_invite', CROWD_CONFIG.trialInvite);
      await chrome.runtime.openOptionsPage?.();
    }
    await agent.tick();
  })().catch(console.error);
});
chrome.tabs.onRemoved.addListener(id => {
  storage.get('work_tab').then(owned => { if (owned === id) return storage.set('work_tab', null); }).catch(console.error);
});
