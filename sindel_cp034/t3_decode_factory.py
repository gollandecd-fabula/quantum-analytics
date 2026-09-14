from __future__ import annotations
import hashlib, json, os, shutil, subprocess, sys, tarfile
from pathlib import Path

GRADLE_VERSION='9.6.0'
BUNDLETOOL_VERSION='1.18.3'

def run(*args: str, env=None) -> None:
    print('RUN', *args, flush=True)
    subprocess.run(args, check=True, env=env or os.environ.copy())

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()

def find_jdk17() -> Path:
    cands=[]
    for key in ('JAVA_HOME_17_X64','JAVA_HOME'):
        v=os.environ.get(key)
        if v: cands.append(Path(v))
    cands += sorted(Path('/opt/hostedtoolcache').glob('Java_*jdk/17*/x64'))
    for p in cands:
        java=p/'bin/java'
        if java.is_file():
            out=subprocess.check_output([str(java),'-version'],stderr=subprocess.STDOUT,text=True)
            if 'version "17' in out:
                print('JDK17',p,flush=True); return p
    raise SystemExit('FAIL-CLOSED: JDK17 not found')

def split_four(src: Path, outdir: Path):
    size=src.stat().st_size
    q=(size+3)//4
    rows=[]
    with src.open('rb') as f:
        for i in range(4):
            data=f.read(q if i<3 else size-q*3)
            if not data: data=b'\0'
            p=outdir/f't3_decode.pte.part_{i:02d}'
            p.write_bytes(data)
            rows.append({'name':p.name,'size':p.stat().st_size,'sha256':sha256(p)})
    return rows

def main() -> int:
    work=Path('work'); chunks=work/'chunks'; payload=work/'toolchain_payload'
    shutil.rmtree(work,ignore_errors=True); chunks.mkdir(parents=True); payload.mkdir(parents=True)
    android_home=Path(os.environ.get('ANDROID_HOME') or os.environ.get('ANDROID_SDK_ROOT') or '')
    sdkmanager=android_home/'cmdline-tools/latest/bin/sdkmanager'
    if not sdkmanager.is_file(): raise SystemExit('FAIL-CLOSED: sdkmanager not found')
    run(str(sdkmanager),'platforms;android-36','build-tools;36.0.0')
    for p in (android_home/'platforms/android-36',android_home/'build-tools/36.0.0'):
        if not p.is_dir(): raise SystemExit(f'FAIL-CLOSED: missing {p}')
    # Gradle exact minimum/default for AGP 9.4.
    gradle_zip=work/'gradle.zip'
    run('curl','-fL','--retry','5','-o',str(gradle_zip),f'https://services.gradle.org/distributions/gradle-{GRADLE_VERSION}-bin.zip')
    run('unzip','-q',str(gradle_zip),'-d',str(payload))
    # Bundletool exact release.
    bdir=payload/'bundletool'; bdir.mkdir()
    bjar=bdir/f'bundletool-all-{BUNDLETOOL_VERSION}.jar'
    run('curl','-fL','--retry','5','-o',str(bjar),f'https://github.com/google/bundletool/releases/download/{BUNDLETOOL_VERSION}/bundletool-all-{BUNDLETOOL_VERSION}.jar')
    # Minimal Android SDK needed for private local compilation.
    sdkout=payload/'android-sdk'; (sdkout/'platforms').mkdir(parents=True); (sdkout/'build-tools').mkdir(parents=True)
    shutil.copytree(android_home/'platforms/android-36',sdkout/'platforms/android-36',symlinks=True)
    shutil.copytree(android_home/'build-tools/36.0.0',sdkout/'build-tools/36.0.0',symlinks=True)
    # JDK17 exact build JDK.
    jdk=find_jdk17(); shutil.copytree(jdk,payload/'jdk17',symlinks=True)
    # Version evidence.
    java=payload/'jdk17/bin/java'; gradle=payload/f'gradle-{GRADLE_VERSION}/bin/gradle'
    versions={
      'schema':'sindel.cp034.android-toolchain.v1',
      'gradle_version':GRADLE_VERSION,
      'bundletool_version':BUNDLETOOL_VERSION,
      'android_platform':'android-36',
      'build_tools':'36.0.0',
      'java_version':subprocess.check_output([str(java),'-version'],stderr=subprocess.STDOUT,text=True).splitlines()[0],
    }
    (payload/'TOOLCHAIN_META.json').write_text(json.dumps(versions,indent=2),encoding='utf-8')
    run(str(gradle),'--version')
    run(str(java),'-jar',str(bjar),'version')
    # Deterministic-ish tar transport; file SHA is the transport lock.
    archive=work/'cp034_android_toolchain.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=6) as tf:
        tf.add(payload,arcname='cp034_android_toolchain')
    rows=split_four(archive,chunks)
    manifest={'schema':'sindel.cp034.toolchain-transport.v1','archive_name':archive.name,'archive_size':archive.stat().st_size,'archive_sha256':sha256(archive),'chunks':rows,'toolchain':versions}
    (work/'CP034_T3_DECODE_SPLIT_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (work/'t3_decode.report.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('CP034_ANDROID_TOOLCHAIN_READY',archive.stat().st_size,manifest['archive_sha256'],flush=True)
    return 0

if __name__=='__main__': raise SystemExit(main())
