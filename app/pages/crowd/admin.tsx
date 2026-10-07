import Head from 'next/head';
import { useEffect, useState } from 'react';
export default function CrowdPublisher() {
  const [key, setKey] = useState(''), [result, setResult] = useState<{ link: string; qr: string; expires_at: string }>(), [message, setMessage] = useState(''), [busy, setBusy] = useState(false), [ready, setReady] = useState(false), [devices, setDevices] = useState<string[]>([]);
  const [received, setReceived] = useState<any[]>([]), [loaded, setLoaded] = useState(false);
  const names: Record<string, string> = { android: '安卓 / 兼容安卓的华为', windows: 'Windows', macos: 'Mac', ios: 'iPhone / iPad', harmony: '原生鸿蒙' };
  useEffect(() => { fetch('/api/crowd/manifest', { cache: 'no-store' }).then(r => r.json()).then(data => { setReady(data.ready === true); setDevices(Object.keys(data.releases || {}).map(os => names[os]).filter(Boolean)); }).catch(() => {}); }, []);
  const sms = result ? '邀请你自愿参加公开笔记研究。点链接安装并打开客户端，同意参与、首次登录小红书后自动执行，可随时停止：\n' + result.link : '';
  async function copySMS() { try { await navigator.clipboard.writeText(sms); setMessage('整条短信已复制，粘贴发给朋友即可。'); } catch { const field = document.querySelector<HTMLTextAreaElement>('textarea[aria-label="分发短信"]'); field?.focus(); field?.select(); setMessage('短信已选中，请按复制，再粘贴发给朋友。'); } }
  async function recovery(action: 'list' | 'export') {
    setBusy(true); setMessage('');
    try {
      const records: any[] = []; let after_id = 0;
      for (let page = 0; page < 100; page++) {
        const response = await fetch('/api/crowd/data', { method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key }, body: JSON.stringify({ action, after_id }) });
        const body = await response.json(); if (!response.ok || !Array.isArray(body.data)) throw new Error(body.error || 'backend_unavailable');
        if (action === 'list') { setReceived(body.data); setLoaded(true); setMessage('已读取待核验记录，最多显示前 100 条。'); return; }
        if (!body.data.length) {
          if (!records.length) { setMessage('目前没有已核验证据；新回传记录会先进入待核验区。'); return; }
          const file = new Blob([records.map(record => JSON.stringify(record)).join('\n') + '\n'], { type: 'application/x-ndjson;charset=utf-8' });
          const url = URL.createObjectURL(file), link = document.createElement('a'); link.href = url; link.download = 'crowd_v4_verified.jsonl'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
          setMessage('已下载 ' + records.length + ' 条已核验证据，包含标准字段、非标字段和原文。'); return;
        }
        const next = Math.max(...body.data.map((record: any) => record.proof_id));
        if (!Number.isSafeInteger(next) || next <= after_id) throw new Error('backend_unavailable');
        records.push(...body.data); after_id = next;
      }
      throw new Error('export_limit');
    } catch (error) { setMessage(error instanceof Error && error.message === 'operator_required' ? '发布身份验证失败。' : '数据服务暂不可用；没有下载不完整的数据文件。'); }
    finally { setBusy(false); }
  }
  async function submit(action: string) {
    setBusy(true); setMessage('');
    try {
      const r = await fetch('/api/crowd/invite', { method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + key },
        body: JSON.stringify({ action, ...(action === 'revoke' && result ? { invite: new URLSearchParams(new URL(result.link).hash.slice(1)).get('invite') } : {}) }) });
      const data = await r.json(); if (!r.ok) throw new Error(data.error);
      if (action === 'create') setResult(data); else { setResult(undefined); setMessage('此邀请已停用，已接入的参与者仍保留进度。'); }
    } catch (e) { const code = e instanceof Error ? e.message : ''; setMessage(code === 'operator_required' ? '发布身份验证失败。' : code === 'release_not_ready' ? '尚无通过验收的安装渠道，暂不能发邀请。' : '发布服务尚未接通，请联系部署负责人。'); }
    finally { setBusy(false); }
  }
  return <main className="mx-auto max-w-lg px-6 py-10"><Head><title>众包邀请发布</title><meta name="referrer" content="no-referrer" /></Head>
    <h1 className="text-3xl font-bold">发一个链接就可以邀请</h1>
    <p className="my-4">系统自动识别设备并接入任务；一批最多 100 人，邀请 7 天有效。参与者不需要中台账号和人工审批。</p>
    <label className="block">发布身份<input type="password" autoComplete="off" value={key} onChange={e => setKey(e.target.value)} className="my-2 w-full rounded border p-3" /></label>
    <button disabled={busy || !ready || !key} onClick={() => submit('create')} className="my-4 w-full rounded-xl bg-red-600 p-4 text-white disabled:opacity-50">生成邀请链接和二维码</button>
    {!ready && <p>入口尚未完成部署或没有可用安装渠道；就绪后按钮会开放。</p>}
    {ready && <p className="my-3">现在可以参与的设备：{devices.join('、')}。其他设备的渠道开放后，同一个入口会显示安装方式。</p>}
    {result && <section className="rounded-xl border p-4"><p>你只需要把下面这条短信或二维码发出去。同一链接可以转发，名额和期限仍按这一批计算。</p><img src={result.qr} alt="参与邀请二维码" width={320} height={320} /><textarea readOnly value={sms} className="my-3 min-h-36 w-full rounded border p-3" aria-label="分发短信" />
      <button onClick={copySMS} className="rounded border p-3">复制整条短信</button>
      <a href={'sms:?body=' + encodeURIComponent(sms)} className="ml-4 underline">用短信发送</a>
      <a href={result.qr} download="众包邀请二维码.png" className="ml-4 underline">保存二维码</a>
      <p className="my-3">到期：{new Date(result.expires_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</p>
      <button disabled={busy} onClick={() => submit('revoke')} className="text-red-700 underline">停用这个邀请</button>
    </section>}
    <section className="my-6 rounded-xl border p-4"><h2 className="text-xl font-bold">数据回收</h2>
      <p className="my-3">回传记录保存在研究中台，包含标准字段、非标字段和原文证据。新记录先待核验；核验通过后才供资料入库使用。</p>
      <button disabled={busy || !key} onClick={() => recovery('list')} className="rounded border p-3 disabled:opacity-50">查看待核验记录</button>
      <button disabled={busy || !key} onClick={() => recovery('export')} className="my-3 rounded border p-3 disabled:opacity-50">下载已核验证据</button>
      {loaded && !received.length && <p>目前没有待核验记录。</p>}
      {received.map(record => <details key={record.id} className="my-3 border-t pt-3"><summary>{record.record?.standard?.title || '公开笔记'} · 待核验</summary><pre className="overflow-auto whitespace-pre-wrap break-all text-sm">{JSON.stringify(record.record, null, 2)}</pre></details>)}
    </section>
    <p role="status" aria-live="polite" className="my-4">{message}</p>
  </main>;
}
