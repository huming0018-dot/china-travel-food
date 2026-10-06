#!/usr/bin/env python3
"""Publisher-only one-click rollout. Participants receive only the resulting URL/QR."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import zipfile
from crowd_build import ROOT, EXT, VERSION, config, values, source_integrity, controller_html


def check(env):
    missing=[]
    try:
        # Reuse the builder's public-key and HTTPS validation.
        conf=config()
        if not conf.get('portal'): missing.append('HTTPS participation origin')
    except (ValueError,KeyError): conf={}; missing.append('public Supabase configuration')
    for key in ['SUPABASE_SERVICE_ROLE_KEY','SUPABASE_DB_URL','VERCEL_TOKEN']:
        if not env.get(key): missing.append(key)
    role_key=env.get('SUPABASE_SERVICE_ROLE_KEY','')
    if role_key and not role_key.startswith('sb_secret_'):
        try:
            body=role_key.split('.')[1]; claims=json.loads(base64.urlsafe_b64decode(body+'='*(-len(body)%4)))
            if claims.get('role')!='service_role': missing.append('valid server-only Supabase key')
            ref=urllib.parse.urlsplit(conf.get('url','')).hostname
            if claims.get('ref') and ref!=claims['ref']+'.supabase.co': missing.append('matching Supabase key/project')
        except (ValueError,IndexError): missing.append('valid server-only Supabase key')
    database=urllib.parse.urlsplit(env.get('SUPABASE_DB_URL',''))
    ref=urllib.parse.urlsplit(conf.get('url','')).hostname
    if env.get('SUPABASE_DB_URL') and (database.scheme not in ('postgres','postgresql') or not ref or
        (database.hostname!='db.'+ref and not ((database.hostname or '').endswith('.pooler.supabase.com') and urllib.parse.unquote(database.username or '').endswith('.'+ref.split('.')[0])))):
        missing.append('database URL matching the configured Supabase project')
    if not (ROOT/'app/.vercel/project.json').exists(): missing.append('linked existing website project')
    cli=env.get('SUPABASE_CLI') or shutil.which('supabase')
    vercel=env.get('VERCEL_CLI') or shutil.which('vercel')
    if not cli: missing.append('Supabase CLI')
    if not vercel: missing.append('Vercel CLI')
    try: releases=json.loads(env.get('CROWD_RELEASES_JSON','{}'))
    except ValueError: releases={}; missing.append('valid release manifest')
    accepted={}
    for platform,item in releases.items():
        if platform not in ('android','windows','macos','ios','harmony') or not isinstance(item,dict) or item.get('verified') is not True: continue
        if item.get('version')!=VERSION: missing.append(platform+' release version'); continue
        url=urllib.parse.urlsplit(item.get('url',''))
        if url.scheme!='https' or url.username or url.password: missing.append(platform+' HTTPS release'); continue
        if item.get('channel') in ('desktop','apk'):
            if url.query or url.fragment: missing.append(platform+' direct release URL'); continue
            name=Path(url.path).name; local=EXT/'releases'/name
            if url.netloc!=urllib.parse.urlsplit(conf.get('portal','')).netloc or url.path!='/crowd/releases/'+name or not local.is_file(): missing.append(platform+' release artifact'); continue
            if hashlib.sha256(local.read_bytes()).hexdigest()!=item.get('sha256'): missing.append(platform+' release checksum'); continue
            with zipfile.ZipFile(local) as archive:
                candidates=[name for name in archive.namelist() if name.endswith('assets/config.js')]
                if not candidates: missing.append(platform+' bundled configuration'); continue
                settings=json.loads(archive.read(candidates[0]).decode().split('=',1)[1].strip().rstrip(';'))
                if settings.get('portal')!=conf.get('portal') or settings.get('url')!=conf.get('url') or settings.get('key')!=conf.get('key'): missing.append(platform+' client/portal/backend mismatch'); continue
                prefix=candidates[0].rsplit('/',1)[0]+'/'
                current=True
                for filename in ['core.js','agent.js','api.js','join.js','native-runtime.js','controller.js','controller.css','content.js']:
                    if prefix+filename not in archive.namelist() or archive.read(prefix+filename)!=(EXT/'src'/filename).read_bytes(): current=False; break
                if prefix+'controller.html' not in archive.namelist() or archive.read(prefix+'controller.html')!=controller_html(conf).encode(): current=False
                try:
                    native=json.loads(archive.read(prefix+'source-integrity.json'))
                    if native!=source_integrity('desktop' if item['channel']=='desktop' else 'android'): current=False
                except (KeyError,ValueError): current=False
                if not current: missing.append(platform+' package is stale; rebuild before publishing'); continue
        accepted[platform]={key:item[key] for key in ['channel','url','version','verified','extension_id','sha256'] if key in item}
    if not accepted: missing.append('at least one device-tested installation channel')
    return {'ready':not missing,'missing':missing,'platforms':list(accepted)},conf,accepted,cli,vercel


def run(args,env,cwd):
    result=subprocess.run(args,cwd=cwd,env=env,capture_output=True,text=True)
    if result.returncode: raise RuntimeError('Deployment command failed; no credentials printed. Inspect the trusted deployment console.')
    return result.stdout


def stage_download(source,destination):
    # Desktop runtimes exceed common static-host per-file limits. Reassemble verified
    # 24 MiB pieces in the browser; the participant still presses a single button.
    parts=[]; total=0
    with Path(source).open('rb') as stream:
        while chunk:=stream.read(24*1024*1024):
            name=Path(source).name+'.part'+str(len(parts)); (destination/name).write_bytes(chunk)
            parts.append({'url':'/crowd/releases/'+name,'bytes':len(chunk),'sha256':hashlib.sha256(chunk).hexdigest()}); total+=len(chunk)
    descriptor={'file':Path(source).name,'bytes':total,'sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest(),'parts':parts}
    (destination/(Path(source).name+'.json')).write_text(json.dumps(descriptor))
    return descriptor


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--apply',action='store_true'); args=ap.parse_args()
    env={**values(),**os.environ}; report,conf,releases,cli,vercel=check(env)
    if not args.apply or not report['ready']:
        print(json.dumps(report,ensure_ascii=False,indent=2)); return 0 if report['ready'] else 2
    state=ROOT/'.crowd-launch'; state.mkdir(mode=0o700,exist_ok=True)
    key_file=state/'operator-key'; operator=env.get('CROWD_OPERATOR_KEY') or (key_file.read_text() if key_file.exists() else secrets.token_hex(32))
    if len(operator)<32: raise ValueError('CROWD_OPERATOR_KEY must contain at least 32 characters')
    key_file.write_text(operator); key_file.chmod(0o600)
    env.update(CROWD_OPERATOR_KEY=operator,CROWD_RELEASES_JSON=json.dumps(releases,separators=(',',':')),CROWD_PUBLIC_ORIGIN=conf['portal'])
    # CLI migration history makes repeated rollouts safe; do not recreate existing v4 tables.
    print('Applying pending migrations…')
    run([cli,'db','push','--db-url',env['SUPABASE_DB_URL'],'--workdir',str(ROOT/'cloud'),'--yes'],env,ROOT)
    destination=ROOT/'app/public/crowd/releases'; destination.mkdir(parents=True,exist_ok=True)
    for item in releases.values():
        if item['channel'] in ('desktop','apk'):
            name=Path(urllib.parse.urlsplit(item['url']).path).name
            if item['channel']=='desktop': stage_download(EXT/'releases'/name,destination)
            else: shutil.copyfile(EXT/'releases'/name,destination/name)
    print('Building and publishing the connected website…')
    run([sys.executable,str(ROOT/'cloud/crowd_build.py')],env,ROOT)
    command=[vercel,'deploy','--prod','--yes','--token',env['VERCEL_TOKEN']]
    for name in ['NEXT_PUBLIC_SUPABASE_URL','NEXT_PUBLIC_SUPABASE_ANON_KEY','SUPABASE_SERVICE_ROLE_KEY','CROWD_PUBLIC_ORIGIN','CROWD_OPERATOR_KEY','CROWD_RELEASES_JSON']:
        command.extend(['--env',name+'='+env[name]])
    for name in ['NEXT_PUBLIC_SUPABASE_URL','NEXT_PUBLIC_SUPABASE_ANON_KEY']: command.extend(['--build-env',name+'='+env[name]])
    run(command,env,ROOT/'app')
    url=conf['portal']
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url+'/api/crowd/manifest',timeout=15) as response: live=json.load(response)
            if live.get('ready') and live.get('origin')==url and live.get('releases')==releases: break
        except (OSError,ValueError): pass
        if attempt==5: raise RuntimeError('Website not ready at the intended origin; no invitation issued')
        time.sleep(2)
    request=urllib.request.Request(url+'/api/crowd/invite',data=b'{}',headers={'Content-Type':'application/json','Authorization':'Bearer '+operator},method='POST')
    with urllib.request.urlopen(request,timeout=20) as response: invitation=json.load(response)
    (state/'invite-link.txt').write_text(invitation['link']+'\n')
    (state/'invite-qr.png').write_bytes(base64.b64decode(invitation['qr'].split(',',1)[1]))
    # The sole result the owner distributes. Private operator credentials remain local.
    print(json.dumps({'link':invitation['link'],'qr_file':str(state/'invite-qr.png')},ensure_ascii=False))
    return 0


if __name__=='__main__':
    try: sys.exit(main())
    except Exception: print('Deployment did not complete; no usable invitation claimed. Credentials were not printed.',file=sys.stderr); sys.exit(1)
