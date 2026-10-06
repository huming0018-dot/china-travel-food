import Head from 'next/head';
import { useEffect, useState } from 'react';
export default function CrowdPublisher() {
  const [key, setKey] = useState(''), [result, setResult] = useState<{ link: string; qr: string; expires_at: string }>(), [message, setMessage] = useState(''), [busy, setBusy] = useState(false), [ready, setReady] = useState(false);
  useEffect(() => { fetch('/api/crowd/manifest', { cache: 'no-store' }).then(r => r.json()).then(data => setReady(data.ready === true)).catch(() => {}); }, []);
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
    {result && <section className="rounded-xl border p-4"><img src={result.qr} alt="参与邀请二维码" width={320} height={320} /><textarea readOnly value={result.link} className="my-3 w-full rounded border p-3" aria-label="邀请链接" />
      <button onClick={async () => { try { await navigator.clipboard.writeText(result.link); setMessage('已复制，可以通过短信转发。'); } catch { setMessage('请长按上面的链接复制。'); } }} className="rounded border p-3">复制链接发短信</button>
      <a href={result.qr} download="众包邀请二维码.png" className="ml-4 underline">保存二维码</a>
      <p className="my-3">到期：{new Date(result.expires_at).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai' })}</p>
      <button disabled={busy} onClick={() => submit('revoke')} className="text-red-700 underline">停用这个邀请</button>
    </section>}
    <p role="status" aria-live="polite" className="my-4">{message}</p>
  </main>;
}
