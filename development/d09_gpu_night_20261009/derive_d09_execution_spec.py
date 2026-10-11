#!/usr/bin/env python3
"""Derive D09's immutable execution packet from the R067d formal recipe; CPU-only."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
R067=ROOT/'r067d_short_tail_v1'/'R067D_CONFIG_CPU_ONLY.json'
PRED=ROOT/'d09_prediction_20261009'
CAND='c17b69a46cd512fbf3d127d3879bce92caae457b'; BASE='481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'; RID='E2-D09-message-boundary-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 r=json.loads(R067.read_text()); m=json.loads((PRED/'PREDICTION_MANIFEST_v4.json').read_text())
 # Retain R067d service/call budget exactly; D09 adds no broader concurrency.
 services=[]
 for s in r['services']:
  x={k:v for k,v in s.items() if k in ('name','kind','port_pair','requests','request','schedule')}
  x['worktree']='/data2/FreeToken/wt/d09-message-boundary-v1'; x['candidate_commit']=CAND
  x['argv']=[str(v).replace('/data2/FreeToken/wt/d20_short_tail_v1','/data2/FreeToken/wt/d09-message-boundary-v1').replace('E2-R067d-d20-short-tail-v1',RID) for v in s['argv']]
  x['argv_recipe']='R067d argv with worktree/python and arm paths rewritten to D09 run root; candidate arms add --enable-message-boundary-ckpt, T16 default-off arms omit it.'
  services.append(x)
 inputs={p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in (PRED/'source').glob('*.json')}
 packet={'schema':'freetoken.d09.execution-spec/v1','rid':RID,'base_commit':BASE,'candidate_commit':CAND,
 'source_recipe':{'path':str(R067),'sha256':sha(R067),'budget':r['scope']},
 'worktrees':{'base':'/data2/FreeToken/wt/release-e2','candidate':'/data2/FreeToken/wt/d09-message-boundary-v1'},
 'extension_provenance':{'policy':'copy existing release481 extensions only after SHA+size manifest equality; no build/NVCC/JIT','required_python_only_diff':'git diff --name-only 481d3a7..c17b69a must exclude kernel/csrc and .cu/.cpp/.so'},
 't16':{'arms':['base_default_off','candidate_default_off'],'judge':'retained fullrunner strict_args + deterministic sampled-token/full-text equality','default_off':True},
 't17':{'topology':'cold_A/cold_B versus hot seed+query using R067d exact-ID endpoint and owned lifecycle','cases':[{'boundary':20282,'tail':1020},{'boundary':22558,'tail':197}],'page_size':64,'candidate_flag':'--enable-message-boundary-ckpt'},
 't03b':{'input':'C_edit.json','judge':'edit replay is compared to its cold replay; stop first nonempty delta'},
 't2':{'order':['reverse_cold','ascending_warm','edit'],'inputs':inputs,'judge':'per round first nonempty delta compared to sealed prediction; preserve source max_tokens'},
 'services':services,'prediction':{'path':str(PRED/'CURRENT_PREDICTION.json'),'sha256':sha(PRED/'CURRENT_PREDICTION.json'),'manifest_sha256':'edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9'},
 'admission':'root seals actual argv after FILEdry binding; no GPU/HTTP/compiler action by this preparer'}
 out=HERE/'D09_EXECUTION_SPEC.json';out.write_text(json.dumps(packet,indent=2)+'\n');print(out,sha(out))
if __name__=='__main__':main()
