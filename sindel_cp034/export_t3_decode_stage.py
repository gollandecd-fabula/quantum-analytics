from __future__ import annotations
import argparse, ctypes, gc, hashlib, json
from pathlib import Path
import torch
import torch.nn as nn
import torch.nn.functional as F
from safetensors.torch import load_file as load_safetensors

T3_SHA='5abca8321ede76f8e61f1cc0d19aea6c946b28871017ce8726f8a69203f05953'
SOURCE_COMMIT='5de7a54aa4e5e2baadb0182dde554908b48b85c2'
EXACT_EXPORTER_SHA='532d84ded6cb06714f9298621aa565859b8d481e91e2aea6d66bb6a9a80ed595'
COND_LEN=34
MAX_TEXT=256
MAX_SPEECH=1000

def sha(p: Path) -> str:
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):
            h.update(b)
    return h.hexdigest()

def graph_digest(ep):
    b=ep.graph_module.code.encode('utf-8')
    return hashlib.sha256(b).hexdigest(),len(b)

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--t3',required=True)
    ap.add_argument('--out',required=True)
    ap.add_argument('--half-init',action='store_true')
    a=ap.parse_args()
    t3p=Path(a.t3)
    if sha(t3p)!=T3_SHA:
        raise SystemExit('FAIL-CLOSED T3 SHA drift')
    from chatterbox.models.t3 import T3
    from chatterbox.models.t3.modules.t3_config import T3Config
    if a.half_init:
        old=torch.get_default_dtype(); torch.set_default_dtype(torch.float16)
        try: t3=T3(T3Config.multilingual())
        finally: torch.set_default_dtype(old)
    else:
        t3=T3(T3Config.multilingual())
    st=load_safetensors(t3p)
    if 'model' in st:
        st=st['model'][0]
    t3.load_state_dict(st)
    t3.eval().cpu()
    del st
    if t3.cfg.num_attention_heads != t3.cfg.num_key_value_heads:
        raise RuntimeError('Exporter requires equal Q/KV heads')
    N_LAYERS=int(t3.cfg.num_hidden_layers)
    N_HEADS=int(t3.cfg.num_attention_heads)
    HD=int(t3.cfg.hidden_size//N_HEADS)
    DIM=int(t3.cfg.hidden_size)
    SPEECH_VOCAB=int(t3.hp.speech_tokens_dict_size)
    SPEECH_SOT=int(t3.hp.start_speech_token)
    TEXT_SEQ=MAX_TEXT+2
    PREFILL_LEN=COND_LEN+TEXT_SEQ+2
    MAX_KV=PREFILL_LEN+MAX_SPEECH
    def rotate_half(x):
        half=x.shape[-1]//2
        return torch.cat([-x[...,half:],x[...,:half]],dim=-1)
    class Layer(nn.Module):
        def __init__(self,h):
            super().__init__()
            def lin(src):
                z=nn.Linear(src.in_features,src.out_features,bias=False)
                z.weight=nn.Parameter(src.weight.data.clone(),requires_grad=False)
                return z
            self.q=lin(h.self_attn.q_proj); self.k=lin(h.self_attn.k_proj)
            self.v=lin(h.self_attn.v_proj); self.o=lin(h.self_attn.o_proj)
            self.g=lin(h.mlp.gate_proj); self.u=lin(h.mlp.up_proj); self.d=lin(h.mlp.down_proj)
            self.register_buffer('ln1',h.input_layernorm.weight.data.clone())
            self.register_buffer('ln2',h.post_attention_layernorm.weight.data.clone())
    class T3DecodeN3(nn.Module):
        def __init__(self,model):
            super().__init__()
            self.speech_emb=model.speech_emb
            self.speech_pos=model.speech_pos_emb
            self.layers=nn.ModuleList([Layer(x) for x in model.tfmr.layers])
            self.head=nn.Linear(DIM,SPEECH_VOCAB,bias=False)
            self.head.weight=nn.Parameter(model.speech_head.weight.data.clone(),requires_grad=False)
            self.register_buffer('norm',model.tfmr.norm.weight.data.clone())
            self.eps=float(model.cfg.rms_norm_eps)
            inv=model.tfmr.rotary_emb.inv_freq.float()
            pos=torch.arange(MAX_KV,dtype=torch.float32)
            freq=torch.outer(pos,inv)
            emb=torch.cat([freq,freq],-1)
            self.register_buffer('rcos',emb.cos())
            self.register_buffer('rsin',emb.sin())
            self.register_buffer('kvpos',torch.arange(MAX_KV))
        def rms(self,x,w):
            return x*torch.rsqrt(x.pow(2).mean(-1,keepdim=True)+self.eps)*w
        def forward(self,prev_token,speech_pos,kv_k,kv_v):
            sp=speech_pos[0]
            x=self.speech_emb(prev_token)+self.speech_pos.get_fixed_embedding(sp.reshape(1,1))
            x=torch.cat([x,x],dim=0)
            write=torch.tensor(PREFILL_LEN,dtype=torch.long,device=x.device)+(sp-1)
            valid=self.kvpos<=write
            bias=torch.where(valid,torch.zeros(MAX_KV,dtype=x.dtype,device=x.device),torch.full((MAX_KV,),float('-inf'),dtype=x.dtype,device=x.device)).reshape(1,1,1,MAX_KV)
            wi=write.reshape(1)
            cw=torch.index_select(self.rcos,0,wi).reshape(1,1,1,HD)
            sw=torch.index_select(self.rsin,0,wi).reshape(1,1,1,HD)
            score_pm=(self.kvpos==write).reshape(1,1,1,MAX_KV)
            value_pm=(self.kvpos==write).reshape(1,1,MAX_KV,1)
            nks=[]; nvs=[]
            for i,layer in enumerate(self.layers):
                r=x; xn=self.rms(x,layer.ln1)
                q=layer.q(xn).view(2,1,N_HEADS,HD).permute(0,2,1,3)
                k=layer.k(xn).view(2,1,N_HEADS,HD).permute(0,2,1,3)
                v=layer.v(xn).view(2,1,N_HEADS,HD).permute(0,2,1,3)
                q=q*cw+rotate_half(q)*sw
                k=k*cw+rotate_half(k)*sw
                nks.append(k); nvs.append(v)
                base_scores=torch.matmul(q,kv_k[i].transpose(-2,-1))*(HD**-0.5)+bias
                current_score=torch.matmul(q,k.transpose(-2,-1))*(HD**-0.5)
                scores=torch.where(score_pm,current_score,base_scores)
                att=F.softmax(scores,dim=-1)
                uv=torch.where(value_pm,v.expand(2,N_HEADS,MAX_KV,HD),kv_v[i])
                ao=torch.matmul(att,uv)
                ao=ao.permute(0,2,1,3).reshape(2,1,DIM)
                x=layer.o(ao)+r
                r=x; xn=self.rms(x,layer.ln2)
                x=layer.d(F.silu(layer.g(xn))*layer.u(xn))+r
            x=self.rms(x,self.norm)
            return self.head(x[:,-1,:]),torch.stack(nks),torch.stack(nvs)
    dec=T3DecodeN3(t3).eval().half()
    dk=torch.zeros(N_LAYERS,2,N_HEADS,MAX_KV,HD,dtype=torch.float16)
    dv=torch.zeros_like(dk)
    dprev=torch.tensor([[SPEECH_SOT]],dtype=torch.long)
    dpos=torch.tensor([1],dtype=torch.long)
    with torch.no_grad():
        dlo,dko,dvo=dec(dprev,dpos,dk,dv)
    delta_shape=(N_LAYERS,2,N_HEADS,1,HD)
    if tuple(dlo.shape)!=(2,SPEECH_VOCAB) or tuple(dko.shape)!=delta_shape or tuple(dvo.shape)!=delta_shape:
        raise RuntimeError('decode delta shape mismatch')
    from torch.export import export
    ep=export(dec,(dprev,dpos,dk,dv))
    gd,gs=graph_digest(ep)
    del t3,dec,dk,dv,dprev,dpos,dlo,dko,dvo
    gc.collect()
    try: ctypes.CDLL('libc.so.6').malloc_trim(0)
    except Exception: pass
    report={'source_exporter_sha256':EXACT_EXPORTER_SHA,'source_commit':SOURCE_COMMIT,'t3_sha256':T3_SHA,'cond_len':COND_LEN,'prefill_len':PREFILL_LEN,'max_kv':MAX_KV,'n_layers':N_LAYERS,'n_heads':N_HEADS,'head_dim':HD,'speech_vocab':SPEECH_VOCAB,'graph_code_sha256':gd,'graph_code_bytes':gs}
    print(json.dumps({'event':'T3_DECODE_GRAPH_READY',**report},sort_keys=True),flush=True)
    from executorch.exir import to_edge_transform_and_lower, EdgeCompileConfig
    from executorch.backends.xnnpack.partition.xnnpack_partitioner import XnnpackPartitioner
    edge=to_edge_transform_and_lower(ep,compile_config=EdgeCompileConfig(_check_ir_validity=False),partitioner=[XnnpackPartitioner()])
    del ep
    gc.collect()
    try: ctypes.CDLL('libc.so.6').malloc_trim(0)
    except Exception: pass
    program=edge.to_executorch()
    del edge
    gc.collect()
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('wb') as f:
        program.write_to_file(f)
    report.update({'pte_size':out.stat().st_size,'pte_sha256':sha(out)})
    out.with_suffix('.report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'event':'T3_DECODE_PTE_READY',**report},sort_keys=True),flush=True)
    return 0
if __name__=='__main__':
    raise SystemExit(main())
