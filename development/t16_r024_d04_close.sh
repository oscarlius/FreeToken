set -euo pipefail
round=/data2/_shared/runs/ft_rounds/E2-R024-gate-D07
test ! -e "$round/round.json"
test ! -e "$round/MANIFEST.sha256"
mkdir -p "$round/source_tools"
cat > "$round/source_tools/t16_r024_d04_close.py" <<'PY'
import hashlib,json,os,pathlib,re,subprocess,sys
R=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R024-gate-D07');ROOT=pathlib.Path('/data2/FreeToken');RID='E2-R024-gate-D07';BATCH=52
PARENT='03692633df48456fb0baa78de7b64e5628a12ab1';CANDIDATE='fefb19cbac6bb1cb08835c411c895310600b3677'
RUNNER='0451e41128b4d1e0c73f892b375b9fbe70b30a9fbac46bc022500bd3c1b6d8b8';BASE='379948776d42d5429304afb11dafb0d316e641638caf7cad15fb5b5e6be7340f';BINDING='3b352ec25e513c9d53c6826c363bdbe05bf48c817217709c3ded1a8638a54e33';GATE='671ed5231b357c7de8639df1968fdb2a270f38fb4ebb5743024382257e6cbf80'
ARMS=('PARENT_b52','NEW_b52','PARENT_P_b52','NEW_P_b52')
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def load(p):
 p=pathlib.Path(p)
 if p.is_symlink() or not p.is_file():raise ValueError('missing/symlink '+str(p))
 return json.loads(p.read_text())
def put(p,obj):
 p=pathlib.Path(p)
 with p.open('x') as f:json.dump(obj,f,sort_keys=True,indent=2);f.write('\n')
def terminal(pid):
 p=pathlib.Path('/proc')/str(pid)/'stat'
 return not p.exists() or p.read_text().rpartition(') ')[2].split()[0]=='Z'
def audit():
 if any((R/n).exists() for n in ('round.json','round_history','MANIFEST.sha256','review_batch52.json')):raise ValueError('already sealed/reviewed')
 if any(p.is_symlink() or p.stat().st_uid!=os.geteuid() for p in (R,*R.rglob('*'))):raise ValueError('foreign/symlink')
 status=load(R/'status_batch52.json');need={'rid':RID,'batch':BATCH,'candidate_case':'D07','state':'complete_measurements_pending_review','proposed_verdict':'kept'}
 if any(status.get(k)!=v for k,v in need.items()) or not terminal(status['batch_pid']):raise ValueError('status/terminal')
 if sha(R/'runner_batch52.py')!=RUNNER or sha(R/'base_runner_batch52.py')!=BASE or sha(R/'candidate_binding.json')!=BINDING or sha(R/'gate_batch52.json')!=GATE:raise ValueError('pinned archive')
 b=load(R/'candidate_binding.json')
 if b.get('parent_commit')!=PARENT or b.get('new_commit')!=CANDIDATE or b.get('case')!='D07':raise ValueError('binding')
 gate=load(R/'gate_batch52.json'); texts=[];pids={};d0=[]
 for arm in ARMS:
  a=R/arm
  for n in ('SERVE_CMD.txt','serve.log','serve_args.txt','ENV.txt','det.json','prefill_seq.txt','business_prefill_events.json'):load(a/n) if n.endswith('.json') else (a/n).read_bytes()
  pid=int(re.search(r'\.pid=(\d+)',(a/'serve_args.txt').read_text()).group(1));
  if not terminal(pid):raise ValueError('live service '+arm)
  if (PARENT if arm.startswith('PARENT') else CANDIDATE) not in (a/'ENV.txt').read_text():raise ValueError('commit '+arm)
  det=load(a/'det.json');
  if det.get('events')!=128 or det.get('record',{}).get('completion_tokens')!=128:raise ValueError('tokens '+arm)
  texts.append(det['text']);pids[arm]=pid
  if '_P_' not in arm:
   rows=[json.loads(x) for x in (a/'d0_prefill.jsonl').read_text().splitlines() if x.strip()]
   if len(rows)!=13:raise ValueError('d0 rows '+arm)
   # Timings differ between independently executed parent/candidate arms.  The
   # gate identity is the complete ordered D0 transfer/request sequence.
   d0.append([{k:x[k] for k in ('chunk','h2d_bytes','d2d_bytes','reqs')} for x in rows])
  elif list(a.glob('d0*')):raise ValueError('prod d0 '+arm)
 if len(set(texts))!=1 or len(d0)!=2 or d0[0]!=d0[1]:raise ValueError('text/d0 mismatch')
 if gate.get('proposed_verdict')!='kept' or gate.get('parent_commit')!=PARENT or gate.get('new_commit')!=CANDIDATE or gate.get('layer_major',{}).get('prefill',{}).get('all_prefill_events')!=13:raise ValueError('gate')
 return {'rid':RID,'batch':BATCH,'recommendation':'PASS','parent_commit':PARENT,'candidate_commit':CANDIDATE,'service_pids':pids,'fulltext_sha256':hashlib.sha256(texts[0].encode()).hexdigest(),'fulltext_equal':True,'completion_tokens':128,'d0_prefill_rows':13,'d0_transfer_request_sequence_sha256':hashlib.sha256(json.dumps(d0[0],sort_keys=True,separators=(',',':')).encode()).hexdigest(),'d0_raw_sha256':{a:sha(R/a/'d0_prefill.jsonl') for a in ARMS if '_P_' not in a},'gate_sha256':sha(R/'gate_batch52.json'),'binding_sha256':sha(R/'candidate_binding.json')}
