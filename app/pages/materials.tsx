import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/lib/auth';
import { supabase } from '@/lib/supabase';

type Snapshot = { slug: string; title: string; project_id: string; report_hash: string };
const errors: Record<string, string> = { login_required: '请先登录后查看获授权的资料。', project_access_denied: '当前账号没有这份资料的访问权限。', publication_not_configured: '资料入口尚未配置完成，请联系项目维护者。', publication_mismatch: '资料版本校验未通过，本次没有显示或下载。', publication_unavailable: '资料暂时不可用，请稍后刷新。' };
const text = (value: unknown, fallback = '未知') => typeof value === 'string' && value.trim() ? value : fallback;

export default function MaterialsPage() {
  const { user, loading } = useAuth();
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]), [selected, setSelected] = useState(''), [report, setReport] = useState<any>(null);
  const [message, setMessage] = useState(''), [busy, setBusy] = useState(false), [refresh, setRefresh] = useState(0);
  const [ownerUID, setOwnerUID] = useState<string | null>(null);
  const currentUID = useRef<string | null>(null); currentUID.current = user?.id || null;
  const sameOwner = !!user && ownerUID === user.id;
  const epoch = useRef(0), controllers = useRef(new Set<AbortController>());
  async function read(query: string, ticket: number) {
    const controller = new AbortController(); controllers.current.add(controller);
    try {
      const { data } = await supabase.auth.getSession();
      if (ticket !== epoch.current || !user || currentUID.current !== user.id || data.session?.user.id !== user.id || !data.session?.access_token) throw Error('login_required');
      const response = await fetch('/api/publications' + query, { cache: 'no-store', credentials: 'same-origin', signal: controller.signal, headers: { Authorization: 'Bearer ' + data.session.access_token } });
      if (!response.ok) { const body = await response.json().catch(() => ({})); throw Error(body.error || 'publication_unavailable'); }
      if (ticket !== epoch.current || currentUID.current !== user?.id) throw Error('cancelled');
      return response;
    } finally { controllers.current.delete(controller); }
  }
  useEffect(() => {
    const ticket = ++epoch.current; controllers.current.forEach(c => c.abort()); controllers.current.clear();
    setOwnerUID(user?.id || null); setSnapshots([]); setSelected(''); setReport(null); setMessage(''); setBusy(false);
    if (!user) return;
    setBusy(true);
    read('', ticket).then(r => r.json()).then(value => {
      if (ticket !== epoch.current) return;
      if (!Array.isArray(value.snapshots)) throw Error('publication_unavailable');
      setSnapshots(value.snapshots); setSelected(value.snapshots[0]?.slug || '');
    }).catch(e => { if (ticket === epoch.current) setMessage(errors[e.message] || '资料暂时不可用，请稍后刷新。'); }).finally(() => { if (ticket === epoch.current) setBusy(false); });
    return () => { ++epoch.current; controllers.current.forEach(c => c.abort()); controllers.current.clear(); };
  }, [user?.id, refresh]);
  useEffect(() => {
    if (!selected || !user) return;
    let active = true; const ticket = epoch.current; setReport(null); setBusy(true); setMessage('');
    read('?snapshot=' + encodeURIComponent(selected) + '&format=json', ticket).then(r => r.json()).then(value => { if (active && ticket === epoch.current) setReport(value); }).catch(e => { if (active && ticket === epoch.current) setMessage(errors[e.message] || '资料暂时不可用，请稍后刷新。'); }).finally(() => { if (active && ticket === epoch.current) setBusy(false); });
    return () => { active = false; };
  }, [selected, user?.id]);
  async function download(format: string) {
    const ticket = epoch.current, slug = selected; if (!slug || busy || !sameOwner || currentUID.current !== user?.id) return; setBusy(true); setMessage('');
    try {
      const response = await read('?snapshot=' + encodeURIComponent(slug) + '&format=' + format + '&download=1', ticket), blob = await response.blob();
      if (ticket !== epoch.current || currentUID.current !== user?.id || !blob.size) return;
      const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = 'ctfs-' + slug + '.' + format; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      setMessage('已下载当前版本，保留原始来源与覆盖说明。');
    } catch (e) { if (ticket === epoch.current) setMessage(errors[e instanceof Error ? e.message : ''] || '下载未完成，请稍后重试。'); }
    finally { if (ticket === epoch.current) setBusy(false); }
  }
  const current = snapshots.find(s => s.slug === selected), items = Array.isArray(report?.items) ? report.items : [];
  return <main className="mx-auto max-w-4xl px-6 py-10">
    <Head><title>项目资料 · China Travel</title><meta name="robots" content="noindex,nofollow" /></Head>
    <nav className="mb-8"><Link href="/">← 返回首页</Link></nav>
    <h1 className="serif text-3xl font-semibold">项目资料</h1>
    <p className="my-4 text-mocha-faint">查看你获授权的已发布快照。资料可能仍有缺口；已收录不等于已经核实或推荐。</p>
    {loading ? <p>正在读取登录状态…</p> : !user ? <p><Link className="underline" href="/login">使用原账号登录</Link>后，再返回“项目资料”。</p> : !sameOwner ? <p role="status">正在切换账号资料…</p> : <>
      <button disabled={busy} onClick={() => setRefresh(n => n + 1)} className="my-3 rounded border p-3">刷新资料</button>
      {!!snapshots.length && <label className="block">选择项目资料<select className="my-3 block w-full rounded border p-3" value={selected} onChange={e => setSelected(e.target.value)}>{snapshots.map(s => <option key={s.slug} value={s.slug}>{s.title}</option>)}</select></label>}
      {!busy && !message && !snapshots.length && <p>当前账号暂无可访问的已发布资料。</p>}
      {current && report && <section aria-label="当前资料版本">
        <h2 className="serif text-2xl">{current.title}</h2><p className="my-3">{items.length}条资料 · 快照时间：{text(report.as_of)} · 状态：{text(report.coverage, text(report.status, '保留原报告说明'))}</p>
        <p className="my-3">未知、候选和未完成项均按原报告保留。本页不发起采集，也不授予账号来源权限；媒体字节不在此文字快照内。</p>
        <div className="my-4 flex flex-wrap gap-3">{['json', 'jsonl', 'csv', 'html'].map(format => <button key={format} disabled={busy} onClick={() => download(format)} className="rounded border p-3">下载{format.toUpperCase()}</button>)}</div>
        <details className="my-4"><summary>查看版本及覆盖依据</summary><pre className="overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({ project: current.project_id, report_hash: current.report_hash, as_of: report.as_of, coverage: report.coverage, status: report.status, summary: report.summary, audit: report.audit }, null, 2)}</pre></details>
        {items.map((item: any, i: number) => <article key={String(item.identity?.source_record_id || item.entity_id || i)} className="my-4 rounded border p-4"><h3 className="text-lg font-semibold">{text(item.name, text(item.title, text(item.fields?.name, text(item.fields?.title, '资料' + (i + 1)))))}</h3><p className="my-2">{text(item.status, text(item.classification, '按原记录保留，未另行判定'))}</p><details><summary>原始字段与来源引用</summary><pre className="mt-3 overflow-auto whitespace-pre-wrap break-all text-sm">{JSON.stringify(item, null, 2)}</pre></details></article>)}
      </section>}
    </>}
    {sameOwner && busy && <p role="status">正在读取当前版本…</p>}
    <p role="status" aria-live="polite" className="my-4">{sameOwner ? message : ''}</p>
  </main>;
}
