"""CPU-only validation in an isolated server directory, never a deployed tree."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("transport", HERE.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
transport = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transport)
repo = ROOT / 'upstream-flashml'
head = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
bundle = ROOT/'archive/local_finalization_20261014/upstream_engine/integrated.bundle'
subprocess.run(['git','-C',str(repo),'bundle','create',str(bundle),'local/final-20261014'],check=True)
sha = hashlib.file_digest(bundle.open('rb'),'sha256').hexdigest()
shallow = (ROOT/'archive/local_finalization_20261014/upstream_engine/shallow.txt').read_text(encoding='utf-8')
code = r'''
import datetime,hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/data2/FreeToken/development/local_finalization_20261014')
bundle=root/'integration.bundle'
assert hashlib.sha256(bundle.read_bytes()).hexdigest()==BUNDLE_SHA
stage=root/'integration_a7c24b2'
assert not stage.exists()
subprocess.run(['git','init','--quiet',str(stage)],check=True,capture_output=True)
if SHALLOW:
    (stage/'.git/shallow').write_text(SHALLOW)
subprocess.run(['git','-C',str(stage),'bundle','unbundle',str(bundle)],check=True,capture_output=True)
subprocess.run(['git','-C',str(stage),'update-ref','refs/heads/integration',HEAD],check=True,capture_output=True)
subprocess.run(['git','-C',str(stage),'checkout','--quiet','integration'],check=True,capture_output=True)
env=os.environ.copy()
env.update(CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONPATH=str(stage/'python'),PYTHONNOUSERSITE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
python='/data2/FreeToken/development/upstream_layer_major_pr_20261014/main-venv/bin/python'
argv=[python,'-m','pytest','-q','tests/server','tests/tokenizer','tests/daemon','tests/scheduler','tests/kvcache','tests/engine']
started=datetime.datetime.now().astimezone().isoformat()
with (root/'CPU.stdout.log').open('w') as out,(root/'CPU.stderr.log').open('w') as err:
    result=subprocess.run(argv,cwd=stage,env=env,stdout=out,stderr=err,timeout=180)
receipt={'at':started,'finished_at':datetime.datetime.now().astimezone().isoformat(),'head':HEAD,'bundle_sha256':BUNDLE_SHA,'argv':argv,'exit_code':result.returncode,'cuda_visible_devices':'','production_actions':0,'generation_calls':0,
         'stdout_sha256':hashlib.sha256((root/'CPU.stdout.log').read_bytes()).hexdigest(),'stderr_sha256':hashlib.sha256((root/'CPU.stderr.log').read_bytes()).hexdigest()}
(root/'CPU_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt))
print((root/'CPU.stdout.log').read_text()[-3000:])
'''.replace('BUNDLE_SHA', repr(sha)).replace('SHALLOW',repr(shallow)).replace('HEAD', repr(head))
client=transport.connect()
try:
    sftp=client.open_sftp()
    remote='/data2/FreeToken/development/local_finalization_20261014'
    sftp.put(str(bundle),remote+'/integration.bundle')
    _,out,err=client.exec_command('/data2/FreeToken/venv/bin/python -c '+shlex.quote(code))
    result,errors=out.read().decode(),err.read().decode()
    status=out.channel.recv_exit_status()
    for name in ['CPU_RECEIPT.json','CPU.stdout.log','CPU.stderr.log']:
        try:
            sftp.get(remote+'/'+name,str(HERE/name))
        except FileNotFoundError:
            pass
    sftp.close()
    print(result)
    if errors:
        print(errors)
    assert status==0,status
    assert json.loads((HERE/'CPU_RECEIPT.json').read_text())['exit_code']==0
finally:
    client.close()
