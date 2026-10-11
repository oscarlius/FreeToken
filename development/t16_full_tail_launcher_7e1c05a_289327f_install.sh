set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib, json, os, pathlib, subprocess, tarfile
stage = pathlib.Path('/data2/FreeToken/runs/dev_D06/t16_full_tail_launcher_7e1c05a_289327f')
archive = stage / 'source.tar'
expected = 'c28473cbaa408b760a158925af359a979f662bd51f673b71641cf3e121519266'
if archive.is_symlink() or hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
    raise ValueError('candidate gate archive changed')
names = {'t16_legacy_base_runner.py', 't16_candidate_launch_full_tail.py', 'tests/test_t16_full_tail.py', 'tests/test_t16_candidate_launch_full_tail.py', 't16_candidate_runner_full_tail.py', 't16_full_tail_README.md', 't16_full_tail_base_runner.py', 'source_manifest.json', 'tests/test_t16_candidate_runner_full_tail.py'}
if any((stage / name).exists() for name in names):
    raise ValueError('candidate CPU install already has source artifacts')
with tarfile.open(archive) as tar:
    members = tar.getmembers()
    if {m.name for m in members} != names or len(members) != len(names):
        raise ValueError('unexpected candidate gate archive members')
    if any(not m.isfile() or m.size > 1024*1024 for m in members):
        raise ValueError('candidate gate member not a bounded regular source file')
    for member in members:
        path = stage / member.name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(tar.extractfile(member).read())
        path.chmod(0o444)
manifest = json.loads((stage / 'source_manifest.json').read_text())
if any(hashlib.sha256((stage / name).read_bytes()).hexdigest() != digest for name,digest in manifest.items()):
    raise ValueError('installed gate source differs from source manifest')
env = os.environ.copy()
env.update(CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='4', MKL_NUM_THREADS='4')
steps = [
    ['/data2/FreeToken/venv/bin/python','-m','pytest','-q','-p','no:cacheprovider','tests/test_t16_full_tail.py','tests/test_t16_candidate_runner_full_tail.py','tests/test_t16_candidate_launch_full_tail.py'],
    ['/data2/FreeToken/venv/bin/python','t16_full_tail_base_runner.py','--self-test'],
    ['/data2/FreeToken/venv/bin/python','t16_candidate_runner_full_tail.py','--self-test'],
]
log = stage / 'cpu_validation.log'
results = []
with log.open('x') as output:
    for argv in steps:
        completed = subprocess.run(argv,cwd=stage,env=env,stdout=output,stderr=subprocess.STDOUT,timeout=120)
        results.append({'argv':argv,'returncode':completed.returncode})
        if completed.returncode:
            break
report = {'archive_sha256':expected,'stage':str(stage),'files':manifest,'steps':results,
          'gpu_started':False,'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
with (stage/'cpu_validation.json').open('x') as output:
    output.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
print(log.read_text())
if any(step['returncode'] for step in results):
    raise SystemExit(1)
PY
