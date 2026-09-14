from __future__ import annotations
import hashlib, importlib.metadata, importlib.util, json, os, subprocess, sys
from pathlib import Path

T3_SHA='5abca8321ede76f8e61f1cc0d19aea6c946b28871017ce8726f8a69203f05953'
T3_SIZE=2143989928
GRAPH_SHA='f4efd70b131bd2c06a1fbaf06ba9b3aed3dc319994cc8b5748edfdb45f7a17f9'
HF_REV='e2d6902dd4c1301892935d0a0277325551e8060e'
CHATTERBOX_COMMIT='5de7a54aa4e5e2baadb0182dde554908b48b85c2'

def run(*args: str) -> None:
    print('RUN', *args, flush=True)
    subprocess.run(args, check=True, env=os.environ.copy())

def sha256(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):
            h.update(b)
    return h.hexdigest()

def ensure_env() -> None:
    marker=Path('work/.deps_ready')
    if marker.exists(): return
    run(sys.executable,'-m','pip','install','--upgrade','pip')
    run(sys.executable,'-m','pip','install','--index-url','https://download.pytorch.org/whl/cpu','torch==2.10.0','torchaudio==2.10.0')
    run(sys.executable,'-m','pip','install','--no-deps','executorch==1.1.0','torchao==0.16.0')
    run(sys.executable,'-m','pip','install','flatbuffers','expecttest','hypothesis','kgb','parameterized','hydra-core','omegaconf','pytorch-tokenizers','ruamel.yaml','tabulate','typing-extensions','pyyaml','safetensors==0.5.3','transformers==5.2.0','huggingface_hub[hf_xet]','einops')
    run(sys.executable,'-m','pip','install','--no-deps',f'git+https://github.com/resemble-ai/chatterbox.git@{CHATTERBOX_COMMIT}')
    marker.parent.mkdir(parents=True,exist_ok=True); marker.write_text('ready')

def configure_exact_imports() -> None:
    real=Path(importlib.metadata.distribution('chatterbox-tts').locate_file('chatterbox')).resolve()
    shim=Path('work/import_shim/chatterbox'); shim.mkdir(parents=True,exist_ok=True)
    (shim/'__init__.py').write_text("__path__=["+repr(str(real))+"]\n",encoding='utf-8')
    os.environ['PYTHONPATH']=str(shim.parent.resolve())+os.pathsep+os.environ.get('PYTHONPATH','')
    spec=importlib.util.find_spec('executorch')
    if not spec or not spec.submodule_search_locations: raise SystemExit('FAIL-CLOSED executorch package missing')
    eroot=Path(next(iter(spec.submodule_search_locations))).resolve()
    candidates=[eroot/'data/bin/flatc',eroot.parent/'bin/flatc']
    flatc=next((p for p in candidates if p.is_file()),None)
    if flatc is None: raise SystemExit('FAIL-CLOSED flatc not found')
    flatc.chmod(flatc.stat().st_mode | 0o111)
    os.environ['FLATC_EXECUTABLE']=str(flatc)
    print('IMPORT_SHIM_PASS',real,flush=True); print('FLATC',flatc,flush=True)

def fetch_t3() -> Path:
    from huggingface_hub import hf_hub_download
    import shutil
    out=Path('work/t3_mtl23ls_v3.safetensors')
    if not out.exists():
        src=Path(hf_hub_download(repo_id='ResembleAI/chatterbox',filename='t3_mtl23ls_v3.safetensors',revision=HF_REV))
        out.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(src,out)
    got=sha256(out)
    if got!=T3_SHA or out.stat().st_size!=T3_SIZE:
        raise SystemExit(f'FAIL-CLOSED T3 bytes drift size={out.stat().st_size} sha={got}')
    print('T3_BYTES_PASS',out.stat().st_size,got,flush=True)
    return out

def main() -> int:
    os.environ.setdefault('MALLOC_ARENA_MAX','2'); os.environ.setdefault('OMP_NUM_THREADS','1'); os.environ.setdefault('MKL_NUM_THREADS','1')
    Path('work/chunks').mkdir(parents=True,exist_ok=True)
    ensure_env(); configure_exact_imports(); t3=fetch_t3()
    out=Path('work/t3_decode.pte')
    run(sys.executable,'sindel_cp034/export_t3_decode_stage.py','--t3',str(t3),'--out',str(out),'--half-init')
    report=Path('work/t3_decode.report.json'); j=json.loads(report.read_text())
    if j.get('graph_code_sha256')!=GRAPH_SHA:
        raise SystemExit(f"FAIL-CLOSED graph mismatch {j.get('graph_code_sha256')}")
    psha=sha256(out)
    if j.get('pte_sha256')!=psha or j.get('pte_size')!=out.stat().st_size:
        raise SystemExit('FAIL-CLOSED PTE report mismatch')
    rows=[]
    with out.open('rb') as f:
        i=0
        while True:
            b=f.read(300*1024*1024)
            if not b: break
            q=Path('work/chunks')/f't3_decode.pte.part_{i:02d}'
            q.write_bytes(b)
            rows.append({'name':q.name,'size':len(b),'sha256':hashlib.sha256(b).hexdigest()}); i+=1
    manifest={'graph_code_sha256':GRAPH_SHA,'pte_size':out.stat().st_size,'pte_sha256':psha,'chunks':rows}
    Path('work/CP034_T3_DECODE_SPLIT_MANIFEST.json').write_text(json.dumps(manifest,indent=2))
    print('REMOTE_GRAPH_PASS',GRAPH_SHA,flush=True); print('PTE_PASS',out.stat().st_size,psha,flush=True); print('CHUNKS',len(rows),flush=True)
    return 0

if __name__=='__main__': raise SystemExit(main())
