#!/usr/bin/env python3
"""Prepare the narrow gateway deployment; keep the random server key private."""
import hashlib
import json
import os
from pathlib import Path
import secrets
from crowd_build import ROOT, config


def prepare(root=ROOT):
    state=Path(root)/'.crowd-launch';state.mkdir(mode=0o700,parents=True,exist_ok=True)
    state.chmod(0o700)
    key_file=state/'gateway-token'
    if not key_file.exists():
        fd=os.open(key_file,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(secrets.token_hex(32))
    key_file.chmod(0o600)
    value=key_file.read_text().strip()
    if len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('Invalid existing gateway key; never rotate silently')
    source=Path(root)/'cloud/supabase/functions/crowd-gateway'
    index=(source/'index.ts').read_text().replace('__CROWD_GATEWAY_TOKEN_SHA256__',hashlib.sha256(value.encode()).hexdigest())
    project=config()['url'].split('//',1)[1].split('.',1)[0]
    payload={'project_id':project,'name':'crowd-gateway','entrypoint_path':'index.ts','verify_jwt':True,
             'files':[{'name':'index.ts','content':index},{'name':'core.mjs','content':(source/'core.mjs').read_text()}]}
    path=state/'gateway-deploy.json'
    path.write_text(json.dumps(payload));path.chmod(0o600)
    return path


if __name__=='__main__':
    path=prepare();print('Gateway deployment prepared; server key remains in private publisher state.')
