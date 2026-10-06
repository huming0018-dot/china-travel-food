#!/usr/bin/env python3
"""Wrap the verified desktop ZIP in a per-user Windows installer; no administrator policy."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from crowd_build import EXT, VERSION, source_integrity


def digest(data): return hashlib.sha256(data).hexdigest()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--arch',choices=['x64','arm64'],default='x64')
    ap.add_argument('--makensis',default=os.environ.get('CROWD_MAKENSIS') or shutil.which('makensis'))
    args=ap.parse_args()
    if not args.makensis: ap.error('NSIS 3 required (CROWD_MAKENSIS or --makensis)')
    source=EXT/'releases'/f'crowd-windows-{args.arch}-v{VERSION}.zip'
    if not source.is_file(): ap.error('Run crowd_build.py and crowd_desktop_build.py --platform win32 first')
    output=source.with_name(f'crowd-windows-{args.arch}-v{VERSION}-setup.exe')
    with tempfile.TemporaryDirectory(prefix='crowd-installer-') as tmp:
        tmp=Path(tmp)
        with zipfile.ZipFile(source) as archive:
            for name in archive.namelist():
                if not (tmp/name).resolve().is_relative_to(tmp): raise ValueError('Unsafe archive path')
            archive.extractall(tmp)
        payload=tmp/'众包采集'; assets=payload/'resources/app/assets'
        native=json.loads((assets/'source-integrity.json').read_text())
        if native!=source_integrity('desktop'): raise ValueError('Stale desktop host; rebuild sources and runtime')
        shared={file.name:digest(file.read_bytes()) for file in assets.iterdir() if file.suffix in ('.js','.css','.html') and file.name!='config.js'}
        settings=json.loads((assets/'config.js').read_text().split('=',1)[1].strip().rstrip(';'))
        subprocess.run([args.makensis,'-V2','-DOUTPUT='+str(output),'-DPAYLOAD='+str(payload),'-DVERSION='+VERSION,str(EXT/'desktop/windows.nsi')],check=True)
        # The local build record binds this exact EXE to its compiled payload and source.
        manifest={'sha256':digest(output.read_bytes()),'platform':'windows','version':VERSION,'arch':args.arch,
                  'config':settings,'shared_sources':shared,'native_sources':native}
        output.with_suffix('.exe.build.json').write_text(json.dumps(manifest,sort_keys=True))
    (output.parent/f'SHA256SUMS-windows-{args.arch}-installer-v4.txt').write_text(manifest['sha256']+'  '+output.name+'\n')
    print('Built per-user Windows installer; code signing and Windows device acceptance remain required')


if __name__=='__main__': main()
