set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 /data2/FreeToken/venv/bin/python - <<'PY'
import hashlib,json,os,pathlib,subprocess,sys,tarfile
BASE=pathlib.Path('/data2/FreeToken/runs/dev_D06')
TAG='d06_selfcheck_195aa332'
HASHES={'d06_gpu_selfcheck.py': '195aa332d220cf43955a50c25d68276e39ac66a67002e9be0d25497b8df38a10', 'tests/test_d06_gpu_selfcheck.py': '45ca072a54be15164d7d6e26d149c011b12e182cb10f7d2267f35f9ae67106b7', 'd06_gpu_selfcheck_README.md': '67f27cd03656cb67458cd37820fdaa03553ddc5957f9e3c39e048c6bd1c01a94'}
ARCHIVE_SHA='9f6fec6eaab74fed4c38de4799efe44ada0a4e20c9bc9d584193e68fbebdeccd'
STAGE=BASE/TAG
archive=BASE/(TAG+'.tar')
assert not STAGE.exists(),'existing exact source stage retained'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==ARCHIVE_SHA
STAGE.mkdir()
with tarfile.open(archive) as tar:
 members=tar.getmembers()
 assert {m.name for m in members}==set(HASHES)
 for member in members:
  assert member.isfile() and member.size<=2*1024*1024
  target=STAGE/member.name
  target.parent.mkdir(parents=True,exist_ok=True)
  with target.open('xb') as stream:stream.write(tar.extractfile(member).read())
for name,digest in HASHES.items():assert hashlib.sha256((STAGE/name).read_bytes()).hexdigest()==digest
steps=[]
with (STAGE/'cpu_validation.log').open('xb') as log:
 for argv in [[sys.executable,'-m','pytest','-q','tests/test_d06_gpu_selfcheck.py'],[sys.executable,'d06_gpu_selfcheck.py','--self-test']]:
  result=subprocess.run(argv,cwd=STAGE,stdout=log,stderr=subprocess.STDOUT,env=os.environ.copy(),timeout=60)
  steps.append({'argv':argv,'returncode':result.returncode})
report={'source_stage':str(STAGE),'archive_sha256':ARCHIVE_SHA,'files':HASHES,'steps':steps,'gpu_started':False,'log_sha256':hashlib.sha256((STAGE/'cpu_validation.log').read_bytes()).hexdigest()}
with (STAGE/'cpu_validation.json').open('x') as stream:json.dump(report,stream,indent=2);stream.write('\n')
print((STAGE/'cpu_validation.log').read_text())
print(json.dumps(report))
if any(s['returncode'] for s in steps):raise SystemExit(1)
for path in sorted(STAGE.rglob('*'),reverse=True):path.chmod(path.stat().st_mode & ~0o222)
STAGE.chmod(STAGE.stat().st_mode & ~0o222)
PY
