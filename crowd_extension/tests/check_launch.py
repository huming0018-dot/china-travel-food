"""Deployment rejects mismatched targets, stale clients and unverified channels; no network."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'cloud'))
import crowd_launch as launch

actual=launch.EXT
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary); ext=root/'ext'; (ext/'releases').mkdir(parents=True); (ext/'src').mkdir()
    (root/'app/.vercel').mkdir(parents=True); (root/'app/.vercel/project.json').write_text('{}')
    conf={'url':'https://test.supabase.co','key':'sb_publishable_test','portal':'https://crowd.example.test'}
    package=ext/'releases/crowd-android-v4.0.0-debug.apk'
    files=['core.js','agent.js','api.js','join.js','native-runtime.js','controller.js','controller.css','content.js']
    native={'mobile/android/CollectorService.java':'fixture-current-native-digest'}
    with zipfile.ZipFile(package,'w') as z:
        z.writestr('assets/config.js','globalThis.CROWD_CONFIG = '+json.dumps(conf)+';')
        for file in files:
            content=(actual/'src'/file).read_bytes(); (ext/'src'/file).write_bytes(content); z.writestr('assets/'+file,content)
        z.writestr('assets/controller.html',launch.controller_html(conf))
        z.writestr('assets/source-integrity.json',json.dumps(native))
    release={'channel':'apk','url':conf['portal']+'/crowd/releases/'+package.name,'version':'4.0.0','verified':True,'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}
    env={'SUPABASE_SERVICE_ROLE_KEY':'sb_secret_TEST_ONLY','SUPABASE_DB_URL':'postgresql://postgres:test-only@db.test.supabase.co/postgres','VERCEL_TOKEN':'TEST_ONLY','SUPABASE_CLI':'fake-supabase','VERCEL_CLI':'fake-vercel','CROWD_RELEASES_JSON':json.dumps({'android':release})}
    with patch.object(launch,'ROOT',root),patch.object(launch,'EXT',ext),patch.object(launch,'config',return_value=conf),patch.object(launch,'source_integrity',side_effect=lambda platform:native):
        assert launch.check(env)[0]['ready']
        assert not launch.check({**env,'SUPABASE_DB_URL':'postgresql://postgres:test-only@db.other.supabase.co/postgres'})[0]['ready']
        assert not launch.check({**env,'CROWD_RELEASES_JSON':json.dumps({'android':{**release,'verified':False}})})[0]['ready']
        assert not launch.check({**env,'CROWD_RELEASES_JSON':json.dumps({'android':{**release,'sha256':'0'*64}})})[0]['ready']
        for file in ['content.js','agent.js']:
            original=(ext/'src'/file).read_bytes(); (ext/'src'/file).write_text('changed implementation')
            report=launch.check(env)[0];assert not report['ready'];assert any('stale' in item for item in report['missing'])
            (ext/'src'/file).write_bytes(original)
        native['mobile/android/CollectorService.java']='changed-native-digest'
        assert not launch.check(env)[0]['ready'],'changed native host must invalidate the old installation package'
        native['mobile/android/CollectorService.java']='fixture-current-native-digest'
        (ext/'src/agent.js').write_text('new implementation')
        report=launch.check(env)[0];assert not report['ready'];assert any('stale' in item for item in report['missing'])
    assert not (root/'.crowd-launch').exists(),'checks cannot create operator credentials or an invitation'
    staged=root/'downloads';staged.mkdir(); descriptor=launch.stage_download(package,staged)
    rebuilt=b''.join((staged/Path(part['url']).name).read_bytes() for part in descriptor['parts'])
    assert rebuilt==package.read_bytes();assert hashlib.sha256(rebuilt).hexdigest()==descriptor['sha256']
print('PASS deployment: matching project, verified channel, artifact/config/source integrity, no mutation during checks')
