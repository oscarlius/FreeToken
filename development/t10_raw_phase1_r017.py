#!/usr/bin/env python3
"""T10 phase 1: replay the sealed trace while retaining exact terminal engine IDs."""
from __future__ import annotations
import argparse, os, ast, hashlib, os, importlib.util, json, re, shlex, subprocess, sys
from pathlib import Path

ROOT=Path('/data2/FreeToken'); ROUNDS=Path('/data2/_shared/runs/ft_rounds'); CANDIDATE=ROOT/'wt/e1r003st'
CANDIDATE_COMMIT='c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
FRONTEND_PATH=ROOT/'runs/dev_D03/t10_frontend_tokens_c30ae0d.json'
FRONTEND_SHA='bf1f38901055e79e0b4ae48615f4ce1f58a4efc02a31f88ff644d857c6bc0356'
RID='E2-R017'; PY=str(ROOT/'venv/bin/python'); MODEL='Qwen3.8-Flash-Next-NVFP4'; PORT=8095

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_new(p,v):
 with Path(p).open('x',encoding='utf-8') as f: json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False); f.write('\n')
def digest(ids):
 import struct
 if not isinstance(ids,list) or not ids or any(type(x)is not int or x<0 or x>2**31-1 for x in ids): raise ValueError('nonempty uint31 IDs required')
 return hashlib.sha256(struct.pack(f'<{len(ids)}i',*ids)).hexdigest()
def load_sc():
 p=ROOT/'runs/dev_D03/d03_gpu_selfcheck.py'; spec=importlib.util.spec_from_file_location('d03_sc',p)
 if spec is None or spec.loader is None: raise RuntimeError('cannot load uploaded D03 lifecycle')
 m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def token(p):
 x=json.loads(Path(p).read_text(encoding='utf-8')); prompt=x.get('prompt_ids'); out=x.get('generated_ids')
 if x.get('schema')!='ft_dev_tokens/v1' or x.get('finish_reason') not in ('stop','length') or type(x.get('uid')) is not int or x['uid'] < 0 or type(x.get('pid')) is not int or x['pid'] <= 0: raise ValueError('invalid terminal token record')
 if x.get('prompt_length')!=len(prompt or []) or x.get('prompt_ids_sha256_int32le')!=digest(prompt) or x.get('generated_ids_sha256_int32le')!=digest(out) or x.get('input_ids_sha256_int32le')!=digest(prompt+out): raise ValueError('unbound terminal IDs')
 return x
def trace_keys(path):
 rows=json.loads(Path(path).read_text(encoding='utf-8')).get('rounds') or []
 out=set()
 for item in rows:
  messages=item.get('messages'); rec=item.get('record') or {}; key=hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:16]
  if rec.get('messages_sha') != key: raise ValueError('trace record/messages digest mismatch')
  out.add(key)
 if len(out)!=12: raise ValueError('canonical trace lacks 12 unique message snapshots')
 return out
def frontend(p, candidate_commit, reverse_sha, forward_sha, reverse_trace, forward_trace):
 if Path(p).resolve()!=FRONTEND_PATH.resolve() or sha(p)!=FRONTEND_SHA: raise ValueError('frontend manifest is not canonical frozen c30 artifact')
 x=json.loads(Path(p).read_text(encoding='utf-8')); rows=x.get('rounds')
 if x.get('schema') != 't10_frontend_tokens/v1' or x.get('candidate_commit') != candidate_commit or x.get('reverse_trace_sha256') != reverse_sha or x.get('forward_trace_sha256') != forward_sha: raise ValueError('frontend manifest does not bind candidate and both canonical traces')
 if not isinstance(rows,list) or len(rows)!=12: raise ValueError('frontend manifest must have exactly 12 rounds')
 out={}
 for r in rows:
  key=r.get('messages_sha'); ids=r.get('prompt_ids')
  if not isinstance(key,str) or key in out or r.get('prompt_ids_sha256_int32le')!=digest(ids) or r.get('prompt_length')!=len(ids): raise ValueError('invalid frontend-manifest row')
  out[key]=r
 if set(out) != trace_keys(reverse_trace) or set(out) != trace_keys(forward_trace): raise ValueError('frontend keys do not exactly bind canonical reverse/forward traces')
 return x,out

def common(a,b):
 n=min(len(a),len(b)); i=0
 while i<n and a[i]==b[i]: i+=1
 return i
def valid_tool_calls(value):
 return isinstance(value,list) and bool(value) and all(type(name) is str and bool(name.strip()) for name in value)
