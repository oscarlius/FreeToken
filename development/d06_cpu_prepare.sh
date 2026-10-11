set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,pathlib,subprocess
source = pathlib.Path('/data2/FreeToken/wt/e2base')
donor = pathlib.Path('/data2/FreeToken/wt/e1r003st')
target = pathlib.Path('/data2/FreeToken/runs/dev_D06/cpu_23f2e2c')
parent = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
candidate = 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
assert subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip() == parent
assert not subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip()
assert subprocess.check_output(['git','-C',str(donor),'rev-parse','HEAD'],text=True).strip() == candidate
assert not target.exists(), 'CPU validation target already exists; inspect rather than replace'
target.mkdir(parents=True)
subprocess.run(['git','-C',str(source),'worktree','add','--detach',str(target/'repo'),parent],check=True)
extensions=[]
for extension in (donor/'python/freetoken').rglob('*.so'):
    path = target/'repo/python/freetoken'/extension.relative_to(donor/'python/freetoken')
    assert not path.exists()
    path.parent.mkdir(parents=True,exist_ok=True)
    path.symlink_to(extension.resolve())
    extensions.append(str(path.relative_to(target/'repo')))
receipt={'scope':'isolated Linux CPU verification only; no model/GPU service',
         'parent_commit':parent,'extension_donor_commit':candidate,'compiled_extension_links':extensions}
with (target/'cpu_surface.json').open('x',encoding='utf-8') as f:
    json.dump(receipt,f,indent=2,allow_nan=False);f.write('\n')
print(json.dumps({'created':str(target),'parent_commit':parent,'compiled_extension_links':len(extensions)},sort_keys=True))
PY
