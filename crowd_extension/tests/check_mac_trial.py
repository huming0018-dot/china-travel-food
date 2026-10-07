"""Offline runtime checks fail closed; this is not Mac device acceptance."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import json
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'cloud'))
from crowd_mac_trial import checked_runtime
from crowd_extension_trial import write_kit
from crowd_build import EXT

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
    for bad in [{**pilot,'max_people':2},{**pilot,'invite':'invalid'},{**pilot,'expires_at':'2000-01-01T00:00:00+00:00'}]:
        try: write_kit(source,bad,output)
        except ValueError: pass
        else: raise AssertionError('Unsafe/expired trial must be rejected')
subprocess.run(['bash','-n',str(Path(__file__).resolve().parents[1]/'crowd-install-mac.command')],check=True)
print('PASS Mac kits: runtime integrity, lightweight MV3-only pack, bounded invitation, expiry; real Mac installation remains required')
