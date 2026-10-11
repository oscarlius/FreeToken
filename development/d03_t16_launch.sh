set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess,sys

root=pathlib.Path('/data2/FreeToken')
dev=root/'runs/dev_D03'
rounds=pathlib.Path('/data2/_shared/runs/ft_rounds')
batches=root/'runs/plan_batches'
candidate='c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
rid='E2-R002-gate-D03'
assert not (dev/'t16_launch_c30ae0d.json').exists(), 'T16 launch record already exists'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def live(pid):
    stat=pathlib.Path(f'/proc/{pid}/stat')
    return stat.exists() and stat.read_text().partition(') ')[2][0]!='Z'

launch=json.loads((dev/'gpu_selfcheck_launch_c30ae0d_urlfix.json').read_text())
assert launch['candidate_commit']==candidate and not live(launch['pid']), 'selfcheck remains live'
check=dev/'gpu_selfcheck_c30ae0d_urlfix'
assert not (check/'selfcheck_error.json').exists(), 'selfcheck failed; preserve evidence'
report=json.loads((check/'selfcheck.json').read_text())
assert report['mode']=='development_selfcheck_not_acceptance' and report['cold_eq']
assert report['g4_boundaries']==[448,4544,8640,12672,14144,18240,21504]
assert json.loads((check/'g5_logits_compare.log').read_text().splitlines()[-1])['peer_vs_recompute']['bitwise_equal'] is True
for owner in check.glob('*/owned_process.json'):
    assert not live(json.loads(owner.read_text())['pid']), str(owner)
for line in (check/'MANIFEST.sha256').read_text().splitlines():
    expected,relative=line.split('  ',1)
    p=(check/relative).resolve()
    assert check.resolve() in p.parents and digest(p)==expected, relative

source=dev/'gate_tools_c30ae0d/t16_runner.py'
assert hashlib.md5(source.read_bytes()).hexdigest()=='00661195a6df1a6f6456fc938c489381'
runner=batches/'t16_runner_d03_c30ae0d.py'
if runner.exists(): assert runner.read_bytes()==source.read_bytes()
else:
    with runner.open('xb') as f: f.write(source.read_bytes())
assert not (rounds/rid).exists()
subprocess.run([sys.executable,str(runner),'--self-test'],check=True)
import importlib.util
launcher=batches/'e2_launch.py'
assert digest(launcher)=='a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf'
spec=importlib.util.spec_from_file_location('e2_launch',launcher)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
batch=module.next_batch(rounds)
argv=[sys.executable,'-u',str(runner),'--gate','D03','--rid',rid,'--batch',str(batch),'--candidate-commit',candidate]
subprocess.run(argv,check=True)
assert module.next_batch(rounds)==batch and not (rounds/rid).exists()
# CUDA_VISIBLE_DEVICES was limited to CPU checks; the GPU subprocess needs its normal view.
import os
os.environ.pop('CUDA_VISIBLE_DEVICES',None)
process,wrapper,log=module.reserve_and_launch(batch,rid,argv)
record={'rid':rid,'batch':batch,'batch_pid':process.pid,'pgid':process.pid,'candidate_commit':candidate,
        'runner':str(runner),'runner_sha256':digest(runner),'wrapper':str(wrapper),'wrapper_sha256':digest(wrapper),
        'log':str(log),'selfcheck_manifest_sha256':digest(check/'MANIFEST.sha256')}
with (dev/'t16_launch_c30ae0d.json').open('x') as f: json.dump(record,f,indent=2);f.write('\n')
print('D03_T16_LAUNCH',json.dumps(record),flush=True)
PY
