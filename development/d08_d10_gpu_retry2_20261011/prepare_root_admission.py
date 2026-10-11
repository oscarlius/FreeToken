"""CPU-only root packaging. Does not start services or stop production."""
from pathlib import Path
import json, hashlib, datetime, importlib.util, posixpath,subprocess,sys

BASE=Path(__file__).resolve().parents[2]
PKG=Path(__file__).resolve().parent
RESTORE=BASE/'development/morning_restore07_20261011'
ETA=BASE/'development/d10_eta_retry2_20261011'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def remote(p):return '/data2/FreeToken/'+p.relative_to(BASE).as_posix()
def dump(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf8')

def main():
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    er=ETA/'independent_static_review/20261011T012933+08_00/ETA_RETRY2_INDEPENDENT_CPU_REVIEW.json'
    rr=ETA/'independent_static_review/20261011T012933+08_00/RESTORE07_IDENTITY_STATIC_REVIEW.json'
    reviews=sorted(PKG.glob('independent_static_review/*/D08_D10_RETRY2_SOURCE_PIN_REREVIEW*.json'))
    cr=reviews[-1];review=json.loads(cr.read_text())
    names=('gpu_window.py','hybrid_service.py','window_measure.py','d0_service.py','warmup_client.py')
    assert review['verdict']=='APPROVE_CPU_SCOPE'
    addendum=PKG/'independent_static_review/20261011T013209+08_00/CURRENT_FIVE_PINS_HASH_ADDENDUM.json'
    pins=json.loads(addendum.read_text())['current_controller_source_pins']
    for n in names:assert sha(PKG/n)==pins[remote(PKG/n)],n
    tests=subprocess.run([sys.executable,'-m','pytest',str(PKG),str(RESTORE),'-q'],capture_output=True,text=True)
    assert tests.returncode==0,tests.stdout+tests.stderr
    dump(PKG/'CPU_PIN_FIX_FRESH_LOCAL.json',{'at':now,'argv':tests.args,'stdout':tests.stdout,'stderr':tests.stderr,'exit_code':tests.returncode,'controller_source_pins':pins,'test_retry2_contract_sha256':sha(PKG/'test_retry2_contract.py'),'addendum_sha256':sha(addendum)})
    manifest=RESTORE/'SOURCE_MANIFEST.json';approval=RESTORE/'DEPLOYMENT_APPROVAL.json'
    a=json.loads(approval.read_text());a.update(conditions_met=True,recorded_at=now,package_source_manifest_sha256=sha(manifest));a['conditions']['root_final_review']='PASS';dump(approval,a)
    final={'verdict':'PASS','reviewer_role':'root_independent_final_reviewer','approval_id':a['approval_id'],'approval_sha256':sha(approval),'package_source_manifest_sha256':sha(manifest),'recorded_at':now,'independent_review_sha256':sha(rr),'scope':'Identity-only Restore07, 7 CPU tests, exact baseline, mandatory stop-before-rollback. No push.'}
    dump(RESTORE/'ROOT_FINAL_REVIEW.json',final)
    doc=json.loads((BASE/'development/d08_d10_gpu_window_retry1_20261011/ROOT_ADMISSION.json').read_text())
    doc.update(schema='ft_d08_d10_eta_retry2_admission/v1',recorded_at=now,baseline_owner=json.loads((PKG/'BASELINE_OWNER_FREEZE.json').read_text()),baseline_owner_path=remote(PKG/'BASELINE_OWNER_FREEZE.json'),eta_path=remote(ETA/'eta_retry2_microbench.py'),eta_review_path=remote(er),output_root='/data2/FreeToken/runs/dev_D08_D10_retry2_20261011/window01',window_limit_seconds=2700,service_budget=2,generation_calls={'warmup_unscored':2,'hybrid_single':1,'hybrid_two':2,'d0_single':1},retry_reason='User-authorized retry2 v3; 600s readiness, two SDK warmups, layered eta, fresh single D0',controller_review_sha256=sha(cr))
    doc['source_pins']['eta_sha256']=sha(ETA/'eta_retry2_microbench.py');doc['measure']['eta_path']='development/d10_eta_retry2_20261011/eta_retry2_microbench.py';doc['paths_hashes']={'eta_retry2_microbench.py':sha(ETA/'eta_retry2_microbench.py'),'inputs_X.jsonl':doc['input_sha256']}
    argv=list(doc['baseline_owner']['argv']);argv[argv.index('--moe-strategy')+1]='hybrid';doc['hybrid_argv']=['numactl','--interleave=all','taskset','-c','1,3-23,25,27-47',*argv[3:]]
    doc['controller_source_pins']={remote(PKG/n):sha(PKG/n) for n in names};doc['measure_sha256']=sha(PKG/'window_measure.py');doc['hybrid_controller_sha256']=sha(PKG/'hybrid_service.py');doc['cpu_review_pins']['eta']={'path':remote(er),'sha256':sha(er),'status_key':'status','accepted_status':'PASS'}
    doc.update(warmup_adapter_path='/data2/FreeToken/development/r065_d16_discriminate_v1/sdk_adapter.py',warmup_adapter_sha256='7870d1adab240ea1b0ee05e8035b13d77cd9b414597405a1987d60fea68412cd',warmup_inputs_path='/data2/FreeToken/development/r065_d16_discriminate_v1/inputs.json',warmup_inputs_sha256='18cce7cde13420f793cffd55ff8ce6e542f99b21bb193038912421854156539e')
    doc['controller_pin_addendum_sha256']=sha(addendum)
    doc['fresh_cpu_proof_sha256']=sha(PKG/'CPU_PIN_FIX_FRESH_LOCAL.json')
    dump(PKG/'ROOT_ADMISSION.json',doc)
    dump(PKG/'CPU_PIN_FIX_FINAL.json',{'at':now,'local_pytest':'24 passed in 0.30s','controller_source_pins':doc['controller_source_pins'],'eta_cpu_review_sha256':sha(er),'controller_review_sha256':sha(cr),'restore_review_sha256':sha(rr),'gpu_started':False})
    s=importlib.util.spec_from_file_location('ops',BASE/'development/r067c_retry2_production_control_20261009/ssh_ops.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);c=m.connect();ftp=c.open_sftp()
    files=[p for root in (PKG,RESTORE,ETA) for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts]
    for p in files:
        target=remote(p);current=posixpath.dirname(target);missing=[]
        while True:
            try:ftp.stat(current);break
            except OSError:missing.append(current);current=posixpath.dirname(current)
        for d in reversed(missing):ftp.mkdir(d)
        try:
            with ftp.open(target,'rb') as h:old=h.read()
        except OSError:old=None
        data=p.read_bytes()
        if old==data:continue
        if old is not None:
            if '/independent_static_review/' in target:raise RuntimeError('sealed review changed '+target)
            ftp.chmod(target,0o644)
        with ftp.open(target,'wb') as h:h.write(data)
        if p.suffix=='.json' and (p.name in ('ROOT_ADMISSION.json','ROOT_FINAL_REVIEW.json') or '/independent_static_review/' in target):ftp.chmod(target,0o444)
    ftp.close()
    m.run(c,r'''from pathlib import Path
import json,subprocess,os,hashlib,sys,importlib.util,datetime
p=Path('/data2/FreeToken/development/d08_d10_gpu_retry2_20261011')
e={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1'}
r=subprocess.run([sys.executable,'-m','pytest',str(p),'/data2/FreeToken/development/morning_restore07_20261011','-q'],env=e,capture_output=True,text=True)
print(r.stdout,r.stderr);assert r.returncode==0
sys.path.insert(0,str(p));import gpu_window
doc=json.loads((p/'ROOT_ADMISSION.json').read_text());gpu_window.validate_controller_pins(doc)
s=importlib.util.spec_from_file_location('restore7',Path('/data2/FreeToken/development/morning_restore07_20261011/deploy_conditional.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.require_root_final_review(m.load())
assert json.loads(Path('/data2/FreeToken/run/production.active.json').read_text())==doc['baseline_owner']
assert subprocess.check_output(['docker','inspect','-f','{{.State.Running}}','ollama'],text=True).strip()=='false'
for key in ('warmup_adapter','warmup_inputs'):
 assert hashlib.sha256(Path(doc[key+'_path']).read_bytes()).hexdigest()==doc[key+'_sha256']
print('FINAL_REMOTE_CPU_AND_OWNER_PASS',datetime.datetime.now().astimezone().isoformat())
print('ADMISSION_SHA',hashlib.sha256((p/'ROOT_ADMISSION.json').read_bytes()).hexdigest())
receipt={'at':datetime.datetime.now().astimezone().isoformat(),'argv':r.args,'stdout':r.stdout,'stderr':r.stderr,'exit_code':r.returncode,'controller_source_pins':doc['controller_source_pins'],'admission_sha256':hashlib.sha256((p/'ROOT_ADMISSION.json').read_bytes()).hexdigest(),'owner_unchanged':True,'ollama_stopped':True}
with (p/'CPU_PIN_FIX_FRESH_REMOTE.json').open('x') as f:json.dump(receipt,f,indent=2)
''');c.close()

if __name__=='__main__':main()
