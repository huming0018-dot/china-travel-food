import Head from 'next/head';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/lib/auth';
import { supabase } from '@/lib/supabase';
import { Delivery, Format, FORMATS, parseFragment, validateDelivery, verifiedBytes, reportFromBytes } from '@/lib/publication-capability';

type Snapshot = { slug: string; title: string; project_id: string; report_hash: string };
const errors: Record<string, string> = { login_required: '请先登录后查看获授权的资料。', project_access_denied: '当前账号没有这份资料的访问权限。', publication_not_configured: '资料入口尚未配置完成，请联系项目维护者。', publication_mismatch: '资料版本校验未通过，本次没有显示或下载。', publication_unavailable: '资料暂时不可用，请稍后刷新。' };
const text = (value: unknown, fallback = '未知') => typeof value === 'string' && value.trim() ? value : fallback;

export function UIDMaterialsPage() {
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


const linkErrors: Record<string, string> = {link_expired: '这份私有链接已到期。请向分享者索取新链接，本页不会自动续期。', link_invalid: '私有链接不完整或格式不受支持。请使用分享者提供的完整链接。', link_mismatch: '文件与交付清单不一致，本次未显示或下载。', link_unavailable: '暂时无法读取文件。可能链接已失效或网络不可用，本页不会自动续签。'};
export function CapabilityMaterials({fragment}: {fragment: string}) {
  const [data, setData] = useState<{fragment: string; report: any; delivery: Delivery} | null>(null);
  const [message, setMessage] = useState(''), [busy, setBusy] = useState(false), [expired, setExpired] = useState(false);
  const epoch = useRef(0), controllers = useRef(new Set<AbortController>()), access = useRef(fragment); access.current = fragment;
  const same = () => access.current === fragment && typeof window !== 'undefined' && window.location.hash === fragment;
  useEffect(() => {
    const ticket = ++epoch.current; setData(null); setMessage(''); setBusy(true); setExpired(false);
    controllers.current.forEach(c => c.abort()); controllers.current.clear();
    let expiryTimer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController(); controllers.current.add(controller);
    const timeout = setTimeout(() => controller.abort(), 15000);
    (async () => {
      try {
        const delivery = parseFragment(fragment);
        expiryTimer = setTimeout(() => { if (ticket === epoch.current) {setExpired(true); setData(null); setMessage(linkErrors.link_expired); controllers.current.forEach(c => c.abort());} }, Math.max(0, Date.parse(delivery.expires_at) - Date.now()));
        const bytes = await verifiedBytes(delivery, 'json', controller.signal, () => ticket === epoch.current && same());
        const report = reportFromBytes(bytes, delivery);
        if (ticket === epoch.current && same()) setData({fragment, report, delivery});
      } catch (error) { if (ticket === epoch.current && same()) setMessage(linkErrors[error instanceof Error ? error.message : ''] || linkErrors.link_unavailable); }
      finally {clearTimeout(timeout); controllers.current.delete(controller); if (ticket === epoch.current) setBusy(false);}
    })();
    return () => {++epoch.current; clearTimeout(timeout); if (expiryTimer) clearTimeout(expiryTimer); controllers.current.forEach(c => c.abort()); controllers.current.clear();};
  }, [fragment]);
  // The actual address is checked in render as well as in callbacks: old state is never painted after hashchange.
  const current = !expired && same() && data?.fragment === fragment && Date.parse(data.delivery.expires_at) > Date.now() ? data : null;
  async function download(format: Format) {
    if (!current || busy || !same()) return;
    const ticket = epoch.current, controller = new AbortController(); controllers.current.add(controller); setBusy(true); setMessage('');
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      const bytes = await verifiedBytes(current.delivery, format, controller.signal, () => ticket === epoch.current && same());
      validateDelivery(current.delivery);
      if (ticket !== epoch.current || !same()) return;
      const url = URL.createObjectURL(new Blob([new Uint8Array(bytes).buffer], {type: current.delivery.formats[format].mime}));
      try { const a = document.createElement('a'); a.href = url; a.download = 'ctfs-' + current.delivery.report_hash.slice(0, 12) + '.' + format; a.rel = 'noreferrer'; a.click(); }
      finally { setTimeout(() => URL.revokeObjectURL(url), 1000); }
      if (same()) setMessage('已校验并下载原文件。HTML文件可在本地打开。');
    } catch (error) { if (ticket === epoch.current && same()) setMessage(linkErrors[error instanceof Error ? error.message : ''] || linkErrors.link_unavailable); }
    finally {clearTimeout(timer); controllers.current.delete(controller); if (ticket === epoch.current) setBusy(false);}
  }
  return <main className="mx-auto max-w-4xl px-6 py-10">
    <Head><title>分享资料 · China Travel</title><meta name="robots" content="noindex,nofollow" /><meta name="referrer" content="no-referrer" /></Head>
    <nav className="mb-8"><Link href="/">← 返回首页</Link></nav><h1 className="serif text-3xl font-semibold">{text(current?.report.presentation?.report_title, '分享资料')}</h1>
    <p className="my-4">无需登录。私有链接自签发起15分钟内有效，请勿转发给无关人员。到期后不会自动续签。</p>
    {current && <section aria-label="当前分享资料"><h2 className="text-2xl">{current.report.items.length}条已发布素材</h2>
      <p className="my-3">快照时间：{text(current.report.as_of)} · 有效期至：{new Date(current.delivery.expires_at).toLocaleString()}</p>
      <p className="my-3">{text(current.report.presentation?.description, '有来源支持的素材，保留尚未核实的缺口。')}</p><p>{text(current.report.presentation?.notice, '这是发现候选，不等于已核实的推荐。')}</p>
      <div className="my-4 flex flex-wrap gap-3">{FORMATS.map(f => <button key={f} disabled={busy} onClick={() => download(f)} className="rounded border p-3">下载{f.toUpperCase()}</button>)}</div>
      <details><summary>版本与覆盖依据</summary><pre className="overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({report_hash: current.delivery.report_hash, project_id: current.report.project_id, as_of: current.report.as_of, summary: current.report.summary, coverage: current.report.coverage, status: current.report.status}, null, 2)}</pre></details>
      {current.report.items.map((item: any, i: number) => <article key={i} className="my-4 rounded border p-4"><h3 className="text-lg font-semibold">{text(item.draft?.title, text(item.identity?.title, text(item.draft?.subject_name, text(item.name, '素材' + (i + 1)))))}</h3><p className="my-2">{text(item.draft?.summary, '尚无摘要，原始材料见下方。')}</p>{item.unknowns && typeof item.unknowns === 'object' && <p className="my-2">待确认：{Object.keys(item.unknowns).map(k => text(current.report.presentation?.unknown_labels?.[k], k)).join('、')}</p>}<details><summary>素材原文、未知项与来源引用</summary><pre className="mt-3 overflow-auto whitespace-pre-wrap break-all text-sm">{JSON.stringify(item, null, 2)}</pre></details></article>)}
    </section>}
    {same() && busy && <p role="status">正在读取并校验文件…</p>}<p role="status" aria-live="polite">{same() ? message : ''}</p>
  </main>;
}
export default function MaterialsPage() {
  const [fragment, setFragment] = useState<string | null>(null);
  useEffect(() => { const sync = () => setFragment(window.location.hash); sync(); window.addEventListener('hashchange', sync); return () => window.removeEventListener('hashchange', sync); }, []);
  if (fragment === null) return <main className="p-8"><Head><title>项目资料 · China Travel</title><meta name="robots" content="noindex,nofollow" /></Head><p role="status">正在打开资料…</p></main>;
  if (fragment) return <CapabilityMaterials fragment={fragment} />;
  return <><p className="mx-auto max-w-4xl px-6 pt-6">免登录查看：请打开分享者提供的完整私有链接。也可继续使用原账号访问已授权资料。</p><UIDMaterialsPage /></>;
}
