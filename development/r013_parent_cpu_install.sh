set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, os, pathlib, subprocess, tarfile
stage = pathlib.Path('/data2/FreeToken/runs/dev_D03/r013_parent_3bf5f99')
archive = stage / 'source.tar'
expected = 'f0777f15bfae9a0db534c80a059040f23b09242a259b459ade7aa02b6e09ad7d'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
if archive.is_symlink() or sha(archive) != expected:
    raise ValueError('parent provenance archive changed')
names = {'development/d03_phase2_prepare_r013_parent.py','development/initial_measurement_close_r013_parent.py',
         'development/tests/test_r013_parent_provenance.py','development/tests/test_d03_phase2_prepare.py',
         'development/d03_phase2_prepare.py','scripts/round_json_append.py','scripts/round_close.py','source_manifest.json'}
if any((stage / name).exists() for name in names):
    raise ValueError('parent provenance source already installed')
with tarfile.open(archive) as tar:
    members = tar.getmembers()
    if {m.name for m in members} != names or len(members) != len(names):
        raise ValueError('unexpected source archive members')
    if any(not m.isfile() or m.size > 1024*1024 for m in members):
        raise ValueError('source member must be a bounded regular file')
    for member in members:
        path = stage / member.name
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:
            stream.write(tar.extractfile(member).read())
        path.chmod(0o444)
manifest = json.loads((stage/'source_manifest.json').read_text())
if any(sha(stage/name) != digest for name,digest in manifest.items()):
    raise ValueError('installed source manifest differs')
env = os.environ.copy()
env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4')
steps = [
    ['/data2/FreeToken/venv/bin/python','-m','pytest','-q','-p','no:cacheprovider','development/tests/test_r013_parent_provenance.py'],
    ['/data2/FreeToken/venv/bin/python','development/initial_measurement_close_r013_parent.py','--self-test'],
]
results = []
log = stage/'cpu_validation.log'
with log.open('x') as output:
    for argv in steps:
        result = subprocess.run(argv,cwd=stage,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=120)
        results.append({'argv':argv,'returncode':result.returncode})
        if result.returncode:
            break
report = {'archive_sha256':expected,'files':manifest,'steps':results,'log_sha256':sha(log),'gpu_started':False}
with (stage/'cpu_validation.json').open('x') as output:
    output.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(report)); print(log.read_text())
for path in sorted(stage.rglob('*'),key=lambda p:len(p.parts),reverse=True):
    path.chmod(0o555 if path.is_dir() else 0o444)
stage.chmod(0o555)
if any(step['returncode'] for step in results):
    raise SystemExit(1)
PY