def expected_engine_finish_reason(row):
 reason=row.get('finish_reason')
 if reason in ('stop','length'): return reason
 if reason == 'tool_calls' and valid_tool_calls(row.get('tool_calls')): return 'stop'
 raise ValueError('replay row has an unsupported HTTP terminal reason')
def validate_replay_rows(document):
 rows=document.get('rounds'); params=(document.get('meta') or {}).get('params') or {}
 if params.get('max_tokens') != 200 or not isinstance(rows,list) or len(rows)!=12: raise ValueError('live replay lacks exactly 12 cap-200 rows')
 for row in rows:
  if row.get('error') is not None or row.get('dry_run') or type(row.get('completion_tokens')) is not int or not 1 <= row['completion_tokens'] <= 200: raise ValueError('live replay row is not an error-free non-dry cap-200 terminal result')
  expected_engine_finish_reason(row)
 return rows
class Run:
 def __init__(self,a):
  self.a=a; self.sc=load_sc(); self.base=self.sc.SelfCheck(argparse.Namespace(tail_k=1,trace=str(a.reverse_trace))); self.out=ROUNDS/a.rid; self.base.out=self.out
 def gate(self):
  if self.a.rid!=RID or self.a.candidate_commit != CANDIDATE_COMMIT: raise ValueError('require E2-R017 and explicit full candidate SHA')
  if self.out.exists(): raise FileExistsError(self.out)
  if self.a.agent_trace_md5 != 'f81acb79c3dbc89999f5f76de4c9a070': raise ValueError('require exact legacy agent_trace MD5 beginning f81')
  if hashlib.md5((ROOT/'scripts/agent_trace.py').read_bytes()).hexdigest()!=self.a.agent_trace_md5: raise ValueError('agent_trace MD5 mismatch')
  subprocess.run(['git','-C',str(CANDIDATE),'merge-base','--is-ancestor','23f2e2caa3395837c9474735ffc83321f3b9b5a1',self.a.candidate_commit],check=True)
  return self.base.gate(CANDIDATE,self.a.candidate_commit)
 def replay(self,arm,env,name,trace):
  out=arm/f'{name}.json'; argv=[PY,str(ROOT/'scripts/agent_trace.py'),'replay','--trace',str(trace),'--out',str(out),'--base-url',f'http://127.0.0.1:{PORT}/v1','--model',MODEL,'--fresh-note',f'{self.a.rid}-{arm.name}-{name}']
  env={**env,'FT_REPLAY_MAX_TOKENS':'200'}
  with (arm/f'{name}.log').open('x',encoding='utf-8') as f: subprocess.run(argv,cwd=arm,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=7200)
  return validate_replay_rows(json.loads(out.read_text(encoding='utf-8')))
 def bind(self,arm,rows,expected,old):
  owned=json.loads((arm/'owned_process.json').read_text()); pgid=owned.get('pgid')
  paths=sorted((arm/'logits').glob('tokens_uid*_pid*.json')); new=[p for p in paths if p.name not in old]
  if len(new)!=12: raise ValueError(f'{arm.name} expected 12 exclusive terminal records, got {len(new)}')
  bysha={}
  for p in new:
   t=token(p);
   if os.getpgid(t['pid']) != pgid: raise ValueError('terminal token PID is outside owned service process group')
   key=t['prompt_ids_sha256_int32le']
   if key in bysha: raise ValueError('duplicate terminal prompt SHA cannot bind replay sequence')
   bysha[key]=(p,t)
  out={}
  for r in rows:
   e=expected.get(r.get('messages_sha')); p,t=bysha.get(e['prompt_ids_sha256_int32le'],(None,None)) if e else (None,None)
   if t is None or r.get('messages_sha')!=e['messages_sha'] or r.get('prompt_tokens')!=e['prompt_length'] or t['prompt_ids']!=e['prompt_ids'] or len(t['generated_ids']) != r.get('completion_tokens') or t['finish_reason'] != expected_engine_finish_reason(r): raise ValueError('terminal record does not bind live replay messages/input')
   out[r['messages_sha']]={'round':r['round'],'messages_sha':r['messages_sha'],'terminal_file':p.name,'terminal_sha256':sha(p),'uid':t['uid'],'pid':t['pid'],'prompt_ids':t['prompt_ids'],'generated_ids':t['generated_ids'],'http_finish_reason':r['finish_reason'],'engine_finish_reason':t['finish_reason']}
  if len(out) != 12 or set(out) != set(expected): raise ValueError('replay messages_sha set does not exactly match canonical frontend inputs')
  if len({row['uid'] for row in out.values()}) != 12: raise ValueError('terminal UID sequence is not one-to-one with replay records')
  return out
 def parsed_identity(self, arms):
  baseline=None
  for name in arms:
   parsed=self.base.parser(str(self.out/name/'serve.log'))
   suffix=ast.literal_eval(parsed.get('_unique_suffix',''))
   pid=json.loads((self.out/name/'owned_process.json').read_text())['pid']
   if suffix != '.pid='+str(pid): raise ValueError('parsed PID suffix does not bind owned arm')
   if any(str(parsed.get(k)) != v for k,v in {'mamba_host_slots':'0','max_extend_tokens':'4096','prefill_layer_major':'False','enable_cache_report':'True'}.items()): raise ValueError('T10 B-arm parsed configuration violates contract')
   cleaned={k:v for k,v in parsed.items() if k!='_unique_suffix'}
   if baseline is None: baseline=cleaned
   elif cleaned != baseline: raise ValueError('T10 arm parsed arguments differ beyond real PID')
  return baseline
 def run(self):
  proof=self.gate(); manifest,expect=frontend(self.a.frontend_manifest, self.a.candidate_commit, sha(self.a.reverse_trace), sha(self.a.forward_trace), self.a.reverse_trace, self.a.forward_trace); self.base.lock_take(); made=False
  try:
   self.out.mkdir(); made=True; src=Path(__file__).read_bytes(); (self.out/Path(__file__).name).write_bytes(src)
   (self.out/'reverse_trace.json').write_bytes(self.a.reverse_trace.read_bytes())
   (self.out/'forward_trace.json').write_bytes(self.a.forward_trace.read_bytes())
   (self.out/'frontend_manifest.json').write_bytes(self.a.frontend_manifest.read_bytes())
   batch=ROOT/'runs/plan_batches'/f'batch{self.a.batch}_{RID}_python.sh'
   if not batch.is_file(): raise FileNotFoundError(f'missing root batch wrapper: {batch}')
   (self.out/'batch.sh').write_bytes(batch.read_bytes())
   batch_sha256=sha(batch)
   write_new(self.out/f'status_batch{self.a.batch}.json',{'rid':RID,'batch':self.a.batch,'batch_wrapper_sha256':batch_sha256,'batch_pid':__import__('os').getpid(),'pid':__import__('os').getpid(),'gate':'T10','state':'running'})
   write_new(self.out/'admission.json',{'rid':RID,'batch':self.a.batch,'batch_wrapper_sha256':batch_sha256,'candidate_commit':self.a.candidate_commit,'parent_lineage':'23f2e2c','commit':'23f2e2caa3395837c9474735ffc83321f3b9b5a1','code_version':'E2-base@23f2e2c','card':'T10','candidate_proof':proof,'agent_trace_md5':self.a.agent_trace_md5,'reverse_trace_sha256':sha(self.a.reverse_trace),'forward_trace_sha256':sha(self.a.forward_trace),'frontend_manifest_sha256':sha(self.a.frontend_manifest)})
   write_new(self.out/'tool_hashes.json',{'runner':hashlib.sha256(src).hexdigest(),'agent_trace.py':sha(ROOT/'scripts/agent_trace.py'),'d03_gpu_selfcheck.py':sha(ROOT/'runs/dev_D03/d03_gpu_selfcheck.py'),'logits_probe.py':sha(CANDIDATE/'scripts/logits_probe.py')})
   arms={}
   for name in ('B1','B2','B3'):
    arm,env=self.base.start(name,CANDIDATE,logits=True,host_slots=0,prefill_chunk=4096,layer_major=False); old={p.name for p in (arm/'logits').glob('tokens_uid*_pid*.json')}
    try:
     cold=self.replay(arm,env,'reverse_cold',self.a.reverse_trace); coldids=self.bind(arm,cold,expect,old); old|={x['terminal_file'] for x in coldids.values()}
     warm=self.replay(arm,env,'forward_warm',self.a.forward_trace); warmids=self.bind(arm,warm,expect,old)
     arms[name]={'cold':coldids,'warm':warmids}
    finally: self.base.stop()
   parsed_args=self.parsed_identity(arms)
   forks=[]
   for message_sha, source in expect.items():
    sequences=[arms[a][phase][message_sha]['generated_ids'] for a in arms for phase in ('cold','warm')]
    if all(x == sequences[0] for x in sequences[1:]): continue
    k=min(common(sequences[0],x) for x in sequences[1:]); values={tuple(x[:k]) for x in sequences}
    if len(values)!=1: raise ValueError('common prefix calculation inconsistent')
    forks.append({'round':source.get('round'),'messages_sha':message_sha,'prompt_ids':source['prompt_ids'],'prompt_ids_sha256_int32le':source['prompt_ids_sha256_int32le'],'common_generated_ids':sequences[0][:k],'first_difference_index':k,'k':k,'observed_next_ids':[seq[k] if k<len(seq) else None for seq in sequences]})
   write_new(self.out/'phase1_manifest.json',{'schema':'t10_engine_tokens/v1','rid':RID,'arms':arms,'forkpoints':forks,'frontend_manifest_sha256':sha(self.a.frontend_manifest),'parsed_args_without_pid':parsed_args})
   write_new(self.out/'round_metadata.json',{'rid':RID,'status':'complete_measurements_pending_review','terminal_records_per_arm':24,'forkpoints':len(forks)})
   (self.out/f'status_batch{self.a.batch}.json').write_text(json.dumps({'rid':RID,'batch':self.a.batch,'batch_wrapper_sha256':batch_sha256,'batch_pid':__import__('os').getpid(),'pid':__import__('os').getpid(),'gate':'T10','state':'complete_measurements_pending_review'})+'\n',encoding='utf-8')
  except BaseException as e:
   if made: write_new(self.out/'error.json',{'error':repr(e)})
   status=self.out/f'status_batch{self.a.batch}.json'
   if status.exists(): status.write_text(json.dumps({'rid':RID,'batch':self.a.batch,'batch_pid':__import__('os').getpid(),'pid':__import__('os').getpid(),'gate':'T10','state':'error','error':repr(e)})+'\n',encoding='utf-8')
   raise
  finally:
   try:self.base.stop()
   finally:
    self.base.lock_release()
    if made: (self.out/'RUN_MANIFEST.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(self.out)}\n' for p in sorted(x for x in self.out.rglob('*') if x.is_file() and x.name!='RUN_MANIFEST.sha256')),encoding='utf-8')
