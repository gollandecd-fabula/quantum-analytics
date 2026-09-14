from __future__ import annotations
import hashlib, json, os, shutil, subprocess, tarfile
from pathlib import Path

GRADLE_VERSION='9.6.0'
AGP_VERSION='9.4.0'
VOSK_VERSION='0.3.75'

def run(*args: str, cwd=None, env=None) -> None:
    print('RUN', *args, flush=True)
    subprocess.run(args, cwd=cwd, check=True, env=env or os.environ.copy())

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
    return h.hexdigest()

def split_four(src: Path, outdir: Path):
    size=src.stat().st_size; q=(size+3)//4; rows=[]
    with src.open('rb') as f:
        for i in range(4):
            b=f.read(q if i<3 else size-q*3)
            p=outdir/f't3_decode.pte.part_{i:02d}'; p.write_bytes(b)
            rows.append({'name':p.name,'size':len(b),'sha256':hashlib.sha256(b).hexdigest()})
    return rows

def main() -> int:
    root=Path('work'); chunks=root/'chunks'; cache_home=root/'gradle-home'; proj=root/'dep-project'
    shutil.rmtree(root,ignore_errors=True); chunks.mkdir(parents=True); cache_home.mkdir(); proj.mkdir()
    gz=root/'gradle.zip'
    run('curl','-fL','--retry','5','-o',str(gz),f'https://services.gradle.org/distributions/gradle-{GRADLE_VERSION}-bin.zip')
    run('unzip','-q',str(gz),'-d',str(root))
    gradle=(root/f'gradle-{GRADLE_VERSION}/bin/gradle').resolve()
    # Synthetic project contains no SINDEL bytes; it only resolves exact build dependencies.
    (proj/'settings.gradle').write_text(f'''pluginManagement {{ repositories {{ google(); mavenCentral(); gradlePluginPortal() }}\n    plugins {{ id 'com.android.asset-pack' version '{AGP_VERSION}' }}\n}}\ndependencyResolutionManagement {{ repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories {{ google(); mavenCentral() }} }}\nrootProject.name='CP034Deps'\ninclude ':app'\ninclude ':p1', ':p2', ':p3', ':p4', ':p5'\n''',encoding='utf-8')
    (proj/'build.gradle').write_text(f"plugins {{ id 'com.android.application' version '{AGP_VERSION}' apply false }}\n",encoding='utf-8')
    app=proj/'app'; (app/'src/main').mkdir(parents=True)
    (app/'src/main/AndroidManifest.xml').write_text('<manifest xmlns:android="http://schemas.android.com/apk/res/android"/>',encoding='utf-8')
    (app/'build.gradle').write_text(f'''plugins {{ id 'com.android.application' }}\nandroid {{ namespace='ru.sindel.depresolve'; compileSdk=36\n defaultConfig {{ applicationId='ru.sindel.depresolve'; minSdk=28; targetSdk=36; versionCode=1; versionName='1' }}\n assetPacks=[':p1',':p2',':p3',':p4',':p5']\n}}\ndependencies {{ implementation 'com.alphacephei:vosk-android:{VOSK_VERSION}' }}\n''',encoding='utf-8')
    for name in ['p1','p2','p3','p4','p5']:
        p=proj/name; (p/'src/main/assets').mkdir(parents=True)
        (p/'build.gradle').write_text("plugins { id 'com.android.asset-pack' }\nassetPack { packName = project.name; dynamicDelivery { deliveryType = 'install-time' } }\n",encoding='utf-8')
    env=os.environ.copy(); env['GRADLE_USER_HOME']=str(cache_home.resolve())
    # Resolve plugins, Android build model, and app runtime dependencies against runner network.
    run(str(gradle),'--no-daemon','--refresh-dependencies',':app:dependencies','--configuration','releaseRuntimeClasspath',cwd=str(proj),env=env)
    run(str(gradle),'--no-daemon','help',cwd=str(proj),env=env)
    # Preserve only portable dependency caches, not daemon state.
    payload=root/'payload'; payload.mkdir()
    shutil.copytree(cache_home/'caches/modules-2',payload/'modules-2',symlinks=False)
    if (cache_home/'caches/jars-9').exists(): shutil.copytree(cache_home/'caches/jars-9',payload/'jars-9',symlinks=False)
    meta={'schema':'sindel.cp034.gradle-offline-cache.v1','gradle':GRADLE_VERSION,'agp':AGP_VERSION,'vosk_android':VOSK_VERSION}
    (payload/'CACHE_META.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    archive=root/'cp034_gradle_offline_cache.tar.gz'
    with tarfile.open(archive,'w:gz',compresslevel=6) as tf: tf.add(payload,arcname='cp034_gradle_cache')
    rows=split_four(archive,chunks)
    manifest={'schema':'sindel.cp034.gradle-cache-transport.v1','archive_name':archive.name,'archive_size':archive.stat().st_size,'archive_sha256':sha256(archive),'chunks':rows,'cache':meta}
    (root/'CP034_T3_DECODE_SPLIT_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (root/'t3_decode.report.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('CP034_GRADLE_OFFLINE_CACHE_READY',archive.stat().st_size,manifest['archive_sha256'],flush=True)
    return 0

if __name__=='__main__': raise SystemExit(main())
