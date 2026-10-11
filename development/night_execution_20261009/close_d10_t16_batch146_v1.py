"""Root-only D04 closure draft for completed D10 T16 batch146; do not run except by root."""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib, json, os, shutil, stat, subprocess
from pathlib import Path

ROOT=Path('/data2/FreeToken'); NIGHT=ROOT/'development/night_execution_20261009'
ROUNDS=Path('/data2/_shared/runs/ft_rounds'); RID='E2-D10-T16-night-20261010'; RUN=ROUNDS/RID
PY=ROOT/'venv/bin/python'; CLOSER=ROOT/'runs/dev_D16/r041_accept_final_20261005_2012/d04_server_round_close_db7b2787.py'; APP=ROOT/'scripts/round_json_append.py'
CLOSER_SHA='db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
REVIEW_SHA='d72a78037e05c46a1eeaeca81bfacadf0b87417472a8c2d3d63cd33cdcf79a4b'; CLEANUP_SHA='c1ccd100ff7175b5c5f28ebad77c76e46ce2e42402166db78cee2784aa6233ae'
STATUS_SHA='542346ce76044cc32a964c06fd87876e3cf8cd4bc3a1315fa9433c2d138b15a5'; GATE_SHA='5d4113473445486ff52d687d7629f3056d63a4f7aebd13356aa03e573362f6e8'; BINDING_SHA='2196b1b07a8e12fc689baa0bca191bda80441820ce2f6488751712f09d205583'; TOOLS_SHA='02605c3c72df196978adbb2cc7036bdf0aab2109a34701fb72653389eeb0d85b'
PARENT='481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'; CANDIDATE='22ff3a389eae3724cdca9a45f2e19577082a2032'
ARMS=('PARENT_b146','NEW_b146','PARENT_P_b146','NEW_P_b146','CHUNK_PARENT_b146','CHUNK_NEW_b146','CHUNK_PARENT_P_b146','CHUNK_NEW_P_b146')
NEW={'NEW_b146','NEW_P_b146','CHUNK_NEW_b146','CHUNK_NEW_P_b146'}; CHUNK={'CHUNK_PARENT_b146','CHUNK_NEW_b146','CHUNK_PARENT_P_b146','CHUNK_NEW_P_b146'}
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def put(p,v):
 with Path(p).open('x',encoding='utf-8') as f: json.dump(v,f,sort_keys=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
def absent(x):
 assert set(x)>= {'pid','start_ticks','execution_id'} and x['execution_id']==f"{x['pid']}:{x['start_ticks']}"
 try: q=Path(f"/proc/{x['pid']}/stat").read_text().rsplit(')',1)[1].split()
 except FileNotFoundError:return True
 return q[0]=='Z' or int(q[19])!=x['start_ticks']
def group_absent(x):
 assert set(x)>= {'pid','start_ticks','execution_id','pgid','session'} and x['pid']==x['pgid']==x['session']
 for p in Path('/proc').iterdir():
  if p.name.isdigit():
   try:q=(p/'stat').read_text().rsplit(')',1)[1].split()
   except (FileNotFoundError,ProcessLookupError):continue
   if q[0]!='Z' and int(q[2])==x['pgid']: return False
 return True
def copy_new(src,dst):
 assert not dst.exists();shutil.copy2(src,dst);assert sha(src)==sha(dst)
def main():
 assert sha(CLOSER)==CLOSER_SHA and not (RUN/'round.json').exists() and not (RUN/'MANIFEST.sha256').exists() and not (RUN/'round_history').exists()
 review=NIGHT/'D10_T16_ACTUAL_TERMINAL_INDEPENDENT_REVIEW.json'; cleanup_path=NIGHT/'D10_T16_OWNED_CLEANUP_READBACK.json'
 status_path=RUN/'status_batch146.json'; gate_path=RUN/'gate_batch146.json'; binding_path=RUN/'candidate_binding.json'; tools_path=RUN/'tools_batch146.json'
 assert [sha(x) for x in (review,cleanup_path,status_path,gate_path,binding_path,tools_path)]==[REVIEW_SHA,CLEANUP_SHA,STATUS_SHA,GATE_SHA,BINDING_SHA,TOOLS_SHA]
 status,gate,binding,cleanup=load(status_path),load(gate_path),load(binding_path),load(cleanup_path)
 assert status['rid']==RID and status['batch']==146 and status['state']=='complete_measurements_pending_review' and status['proposed_verdict']=='kept'
 assert gate['proposed_verdict']=='kept' and tuple(gate['arms'])==ARMS and gate['parent_commit']==PARENT and gate['new_commit']==CANDIDATE
 assert binding['parent_commit']==PARENT and binding['new_commit']==CANDIDATE and binding['default_off_public_flag']=={'d10_staggered_decode':False}
 assert cleanup['rid']==RID and cleanup['cleanup_ok'] is True and cleanup['product_acceptance'] is False and len(cleanup['owners'])==8 and absent(cleanup['child_absent'])
 for arm in ARMS:
  d=RUN/arm;assert all((d/x).is_file() and (d/x).stat().st_size for x in ('SERVE_CMD.txt','ENV.txt','serve_args.txt','serve.log','ready_sayok.json','tax.json','owned_process.json'))
  if arm in NEW: assert 'd10_staggered_decode=False' in (d/'serve_args.txt').read_text() and load(d/'args_checked.json')['d10_staggered_decode']==[None,'False']
  else: assert not (d/'args_checked.json').exists()
  t=load(d/'tax.json');assert t['reps']==5 and len(t['single'])==len(t['multi'])==5 and all(v>0 for v in t['single']+t['multi'])
  for case in (('short','chunked') if arm in CHUNK else ('det',)):
   q=load(d/(case+'.json'))['record']; assert q['cached_tokens']==0 and q['completion_tokens']==128 and q['finish_reason']=='length'
 for x in cleanup['owners']:
  o=load(x['path']);assert sha(x['path'])==x['sha256'] and o['birth']==x['birth'] and x['group_absent'] is True and absent(x['birth']) and group_absent(x['birth'])
 assert 8+4+8+8*5*2==100
 assert (RUN/'batch.sh').is_file() and sha(RUN/'batch.sh')==sha(RUN/'batch146.sh')
 e=RUN/'closure_evidence';assert not e.exists();e.mkdir()
 for name,src in {'independent_review.json':review,'owned_cleanup.json':cleanup_path}.items():copy_new(src,e/name)
 put(e/'owned_cleanup_revalidation.json',{'rid':RID,'checked_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'child_absent_now':True,'owners_absent_now':True,'groups_absent_now':True,'current_global_gpu_state_checked':False,'reason':'D10 historical ownership only; later R044 is outside scope'})
 put(RUN/'round.json',{'schema':'ft_round/v2','round_id':RID,'card':'D10-T16','batch':146,'retry_of':None,'retry_index':0,'verdict':'pending_review','proposed_verdict':'kept','verdict_history':[],'retractions':[],'serve':{'arms':{a:{'raw_source':str(RUN/a)} for a in ARMS}},'base':{'commit':PARENT},'experimental':{'candidate_commit':CANDIDATE},'actual_services':8,'actual_generation_calls':100,'product_acceptance':False,'batch_logs':[],'result_binding':{'status':{'path':'status_batch146.json','sha256':STATUS_SHA},'gate':{'path':'gate_batch146.json','sha256':GATE_SHA},'candidate':{'path':'candidate_binding.json','sha256':BINDING_SHA},'review':{'path':'closure_evidence/independent_review.json','sha256':sha(e/'independent_review.json')},'cleanup':{'path':'closure_evidence/owned_cleanup.json','sha256':sha(e/'owned_cleanup.json')}}})
 for argv in ([str(PY),str(CLOSER),RID,'--round-root',str(ROUNDS)],[str(PY),str(APP),str(RUN),'verdict','--new','kept','--reason','batch146 eight-arm default-off D10 measurement passed with 100 actual protocol calls','--evidence',str(e/'independent_review.json'),str(gate_path),str(e/'owned_cleanup_revalidation.json'),'--by','root'],[str(PY),str(APP),str(RUN),'check']):
  z=subprocess.run(argv,capture_output=True,text=True);assert z.returncode==0,(z.stdout,z.stderr)
 for line in (RUN/'MANIFEST.sha256').read_text().splitlines():d,n=line.split('  ',1);assert sha(RUN/n.removeprefix('./'))==d
 assert all(not p.stat().st_mode&0o222 for p in [RUN,*RUN.rglob('*')]);out=NIGHT/'D10_T16_D04_CLOSURE_RECEIPT_V1.json';put(out,{'rid':RID,'closed_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'script_sha256':sha(Path(__file__)),'verdict':'kept','manifest_sha256':sha(RUN/'MANIFEST.sha256'),'actual_services':8,'actual_generation_calls':100,'global_gpu_idle_not_checked':True});os.chmod(out,0o444)
if __name__=='__main__':main()