def self_test():
 import tempfile
 a=[1,2]; assert common(a,[1,2])==2 and common(a,[9])==0 and common(a,[])==0
 try:digest([])
 except ValueError:pass
 else:raise AssertionError('empty IDs accepted')
 with tempfile.TemporaryDirectory() as d:
  p=Path(d)/'t.json'; p.write_text(json.dumps({'schema':'ft_dev_tokens/v1','prompt_ids':[],'generated_ids':[1]}))
  try: token(p)
  except ValueError: pass
  else: raise AssertionError('unbound token record accepted')
 base={'error':None,'dry_run':False,'completion_tokens':200,'finish_reason':'stop','tool_calls':[]}
 assert len(validate_replay_rows({'meta':{'params':{'max_tokens':200}},'rounds':[dict(base) for _ in range(12)]})) == 12
 tool={**base,'finish_reason':'tool_calls','tool_calls':['read_file']}
 assert expected_engine_finish_reason(tool) == 'stop'
 for invalid in ({**base,'finish_reason':'tool_calls','tool_calls':[]},{**base,'finish_reason':'tool_calls','tool_calls':['']},{**base,'finish_reason':'other'}):
  try: expected_engine_finish_reason(invalid)
  except ValueError: pass
  else: raise AssertionError('invalid HTTP finish reason accepted')
 print('T10 R017 self-test PASS: replay finish-reason schema remains fail-closed')
def main():
 p=argparse.ArgumentParser(description=__doc__); p.add_argument('--self-test',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--rid',default=RID);p.add_argument('--batch',type=int);p.add_argument('--candidate-commit');p.add_argument('--reverse-trace',type=Path);p.add_argument('--forward-trace',type=Path);p.add_argument('--frontend-manifest',type=Path);p.add_argument('--agent-trace-md5');a=p.parse_args()
 if a.self_test:self_test();return
 if not a.run:p.error('--run required; no resources touched')
 if not(a.batch and a.candidate_commit and a.reverse_trace and a.forward_trace and a.frontend_manifest and a.agent_trace_md5):p.error('missing required run arguments')
 if not all(x.is_file() for x in (a.reverse_trace,a.forward_trace,a.frontend_manifest)):p.error('missing input artifact')
 if os.name != 'posix': p.error('--run requires Linux')
 Run(a).run()
if __name__=='__main__':main()
