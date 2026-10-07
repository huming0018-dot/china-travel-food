import Head from 'next/head';
import Script from 'next/script';
import { useEffect, useState } from 'react';
import type { Platform, Release } from '@/lib/crowd-server';

type Manifest = { ready: boolean; origin: string; releases: Partial<Record<Platform, Release>> };
const names: Record<Platform, string> = { windows: 'Windows', macos: 'Mac', android: '安卓 / 兼容安卓的华为', harmony: '原生鸿蒙', ios: 'iPhone / iPad' };
export default function CrowdJoinPage() {
  const [os, setOS] = useState(''), [invite, setInvite] = useState(''), [manifest, setManifest] = useState<Manifest>(), [message, setMessage] = useState('正在检查参与入口…'), [downloading, setDownloading] = useState(false), [helpers, setHelpers] = useState(false), [embedded, setEmbedded] = useState(false), [downloaded, setDownloaded] = useState(false);
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
  const release = manifest?.ready ? manifest.releases[os as Platform] : undefined;
  useEffect(() => { setDownloaded(false); }, [os, release?.url]);
  const deepLink = 'foodcrowd://join#invite=' + invite;
  function detect() { setHelpers(true); setOS(current => current && current !== 'unsupported' ? current : (window as any).CrowdJoin.platform()); setEmbedded(/MicroMessenger|AlipayClient|QQ\//i.test(navigator.userAgent)); }
  async function copyLink() { try { await navigator.clipboard.writeText(location.href); setMessage('链接已复制。打开系统浏览器，粘贴链接后继续。'); } catch { setMessage('请从短信复制完整链接，再用系统浏览器打开。'); } }
  async function download() {
    if (!release) return; setDownloading(true);
    try { await (window as any).CrowdJoin.download(release, (percent: number) => setMessage('正在下载安装包：' + percent + '%')); setDownloaded(true); setMessage(release.url.endsWith('.exe') ? '下载完成。打开下载列表里的安装程序；安装后回到这里点继续参与。' : '下载完成。解压并打开客户端，然后回到这里点继续参与。'); }
    catch { setMessage('下载未完成或校验失败，请点安装按钮重试。'); }
    finally { setDownloading(false); }
  }
  function connect() {
    if (!invite || !release) return;
    if (release.channel !== 'extension') { setMessage('请在系统提示中选择打开众包采集。没有弹出客户端？先完成安装，再点一次继续参与。'); location.href = deepLink; return; }
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
    <h1 className="text-3xl font-bold">三步开始，之后自动执行</h1>
    <p className="mt-4">自愿参加公开笔记研究，随时停止。只需安装、打开并同意，首次登录小红书；之后客户端自动领取、搜索、采集和回传。</p>
    {embedded && <aside className="mt-5 rounded-xl border border-amber-300 bg-amber-50 p-4"><p>请用手机的系统浏览器打开。微信、QQ 等内置浏览器可能无法安装或打开客户端。</p><button onClick={copyLink} className="mt-3 rounded border bg-white p-3">复制链接，用系统浏览器打开</button></aside>}
    <section className="my-6 rounded-2xl border bg-white p-5">
      <p className="font-medium">{names[os as Platform] ? '已识别：' + names[os as Platform] : '请选择你的设备'}</p>
      <details className="my-3" open={!os || os === 'unsupported'}><summary className="cursor-pointer text-sm text-gray-600">设备识别有误？点这里切换</summary><label className="sr-only" htmlFor="device">你的设备</label><select id="device" value={os} onChange={e => setOS(e.target.value)} className="my-3 w-full rounded border p-3"><option value="">请选择设备</option>{Object.entries(names).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select><p className="text-sm text-gray-600">华为手机能安装 APK 时选安卓；原生鸿蒙使用鸿蒙渠道。</p></details>
      {!invite ? <p>请打开邀请人发来的完整链接或扫描二维码。</p> : release ? <>
        <h2 className="mb-3 text-lg font-semibold">① 安装到这台设备</h2>
        {release.channel === 'desktop' ? <button disabled={downloading || !helpers || embedded} onClick={download} className="w-full rounded-xl bg-red-600 p-4 text-center font-semibold text-white disabled:opacity-50">{downloading ? '正在下载安装包…' : downloaded ? '重新下载安装包' : '首次参与：安装客户端'}</button> : <a href={release.url} onClick={e => { if (embedded) { e.preventDefault(); setMessage('请先用系统浏览器打开邀请链接。'); } }} rel="noreferrer" className="block rounded-xl bg-red-600 p-4 text-center font-semibold text-white">首次参与：安装客户端</a>}
        <p className="my-3 text-sm">{os === 'android' ? '下载后打开安装包，按系统提示确认安装。如果要求允许此浏览器安装应用，请确认来源是邀请人提供的本系统。' : os === 'windows' && release.url.endsWith('.exe') ? '下载后打开安装程序，自动安装并创建桌面图标，无需解压或输入命令。若系统拦截，请联系邀请人核对发布签名。' : release.channel === 'desktop' ? '下载后解压，打开里面的众包采集程序。Mac 请把应用移到应用程序文件夹；若系统拦截，请联系邀请人核对签名。' : '按应用商店或 TestFlight 的提示安装。'}</p>
        <h2 className="mb-3 mt-6 text-lg font-semibold">② 安装后，回这里打开</h2>
        <button disabled={embedded || downloading} onClick={connect} className="w-full rounded-xl border p-4 font-semibold disabled:opacity-50">已安装，继续参与</button>
        <p className="my-3 text-sm">已安装的参与者直接点这个按钮。系统询问时，选择打开众包采集。</p>
        <h2 className="mb-3 mt-6 text-lg font-semibold">③ 同意参与，首次登录</h2>
        <p className="text-sm">在客户端勾选自愿参与，点同意并开始，再按提示登录小红书。自动接入研究身份，无需填服务器或注册邮箱。</p>
      </> : <p>{message && !manifest ? '参与入口还没有准备好，请联系邀请人，暂时不要下载安装包。' : os ? '这类设备的安装渠道尚未开放。请保留邀请链接，开放后可继续使用。' : '正在识别设备，或手动选择上方设备。'}</p>}
    </section>
    <p role="status" aria-live="polite" className="my-4 text-amber-800">{message}</p>
    <p>客户端里勾选同意并开始；首次按提示登录小红书。之后自动执行，遇到验证或限流会暂停并保留进度。</p>
    <p className="mt-4 text-sm text-gray-600">只处理公开笔记，小红书登录凭据留在设备。每 100 条经核验、全局去重的笔记奖励 ¥0.10，不足 100 条继续累计。手机后台受系统限制，可能需要回到客户端点继续。</p>
  </main>;
}
