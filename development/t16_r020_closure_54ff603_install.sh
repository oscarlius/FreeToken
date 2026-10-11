set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import datetime,hashlib,json,os,pathlib,shutil,subprocess,sys,tarfile
stage=pathlib.Path('/data2/FreeToken/runs/dev_D06/t16_r020_closure_54ff603')
archive=stage.parent/'t16_r020_closure_54ff603.tar'
if stage.exists():raise FileExistsError('existing exact source stage retained')
stage.mkdir(mode=0o700)
if archive.is_symlink() or hashlib.sha256(archive.read_bytes()).hexdigest()!='ddb9ee73c7f44f2312b1516d6158de90805bb06e17e0f4c5670eda789a1ee6ac':raise ValueError('source archive changed')
names=['t16_r020_prepare.py', 't16_r020_close.py', 'tests/test_t16_r020_close.py', 't16_r020_raw_review.json', 'source_manifest.json']
if any((stage/name).exists() for name in names):raise FileExistsError('existing source retained')
with tarfile.open(archive) as tar:
 members=tar.getmembers()
 if len(members)!=len(names) or {m.name for m in members}!=set(names) or any(not m.isfile() or m.size>1024*1024 for m in members):raise ValueError('unexpected archive member')
 for member in members:
  path=stage/member.name;path.parent.mkdir(parents=True,exist_ok=True)
  with path.open('xb') as stream:stream.write(tar.extractfile(member).read())
  path.chmod(0o444)
manifest=json.loads((stage/'source_manifest.json').read_text())
if any(hashlib.sha256((stage/n).read_bytes()).hexdigest()!=h for n,h in manifest.items()):raise ValueError('source differs')
env={**os.environ,'CUDA_VISIBLE_DEVICES':'','PYTHONDONTWRITEBYTECODE':'1','OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4'}
log=stage/'cpu_validation.log'
steps=[]
with log.open('x') as sink:
 argv=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_t16_r020_close.py']
 result=subprocess.run(argv,cwd=stage,env=env,stdout=sink,stderr=subprocess.STDOUT,timeout=120)
 steps.append({'argv':argv,'returncode':result.returncode})
 if result.returncode:raise RuntimeError('targeted Linux tests failed')
 source=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R020-gate-D06')
 if any((source/n).exists() for n in ('round.json','round_history','MANIFEST.sha256','initial_metadata.json','review_batch48.json')):raise FileExistsError('original round no longer raw')
 for p in [source,*source.rglob('*')]:
  if p.is_symlink() or p.stat().st_uid!=os.geteuid() or not(p.is_file() or p.is_dir()):raise ValueError('foreign or nonregular raw copy source')
 dest=stage/'d04_actual_raw_copy'/source.name
 dest.parent.mkdir()
 shutil.copytree(source,dest)
 shutil.copyfile(source.parent/'batch48.log',dest.parent/'batch48.log')
 review_data=(stage/'t16_r020_raw_review.json').read_bytes()
 with (dest/'review_batch48.json').open('xb') as stream:stream.write(review_data)
 # Only this CPU fixture overrides the production-only canonical constant.
 # The exact installed production source and its CLI keep the canonical guard.
 import contextlib,importlib.util
 spec=importlib.util.spec_from_file_location('cpu_fixture_closer',stage/'t16_r020_close.py')
 closer=importlib.util.module_from_spec(spec);spec.loader.exec_module(closer)
 def fixture_exec(code,namespace):
  exec(code,namespace)
  namespace['CANONICAL_ROUND']=dest
 closer.exec=fixture_exec
 with contextlib.redirect_stdout(sink),contextlib.redirect_stderr(sink):
  result=closer.close(dest,'/data2/FreeToken')
  print(json.dumps(result))
 steps.append({'method':'CPU fixture close with explicit canonical constant override','returncode':0})
report={'stage':str(stage),'archive_sha256':'ddb9ee73c7f44f2312b1516d6158de90805bb06e17e0f4c5670eda789a1ee6ac','files':manifest,'steps':steps,
        'gpu_started':False,'original_round_mutated':False,'test_kind':'published D04 actual raw-copy closure','fixture_canonical_override':True,
        'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
if steps[-1]['returncode']==0:
 metadata=json.loads((dest/'round.json').read_text())
 report.update(copy_round_dir=str(dest),metadata=metadata,manifest_sha256=hashlib.sha256((dest/'MANIFEST.sha256').read_bytes()).hexdigest(),round_sha256=hashlib.sha256((dest/'round.json').read_bytes()).hexdigest())
with (stage/'cpu_validation.json').open('x') as stream:stream.write(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='metadata'}))
print(log.read_text()[-2500:])
for path in sorted(stage.rglob('*'),reverse=True):path.chmod(path.stat().st_mode & ~0o222)
stage.chmod(stage.stat().st_mode & ~0o222)
if any(s['returncode'] for s in steps):raise SystemExit(1)
PY
