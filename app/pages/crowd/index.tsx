import Head from 'next/head';
import Script from 'next/script';
import { useEffect, useState } from 'react';
import type { Platform, Release } from '@/lib/crowd-server';

type Manifest = { ready: boolean; origin: string; releases: Partial<Record<Platform, Release>> };
const names: Record<Platform, string> = { windows: 'Windows', macos: 'Mac', android: '安卓 / 兼容安卓的华为', harmony: '原生鸿蒙', ios: 'iPhone / iPad' };
export default function CrowdJoinPage() {
  const [os, setOS] = useState(''), [invite, setInvite] = useState(''), [manifest, setManifest] = useState<Manifest>(), [message, setMessage] = useState('正在检查参与入口…'), [downloading, setDownloading] = useState(false), [helpers, setHelpers] = useState(false);
  useEffect(() => {
    let sequence = 0;
    function sync() {
      if (document.hidden) return;
      const value = new URLSearchParams(location.hash.slice(1)).get('invite') || '';
      setInvite(/^[a-f0-9]{64}$/.test(value) ? value : '');
      const ticket = ++sequence;
      fetch('/api/crowd/manifest', { cache: 'no-store' }).then(async r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(data => { if (ticket === sequence) { setManifest(data); setMessage(''); } }).catch(() => { if (ticket === sequence) { setManifest(undefined); setMessage('参与入口暂未准备好，请稍后再试。'); } });
    }
    sync(); window.addEventListener('hashchange', sync); window.addEventListener('focus', sync); document.addEventListener('visibilitychange', sync);
    return () => { ++sequence; window.removeEventListener('hashchange', sync); window.removeEventListener('focus', sync); document.removeEventListener('visibilitychange', sync); };
  }, []);
  const release = manifest?.releases[os as Platform];
  const deepLink = 'foodcrowd://join#invite=' + invite;
  function detect() { setHelpers(true); setOS(current => current && current !== 'unsupported' ? current : (window as any).CrowdJoin.platform()); }
  async function download() {
    if (!release) return; setDownloading(true);
    try { await (window as any).CrowdJoin.download(release, (percent: number) => setMessage('正在下载安装包：' + percent + '%')); setMessage('下载完成。解压并打开客户端，然后回到这里点继续参与。'); }
    catch { setMessage('下载未完成或校验失败，请点安装按钮重试。'); }
    finally { setDownloading(false); }
  }
  function connect() {
    if (!invite || !release) return;
    if (release.channel !== 'extension') { location.href = deepLink; return; }
    const runtime = (window as any).chrome?.runtime;
    if (!runtime?.sendMessage) { setMessage('请在安装扩展的 Chrome / Edge 中打开这个邀请链接。'); return; }
    runtime.sendMessage(release.extension_id, { type: 'connect', invite }, (reply: { ok?: boolean }) => {
      setMessage(reply?.ok ? '邀请已接续，请在打开的客户端里确认参与。' : '还没有连接到扩展。安装完成后，再点“继续参与”。');
      void runtime.lastError;
    });
  }
  return <main className="mx-auto max-w-lg px-6 py-10 text-gray-800">
    <Head><title>参与公开笔记研究</title><meta name="referrer" content="no-referrer" /></Head>
    <Script src="/crowd/join.js" onLoad={detect} onReady={detect} />
    <h1 className="text-3xl font-bold">一起参与公开笔记研究</h1>
    <p className="mt-4">自愿参加，随时停止。客户端会自动领取任务、搜索并采集公开笔记，无需注册研究账号。</p>
    <section className="my-6 rounded-2xl border bg-white p-5">
      <label className="block font-medium" htmlFor="device">你的设备</label>
      <select id="device" value={os} onChange={e => setOS(e.target.value)} className="my-3 w-full rounded border p-3"><option value="">请选择设备</option>{Object.entries(names).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select>
      {!invite ? <p>请打开邀请人发来的完整链接或扫描二维码。</p> : release ? <>
        {release.channel === 'desktop' ? <button disabled={downloading || !helpers} onClick={download} className="w-full rounded-xl bg-red-600 p-4 text-center font-semibold text-white disabled:opacity-50">{downloading ? '正在下载安装包…' : '首次参与：安装客户端'}</button> : <a href={release.url} rel="noreferrer" className="block rounded-xl bg-red-600 p-4 text-center font-semibold text-white">首次参与：安装客户端</a>}
        <p className="my-3 text-sm">安装后回到这个页面点继续。系统可能要求你确认安装或打开应用。</p>
        <button onClick={connect} className="w-full rounded-xl border p-4 font-semibold">已安装，继续参与</button>
      </> : <p>{os ? '这类设备的安装渠道尚未开放。请保留邀请链接，开放后可继续使用。' : '正在识别设备，或手动选择上方设备。'}</p>}
    </section>
    <p role="status" aria-live="polite" className="my-4 text-amber-800">{message}</p>
    <p>客户端里勾选同意并开始；首次按提示登录小红书。之后自动执行，遇到验证或限流会暂停并保留进度。</p>
    <p className="mt-4 text-sm text-gray-600">只处理公开笔记，小红书登录凭据留在设备。每 100 条经核验、全局去重的笔记奖励 ¥0.10，不足 100 条继续累计。手机后台受系统限制，可能需要回到客户端点继续。</p>
  </main>;
}
