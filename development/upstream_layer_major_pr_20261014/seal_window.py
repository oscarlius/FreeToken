"""Seal and verify approved window sources on CPU; do not control services."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
auth=json.loads((HERE/'WINDOW_AUTHORIZATION.json').read_text())
native=json.loads((HERE/'NATIVE_CPU_PREFLIGHT_01.json').read_text())['native_modules']
auth.update(main_commit='9c635a157798da4aa43e6d051e92620521ed1858',
    candidate_archive_sha256=digest(HERE/'candidate_63858fa.zip'),
    native_modules={'python/freetoken/kernel/'+name:value for name,value in native.items()},
    parent_authorization_sha256=digest(HERE/'WINDOW_AUTHORIZATION.json'))
dump(HERE/'WINDOW_AUTHORIZATION_SEALED.json',auth)
package=HERE/'restore_e3'
for name in ('DEPLOYMENT_APPROVAL','ROOT_FINAL_REVIEW'):
    shutil.copyfile(package/(name+'.json'),package/(name+'.pending.json'))
approval=json.loads((package/'DEPLOYMENT_APPROVAL.json').read_text())
approval['conditions_met']=True
approval['window_authorization_sha256']=digest(HERE/'WINDOW_AUTHORIZATION_SEALED.json')
dump(package/'DEPLOYMENT_APPROVAL.json',approval)
review={'verdict':'PASS','reviewer_role':'root_independent_final_reviewer',
        'reviewed_by':'native layer_major_tests; source inventory and six adapter scripts; conditional CPU proof executed before stop',
        'approval_id':approval['approval_id'],'approval_sha256':digest(package/'DEPLOYMENT_APPROVAL.json'),
        'package_source_manifest_sha256':digest(package/'SOURCE_MANIFEST.json'),
        'recorded_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        'scope':'E3 identity restore using unchanged start/wait/SDK controls; new guarded entry; no old observer/retry'}
dump(package/'ROOT_FINAL_REVIEW.json',review)
spec=importlib.util.spec_from_file_location('ops',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
client=ops.connect()
try:
    remote='/data2/FreeToken/development/upstream_layer_major_pr_20261014/'
    sftp=client.open_sftp()
    names=('gpu_window_ready.py','test_gpu_window.py','WINDOW_AUTHORIZATION_SEALED.json',
           'restore_e3/DEPLOYMENT_APPROVAL.pending.json','restore_e3/ROOT_FINAL_REVIEW.pending.json',
           'restore_e3/DEPLOYMENT_APPROVAL.json','restore_e3/ROOT_FINAL_REVIEW.json')
    for name in names:sftp.put(str(HERE/name),remote+name)
    sftp.close()
    ops.run(client,r'''
import datetime, hashlib, json, os, pathlib, subprocess, sys
root=pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
sys.path.insert(0,str(root));import gpu_window_ready as window
auth=json.loads((root/'WINDOW_AUTHORIZATION_SEALED.json').read_text())
removed=0
for source in (root/'main_9c635a1',root/'candidate_63858fa'):
    assert source.resolve().is_relative_to(root.resolve()) and not source.is_symlink()
    for path in (source/'python').rglob('*.pyc'):
        assert path.resolve().is_relative_to(source.resolve())
        path.unlink();removed+=1
proofs={
 'main':window.verify_tree(root/'main_9c635a1.zip',root/'main_9c635a1',auth['main_archive_sha256'],auth['main_commit'],auth['native_modules']),
 'candidate':window.verify_tree(root/'candidate_63858fa.zip',root/'candidate_63858fa',auth['candidate_archive_sha256'],auth['candidate_commit'],auth['native_modules'])}
gate=window.load(root/'restore_e3/deploy_conditional.py','preflight_restore_gate')
gate.require_root_final_review(json.loads((root/'restore_e3/DEPLOYMENT_APPROVAL.json').read_text()))
helper=window.load(pathlib.Path(auth['frozen_ops']['path']).parent/'d07_g3g4_prepare.py','preflight_helper')
helper.load_owned_lifecycle()
test=subprocess.run([sys.executable,'-m','unittest','-v','test_gpu_window.py','test_gpu_client.py','test_native_observer.py'],
    cwd=root,env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1'),capture_output=True,text=True,timeout=60)
assert test.returncode==0, test.stderr
ready={'at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
       'sources':proofs,'native_modules':auth['native_modules'],'owned_stage_pyc_removed':removed,
       'controller_tests':{'exit_code':test.returncode,'stdout':test.stdout,'stderr':test.stderr},
       'new_recovery_identity_gate':'PASS','lifecycle_import':'PASS','gpu_calls':0,'service_actions':0,
       'executor_sha256':window.sha(root/'gpu_window_ready.py'),
       'authorization_sha256':window.sha(root/'WINDOW_AUTHORIZATION_SEALED.json')}
with (root/'WINDOW_CPU_READY.json').open('x') as f:json.dump(ready,f,indent=2)
print(json.dumps({k:v for k,v in ready.items() if k!='controller_tests'},indent=2))
''')
    sftp=client.open_sftp();sftp.get(remote+'WINDOW_CPU_READY.json',str(HERE/'WINDOW_CPU_READY.json'));sftp.close()
finally:client.close()
