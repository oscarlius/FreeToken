import json,hashlib,shutil,subprocess,datetime,os
from pathlib import Path
ROOT=Path('/data2/FreeToken'); ROUNDS=Path('/data2/_shared/runs/ft_rounds'); RID='E2-D09-T16-night-20261009'; RUN=ROUNDS/RID
HERE=Path(__file__).resolve().parent
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,v):
 with p.open('x') as f:json.dump(v,f,indent=2);f.flush();os.fsync(f.fileno())
review=ROOT/'development/D09_T16_BATCH142_INDEPENDENT_TERMINAL_REVIEW.json'
assert sha(review)=='1818e9d9011e4d1e0229705982190c11ce537d459464a5b7a9991c631cf6271c'
assert json.loads(review.read_text())['verdict'].lower()=='failed_harness'
status=RUN/'status_batch142.json';assert json.loads(status.read_text())['state']=='failed'
clean=HERE/'D09_T16_OWNED_CLEANUP_READBACK.json';assert json.loads(clean.read_text())['cleanup_ok']
launch=ROOT/'runs/dev_T16/launch_E2-D09-T16-night-20261009_batch142.json'; binding=json.loads(launch.read_text())
assert binding['child']['pid']==199552 and not Path('/proc/199552').exists()
arms={p.parent.name:{'raw_source':str(p.parent)} for p in RUN.glob('*/owned_process.json')};assert len(arms)==4
for src,name in [(review,'independent_review.json'),(clean,'cleanup_readback.json'),(launch,'launch_receipt.json'),(Path(binding['batch_log']),'batch142.log')]:shutil.copy2(src,RUN/name)
doc={'schema':'ft_round/v2','round_id':RID,'card':'D09-T16','batch':142,'retry_index':0,'retry_of':None,'verdict':'pending_review','proposed_verdict':'failed_harness','verdict_history':[],'retractions':[],'serve':{'arms':arms},'base':{'commit':'481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'},'experimental':{'candidate_commit':'c17b69a46cd512fbf3d127d3879bce92caae457b'},'actual_services':4,'actual_generation_calls':48,'planned_services':8,'planned_generation_calls':96,'product_acceptance':False,'batch_logs':[{'path':binding['batch_log'],'sha256':sha(binding['batch_log'])}],'result_binding':{name:{'path':name,'sha256':sha(RUN/name)} for name in ['status_batch142.json','cleanup_readback.json','independent_review.json']}}
put(RUN/'round.json',doc)
closer=ROOT/'runs/dev_D16/r041_accept_final_20261005_2012/d04_server_round_close_db7b2787.py';assert sha(closer)=='db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
py=str(ROOT/'venv/bin/python');app=ROOT/'scripts/round_json_append.py'
for argv in [[py,str(closer),RID,'--round-root',str(ROUNDS)],[py,str(app),str(RUN),'verdict','--new','failed_harness','--reason','Dynamic process PID suffix rejected by adapter after four arms; no product conclusion','--evidence',str(RUN/'independent_review.json'),str(status),'--by','root'],[py,str(app),str(RUN),'check']]:
 r=subprocess.run(argv,capture_output=True,text=True);assert r.returncode==0,(r.stdout,r.stderr);print(r.stdout)
for line in (RUN/'MANIFEST.sha256').read_text().splitlines():
 digest,name=line.split('  ',1);assert sha(RUN/name)==digest
assert all(not p.stat().st_mode & 0o222 for p in [RUN,*RUN.rglob('*')])
v={'at':datetime.datetime.now().astimezone().isoformat(),'rid':RID,'verdict':'failed_harness','manifest_sha256':sha(RUN/'MANIFEST.sha256'),'raw_hashes_match':True,'read_only':True,'actual_services':4,'actual_generation_calls':48}
put(HERE/'D09_T16_FAILED_HARNESS_CLOSURE.json',v)
with (HERE/'COORDINATION_LOG.jsonl').open('a') as f:f.write(json.dumps(v|{'event':'D09_T16_BATCH142_SEALED'})+chr(10));f.flush();os.fsync(f.fileno())
print(json.dumps(v))
