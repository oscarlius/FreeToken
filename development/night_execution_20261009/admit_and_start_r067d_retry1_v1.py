import os,json,hashlib,subprocess,datetime,stat,importlib.util
from pathlib import Path
ROOT=Path('/data2/FreeToken');HERE=Path(__file__).resolve().parent;P=ROOT/'development/r067d_short_tail_retry1_20261010';BASE=ROOT/'development/r067_d20_short_tail_v1';RID='E2-R067d-d20-short-tail-retry1';PY=str(ROOT/'venv/bin/python')
def sha(p):
 p=Path(p);assert p.is_file() and not p.is_symlink() and stat.S_ISREG(p.stat().st_mode);return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2);f.flush();os.fsync(f.fileno())
 p.chmod(0o444)
 with p.open('rb') as f:os.fsync(f.fileno())
 d=os.open(p.parent,os.O_DIRECTORY)
 try:os.fsync(d)
 finally:os.close(d)
now=datetime.datetime.now().astimezone();assert now.hour<6 or now.hour==6 and now.minute<45
cleanup=HERE/'STRATA_S2_RETRY1_CLEANUP_RECOVERY.json';assert sha(cleanup)=='27b066e85f8c5177cbe2ebc341c6bbce4e700a8f2b95434583a7d257f4bffd4b'
assert json.loads(cleanup.read_text())['cleanup_ok']
for name in ['/data2/_shared/gpu.lock','/data2/FreeToken/run/production.active.json','/data2/FreeToken/run/production.cleanup_failed.json']:
 q=Path(name);assert not q.exists() and not q.is_symlink()
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
compile_procs=[]
for q in Path('/proc').iterdir():
 if not q.name.isdigit():continue
 try:
  comm=(q/'comm').read_text().strip()
  if comm in ['ninja','make','cmake','nvcc','cc1plus','gcc','g++','clang','clang++','cicc','ptxas']:compile_procs.append(q.name+':'+comm)
 except (FileNotFoundError,ProcessLookupError):pass
assert not compile_procs,compile_procs
cfg=P/'R067D_RETRY1_CONFIG_CPU_ONLY.json';assert sha(cfg)=='88a587c598cf53d0465d99e50d48286621ad0ed9b2313001fea5ca23482a8d92';fd=json.loads(cfg.read_text())
packet=P/'R067D_RETRY1_PREPARED_RUNNER_PACKET_V2.json';assert sha(packet)=='6a32a526b4190fc60ce102f320123a0182ddb5a29c9ce1dcbe91074b56f76237'
review=P/'CAN_CONSUME_CPU_APPROVE_R067D_RETRY1_V2.json';assert sha(review)=='2f5082bf5bcdf14c3e16d1b1b7ae31a9ea26c6e23f399dc9078b0a2429b773a8';assert json.loads(review.read_text())['verdict']=='CPU_APPROVE_CONDITIONAL_QUEUE_ADMIT'
assert json.loads(review.read_text())['packet_sha256']==sha(packet)
bindings={str(p):sha(p) for p in [cfg,packet,review,P/'r067d_cpu_prep.py',P/'r067d_retry1_v2_tools.py',ROOT/'development/r067d_short_tail_v1/R067D_CONFIG_CPU_ONLY.json',cleanup]}
assert sha(P/'r067d_retry1_v2_tools.py')==json.loads(packet.read_text())['helper_sha256']
for q in [*list((BASE/'t17_existing').glob('*.py')),*list((P/'tooling').glob('*.py'))]:bindings[str(q)]=sha(q)
for n,digest in fd['source_tools'].items():
 if n=='d07_g3g4_prepare.py':q=ROOT/'development'/n;assert sha(q)==digest;bindings[str(q)]=digest
 else:
  candidates=[p for p in BASE.rglob(n) if p.is_file() and not p.is_symlink() and sha(p)==digest];assert candidates,n
  for q in candidates:bindings[str(q)]=digest
for rec in [fd['binary_manifest'],fd['input_binding'],*fd['worktree_binding'].values()]:
 if 'sha256' in rec:q=Path(rec['path']);assert sha(q)==rec['sha256'];bindings[str(q)]=rec['sha256']
for s in fd['services']:
 if s.get('schedule'):q=Path(s['schedule']['path']);assert sha(q)==s['schedule']['sha256'];bindings[str(q)]=s['schedule']['sha256']
for rec in fd['worktree_binding'].values():
 assert subprocess.check_output(['git','-C',rec['path'],'rev-parse','HEAD'],text=True).strip()==rec['commit']
 assert not subprocess.check_output(['git','-C',rec['path'],'status','--porcelain','--untracked-files=all'],text=True).strip()
 q=Path(rec['path'])/'python/freetoken/engine.py';assert sha(q)==rec['engine_sha256'];bindings[str(q)]=rec['engine_sha256']
proof=P/'R067D_RETRY1_ROOT_PREFLIGHT_V2.json';put(proof,{'at':now.isoformat(),'bindings':bindings,'source_packet_version':2,'cpu_packet_v1_retracted':True,'services_max':10,'calls_max':14})
prior=ROOT/'runs/dev_R067/E2-R067d-d20-short-tail-v1/terminal.json';assert json.loads(prior.read_text())['verdict']=='failed_harness'
entry=HERE/'launch_r067d_retry1_v3.py'
put(P/'R067D_RETRY1_ROOT_STARTUP_ADMISSION.json',{'approved':True,'rid':RID,'scope':{'services_max':10,'generation_calls_max':14},'config_sha256':sha(cfg),'launch_helper_sha256':sha(entry),'root_preflight_path':str(proof),'root_preflight_sha256':sha(proof),'independent_review_path':str(review),'independent_review_sha256':sha(review),'prepared_runner_packet_path':str(packet),'prepared_runner_packet_sha256':sha(packet),'prior_terminal_path':str(prior),'predecessor_cleanup':{'path':str(cleanup),'sha256':sha(cleanup)},'at':now.isoformat(),'authority':'NIGHT_SUPPLEMENT_20261010_0035','root_helper_delta_from_reviewed_v2':'only accept actual new conditional V2 packet review enum CPU_APPROVE_CONDITIONAL_QUEUE_ADMIT','no_push':True})
put(HERE/'R067D_RETRY1_MEASUREMENT_WINDOW_READY.json',{'ready':True,'compilation_processes_absent':True,'at_epoch':__import__('time').time(),'at':datetime.datetime.now().astimezone().isoformat(),'predecessor_cleanup_sha256':sha(cleanup)})
argv=[PY,'-B','-u',str(entry)]
with (HERE/'R067D_RETRY1_ROOT_DRIVER.log').open('xb') as log:proc=subprocess.Popen(argv,cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
f=Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()
v={'at':datetime.datetime.now().astimezone().isoformat(),'pid':proc.pid,'start_ticks':int(f[19]),'argv':argv,'helper_sha256':sha(entry),'admission_sha256':sha(P/'R067D_RETRY1_ROOT_STARTUP_ADMISSION.json'),'prepared_packet_sha256':sha(packet)}
put(HERE/'R067D_RETRY1_ROOT_DRIVER_RECEIPT.json',v)
with (HERE/'COORDINATION_LOG.jsonl').open('a') as f:f.write(json.dumps(v|{'event':'R067D_RETRY1_ACTUAL_CPU_V2_ADMITTED'})+chr(10));f.flush();os.fsync(f.fileno())
print(json.dumps(v))
