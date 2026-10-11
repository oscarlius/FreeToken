#!/usr/bin/env python3
"""T10 stage 2: fresh two-process FP32 logits for every recorded engine-token fork."""
from __future__ import annotations
import argparse, os, ast, struct, hashlib, importlib.util, json, re, shlex, subprocess, sys
from pathlib import Path

ROOT=Path('/data2/FreeToken'); ROUNDS=Path('/data2/_shared/runs/ft_rounds'); CANDIDATE=ROOT/'wt/e1r003st'; CANDIDATE_COMMIT='c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
FRONTEND_PATH=ROOT/'runs/dev_D03/t10_frontend_tokens_c30ae0d.json'
FRONTEND_SHA='bf1f38901055e79e0b4ae48615f4ce1f58a4efc02a31f88ff644d857c6bc0356'
RID='E2-R013'; PY=str(ROOT/'venv/bin/python'); MODEL='Qwen3.8-Flash-Next-NVFP4'; PORT=8095

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_new(p,v):
 with Path(p).open('x',encoding='utf-8') as f: json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def load_sc():
 p=ROOT/'runs/dev_D03/d03_gpu_selfcheck.py';spec=importlib.util.spec_from_file_location('d03_sc',p)
 if spec is None or spec.loader is None:raise RuntimeError('missing uploaded D03 lifecycle')
 m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def idsha(x): return hashlib.sha256(struct.pack(f'<{len(x)}i',*x)).hexdigest()
def ids(x):
 if not isinstance(x,list) or not x or any(type(v)is not int or v<0 or v>2**31-1 for v in x):raise ValueError('nonempty uint31 IDs required')
 return x
def probe_split(prompt, common_prefix):
 full=ids(prompt)+common_prefix
 return full[:-1],[full[-1]]
def token_record(path):
 x=json.loads(Path(path).read_text(encoding='utf-8'))
 if x.get('schema')!='ft_dev_tokens/v1' or type(x.get('uid')) is not int or x['uid']<0 or type(x.get('pid')) is not int or x['pid']<=0 or x.get('finish_reason') not in ('stop','length'): raise ValueError('invalid sealed terminal token record')
 ids(x.get('prompt_ids')); ids(x.get('generated_ids'))
 if x.get('prompt_length')!=len(x['prompt_ids']) or x.get('prompt_ids_sha256_int32le')!=idsha(x['prompt_ids']) or x.get('generated_ids_sha256_int32le')!=idsha(x['generated_ids']) or x.get('input_ids_sha256_int32le')!=idsha(x['prompt_ids']+x['generated_ids']): raise ValueError('unbound sealed terminal token record')
 return x
def unique_forks(doc):
 if doc.get('schema')!='t10_engine_tokens/v1' or doc.get('rid')!='E2-R012':raise ValueError('not an E2-R012 engine-token manifest')
 out={}
 for f in doc.get('forkpoints') or []:
  p=ids(f.get('prompt_ids')); c=f.get('common_generated_ids'); k=f.get('k')
  if not isinstance(c,list) or any(type(v)is not int for v in c) or type(k)is not int or k!=len(c) or k<0:raise ValueError('invalid forkpoint IDs')
  key=(f.get('prompt_ids_sha256_int32le'),tuple(c))
  if not isinstance(key[0],str):raise ValueError('forkpoint lacks prompt SHA')
  out[key]=f
 return list(out.values())
