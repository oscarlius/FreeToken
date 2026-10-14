"""CPU-only fresh-window authorization and E3 identity recovery preparation."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
TZ = datetime.timezone(datetime.timedelta(hours=8))
REMOTE = '/data2/FreeToken/development/upstream_layer_major_pr_20261014/'
identity = 'UPSTREAM-LM-PR-RESTORE-E3-20261014-01'
target = HERE/'restore_e3'
target.mkdir()
old = HERE/'recovery_source_snapshot/e3_package'
for name in ('approved_attempt.py','start_approved_release.py','wait_release_and_smoke.py',
             'run_exclusive_smoke.py','stop_approved_restore.py'):
    shutil.copyfile(old/name,target/name)
gate = '''"""Only explicit start/wait adapters are allowed for this new E3 identity."""
import hashlib, json, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
def require_root_final_review(approval):
    review=json.loads((HERE/'ROOT_FINAL_REVIEW.json').read_text())
    if not approval['conditions_met'] or review.get('verdict')!='PASS':
        raise RuntimeError('PENDING independent recovery review')
    data=(HERE/'DEPLOYMENT_APPROVAL.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=review['approval_sha256'] or json.loads(data)!=approval:
        raise RuntimeError('Recovery approval changed')
    manifest_path=HERE/'SOURCE_MANIFEST.json'
    digest=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if digest!=review['package_source_manifest_sha256'] or digest!=approval['package_source_manifest_sha256']:
        raise RuntimeError('Recovery source manifest changed')
    for name, expected in json.loads(manifest_path.read_text())['files'].items():
        if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Recovery source changed: '+name)
    sys.path.insert(0,str(HERE.parent))
    from recovery_guard import verify_sources
    verify_sources(approval)
if __name__=='__main__':
    raise SystemExit('Use only explicit start_approved_release.py and wait_release_and_smoke.py; no old observer or automatic retry')
'''
(target/'deploy_conditional.py').write_text(gate,encoding='utf-8',newline='\n')
manifest={'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file()}}
def dump(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
dump(target/'SOURCE_MANIFEST.json',manifest)
approval=json.loads((HERE/'recovery_source_snapshot/production/deployment_approval.json').read_text())
approval.update(approval_id=identity,run_dir='/data2/FreeToken/runs/production/'+identity,
                conditions_met=False,recorded_at=datetime.datetime.now(TZ).isoformat(),
                package_source_manifest_sha256=hashlib.sha256((target/'SOURCE_MANIFEST.json').read_bytes()).hexdigest(),
                user_authority='User acknowledged 2026-10-14 new GPU window: 已知悉，现在执行; three serial measurement services,27 calls,concurrency1; one E3 restoration service with2SDK calls;45min cap including restore.',
                scope=['Restore current E3 9db0ee77 after the specifically approved upstream PR measurement window',
                       'Same frozen E3 ops and own E3 cold/SDK reference; one new identity, two SDK calls; no observer extension or retry'])
dump(target/'DEPLOYMENT_APPROVAL.json',approval)
dump(target/'ROOT_FINAL_REVIEW.json',{'verdict':'PENDING','approval_id':identity})
spec=importlib.util.spec_from_file_location('ops',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
client=ops.connect()
try:
    sftp=client.open_sftp()
    for name in ('main_9c635a1.zip','recovery_guard.py'):
        sftp.put(str(HERE/name),REMOTE+name)
    sftp.mkdir(REMOTE+'restore_e3')
    for p in target.iterdir():sftp.put(str(p),REMOTE+'restore_e3/'+p.name)
    frozen=json.loads((HERE/'recovery_source_snapshot/production/deployment_approval.json').read_text())['frozen_ops']['path']
    helper=str(Path(frozen).as_posix()).rsplit('/',1)[0]+'/d07_g3g4_prepare.py'
    sftp.get(helper,str(HERE/'d07_helper_source.py'))
    sftp.close()
    ops.run(client,r'''
import datetime, hashlib, json, os, pathlib, shutil, subprocess, zipfile
root=pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
with zipfile.ZipFile(root/'main_9c635a1.zip') as z:z.extractall(root/'main_9c635a1')
native=root/'candidate_63858fa/python/freetoken/kernel'
for p in native.glob('*.so'):
    shutil.copy2(p,root/'main_9c635a1/python/freetoken/kernel'/p.name)
    assert hashlib.sha256(p.read_bytes()).digest()==hashlib.sha256((root/'main_9c635a1/python/freetoken/kernel'/p.name).read_bytes()).digest()
sys=__import__('sys');sys.path.insert(0,str(root));import recovery_guard
prod=pathlib.Path('/data2/FreeToken/runs/production/RELEASE-E3-20261012-02')
oldapproval=json.loads((prod/'deployment_approval.json').read_text())
owner=json.loads(pathlib.Path('/data2/FreeToken/run/production.active.json').read_text())
recovery_guard.verify_active(json.loads((prod/'owner.json').read_text()),owner)
recovery_guard.verify_sources(oldapproval)
auth={'authorized':True,'recorded_at':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
      'source':'Explicit user reply: 已知悉，现在执行 (new upstream PR GPU window)',
      'services':3,'measurement_calls':27,'recovery_services':1,'recovery_sdk_calls':2,
      'concurrency':1,'measurement_seconds':1800,'window_seconds':2700,
      'frozen_ops':oldapproval['frozen_ops'],'active_snapshot':owner,
      'old_stop_adapter':'/data2/FreeToken/development/ophak_release_e3_20261012/release_e3_02/stop_approved_restore.py',
      'inputs_sha256':hashlib.sha256((root/'inputs.json').read_bytes()).hexdigest(),
      'main_archive_sha256':hashlib.sha256((root/'main_9c635a1.zip').read_bytes()).hexdigest(),
      'candidate_commit':'63858faa584ddd623d5ea1728e26270e0c7f649b'}
with (root/'WINDOW_AUTHORIZATION.json').open('x') as f:json.dump(auth,f,indent=2)
state={'at':auth['recorded_at'],'active_owner':owner['approval_id'],
       'nvidia_smi':subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader'],text=True),
       'uptime':subprocess.check_output(['uptime'],text=True),'ollama_running':subprocess.check_output(['docker','inspect','--format={{.State.Running}}','ollama'],text=True).strip(),
       'service_actions':0}
with (root/'WINDOW_PREPARATION_01.json').open('x') as f:json.dump(state,f,indent=2)
print(json.dumps(state,indent=2))
''')
    sftp=client.open_sftp()
    for name in ('WINDOW_AUTHORIZATION.json','WINDOW_PREPARATION_01.json'):
        sftp.get(REMOTE+name,str(HERE/name))
    sftp.close()
finally:client.close()
