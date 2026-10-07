'use strict';
const $ = id => document.getElementById(id);
let current, viewTicket = 0, actions = 0;
const labels = {idle: '等待任务', search: '自动搜索', search_done: '选择下一篇笔记', note: '浏览与采集', reopen_note: '恢复笔记浏览'};
// Desktop extension diagnostics are explicit and separate from collection consent.
$('diagnostics_section').hidden = !!globalThis.CrowdNative;
const errors = {invalid_invite: '邀请无效，请重新打开邀请链接', invite_expired: '邀请已过期，请联系邀请人', invite_full: '本批参与名额已满', installation_already_joined: '本设备已加入另一批邀请，请继续原参与身份', portal_not_configured: '安装包尚未接通参与入口', release_not_ready: '此设备的正式安装渠道尚未开放', backend_unavailable: '暂时连接不上，请稍后重试，已有进度会保留', consent_required: '请先确认自愿参与', approval_required: '账户尚未获得中台审核批准', login_required: '请在下方或工作页面登录小红书后继续', captcha: '遇到验证，请在工作页面处理', rate_limit: '平台已限流，已暂停', user_stopped: '已停止', logged_out: '已退出', system_suspended: '系统暂停或本次批次结束，进度已保存，可重新启动', lease_lost: '任务已由其他设备领取，证据保留待审'};
async function send(type, extra = {}) {
  const reply = globalThis.CrowdNative ? await CrowdNative.command(type, extra) : await chrome.runtime.sendMessage({type, ...extra});
  if (!reply.ok) throw new Error(reply.error); return reply.data;
}
errors.page_timeout = '页面准备超时。可点击「查看采集页面」检查加载、登录或验证情况，并开启运行诊断。';
errors.work_page_missing = '采集页面尚未打开，请先开始或继续任务。';
async function refresh() {
  const ticket = ++viewTicket;
  const data = await send('state'), s = data.agent, p = data.status;
  if (ticket !== viewTicket) return;
  current = data;
  $('welcome').textContent = s.enabled ? '正在自动采集，你可以随时停止。' : errors[s.last_error] || (data.invited ? '邀请已接续。确认参与即可自动开工。' : data.session ? '参与身份已就绪，点击继续即可开工。' : '请从邀请链接打开，无需注册中台账号。');
  $('start').hidden = !data.session;
  $('consent').textContent = data.session && !data.invited ? '同意并继续' : '同意并开始';
  const fields = {'中台账户': data.session ? '已登录' : '未登录', '参与状态': p.participant?.status || p.error || '尚未报名', '自动采集': s.enabled ? '运行中' : '已停止', '当前阶段': labels[s.phase] || s.phase,
    '任务': s.task?.query || '暂无', '服务端接收': p.received ?? '—', '核验有效': p.verified ?? '—', '已记奖励': p.reward_fen == null ? '—' : '¥' + (p.reward_fen / 100).toFixed(2), '累计余数': p.remainder ?? '—', '待回传 / 待处理': s.outbox.length + ' / ' + s.rejected.length, '最近提示': errors[s.last_error] || s.last_error || '无'};
  $('status').replaceChildren();
  for (const [name, value] of Object.entries(fields)) { const dt = document.createElement('dt'), dd = document.createElement('dd'); dt.textContent = name; dd.textContent = String(value); $('status').append(dt, dd); }
  $('agree').checked = s.consent === CrowdCore.CONSENT;
  $('diagnostics').checked = data.diagnostics?.enabled === true;
  $('diagnostics').disabled = !data.session || actions > 0;
  $('diagnostics_status').textContent = data.diagnostics?.pending_clear ? '诊断已关闭；联网后清除云端旧状态。' : data.diagnostics?.error ? '诊断暂未送达，联网后自动重试，不影响采集。' : data.diagnostics?.sent_at ? '最近诊断送达：' + new Date(data.diagnostics.sent_at).toLocaleTimeString('zh-CN') : data.diagnostics?.enabled ? '诊断已开启，正在准备发送。' : '诊断未开启。';
}
async function action(fn) { ++actions; ++viewTicket; $('diagnostics').disabled = true; const buttons = [...document.querySelectorAll('button')]; buttons.forEach(b => b.disabled = b.id !== 'stop'); try { $('message').textContent = ''; await fn(); await refresh(); } catch (e) { $('message').textContent = e.message === 'cancelled' ? '已取消启动' : errors[e.message] || e.message; } finally { --actions; buttons.forEach(b => b.disabled = actions > 0 && b.id !== 'stop'); $('diagnostics').disabled = actions > 0 || !current?.session; } }
$('login').addEventListener('submit', e => { e.preventDefault(); action(() => send('login', {email: $('email').value, password: $('password').value}).then(() => { $('password').value = ''; })); });
$('signup').onclick = () => action(async () => { const r = await send('login', {email: $('email').value, password: $('password').value, signup: true}); $('password').value = ''; if (r.confirmation_required) $('message').textContent = '请到邮箱确认账户，再回来登录。'; });
$('consent').onclick = () => action(async () => { if (!$('agree').checked) throw new Error('consent_required'); if (current?.invited) await send('join', {consent: CrowdCore.CONSENT}); else { await send('consent'); await send('start'); } });
$('invite_form').onsubmit = e => { e.preventDefault(); action(async () => { await send('receive_invite', {invite: $('invite_value').value}); $('invite_value').value = ''; $('invitation').open = false; }); };
for (const type of ['start', 'stop', 'logout', 'open_login']) $(type).onclick = () => action(() => send(type));
$('export').onclick = () => action(async () => { const data = await send('export'), text = JSON.stringify(data, null, 2); if (globalThis.CrowdNative) { await CrowdNative.download(text); return; } const blob = new Blob([text], {type: 'application/json'}); const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = 'crowd-pending-evidence.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
$('refresh').onclick = () => action(refresh);
$('diagnostics').onchange = () => action(() => send('diagnostics', {enabled: $('diagnostics').checked}));
$('inspect_work_page').onclick = () => action(() => send('inspect_work_page'));
action(refresh);
globalThis.addEventListener('crowd_invite', () => action(refresh));
setInterval(() => { if (!document.hidden && !actions) refresh().catch(() => {}); }, 10000);