class Run:
 def __init__(self,a):
  self.a=a;self.sc=load_sc();self.base=self.sc.SelfCheck(argparse.Namespace(tail_k=1,trace=''));self.out=ROUNDS/RID;self.base.out=self.out
 def gate(self):
  if self.a.candidate_commit != CANDIDATE_COMMIT:raise ValueError('candidate commit must be explicit full SHA')
  if self.out.exists():raise FileExistsError(self.out)
  subprocess.run(['git','-C',str(CANDIDATE),'merge-base','--is-ancestor','23f2e2caa3395837c9474735ffc83321f3b9b5a1',self.a.candidate_commit],check=True)
  return self.base.gate(CANDIDATE,self.a.candidate_commit)
 def capture(self,arm,env,prefix,suffix):
  pp,ss=arm/'prefix_ids.json',arm/'suffix_ids.json';write_new(pp,prefix);write_new(ss,suffix)
  argv=[PY,str(CANDIDATE/'scripts/logits_probe.py'),'capture','--base-url',f'http://127.0.0.1:{PORT}','--model',MODEL,'--prefix',str(pp),'--suffix',str(ss),'--dump',str(arm/'logits')]
  with (arm/'capture.log').open('x',encoding='utf-8') as f:subprocess.run(argv,cwd=CANDIDATE,env=env,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=3600)
  z=[x for x in (arm/'capture.log').read_text(encoding='utf-8').splitlines() if x.strip()]
  if not z:raise ValueError('empty logits capture')
  r=json.loads(z[-1]);
  if r.get('k')!=1 or r.get('input_length')!=len(prefix)+1 or r.get('positions')!=[len(prefix)]:raise ValueError('capture did not bind K=1 final input position')
  rows=[json.loads(x) for x in (arm/'logits/index.jsonl').read_text(encoding='utf-8').splitlines() if x]
  if len([x for x in rows if x.get('kind')=='logits' and x.get('uid')==r.get('uid') and x.get('seq')==r.get('dump_seq')]) != 1: raise ValueError('logits index UID/seq not unique')
  matches=[]
  for path in (arm/'logits').glob(f"tokens_uid{r['uid']}_pid*.json"):
   t=token_record(path)
   if t['prompt_length']==r['input_length'] and t['prompt_ids_sha256_int32le']==r['input_sha256']: matches.append(t)
  if len(matches)!=1: raise ValueError('terminal token does not uniquely bind stage2 logits input')
  owned=json.loads((arm/'owned_process.json').read_text())
  if os.getpgid(matches[0]['pid']) != owned.get('pgid'): raise ValueError('stage2 terminal PID outside owned PGID')
  r['capture_pid']=matches[0]['pid']
  write_new(arm/'capture.json',r);return r
 def sealed_phase1(self):
  root=(ROUNDS/'E2-R012').resolve(); manifest_path=self.a.phase1_manifest.resolve(); round_path=self.a.phase1_round_json.resolve()
  if manifest_path.parent != root or round_path != root/'round.json' or not root.is_dir() or not (root/'MANIFEST.sha256').is_file(): raise ValueError('phase1 inputs must be canonical sealed E2-R012 artifacts')
  subprocess.run([PY,str(ROOT/'scripts/round_json_append.py'),str(root),'check'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  declared={}
  for line in (root/'MANIFEST.sha256').read_text(encoding='utf-8').splitlines():
   digest,sep,rel=line.partition('  '); target=(root/rel).resolve()
   if not sep or not re.fullmatch(r'[0-9a-f]{64}',digest) or root not in target.parents or not target.is_file() or sha(target)!=digest: raise ValueError('sealed E2-R012 manifest hash mismatch')
   declared[rel]=digest
  proof=json.loads(round_path.read_text(encoding='utf-8'))
  metadata=json.loads((root/'round_metadata.json').read_text(encoding='utf-8'))
  admission=json.loads((root/'admission.json').read_text(encoding='utf-8'))
  manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
  if proof.get('round_id')!='E2-R012' or proof.get('card')!='T10' or metadata.get('rid')!='E2-R012' or metadata.get('status')!='complete_measurements_pending_review' or admission.get('candidate_commit') != self.a.candidate_commit or manifest.get('schema')!='t10_engine_tokens/v1': raise ValueError('sealed phase1 provenance/candidate mismatch')
  if sha(FRONTEND_PATH)!=FRONTEND_SHA or manifest.get('frontend_manifest_sha256')!=FRONTEND_SHA: raise ValueError('sealed phase1 frontend binding is not canonical c30')
  return root,manifest,proof
 def recompute_forks(self,root,doc):
  arms=doc.get('arms'); out={}
  if not isinstance(arms,dict) or set(arms)!={'B1','B2','B3'}: raise ValueError('sealed phase1 lacks B1/B2/B3 arms')
  frontend=json.loads(FRONTEND_PATH.read_text(encoding='utf-8')); canonical={r['messages_sha'] for r in frontend.get('rounds') or []}
  if len(canonical)!=12: raise ValueError('canonical frontend does not have 12 keys')
  for arm in arms.values():
   for phase in ('cold','warm'):
    if not isinstance(arm.get(phase),dict) or set(arm[phase]) != canonical: raise ValueError('all six phase1 streams must contain exact canonical 12 keys')
  for message_sha in sorted(canonical):
   seq=[]; prompt=None
   for arm_name in ('B1','B2','B3'):
    for phase in ('cold','warm'):
     rec=arms[arm_name][phase][message_sha]; path=root/arm_name/'logits'/rec['terminal_file']
     if not path.is_file() or sha(path)!=rec.get('terminal_sha256'): raise ValueError('sealed terminal file/hash missing')
     t=token_record(path)
     if t['uid']!=rec.get('uid') or t['pid']!=rec.get('pid') or t['prompt_ids']!=rec.get('prompt_ids') or t['generated_ids']!=rec.get('generated_ids'): raise ValueError('sealed terminal record disagrees with manifest')
     prompt=prompt or t['prompt_ids'];
     if t['prompt_ids']!=prompt: raise ValueError('same messages SHA has divergent raw prompt IDs')
     seq.append(t['generated_ids'])
   if not all(x==seq[0] for x in seq[1:]):
    k=min(next((i for i,(a,b) in enumerate(zip(seq[0],x)) if a!=b), min(len(seq[0]),len(x))) for x in seq[1:])
    out[(message_sha,tuple(seq[0][:k]))]={'messages_sha':message_sha,'prompt_ids':prompt,'common_generated_ids':seq[0][:k],'k':k,'first_difference_index':k,'observed_next_ids':[x[k] if k<len(x) else None for x in seq]}
  return list(out.values())
 def run(self):
  root,manifest,proof=self.sealed_phase1(); forks=self.recompute_forks(root,manifest)
  if not forks:
   print(json.dumps({'rid':RID,'state':'not_applicable_no_actual_fork','phase1_manifest_sha256':sha(self.a.phase1_manifest)},allow_nan=False)); return
  gate=self.gate();self.base.lock_take();made=False
  try:
   self.out.mkdir();made=True;src=Path(__file__).read_bytes();(self.out/Path(__file__).name).write_bytes(src)
   (self.out/'phase1_manifest.json').write_bytes(self.a.phase1_manifest.read_bytes())
   (self.out/'phase1_round_proof.json').write_bytes(self.a.phase1_round_json.read_bytes())
   batch=ROOT/'runs/plan_batches'/f'batch{self.a.batch}_{RID}_python.sh'
   if not batch.is_file(): raise FileNotFoundError(f'missing root batch wrapper: {batch}')
   (self.out/'batch.sh').write_bytes(batch.read_bytes())
   batch_sha256=sha(batch)
   write_new(self.out/f'status_batch{self.a.batch}.json',{'rid':RID,'batch':self.a.batch,'batch_wrapper_sha256':batch_sha256,'batch_pid':__import__('os').getpid(),'pid':__import__('os').getpid(),'gate':'T10','state':'running'})
   write_new(self.out/'admission.json',{'rid':RID,'parent_rid':'E2-R012','batch':self.a.batch,'batch_wrapper_sha256':batch_sha256,'candidate_commit':self.a.candidate_commit,'parent_lineage':'23f2e2c','commit':'23f2e2caa3395837c9474735ffc83321f3b9b5a1','code_version':'E2-base@23f2e2c','card':'T10','candidate_proof':gate,'phase1_manifest_sha256':sha(self.a.phase1_manifest),'phase1_round_proof_sha256':sha(self.a.phase1_round_json),'forkpoints':len(forks)})
   write_new(self.out/'tool_hashes.json',{'runner':hashlib.sha256(src).hexdigest(),'d03_gpu_selfcheck.py':sha(ROOT/'runs/dev_D03/d03_gpu_selfcheck.py'),'logits_probe.py':sha(CANDIDATE/'scripts/logits_probe.py')})
   results=[]
   for n,f in enumerate(forks):
    full=ids(f['prompt_ids'])+f['common_generated_ids']
    # K=1 measures the next-token logits at the final actual input ID. For a
    # zero-prefix fork this is the final prompt ID, never an invented output ID.
    prefix,suffix=probe_split(f['prompt_ids'],f['common_generated_ids'])
    pair=[]
    for side in ('a','b'):
     arm,env=self.base.start(f'fork{n:02d}_{side}',CANDIDATE,logits=True,host_slots=0,prefill_chunk=4096,layer_major=False)
     try:pair.append(self.capture(arm,env,prefix,suffix))
     finally:self.base.stop()
    argv=[PY,str(CANDIDATE/'scripts/logits_probe.py'),'compare','--recompute',str(self.out/f'fork{n:02d}_a/logits'),'--peer',str(self.out/f'fork{n:02d}_b/logits')]
    parsed=[]
    for side in ('a','b'):
     ap=self.base.parser(str(self.out/f'fork{n:02d}_{side}/serve.log')); pid=json.loads((self.out/f'fork{n:02d}_{side}/owned_process.json').read_text())['pid']
     if ast.literal_eval(ap.get('_unique_suffix','')) != '.pid='+str(pid): raise ValueError('parsed PID does not bind stage2 arm')
     if any(str(ap.get(k)) != v for k,v in {'mamba_host_slots':'0','max_extend_tokens':'4096','prefill_layer_major':'False','enable_cache_report':'True'}.items()): raise ValueError('stage2 parsed configuration violates contract')
     parsed.append({k:v for k,v in ap.items() if k!='_unique_suffix'})
    if parsed[0] != parsed[1]: raise ValueError('stage2 peer parsed arguments differ beyond PID')
    log=self.out/f'fork{n:02d}_compare.log'
    with log.open('x',encoding='utf-8') as h:subprocess.run(argv,cwd=CANDIDATE,stdout=h,stderr=subprocess.STDOUT,check=True,timeout=3600)
    lines=[x for x in log.read_text(encoding='utf-8').splitlines() if x.strip()]
    if not lines:raise ValueError('empty peer comparison')
    result=json.loads(lines[-1]);results.append({'forkpoint':f,'capture_a':pair[0],'capture_b':pair[1],'comparison':result,'probe_semantics':'logits_probe warms prefix then measures full prefix+one final actual input ID; this is recorded, not hidden'})
   write_new(self.out/'stage2_results.json',{'schema':'t10_logits_stage2/v1','results':results})
   write_new(self.out/'round_metadata.json',{'rid':RID,'status':'complete_measurements_pending_review','fresh_pairs':len(results)})
   (self.out/f'status_batch{self.a.batch}.json').write_text(json.dumps({'rid':RID,'batch':self.a.batch,'batch_wrapper_sha256':batch_sha256,'batch_pid':__import__('os').getpid(),'pid':__import__('os').getpid(),'gate':'T10','state':'complete_measurements_pending_review'})+'\n',encoding='utf-8')
  except BaseException as e:
   if made:write_new(self.out/'error.json',{'error':repr(e)})
   status=self.out/f'status_batch{self.a.batch}.json'
   if status.exists(): status.write_text(json.dumps({'rid':RID,'batch':self.a.batch,'batch_pid':__import__('os').getpid(),'pid':__import__('os').getpid(),'gate':'T10','state':'error','error':repr(e)})+'\n',encoding='utf-8')
   raise
  finally:
   try:self.base.stop()
   finally:
    self.base.lock_release()
    if made:(self.out/'RUN_MANIFEST.sha256').write_text(''.join(f'{sha(p)}  {p.relative_to(self.out)}\n' for p in sorted(x for x in self.out.rglob('*') if x.is_file() and x.name!='RUN_MANIFEST.sha256')),encoding='utf-8')
def self_test():
 assert probe_split([1,2],[]) == ([1],[2])
 assert probe_split([1,2],[3]) == ([1,2],[3])
 d={'schema':'t10_engine_tokens/v1','rid':'E2-R012','forkpoints':[{'prompt_ids':[1,2],'prompt_ids_sha256_int32le':'a','common_generated_ids':[],'k':0},{'prompt_ids':[1,2],'prompt_ids_sha256_int32le':'a','common_generated_ids':[3],'k':1}]};assert len(unique_forks(d))==2
 for bad in ({'schema':'wrong','rid':'E2-R012','forkpoints':[]},{'schema':'t10_engine_tokens/v1','rid':'E2-R012','forkpoints':[{'prompt_ids':[],'prompt_ids_sha256_int32le':'a','common_generated_ids':[],'k':0}]}):
  try:unique_forks(bad)
  except ValueError:pass
  else:raise AssertionError('bad fork accepted')
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--self-test',action='store_true');p.add_argument('--run',action='store_true');p.add_argument('--batch',type=int);p.add_argument('--candidate-commit');p.add_argument('--phase1-manifest',type=Path);p.add_argument('--phase1-round-json',type=Path);a=p.parse_args()
 if a.self_test:self_test();return
 if not a.run:p.error('--run required; no resources touched')
 if not(a.batch and a.candidate_commit and a.phase1_manifest and a.phase1_round_json):p.error('missing required run arguments')
 if not a.phase1_manifest.is_file() or not a.phase1_round_json.is_file():p.error('missing phase1 artifacts')
 if os.name != 'posix': p.error('--run requires Linux')
 Run(a).run()
if __name__=='__main__':main()