result=audit();before={p.relative_to(R).as_posix():sha(p) for p in R.rglob('*') if p.is_file()};put(R/'review_batch52.json',result)
for n in ('round_json_append.py','round_close.py','round_close.sh'):
 src=ROOT/'scripts'/n;dst=R/n
 with dst.open('xb') as f:f.write(src.read_bytes())
with (R/'batch.sh').open('xb') as f:f.write((R/'batch52.sh').read_bytes())
meta={'schema':'ft_round/v2','round_id':RID,'epoch':2,'card':'T16','title':'D07 exact four-arm default-path gate','parent':'E2-R020-gate-D06','base':{'commit':PARENT,'code_version':'D06@0369263'},'experimental':{'candidate_commit':CANDIDATE,'worktree':'/data2/FreeToken/wt/e2d07'},'serve':{'arms':{k:{'owned_service_pid':v} for k,v in result['service_pids'].items()}},'design':{'batch':BATCH,'serve_order':list(ARMS)},'independent_review_sha256':sha(R/'review_batch52.json'),'diagnostics':{'gate_sha256':GATE,'binding_sha256':BINDING,'original_raw_files':before},'results':result,'proposed_verdict':'kept','verdict':'pending_review','verdict_history':[],'retractions':[],'batch_logs':[{'path':str(R.parent/'batch52.log'),'sha256':sha(R.parent/'batch52.log')}]} 
put(R/'round.json',meta)
subprocess.run(['bash',str(R/'round_close.sh'),RID,'--round-root',str(R.parent)],check=True,env={**os.environ,'FT_ROUND_PYTHON':sys.executable})
subprocess.run([sys.executable,str(R/'round_json_append.py'),str(R),'verdict','--new','kept','--reason','Independent R024 D07 review PASS: four arms have equal full 128-token text, PID-only parameter differences, complete 13-row D0 prefill evidence, and terminal owned services.','--evidence','review_batch52.json','gate_batch52.json','--by','Codex mainline D04 closure'],check=True)
subprocess.run([sys.executable,str(R/'round_json_append.py'),str(R),'check'],check=True)
if any(sha(R/n)!=v for n,v in before.items()):raise ValueError('raw changed')
if any(p.stat().st_mode&0o222 for p in (R,*R.rglob('*'))):raise ValueError('writable after close')
print(json.dumps({'rid':RID,'review_sha256':sha(R/'review_batch52.json'),'round_sha256':sha(R/'round.json'),'manifest_sha256':sha(R/'MANIFEST.sha256'),'v001_sha256':sha(R/'round_history/round.v001.json'),'formal_verdict':load(R/'round.json')['verdict']},sort_keys=True))
PY
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python "$round/source_tools/t16_r024_d04_close.py"
