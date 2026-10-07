"""Offline runtime checks fail closed; this is not Mac device acceptance."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import json
import os
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'cloud'))
from crowd_mac_trial import checked_runtime
from crowd_extension_trial import write_kit
from crowd_build import EXT, extension_id

with tempfile.TemporaryDirectory() as temporary:
    cache=Path(temporary);name='electron-vtest-darwin-arm64.zip'
    runtime=cache/name;runtime.write_bytes(b'local fixture, never an installable runtime')
    digest=hashlib.sha256(runtime.read_bytes()).hexdigest()
    (cache/'SHASUMS256-test.txt').write_text(digest+'  '+name+'\n')
    assert checked_runtime(cache,'test','arm64')==(runtime,digest)
    runtime.write_bytes(b'corrupted runtime')
    try: checked_runtime(cache,'test','arm64')
    except ValueError: pass
    else: raise AssertionError('Corrupted Mac runtime must be rejected')
    source=cache/'extension.zip'
    with zipfile.ZipFile(source,'w') as archive:
        archive.writestr('manifest.json',(EXT/'manifest.json').read_bytes())
        archive.writestr('src/background.js',(EXT/'src/background.js').read_bytes())
    pilot={'invite':'a'*64,'expires_at':'2099-01-01T00:00:00+00:00','max_people':1,'quota_day':2}
    output=cache/'mac-light.zip';result=write_kit(source,pilot,output)
    assert result['channel']=='unpacked_extension' and result['device_acceptance'] is False
    with zipfile.ZipFile(output) as archive:
        manifest=json.loads(archive.read('Mac轻量内测/插件/manifest.json'))
        assert manifest['background']=={'service_worker':'src/background.js'}
        assert 'browser_specific_settings' not in manifest
        conf=json.loads(archive.read('Mac轻量内测/插件/src/config.js').decode().split('=',1)[1].strip().rstrip(';'))
        assert conf['platform']=='macos' and conf['trialInvite']==pilot['invite']
        assert not any(name.endswith(('.app','.exe','.apk')) or 'electron' in name.lower() for name in archive.namelist())
        launcher=archive.getinfo('Mac轻量内测/双击开始安装.command')
        assert (launcher.external_attr>>16)&0o111 == 0o111
        assert archive.read(launcher)==(EXT/'crowd-extension-mac.command').read_bytes()
        archive.extractall(cache/'unpacked')
    kit=cache/'unpacked/Mac轻量内测'
    subprocess.run(['shasum','-a','256','-c','SHA256SUMS.txt'],cwd=kit,check=True,stdout=subprocess.DEVNULL)
    # Exercise helper flow with native commands mocked and the home path isolated.
    helper=kit/'双击开始安装.command'
    helper.write_text(helper.read_text().replace('$HOME','$CROWD_TEST_HOME'))
    home=cache/'fake home';(home/'Applications/Google Chrome.app').mkdir(parents=True)
    commands=cache/'commands';commands.mkdir();events=cache/'events'
    shims={'uname':'#!/bin/sh\necho Darwin\n',
           'plutil':'''#!/usr/bin/env python3
import json,sys
try:
    v=json.load(open(sys.argv[-1]))
    for k in sys.argv[2].split('.'): v=v[k]
    print(v)
except (KeyError,ValueError,OSError): sys.exit(1)
''',
           'open':'#!/bin/sh\nprintf "%s\\n" "$*" >> "$CROWD_TEST_EVENTS"\n',
           'pbcopy':'#!/bin/sh\ncat > "$CROWD_TEST_EVENTS.clipboard"\n'}
    for name,body in shims.items():
        p=commands/name;p.write_text(body);p.chmod(0o755)
    # The original script, rather than this isolated copy, is hashed in the kit.
    helper_hash=hashlib.sha256(helper.read_bytes()).hexdigest()
    sums=kit/'SHA256SUMS.txt';sums.write_text(sums.read_text().rsplit('\n',2)[0]+'\n'+helper_hash+'  双击开始安装.command\n')
    env={**os.environ,'PATH':str(commands)+os.pathsep+os.environ['PATH'],'CROWD_TEST_HOME':str(home),'CROWD_TEST_EVENTS':str(events)}
    first=subprocess.run(['bash',str(helper)],env=env,capture_output=True,text=True)
    assert first.returncode==0,first.stderr
    destination=home/'Library/Application Support/众包采集轻量/插件'
    assert (destination/'src/config.js').exists()
    assert Path(str(events)+'.clipboard').read_text()==str(destination)
    assert '尚未安装到浏览器' in first.stdout
    # Updating an old unpacked directory preserves browser state and uses its path.
    original=home/'old extension';original.mkdir()
    (original/'manifest.json').write_bytes((kit/'插件/manifest.json').read_bytes())
    prefs=home/'Library/Application Support/Google/Chrome/Default/Preferences';prefs.parent.mkdir(parents=True)
    prefs.write_text(json.dumps({'extensions':{'settings':{extension_id():{'path':str(original)}}}}))
    old_preferences=prefs.read_bytes()
    updated=subprocess.run(['bash',str(helper)],env=env,capture_output=True,text=True)
    assert updated.returncode==0,updated.stderr
    assert Path(str(events)+'.clipboard').read_text()==str(original)
    assert prefs.read_bytes()==old_preferences and '本机参与身份未删除' in updated.stdout
    config_path=kit/'插件/src/config.js';config_path.write_text('corrupted')
    old_events=events.read_bytes();old_config=(original/'src/config.js').read_bytes()
    bad=subprocess.run(['bash',str(helper)],env=env,capture_output=True,text=True)
    assert bad.returncode!=0
    assert events.read_bytes()==old_events and (original/'src/config.js').read_bytes()==old_config
    for bad in [{**pilot,'max_people':2},{**pilot,'invite':'invalid'},{**pilot,'expires_at':'2000-01-01T00:00:00+00:00'}]:
        try: write_kit(source,bad,output)
        except ValueError: pass
        else: raise AssertionError('Unsafe/expired trial must be rejected')
subprocess.run(['bash','-n',str(Path(__file__).resolve().parents[1]/'crowd-install-mac.command')],check=True)
subprocess.run(['bash','-n',str(EXT/'crowd-extension-mac.command')],check=True)
print('PASS Mac kits: runtime integrity, MV3-only pack, bounded invitation, executable setup helper, prepare/update/checksum failure; native Mac/browser confirmation remains unverified')
