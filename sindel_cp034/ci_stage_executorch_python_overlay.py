#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, pathlib, subprocess, sys

EXPECTED_EXECUTORCH='1.1.0'
EXPECTED_TORCHAO='0.16.0'

def sha256(path:pathlib.Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):
            h.update(b)
    return h.hexdigest()

def main()->int:
    ws=os.environ.get('GITHUB_WORKSPACE')
    if not ws:
        print('CP034_PY_OVERLAY_SKIP_NON_CI')
        return 0
    root=pathlib.Path(ws)/'out'/'python_export_overlay'
    root.mkdir(parents=True,exist_ok=True)
    pkgs=[
        'executorch==1.1.0','torchao==0.16.0','flatbuffers>=24.3.25','expecttest',
        'hypothesis','kgb','parameterized','hydra-core>=1.3.0','omegaconf>=2.3.0',
        'pytorch-tokenizers>=1.1','ruamel.yaml','tabulate','typing-extensions>=4.10.0'
    ]
    subprocess.check_call([sys.executable,'-m','pip','install','--target',str(root),'--no-deps',*pkgs])
    env=dict(os.environ); env['PYTHONPATH']=str(root)
    probe=(
        "import executorch,torchao;"
        "from importlib.metadata import version;"
        "assert version('executorch')=='1.1.0',version('executorch');"
        "assert version('torchao')=='0.16.0',version('torchao');"
        "from executorch.exir import to_edge_transform_and_lower,EdgeCompileConfig;"
        "from executorch.backends.xnnpack.partition.xnnpack_partitioner import XnnpackPartitioner;"
        "print('CP034_PY_OVERLAY_IMPORT_PASS',version('executorch'),version('torchao'))"
    )
    subprocess.check_call([sys.executable,'-c',probe],env=env)
    rows=[]
    for p in sorted(root.rglob('*')):
        if p.is_file(): rows.append({'path':p.relative_to(root).as_posix(),'size':p.stat().st_size,'sha256':sha256(p)})
    manifest={'executorch':EXPECTED_EXECUTORCH,'torchao':EXPECTED_TORCHAO,'files':rows}
    mp=pathlib.Path(ws)/'out'/'CP034_PY_EXPORT_OVERLAY_MANIFEST.json'
    mp.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('CP034_PY_OVERLAY_PASS',len(rows),sha256(mp))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
