#!/usr/bin/env python3
"""Build a debug-signed internal APK using Android SDK tools (no Gradle dependency)."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from crowd_build import EXT, VERSION


def run(*args): subprocess.run([str(x) for x in args],check=True)


def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--sdk',required=True,type=Path); args=ap.parse_args()
    sdk=args.sdk.resolve(); tools=sdk/'build-tools/35.0.0'; android=sdk/'platforms/android-35/android.jar'
    if not android.exists() or not (tools/'aapt2').exists(): ap.error('Android platform 35 and build-tools 35.0.0 required')
    out=EXT/'releases'; project=out/f'crowd-mobile-sources-v{VERSION}.zip'
    if not project.exists(): ap.error('Run cloud/crowd_build.py first')
    with tempfile.TemporaryDirectory(prefix='crowd-android-') as tmp:
        tmp=Path(tmp)
        with zipfile.ZipFile(project) as z:
            for info in z.infolist():
                if info.filename.startswith('android/'):
                    target=(tmp/info.filename).resolve()
                    if not target.is_relative_to(tmp): raise ValueError('Unsafe archive path')
                    z.extract(info,tmp)
        main=tmp/'android/app/src/main'; classes=tmp/'classes'; classes.mkdir()
        run('javac','-encoding','UTF-8','-source','17','-target','17','-classpath',android,'-d',classes,*sorted((main/'java').rglob('*.java')))
        run('jar','cf',tmp/'classes.jar','-C',classes,'.')
        dex=tmp/'dex'; dex.mkdir(); run(tools/'d8','--min-api','26','--lib',android,'--output',dex,tmp/'classes.jar')
        unsigned=tmp/'unsigned.apk'
        ET.register_namespace('android','http://schemas.android.com/apk/res/android')
        manifest=ET.parse(main/'AndroidManifest.xml'); manifest.getroot().set('package','org.foodresearch.crowd'); manifest.write(main/'AndroidManifest.xml',encoding='utf-8')
        run(tools/'aapt2','link','-I',android,'--manifest',main/'AndroidManifest.xml','--min-sdk-version','26','--target-sdk-version','35','--version-code','40000','--version-name',VERSION,'-o',unsigned)
        with zipfile.ZipFile(unsigned,'a',zipfile.ZIP_DEFLATED) as z:
            for file in sorted((main/'assets').rglob('*')):
                if file.is_file(): z.write(file,'assets/'+file.relative_to(main/'assets').as_posix())
            z.write(dex/'classes.dex','classes.dex')
        aligned=tmp/'aligned.apk'; run(tools/'zipalign','-p','-f','4',unsigned,aligned)
        # ponytail: debug signer for internal acceptance only; distribution needs the owner's signing key.
        key=Path(os.environ.get('CROWD_ANDROID_DEBUG_KEYSTORE',str(Path(tempfile.gettempdir())/'crowd-android-debug.keystore'))); key.parent.mkdir(parents=True,exist_ok=True)
        if not key.exists(): run('keytool','-genkeypair','-keystore',key,'-storepass','android','-keypass','android','-alias','androiddebugkey','-dname','CN=Internal Crowd Test','-keyalg','RSA','-keysize','2048','-validity','3650')
        apk=out/f'crowd-android-v{VERSION}-debug.apk'
        run(tools/'apksigner','sign','--v4-signing-enabled','false','--ks',key,'--ks-key-alias','androiddebugkey','--ks-pass','pass:android','--out',apk,aligned)
        run(tools/'apksigner','verify','--verbose',apk)
        (out/'SHA256SUMS-android-v4.txt').write_text(hashlib.sha256(apk.read_bytes()).hexdigest()+'  '+apk.name+'\n')
        print('Built and verified internal test APK; device behavior remains to be tested')


if __name__=='__main__': main()
