set -euo pipefail
CUDA_VISIBLE_DEVICES='' PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python - <<'PY'
import datetime,hashlib,json,os,pathlib,shutil,subprocess,sys,tarfile
stage=pathlib.Path('/data2/FreeToken/runs/dev_D03/t16_r018_closure_00c4301')
archive=stage/'source.tar'
if archive.is_symlink() or hashlib.sha256(archive.read_bytes()).hexdigest()!='8111bf1ec4420fabb8b3807668e8346a3e6bda1c20879455df06b5adc419bfb0':raise ValueError('source archive changed')
names=['t16_r018_prepare.py', 't16_r018_close.py', 'tests/test_t16_r018_close.py', 'source_manifest.json']
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
 argv=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_t16_r018_close.py']
 result=subprocess.run(argv,cwd=stage,env=env,stdout=sink,stderr=subprocess.STDOUT,timeout=120)
 steps.append({'argv':argv,'returncode':result.returncode})
 if result.returncode:raise RuntimeError('targeted Linux tests failed')
 source=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R018-gate-D03')
 if any((source/n).exists() for n in ('round.json','round_history','MANIFEST.sha256','initial_metadata.json','review_batch46.json')):raise FileExistsError('original round no longer raw')
 for p in [source,*source.rglob('*')]:
  if p.is_symlink() or p.stat().st_uid!=os.geteuid() or not(p.is_file() or p.is_dir()):raise ValueError('foreign or nonregular raw copy source')
 dest=stage/'d04_actual_raw_copy'/source.name
 dest.parent.mkdir()
 shutil.copytree(source,dest)
 shutil.copyfile(source.parent/'batch46.log',dest.parent/'batch46.log')
 review={'schema':'ft_independent_raw_review/v1','verdict':'PASS','rid':source.name,'batch':46,'batch_pid':3451139,
         'candidate_commit':'f5067bbe05da51d5f78185213435a8be095a684a','parent_commit':'c30ae0d7003c3bbbf56867ce74da797332fa7ed5',
         'runner_sha256':'29fa24ed89a3e35ddd0c426c67fa9c481f85d1700a5498a7c0abc8daab01e0c6',
         'base_runner_sha256':'51d8216e14417a6d922c44f3048082f985dfb59d8872dfc78ac0984f027fcd16',
         'wrapper_sha256':'d60333ffb4722d1d29e972129a08eb225cfc81ce0a257e2922379a90cd5746b1',
         'gate_sha256':'cfdd3a08f4af422178fdd72f058ea67783002fd0a506ca3388acaaae64b9b566',
         'candidate_binding_sha256':'a6f705dfc66c324c671bc2593f6a5583fb101e0e685299a3843e1ca4c02d4099',
         'reviewer':'/root/d06_server_review','scope':'raw measurement replay and source integrity; not formal acceptance',
         'replay_log_sha256':'d440d06f39e62359ce602639eaa8e2315bb5edd9600754c910a04fa3fc32bb00'}
 with (dest/'review_batch46.json').open('x') as stream:stream.write(json.dumps(review,indent=2)+'
')
 with (stage/'independent_raw_review.json').open('x') as stream:stream.write(json.dumps(review,indent=2)+'
')
 argv=[sys.executable,str(stage/'t16_r018_close.py'),'--close','--round-dir',str(dest),'--root','/data2/FreeToken']
 result=subprocess.run(argv,cwd=stage,env=env,stdout=sink,stderr=subprocess.STDOUT,timeout=120)
 steps.append({'argv':argv,'returncode':result.returncode})
report={'stage':str(stage),'archive_sha256':'8111bf1ec4420fabb8b3807668e8346a3e6bda1c20879455df06b5adc419bfb0','files':manifest,'steps':steps,
        'gpu_started':False,'original_round_mutated':False,'test_kind':'published D04 actual raw-copy closure',
        'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
if steps[-1]['returncode']==0:
 metadata=json.loads((dest/'round.json').read_text())
 report.update(copy_round_dir=str(dest),metadata=metadata,manifest_sha256=hashlib.sha256((dest/'MANIFEST.sha256').read_bytes()).hexdigest(),round_sha256=hashlib.sha256((dest/'round.json').read_bytes()).hexdigest())
with (stage/'cpu_validation.json').open('x') as stream:stream.write(json.dumps(report,indent=2)+'
')
print(json.dumps({k:v for k,v in report.items() if k!='metadata'}))
print(log.read_text()[-2500:])
if any(s['returncode'] for s in steps):raise SystemExit(1)
PY
