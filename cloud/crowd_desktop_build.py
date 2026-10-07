#!/usr/bin/env python3
"""Package the shared desktop client with an official, checksum-verified Electron runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import zipfile
import plistlib
from crowd_build import EXT, VERSION


def download(url, destination):
    subprocess.run(['curl','-fLsS','--connect-timeout','15','--max-time','240','-o',str(destination),url],check=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--platform',choices=['win32','darwin'],required=True)
    ap.add_argument('--arch',choices=['x64','arm64'],default='x64'); ap.add_argument('--runtime',type=Path); args=ap.parse_args()
    electron=json.loads((EXT/'desktop/package.json').read_text())['devDependencies']['electron']
    cache=Path(tempfile.gettempdir())/'crowd-electron'; cache.mkdir(exist_ok=True)
    base=f'https://github.com/electron/electron/releases/download/v{electron}/'
    filename=f'electron-v{electron}-{args.platform}-{args.arch}.zip'
    runtime=args.runtime or cache/filename; sums=cache/f'SHASUMS256-{electron}.txt'
    if not sums.exists(): download(base+'SHASUMS256.txt',sums)
    expected={name.lstrip('*'):digest for digest,name in (line.split() for line in sums.read_text().splitlines())}[filename]
    if not runtime.exists(): download(base+filename,runtime)
    if hashlib.sha256(runtime.read_bytes()).hexdigest()!=expected: raise ValueError('Electron checksum mismatch; runtime rejected')
    source=EXT/'releases'/f'crowd-desktop-sources-v{VERSION}.zip'
    if not source.exists(): ap.error('Run crowd_build.py first')
    with tempfile.TemporaryDirectory(prefix='crowd-desktop-') as temporary:
        tmp=Path(temporary); root=tmp/'众包采集'; root.mkdir()
        with zipfile.ZipFile(runtime) as z:
            for name in z.namelist():
                if not (root/name).resolve().is_relative_to(root): raise ValueError('Unsafe runtime archive path')
        # Native unzip preserves macOS framework symlinks; ZipFile.extractall does not.
        subprocess.run(['unzip','-q',str(runtime.resolve()),'-d',str(root)],check=True)
        if args.platform=='win32':
            (root/'electron.exe').rename(root/'众包采集.exe'); resources=root/'resources'
        else:
            app=root/'Electron.app'; app.rename(root/'众包采集.app'); app=root/'众包采集.app'; resources=app/'Contents/Resources'
            plist=app/'Contents/Info.plist'; data=plistlib.loads(plist.read_bytes())
            data.update(CFBundleName='众包采集',CFBundleDisplayName='众包采集',CFBundleIdentifier='org.foodresearch.crowd',CFBundleShortVersionString=VERSION,CFBundleVersion='40000',CFBundleURLTypes=[{'CFBundleURLSchemes':['foodcrowd'],'CFBundleURLName':'org.foodresearch.crowd.join'}])
            plist.write_bytes(plistlib.dumps(data))
        resources.mkdir(exist_ok=True)
        with zipfile.ZipFile(source) as z:
            for name in z.namelist():
                if not (resources/'app'/name).resolve().is_relative_to(resources/'app'): raise ValueError('Unsafe source archive path')
            z.extractall(resources/'app')
        if args.platform=='darwin':
            if not shutil.which('codesign'): raise ValueError('macOS codesign required after modifying the app bundle; package on Mac')
            subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True,capture_output=True)
        (root/'开始参与.txt').write_text('打开众包采集客户端，然后返回短信中的邀请链接，点击“已安装，继续参与”。在客户端确认自愿参与并登录小红书，之后自动领取和执行任务。可随时停止。\n',encoding='utf-8')
        os_name='windows' if args.platform=='win32' else 'macos'
        output=EXT/'releases'/f'crowd-{os_name}-{args.arch}-v{VERSION}.zip'
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
            for item in sorted(root.rglob('*')):
                info=zipfile.ZipInfo('众包采集/'+item.relative_to(root).as_posix()); info.create_system=3
                info.external_attr=item.lstat().st_mode<<16; info.compress_type=zipfile.ZIP_DEFLATED
                if item.is_symlink(): z.writestr(info,os.readlink(item).encode())
                elif item.is_file(): z.writestr(info,item.read_bytes())
        (EXT/'releases'/f'SHA256SUMS-{os_name}-{args.arch}-v4.txt').write_text(hashlib.sha256(output.read_bytes()).hexdigest()+'  '+output.name+'\n')
        print('Packaged desktop runtime; real OS installation/login/background acceptance remains required')


if __name__=='__main__': main()
