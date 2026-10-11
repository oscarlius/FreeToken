set -euo pipefail
unset FT_DEV_ROUTE_TRACE FT_DEV_PAUSE_ENDPOINT FT_DEV_D0 FT_DEV_D0_TIMELINE
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, pathlib, re, subprocess
stage = pathlib.Path('/data2/FreeToken/runs/dev_D07/candidate_fefb19c')
parent_tree = pathlib.Path('/data2/FreeToken/wt/e2d06')
repo = pathlib.Path('/data2/FreeToken/wt/e2d07')
bundle = stage/'d07_candidate_fefb19c.bundle'
manifest = json.loads((stage/'d07_candidate_commit.json').read_text())
commit = 'fefb19cbac6bb1cb08835c411c895310600b3677'
expected_bundle = 'd9975522e5c1add1c8b88ac7d9a12523e1d5a156d7b43bcb9f879adaa0b25510'
if bundle.is_symlink() or hashlib.sha256(bundle.read_bytes()).hexdigest() != expected_bundle:
    raise ValueError('D07 candidate bundle changed')
if manifest['candidate_commit'] != commit or manifest['bundle_sha256'] != expected_bundle:
    raise ValueError('D07 candidate identity changed')
if subprocess.check_output(['git','-C',str(parent_tree),'rev-parse','HEAD'],text=True).strip() != manifest['parent']:
    raise ValueError('D07 parent candidate differs')
if subprocess.check_output(['git','-C',str(parent_tree),'status','--porcelain'],text=True).strip():
    raise ValueError('D07 parent source is dirty')
if repo.exists() or repo.is_symlink():
    raise ValueError('D07 candidate tree already exists')
subprocess.run(['git','-C',str(parent_tree),'bundle','verify',str(bundle)],check=True)
subprocess.run(['git','-C',str(parent_tree),'fetch',str(bundle),'refs/heads/exp/e2d07'],check=True)
subprocess.run(['git','-C',str(parent_tree),'worktree','add','--detach',str(repo),commit],check=True)
extensions = []
for extension in (parent_tree/'python/freetoken').rglob('*.so'):
    destination = repo/'python/freetoken'/extension.relative_to(parent_tree/'python/freetoken')
    if destination.exists() or destination.is_symlink():
        raise ValueError('D07 compiled extension target already exists')
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.symlink_to(extension.resolve())
    extensions.append({'path':str(destination.relative_to(repo)),
        'source':str(extension.resolve()),'sha256':hashlib.sha256(extension.read_bytes()).hexdigest()})
for name,digest in manifest['git_blob_files'].items():
    if hashlib.sha256((repo/name).read_bytes()).hexdigest() != digest:
        raise ValueError('D07 candidate Git blob mismatch: '+name)
if subprocess.check_output(['git','-C',str(repo),'show','-s','--format=%P','HEAD'],text=True).strip() != manifest['parent']:
    raise ValueError('D07 candidate immediate parent differs')
py = '/data2/FreeToken/venv/bin/python'
bootstrap = """import pathlib,sys
root=pathlib.Path(sys.argv[1])
sys.path.insert(0,str(root/'python'));sys.path.insert(1,str(root))
packages=pathlib.Path(sys.executable).parents[1]/'lib'/f'python{sys.version_info.major}.{sys.version_info.minor}'/'site-packages'
assert packages.is_dir(),packages
sys.path.append(str(packages))
import freetoken
assert freetoken.__file__==str(root/'python/freetoken/__init__.py'),freetoken.__file__
print('SOURCE '+freetoken.__file__,flush=True)
import pytest
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider',
 'tests/layers/test_route_trace_guard.py','scripts/tests/test_agent_trace_route_evidence.py',
 'scripts/tests/test_route_analyze.py']))
"""
command = [py,'-S','-c',bootstrap,str(repo)]
log = stage/'targeted.log'
with log.open('xb') as output:
    result = subprocess.run(command,cwd=repo,stdout=output,stderr=subprocess.STDOUT,timeout=120)
text = log.read_text()
match = re.search(r'(\d+) passed(?:, (\d+) skipped)? in',text)
report = {'schema':'ft_d07_candidate_cpu/v1','scope':'isolated committed candidate; CPU only; GPU gates pending',
    'candidate_commit':commit,'parent':manifest['parent'],'server_tree':str(repo),
    'git_blob_files':manifest['git_blob_files'],'bundle_sha256':expected_bundle,
    'compiled_extension_links':extensions,'command':command,'returncode':result.returncode,
    'passed':int(match[1]) if match else None,'skipped':int(match[2] or 0) if match else None,
    'source_import':str(repo/'python/freetoken/__init__.py'),'gpu_started':False,
    'log':str(log),'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
with (stage/'candidate.json').open('x') as output:
    output.write(json.dumps(report,indent=2)+'\n')
print(text[-12000:])
print(json.dumps(report))
raise SystemExit(result.returncode)
PY
