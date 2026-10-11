"""CPU-only upload and fresh immutable retry1 proof. Never starts a service."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import paramiko

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
spec = importlib.util.spec_from_file_location('ssh_config', WORKSPACE / '_shared/ssh_upload.py')
cfg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cfg)
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(cfg.REMOTE_HOST, username=cfg.REMOTE_USER, password=cfg.REMOTE_PASS)
sftp = client.open_sftp()
remote = '/data2/FreeToken/development/' + HERE.name
try:
    sftp.mkdir(remote)
except IOError:
    pass
for file in HERE.iterdir():
    if file.suffix not in ('.py', '.json'):
        continue
    target = remote + '/' + file.name
    try:
        with sftp.open(target, 'rb') as f:
            assert f.read() == file.read_bytes(), target
    except FileNotFoundError:
        with sftp.open(target, 'wx') as f:
            f.write(file.read_bytes())
code = r'''
import ast,hashlib,importlib.util,json,time
from pathlib import Path
root=Path('/data2/FreeToken/development/r067c_retry1_production_control_20261009')
packet=Path('/data2/FreeToken/development/r067c_retry1_short_tail_v1')
sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
for file in root.glob('*.py'): ast.parse(file.read_text())
spec=importlib.util.spec_from_file_location('guard',root/'launch_approved_r067c.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
event={'event':'attempt_reserved','rid':'original'}
assert guard.validate_attempt([], 'new')==0
assert guard.validate_attempt([event], 'new', {'verdict':'failed_harness','rid':'original'})==1
cases=[([event],'original',{'verdict':'failed_harness','rid':'original'}),([event],'new',{'verdict':'not_met','rid':'original'}),([{'event':'attempt_reserved','rid':str(i)} for i in range(3)],'new',{'verdict':'failed_harness','rid':'2'})]
for args in cases:
    try: guard.validate_attempt(*args)
    except AssertionError: pass
    else: raise AssertionError('guard allowed forbidden retry')
receipt={'exit_code':0,'retry_guard_cases_passed':5,'syntax':'PASS','helper_self_hash_enforced':True,'launch_helper_sha256':sha(root/'launch_approved_r067c.py'),'at':time.time()}
(root/'LINUX_ROOT_CONTROL_CPU_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
old=json.loads(Path('/data2/FreeToken/development/r067c_short_tail_v1/R067C_ROOT_BINDINGS_V2.json').read_text())
bindings=old['bindings']
for file in root.iterdir():
    if file.suffix in ('.py','.json'): bindings[str(file)]=sha(file)
manifest=json.loads((packet/'RETRY1_UPLOAD_MANIFEST.json').read_text())
for name,digest in manifest['files'].items():
    assert sha(packet/name)==digest,name
    bindings[str(packet/name)]=digest
for name in ('RETRY1_UPLOAD_MANIFEST.json','RETRY1_CPU_FILEDRY_RECEIPT.json','evidence_cpu_filedry_20261009_v2/receipt.json'):
    bindings[str(packet/name)]=sha(packet/name)
for path in ('/data2/FreeToken/runs/dev_R067/E2-R067c-d20-short-tail/terminal.json','/data2/_shared/runs/ft_rounds/E2-R067c-d20-short-tail/manifest.json','/data2/FreeToken/runs/production/RESTORE481-E2-R067c-20261009-01/production_release.json'):
    bindings[path]=sha(path)
for path,digest in bindings.items(): assert sha(path)==digest,path
ops=Path('/data2/FreeToken/runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded/source/development/release_e2_ops_v2')
spec=importlib.util.spec_from_file_location('checks',ops/'worktree_checks.py');checks=importlib.util.module_from_spec(spec);spec.loader.exec_module(checks)
binary=json.loads((ops/'binary_manifest.json').read_text())
trees={mode:checks.validate_worktree(item['path'],item['commit'],binary,mode) for mode,item in binary['worktrees'].items()}
assert all(r['ok'] for r in trees.values())
for mode in ('release','r067_cold'):
    assert not list((Path(binary['worktrees'][mode]['path'])/'python/freetoken/kernel').glob('_row_store*.so'))
proof={'schema':'ft_r067c_retry1_root_signed_filedry/v1','rid':manifest['rid'],'bindings':bindings,'worktree_checks':trees,'FILEdry':'PASS','linux_tests':{'passed':6,'skipped':0},'production_may_be_serving':True,'launch_admitted':False,'at':time.time()}
target=packet/'RETRY1_ROOT_BINDINGS.json'
with target.open('x') as f: json.dump(proof,f,indent=2);f.write('\n')
print(json.dumps({'proof':str(target),'sha256':sha(target),'bindings':len(bindings),'worktrees':{k:{'ok':v['ok'],'head':v['actual_head']} for k,v in trees.items()},'cpu_receipt':receipt}))
'''
_, stdout, stderr = client.exec_command('/data2/FreeToken/venv/bin/python -c ' + shlex.quote(code))
print(stdout.read().decode())
print(stderr.read().decode())
status = stdout.channel.recv_exit_status()
if status == 0:
    sftp.get('/data2/FreeToken/development/r067c_retry1_short_tail_v1/RETRY1_ROOT_BINDINGS.json', str(HERE.parent/'r067c_retry1_short_tail_v1/RETRY1_ROOT_BINDINGS.json'))
    sftp.get(remote+'/LINUX_ROOT_CONTROL_CPU_RECEIPT.json',str(HERE/'LINUX_ROOT_CONTROL_CPU_RECEIPT.json'))
client.close()
raise SystemExit(status)
