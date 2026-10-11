set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess
repo=pathlib.Path('/data2/FreeToken/wt/e1r003st')
target=pathlib.Path('/data2/FreeToken/wt/e2d03-continuation')
stage=pathlib.Path('/data2/FreeToken/runs/dev_D03/continuation_f5067bb')
bundle=stage/'candidate.bundle'
commit='f5067bbe05da51d5f78185213435a8be095a684a'
assert hashlib.sha256(bundle.read_bytes()).hexdigest()=='2d2a005b9e366edf51530eb2d7448756bf9ebccaff03a25054fe20d9d48b45b2'
assert not target.exists() and not (stage/'targeted.log').exists()
subprocess.run(['git','-C',str(repo),'bundle','verify',str(bundle)],check=True)
subprocess.run(['git','-C',str(repo),'fetch',str(bundle),'HEAD'],check=True)
assert subprocess.check_output(['git','-C',str(repo),'rev-parse','FETCH_HEAD'],text=True).strip()==commit
subprocess.run(['git','-C',str(repo),'worktree','add','--detach',str(target),commit],check=True)
for extension in (repo/'python/freetoken').rglob('*.so'):
    path=target/'python/freetoken'/extension.relative_to(repo/'python/freetoken')
    assert not path.exists()
    path.parent.mkdir(parents=True,exist_ok=True)
    path.symlink_to(extension.resolve())
expected={'python/freetoken/scheduler/prefill.py':'765b346fa732070a0d301b0562c50f774ed1dd18d52e620f9887740ea20f0533',
          'tests/scheduler/test_scheduler_chunked_prefill.py':'b275602ff1a3c2f3242e509d383791049b1097a1ce02811c17bd11a3c8e27a19'}
for name,digest in expected.items():
    assert hashlib.sha256((target/name).read_bytes()).hexdigest()==digest,name
assert subprocess.check_output(['git','-C',str(target),'rev-parse','HEAD^'],text=True).strip()=='c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
assert not subprocess.check_output(['git','-C',str(target),'status','--porcelain'],text=True).strip()
with (stage/'candidate.json').open('x',encoding='utf-8') as f:
    json.dump({'commit':commit,'worktree':str(target),'source_sha256':expected,
               'scope':'new D03 diagnostic propagation candidate; no GPU activation'},f,indent=2);f.write('\n')
PY
cd /data2/FreeToken/wt/e2d03-continuation
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 PYTHONPATH=python /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider --tb=short tests/scheduler/test_scheduler_chunked_prefill.py tests/scheduler/test_prefill_anchor_cut_switch.py tests/kvcache/test_state_dump_at.py tests/server/test_dev_logits.py > /data2/FreeToken/runs/dev_D03/continuation_f5067bb/targeted.log 2>&1
tail -n 12 /data2/FreeToken/runs/dev_D03/continuation_f5067bb/targeted.log
sha256sum /data2/FreeToken/runs/dev_D03/continuation_f5067bb/targeted.log
