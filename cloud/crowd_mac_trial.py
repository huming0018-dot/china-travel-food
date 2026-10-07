#!/usr/bin/env python3
"""Prepare an offline Mac acceptance kit; no release is marked device-tested."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import secrets
import tempfile
import urllib.request
import zipfile
from crowd_build import ROOT, EXT, VERSION, config, main as build_sources
from crowd_desktop_build import download


def checked_runtime(cache, version, arch):
    name=f'electron-v{version}-darwin-{arch}.zip'
    base=f'https://github.com/electron/electron/releases/download/v{version}/'
    sums=cache/f'SHASUMS256-{version}.txt'
    if not sums.exists(): download(base+'SHASUMS256.txt',sums)
    expected={name.lstrip('*'):digest for digest,name in (line.split() for line in sums.read_text().splitlines())}[name]
    runtime=cache/name
    if not runtime.exists(): download(base+name,runtime)
    with runtime.open('rb') as stream: actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=expected: raise ValueError('Electron checksum mismatch; runtime rejected')
    return runtime,expected


def invitation():
    state=ROOT/'.crowd-launch';state.mkdir(mode=0o700,exist_ok=True);state.chmod(0o700)
    path=state/'mac-trial.json'
    if path.exists():
        saved=json.loads(path.read_text())
        if datetime.fromisoformat(saved['expires_at'])<=datetime.now(timezone.utc):
            raise ValueError('Previous trial expired; revoke/archive its state before issuing another')
        return saved
    conf=config();token=secrets.token_hex(32)
    saved={'invite':token,'expires_at':(datetime.now(timezone.utc)+timedelta(hours=48)).isoformat(),'max_people':1,'quota_day':2}
    body={'action':'rpc','name':'crowd_v4_invite','args':{'p_action':'create','p_payload':{'token_hash':hashlib.sha256(token.encode()).hexdigest(),**{k:saved[k] for k in ['expires_at','max_people','quota_day']}}}}
    request=urllib.request.Request(conf['url']+'/functions/v1/crowd-gateway',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+conf['key'],'apikey':conf['key'],'X-Crowd-Gateway-Key':(state/'gateway-token').read_text().strip()},method='POST')
    with urllib.request.urlopen(request,timeout=20) as response: result=json.load(response)
    if result.get('error') or result.get('data',{}).get('created') is not True: raise ValueError('Trial invitation was not created')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream: json.dump(saved,stream)
    return saved


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--invite',action='store_true',help='Create/reuse one private Mac-only acceptance invitation')
    ap.add_argument('--output',type=Path,default=ROOT/'crowd_extension/releases/crowd-macos-trial-v4.0.0.zip')
    args=ap.parse_args()
    version=json.loads((EXT/'desktop/package.json').read_text())['devDependencies']['electron']
    cache=Path(tempfile.gettempdir())/'crowd-electron';cache.mkdir(exist_ok=True)
    runtimes=[checked_runtime(cache,version,arch) for arch in ['arm64','x64']]
    build_sources([])
    source=EXT/'releases'/f'crowd-desktop-sources-v{VERSION}.zip'
    files=[(source,hashlib.sha256(source.read_bytes()).hexdigest()),*runtimes]
    pilot=invitation() if args.invite else None
    link='foodcrowd://join#invite='+pilot['invite'] if pilot else ''
    page='''<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Mac 内测</title>
<style>body{font:18px system-ui;max-width:680px;margin:48px auto;padding:20px;line-height:1.7}a{display:inline-block;padding:12px;background:#1767ce;color:white;border-radius:8px}</style>
<h1>Mac 内测</h1><p>先双击「双击安装.command」。客户端打开后，点击下面的按钮；系统询问时选择打开众包采集。</p>'''
    page+=('<p><a href="'+html.escape(link,quote=True)+'">打开客户端，开始内测</a></p><p>报名截止：'+html.escape(pilot['expires_at'])+'。仅一台 Mac，每日最多 2 条，不要转发。</p>') if pilot else '<p>此包未附邀请。请联系邀请人完成内部验收接入。</p>'
    page+='''<p>确认自愿参与，点击「同意并开始」，按提示登录小红书。之后客户端自动领任务、搜索和回传；遇到登录、验证码或限流会暂停。</p>
<p>需要验证：收到任务和至少一条真实回传、关闭窗口后仍继续、菜单栏「停止」生效、重新打开后进度保留。Mac 睡眠/关机时不会采集。</p>
<p>安装包没有 Developer ID 公证。若 macOS 拦截，在「系统设置 → 隐私与安全性」核对这个内测文件后按系统提示允许；不要关闭系统安全保护。不能打开时保留系统提示交给 Codex。</p>
<p>这是本机临时签名的内部验收包，尚未通过实机验收，不能作为正式分发包。</p>'''
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output,'w',zipfile.ZIP_STORED) as archive:
        for path,_ in files: archive.write(path,'Mac内测/'+path.name)
        for name,data,mode in [('双击安装.command',(EXT/'crowd-install-mac.command').read_bytes(),0o100755),('SHA256SUMS.txt',''.join(digest+'  '+path.name+'\n' for path,digest in files).encode(),0o100644),('开始Mac内测.html',page.encode(),0o100644)]:
            entry=zipfile.ZipInfo('Mac内测/'+name);entry.create_system=3;entry.external_attr=mode<<16;archive.writestr(entry,data)
    with args.output.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    args.output.with_suffix('.zip.sha256').write_text(digest+'  '+args.output.name+'\n')
    print('Prepared offline Mac trial kit (both architectures); signing and device acceptance must run on Mac.')


if __name__=='__main__': main()
