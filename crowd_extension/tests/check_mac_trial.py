"""Offline runtime checks fail closed; this is not Mac device acceptance."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'cloud'))
from crowd_mac_trial import checked_runtime

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
subprocess.run(['bash','-n',str(Path(__file__).resolve().parents[1]/'crowd-install-mac.command')],check=True)
print('PASS Mac kit: corrupted runtime rejected, installer shell syntax; codesign/launch require real Mac')
