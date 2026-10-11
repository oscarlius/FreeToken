#!/usr/bin/env python3
"""D09 v2 fixed-protocol executor; --filedry exercises the same launch/request/judge plan without GPU."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent; ROOT=HERE.parent; R067=ROOT/'r067d_short_tail_v1'/'R067D_CONFIG_CPU_ONLY.json'; PRED=ROOT/'d09_prediction_20261009'; RID='E2-D09-message-boundary-v2'; CAND='c17b69a46cd512fbf3d127d3879bce92caae457b'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fixed_argv(port,arm,enabled):
 s=json.loads(R067.read_text())['services'][0]; a=list(s['argv']); a[a.index('--port')+1]=str(port); a[5]=arm+'/t17_d14_startup.py'; a=[x.replace('E2-R067d-d20-short-tail-v1',RID).replace('/data2/FreeToken/wt/release-e2','/data2/FreeToken/wt/d09-message-boundary-v1') for x in a]
 if enabled:a.append('--enable-message-boundary-ckpt')
 return a
def spec():
 src={p.name:sha(p) for p in (PRED/'source').glob('*.json')}; stages=[
 {'id':'T16','services':8,'calls':8,'enabled':False,'judge':'retained strict args + sampled token ids/full text bitwise'},
 {'id':'T17','services':6,'calls':8,'enabled':True,'cases':[{'boundary':20282,'tail':1020},{'boundary':22558,'tail':197}],'judge':'exact-id coldA/coldB equals hot; boundary must be derived from frozen rendered message input'},
 {'id':'T03b','services':2,'calls':2,'enabled':True,'input':'C_edit.json','judge':'edited replay equals cold edit; first nonempty delta stops'},
 {'id':'T2','services':6,'calls':6,'enabled':True,'inputs':['trace_rev.json','C_coldfirst.json','C_warm.json','C_edit.json'],'judge':'reverse cold, ascending warm, edit; compare each first nonempty delta to sealed prediction'}]
 port=32101; arms=[]
 for st in stages:
  for n in range(st['services']):
   arm=f'/data2/FreeToken/runs/dev_D09/{RID}/{st["id"]}/arm{n:02d}'; arms.append({'stage':st['id'],'name':f'{st["id"]}_arm{n:02d}','argv':fixed_argv(port,arm,st['enabled']),'cwd':arm,'port':port});port+=1
 return {'schema':'freetoken.d09.execution-spec/v2','rid':RID,'candidate':CAND,'base':'481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9','prediction_manifest_sha256':'edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9','source_recipe_sha256':sha(R067),'inputs':src,'stages':stages,'arms':arms,'budget':{'services':sum(x['services'] for x in stages),'calls':sum(x['calls'] for x in stages),'reason':'four required gates; no probe/toy calls'},'extension_provenance':'before run, copy only existing 481 extensions after SHA+size equality; python-only diff excludes kernel/csrc/.cu/.cpp/.so'}
def judge(a,b):
 assert a['token_ids']==b['token_ids'] and a['text']==b['text'];return {'pass':True,'first_nonempty_delta':None}
def main():
 p=argparse.ArgumentParser();p.add_argument('--filedry',action='store_true');p.add_argument('--run',action='store_true');a=p.parse_args();x=spec(); (HERE/'D09_EXECUTION_SPEC_v2.json').write_text(json.dumps(x,indent=2)+'\n')
 if a.filedry:
  # Mock the actual process/request/judge seam; no network or subprocess is touched.
  mock={'token_ids':[1,2],'text':'ok'}; out={'spec_sha256':sha(HERE/'D09_EXECUTION_SPEC_v2.json'),'arms':len(x['arms']),'calls':x['budget']['calls'],'mock_start_paths':[z['argv'][5] for z in x['arms']],'judge':judge(mock,mock),'gpu_started':False,'http_started':False};(HERE/'FILEDRY_v2.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out));return
 if a.run: raise SystemExit('root admission gate is external; CPU preparer never starts GPU')
 p.error('choose --filedry')
if __name__=='__main__':main()
