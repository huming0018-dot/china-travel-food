#!/usr/bin/env python3
"""Prepare the public enrollment service without publishing owner credentials."""
import hashlib
import json
import os
from pathlib import Path
import secrets
from crowd_build import ROOT, config, values


def prepare():
    state=ROOT/'.crowd-launch';state.mkdir(mode=0o700,exist_ok=True);state.chmod(0o700)
    key_file=state/'operator-key'
    if not key_file.exists():
        fd=os.open(key_file,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(secrets.token_hex(32))
    key_file.chmod(0o600);key=key_file.read_text().strip()
    if len(key)!=64 or any(c not in '0123456789abcdef' for c in key):raise ValueError('Invalid existing owner key; never rotate silently')
    conf=config()
    # Installation channels stay closed until the existing artifact and device
    # acceptance checks have been completed. Never infer readiness from a build.
    channels=state/'accepted-releases.json'
    releases=json.loads(channels.read_text()) if channels.exists() else {}
    if releases:
        from crowd_launch import check
        env={**values(),**os.environ,'CROWD_RELEASES_JSON':json.dumps(releases)}
        gateway=state/'gateway-token'
        if gateway.exists():env['CROWD_GATEWAY_TOKEN']=gateway.read_text().strip()
        report=check(env)[0]
        # This service is deployed through Supabase, independently of Vercel.
        unrelated={'Vercel login or VERCEL_TOKEN','Vercel CLI','linked existing website project','SUPABASE_SERVICE_ROLE_KEY','SUPABASE_DB_URL','Supabase CLI'}
        missing=[item for item in report['missing'] if item not in unrelated]
        if missing:raise ValueError('Installation channel rejected: '+', '.join(missing))
    configuration={'origin':conf['portal'],'previewOrigins':['https://app-git-fix-crowd-distribution-v348-haha-hunter.vercel.app'],'releases':releases}
    source=ROOT/'cloud/supabase/functions/crowd-access'
    index=(source/'index.ts').read_text().replace('__CROWD_ACCESS_CONFIGURATION__',json.dumps(configuration,separators=(',',':'))).replace('__CROWD_OPERATOR_SHA256__',hashlib.sha256(key.encode()).hexdigest())
    payload={'project_id':conf['url'].split('//',1)[1].split('.',1)[0],'name':'crowd-access','entrypoint_path':'index.ts','verify_jwt':False,
             'files':[{'name':'index.ts','content':index},{'name':'core.mjs','content':(source/'core.mjs').read_text().replace('../crowd-gateway/core.mjs','./gateway-core.mjs')},{'name':'gateway-core.mjs','content':(ROOT/'cloud/supabase/functions/crowd-gateway/core.mjs').read_text()}]}
    path=state/'access-deploy.json';path.write_text(json.dumps(payload));path.chmod(0o600)
    return path


if __name__=='__main__':prepare();print('Enrollment service prepared; owner key remains in private state.')
