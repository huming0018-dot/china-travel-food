#!/usr/bin/env python3
"""Build desktop extension + native source projects; no secret or retired v3 scripts."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.parse
import zipfile

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / 'crowd_extension'
VERSION = '4.0.0'
DEFAULT_PORTAL = 'https://app-lyart-eta-22.vercel.app'  # Existing project production origin recorded in HANDOFF.
FILES = ['manifest.json','icons/icon128.png'] + ['src/'+x for x in ['background.js','core.js','api.js','agent.js','content.js','config.js','controller.html','controller.css','controller.js','native-runtime.js','join.js']]


def values():
    # Share the website's public defaults; never put server credentials here.
    public = json.loads((ROOT / 'app/supabase.public.json').read_text())
    values = {'NEXT_PUBLIC_SUPABASE_URL': public['url'],
              'NEXT_PUBLIC_SUPABASE_ANON_KEY': public['key']}
    path = ROOT / 'app/.env.local'
    if path.exists():
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=',1); values[key.strip()] = value.strip().strip('\"\'')
    values.update({key:value for key,value in os.environ.items() if key.startswith('NEXT_PUBLIC_SUPABASE_')})
    return values


def config():
    supplied = values()
    url = supplied.get('NEXT_PUBLIC_SUPABASE_URL','').rstrip('/'); key = supplied.get('NEXT_PUBLIC_SUPABASE_ANON_KEY','')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not (parsed.hostname or '').endswith('.supabase.co') or parsed.username or parsed.path or parsed.query or parsed.fragment: raise ValueError('Valid HTTPS Supabase URL required')
    if key.startswith('eyJ'):
        payload = key.split('.')[1]; role = json.loads(base64.urlsafe_b64decode(payload + '='*(-len(payload)%4))).get('role')
        if role != 'anon': raise ValueError('Only an anon JWT can be distributed')
    elif not key.startswith('sb_publishable_'): raise ValueError('A publishable key or anon JWT is required')
    conf = {'url': url, 'key': key}
    portal = os.environ.get('CROWD_PUBLIC_ORIGIN') or supplied.get('CROWD_PUBLIC_ORIGIN') or DEFAULT_PORTAL
    if portal:
        parsed = urllib.parse.urlsplit(portal)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.path not in ('','/') or parsed.query or parsed.fragment: raise ValueError('CROWD_PUBLIC_ORIGIN must be a bare HTTPS origin')
        conf['portal'] = portal.rstrip('/')
    return conf


def zipdir(source, destination):
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(source.rglob('*')):
            if file.is_file():
                info=zipfile.ZipInfo(file.relative_to(source).as_posix(),(2026,10,5,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=(0o100644 << 16); archive.writestr(info,file.read_bytes())


def source_integrity(platform):
    """Fingerprint native host inputs too, not just the shared agent scripts."""
    directory = EXT/'desktop' if platform == 'desktop' else EXT/'mobile'/platform
    ignored = {'assets','build','.gradle','node_modules','dist','.DS_Store'}
    return {file.relative_to(EXT).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
            for file in sorted(directory.rglob('*'))
            if file.is_file() and not ignored.intersection(file.relative_to(directory).parts)}


def controller_html(conf):
    return (EXT/'src/controller.html').read_text().replace(
        'connect-src https://*.supabase.co;', 'connect-src '+conf['url']+' '+conf['portal']+';')


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--dry',action='store_true'); args=ap.parse_args(argv)
    conf=config()
    for file in FILES:
        if not (EXT/file).is_file(): raise ValueError('Missing '+file)
        if file.endswith('.js'): subprocess.run(['node','--check',str(EXT/file)],check=True,capture_output=True)
    if args.dry: print('v4 source/config validation passed (no credentials printed)'); return
    out=EXT/'releases'; out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='crowd-v4-') as tmp:
        desktop=Path(tmp)/'desktop'; desktop.mkdir()
        for file in FILES:
            destination=desktop/file; destination.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(EXT/file,destination)
        (desktop/'src/config.js').write_text('globalThis.CROWD_CONFIG = '+json.dumps(conf)+';\n')
        if conf.get('portal'):
            controller = desktop/'src/controller.html'
            controller.write_text(controller_html(conf))
        manifest=json.loads((desktop/'manifest.json').read_text()); manifest['host_permissions']=['https://www.xiaohongshu.com/*','https://m.xiaohongshu.com/*',conf['url']+'/*']; (desktop/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        if conf.get('portal'):
            manifest['host_permissions'].append(conf['portal']+'/*')
            manifest['externally_connectable']={'matches':[conf['portal']+'/*']}
            (desktop/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        zipdir(desktop,out/f'crowd-extension-v{VERSION}.zip')
        mobile=Path(tmp)/'mobile'; shutil.copytree(EXT/'mobile',mobile,ignore=shutil.ignore_patterns('build','.gradle','.DS_Store','*.apk','*.ipa','*.hap'))
        for dest in ['android/app/src/main/assets','ios/assets','harmony/entry/src/main/resources/rawfile/assets']:
            assets=mobile/dest; assets.mkdir(parents=True,exist_ok=True)
            for source in (desktop/'src').iterdir():
                if source.name != 'background.js': shutil.copyfile(source,assets/source.name)
            platform = 'android' if dest.startswith('android') else 'ios' if dest.startswith('ios') else 'harmony'
            (assets/'config.js').write_text('globalThis.CROWD_CONFIG = '+json.dumps({**conf,'platform':platform})+';\n')
            (assets/'source-integrity.json').write_text(json.dumps(source_integrity(platform),sort_keys=True))
        shutil.copyfile(EXT/'README.md',mobile/'README.md')
        zipdir(mobile,out/f'crowd-mobile-sources-v{VERSION}.zip')
        desktop_native=Path(tmp)/'desktop-native'; shutil.copytree(EXT/'desktop',desktop_native,ignore=shutil.ignore_patterns('node_modules','build','dist','.DS_Store'))
        assets=desktop_native/'assets'; assets.mkdir()
        for source in (desktop/'src').iterdir():
            if source.name!='background.js': shutil.copyfile(source,assets/source.name)
        shutil.copyfile(EXT/'icons/icon128.png',assets/'icon128.png')
        (assets/'source-integrity.json').write_text(json.dumps(source_integrity('desktop'),sort_keys=True))
        zipdir(desktop_native,out/f'crowd-desktop-sources-v{VERSION}.zip')
    for file in ['crowd-install-win.bat','crowd-install-mac.command']: shutil.copyfile(EXT/file,out/file)
    portal_assets = ROOT/'app/public/crowd'; portal_assets.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(EXT/'src/join.js',portal_assets/'join.js')
    packages=[out/f'crowd-extension-v{VERSION}.zip',out/f'crowd-mobile-sources-v{VERSION}.zip',out/f'crowd-desktop-sources-v{VERSION}.zip']
    (out/'SHA256SUMS-v4.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in packages))
    print('Built desktop and native source packages v'+VERSION)


if __name__=='__main__': main()
