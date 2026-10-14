"""Run CPU tests from a task-owned staged source; never touch the production runtime."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("archive")
parser.add_argument("stage")
parser.add_argument("--tests", nargs="+", default=["tests/server", "tests/tokenizer", "tests/daemon"])
args = parser.parse_args()
archive = Path(args.archive).resolve()
assert archive.parent == HERE
assert args.stage.replace("_", "").isalnum()
spec = importlib.util.spec_from_file_location("ops", HERE.parent / "r067c_retry2_production_control_20261009/ssh_ops.py")
ops = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ops)
client = ops.connect()
remote = "/data2/FreeToken/development/upstream_oom_pr_20261014"
try:
    sftp = client.open_sftp()
    try:
        sftp.mkdir(remote)
    except OSError:
        sftp.stat(remote)
    target = remote + "/" + archive.name
    with sftp.open(target, "wx") as handle:
        handle.write(archive.read_bytes())
    sftp.close()
    payload = json.dumps({"root": remote, "archive": archive.name, "stage": args.stage,
                          "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "tests": args.tests})
    code = r'''
import datetime,hashlib,json,os,pathlib,subprocess,zipfile
value=json.loads(PAYLOAD)
root=pathlib.Path(value['root']); archive=root/value['archive']; stage=root/value['stage']
assert hashlib.sha256(archive.read_bytes()).hexdigest()==value['sha256']
stage.mkdir()
with zipfile.ZipFile(archive) as z:
 for item in z.infolist():
  assert not item.filename.startswith('/') and '..' not in pathlib.PurePosixPath(item.filename).parts
 z.extractall(stage)
env=dict(os.environ)
for key in list(env):
 if key.startswith(('FT_','RELEASE_SMOKE_')):env.pop(key)
env.update(CUDA_VISIBLE_DEVICES='',PYTHONPATH=str(stage/'python'),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',TOKENIZERS_PARALLELISM='false',HF_HUB_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',MASTER_PORT='8139')
python='/data2/FreeToken/development/upstream_layer_major_pr_20261014/main-venv/bin/python'
argv=[python,'-m','pytest','-q',*value['tests']]
started=datetime.datetime.now().astimezone().isoformat()
with (root/(value['stage']+'.stdout.log')).open('xb') as out, (root/(value['stage']+'.stderr.log')).open('xb') as err:
 result=subprocess.run(argv,cwd=stage,env=env,stdout=out,stderr=err,timeout=900)
receipt={'at':started,'finished_at':datetime.datetime.now().astimezone().isoformat(),'stage':str(stage),'archive_sha256':value['sha256'],'argv':argv,'exit_code':result.returncode,'cuda_visible_devices':'','production_untouched':True}
for suffix in ('stdout.log','stderr.log'):
 receipt[suffix+'_sha256']=hashlib.sha256((root/(value['stage']+'.'+suffix)).read_bytes()).hexdigest()
with (root/(value['stage']+'.receipt.json')).open('x') as handle:json.dump(receipt,handle,indent=2)
print(json.dumps(receipt,indent=2))
print((root/(value['stage']+'.stdout.log')).read_text()[-10000:])
print((root/(value['stage']+'.stderr.log')).read_text()[-2500:])
'''.replace("PAYLOAD", repr(payload))
    ops.run(client, code)
    sftp = client.open_sftp()
    for suffix in ("stdout.log", "stderr.log", "receipt.json"):
        name = args.stage + "." + suffix
        sftp.get(remote + "/" + name, str(HERE / name))
    sftp.close()
finally:
    client.close()
