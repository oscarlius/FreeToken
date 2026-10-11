import os,json,hashlib,subprocess,datetime,time,importlib.util,socket
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=Path('/data2/FreeToken');RID='E2-R067d-d20-short-tail-retry1';RUN=ROOT/'runs/dev_R067'/RID
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
helper=HERE/'advance_d09_t16_to_strata_retry1_v5.py';assert sha(helper)=='194ab227e367065594ea1fd47eacccd1caa9cd840d5a61daa30a84df48ecdfc2'
spec=importlib.util.spec_from_file_location('root_clean_helpers',helper);h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
launch=ROOT/'runs/dev_R067/launch_E2-R067d-d20-short-tail-retry1_batch143.json';h.require_regular(launch);binding=json.loads(launch.read_text());child=binding['child'];assert child=={'pid':326609,'start_ticks':166099351,'execution_id':'326609:166099351'}
while not h.absent(child['pid'],child['start_ticks']):time.sleep(30)
terminal=RUN/'terminal.json';h.require_regular(terminal);t=json.loads(terminal.read_text());assert t['rid']==RID and t['batch']==143 and t['verdict'] in ['PASS','not_met','failed_harness','probe_invalid']
assert t['GPU_lock_released'] and not t['cleanup_errors']
for name in ['/data2/_shared/gpu.lock','/data2/FreeToken/run/production.active.json','/data2/FreeToken/run/production.cleanup_failed.json']:
 p=Path(name);assert not p.exists() and not p.is_symlink()
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
owners=[]
for p in RUN.glob('services/*/owner.json'):
 h.require_regular(p);v=json.loads(p.read_text());b=v['pid_identity'];assert h.absent(b['pid'],b['start_ticks'])
 for q in Path('/proc').iterdir():
  if not q.name.isdigit():continue
  try:
   f=(q/'stat').read_text().rsplit(')',1)[1].split();assert f[0]=='Z' or int(f[2])!=b['pgid']
  except (FileNotFoundError,ProcessLookupError):pass
 port=int(v['argv'][v['argv'].index('--port')+1]);states={}
 sockets=[]
 try:
  for n in [port,port+1]:
   states[str(n)]=h.assert_no_listener(n);sock=socket.socket();sockets.append(sock);sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);sock.bind(('0.0.0.0',n))
 finally:
  for sock in sockets:sock.close()
 owners.append({'source':str(p),'sha256':sha(p),'birth':b,'ports_clear':states,'group_absent':True})
assert len(owners)==t['actual_services'] and owners
cleanup=HERE/'R067D_RETRY1_OWNED_CLEANUP_READBACK.json';h.put(cleanup,{'at':datetime.datetime.now().astimezone().isoformat(),'cleanup_ok':True,'rid':RID,'child_absent':child,'terminal_sha256':sha(terminal),'launch_sha256':sha(launch),'owners':owners,'gpu_compute_absent':True,'lock_absent':True,'product_acceptance':False})
# Preserve raw terminal bytes before the independent next item.
manifest=RUN/'RAW_MANIFEST.sha256'
with manifest.open('x') as f:
 for q in sorted(RUN.rglob('*')):
  assert not q.is_symlink()
  if q.is_file() and q!=manifest:f.write(sha(q)+'  '+q.relative_to(RUN).as_posix()+chr(10))
 f.flush();os.fsync(f.fileno())
for q in [*sorted(RUN.rglob('*'),reverse=True),RUN]:q.chmod(q.stat().st_mode&~0o222)
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)));assert now.hour<6 or now.hour==6 and now.minute<45
entry=ROOT/'development/d09_t16_night_v1/d09_owned_launch_retry1.py';assert sha(entry)=='c7ffe74430332f5d15fdf6e1060436720263b2cf4806d415b771459aaa87810f'
spec=importlib.util.spec_from_file_location('actual_d09_retry1',entry);d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d);d.require_leaf_review('D09');d.require_user_scope_approval('D09')
receipt=HERE/'D09_T16_RETRY1_ROOT_DRIVER_RECEIPT.json';assert not receipt.exists()
argv=[str(ROOT/'venv/bin/python'),'-B','-u',str(entry),'--run','--card','D09']
with (HERE/'D09_T16_RETRY1_ROOT_DRIVER.log').open('xb') as log:proc=subprocess.Popen(argv,cwd=str(ROOT),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
f=Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split();v={'at':datetime.datetime.now().astimezone().isoformat(),'pid':proc.pid,'start_ticks':int(f[19]),'argv':argv,'source_sha256':sha(entry),'prior_cleanup_sha256':sha(cleanup),'prior_raw_manifest_sha256':sha(manifest)};h.put(receipt,v)
with (HERE/'COORDINATION_LOG.jsonl').open('a') as f:f.write(json.dumps(v|{'event':'D09_T16_RETRY1_STARTED_AFTER_R067D_RETRY1_RAW_SEAL_AND_OWNED_CLEANUP'})+chr(10));f.flush();os.fsync(f.fileno())
print(json.dumps(v))
