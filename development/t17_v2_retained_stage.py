"""Freeze R034a completed-arm snapshots and exercise the retained CPU lifecycle."""
from __future__ import annotations
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent

PROGRAM = r'''
import base64,hashlib,json,os,pathlib,shutil,subprocess,sys,time
x=json.loads(sys.stdin.read()); stage=pathlib.Path(x['stage']); stage.mkdir(exist_ok=False)
source_tools=stage/'source_tools'; source_tools.mkdir()
original=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R034a')
snapshot=stage/'snapshot'; snapshot.mkdir()
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for raw in iter(lambda:f.read(1024*1024),b''):h.update(raw)
 return h.hexdigest()
def identity(path):
 s=path.stat(); return {'dev':s.st_dev,'inode':s.st_ino,'bytes':s.st_size,'mtime_ns':s.st_mtime_ns,'ctime_ns':s.st_ctime_ns}
def put(path,raw):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('xb') as f:f.write(raw)
gpu_lock=pathlib.Path('/data2/_shared/gpu.lock')
lock_before={'sha256':digest(gpu_lock),'identity':identity(gpu_lock)} if gpu_lock.exists() else None
report={'schema':'ft_t17_v2_retained_cpu/v1','fixture_only':True,'admitted':False,'runtime_lifecycle_verified':False,'gpu_started':False,'requests_sent':False,'steps':{},'snapshot_sources':{}}
try:
 for name,raw in x['files'].items():put(source_tools/name,base64.b64decode(raw))
 put(stage/'stage_source.py',base64.b64decode(x['source']))
 put(stage/'stage_program.py',base64.b64decode(x['program']))
 sys.path.insert(0,str(source_tools)); import t17_d14_runner as helper
 helper.freeze_startup_wrapper(source_tools)
 put(source_tools/'helpers/serve_args_diff.py',pathlib.Path('/data2/FreeToken/scripts/serve_args_diff.py').read_bytes())
 names=['real_inputs.json','cases/prefix-8192-tail-65.json']
 arm_names=['prefix_8192_tail_65_'+suffix for suffix in ('warm','reference_1','reference_2','cold_envelope')]
 for arm in arm_names:
  root=original/arm; assert root.is_dir() and not root.is_symlink()
  names += [p.relative_to(original).as_posix() for p in root.rglob('*') if p.is_file()]
  assert not any(p.is_symlink() for p in root.rglob('*'))
 required=sum((original/name).stat().st_size for name in names)
 assert shutil.disk_usage(stage).free>required+2*1024**3
 bindings={}
 for index,name in enumerate(names):
  src=original/name; dst=snapshot/name; assert not src.is_symlink()
  before=identity(src); sha_before=digest(src)
  dst.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(src,dst)
  assert sha_before==digest(dst)==digest(src) and before==identity(src),name
  bindings[name]={'sha256':sha_before,'source':str(src),'source_identity':before}
  dst.chmod(0o444)
  if index%500==0:print(json.dumps({'copy_files':index+1,'total_files':len(names)}),flush=True)
 for name,entry in bindings.items():assert identity(original/name)==entry['source_identity']
 fixture={'fixture_only':True,'admitted':False,'source_model_round':'E2-R034a','source_candidate':'e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7','snapshot_files':bindings}
 put(stage/'fixture_manifest.json',json.dumps(fixture,sort_keys=True).encode()); (stage/'fixture_manifest.json').chmod(0o444)
 for p in sorted(snapshot.rglob('*'),reverse=True):p.chmod(0o444 if p.is_file() else 0o555)
 snapshot.chmod(0o555)
 files={p.relative_to(source_tools).as_posix():digest(p) for p in source_tools.rglob('*') if p.is_file()}
 archive={'schema':'ft_v2_fixture_source_archive/v1','fixture_only':True,'admitted':False,'verdict':'NOT_EXECUTION_ADMISSION','runtime_lifecycle_verified':False,'files':files}
 put(source_tools/'cpu_validation.json',json.dumps(archive,sort_keys=True).encode())
 for p in sorted(source_tools.rglob('*'),reverse=True):p.chmod(0o444 if p.is_file() else 0o555)
 source_tools.chmod(0o555)
 tree=pathlib.Path('/data2/FreeToken/wt/e2d14-schedule')
 assert subprocess.check_output(['git','-C',str(tree),'rev-parse','HEAD'],text=True).strip()==fixture['source_candidate']
 assert not subprocess.check_output(['git','-C',str(tree),'status','--porcelain'],text=True).strip()
 env={k:v for k,v in os.environ.items() if k!='PYTHONPATH' and not k.startswith('FT_')}
 env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(source_tools)+':'+str(tree/'python'),OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
 python='/data2/FreeToken/venv/bin/python'
 for scenario in ('success','request_error','stop_error'):
  argv=[python,str(source_tools/'t17_v2_retained_replay.py'),'--stage',str(stage),'--scenario',scenario]
  completed=subprocess.run(argv,cwd=stage,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=600)
  log=stage/(scenario+'.log'); put(log,completed.stdout)
  report['steps'][scenario]={'argv':argv,'returncode':completed.returncode,'log_sha256':digest(log)}
  print(json.dumps({'scenario':scenario,'returncode':completed.returncode,'tail':completed.stdout.decode(errors='replace')[-2500:]}),flush=True)
  assert completed.returncode==0,scenario
 assert not list(stage.glob('*.cpu_fixture.lock'))
 lock_after={'sha256':digest(gpu_lock),'identity':identity(gpu_lock)} if gpu_lock.exists() else None
 assert lock_before==lock_after,'real GPU lock changed during CPU replay'
 report.update(verdict='PASS',cpu_lifecycle_contract_verified=True,source_candidate=fixture['source_candidate'],fixture_manifest_sha256=digest(stage/'fixture_manifest.json'),real_gpu_lock_unchanged=True,snapshot_files=len(names),snapshot_bytes=required)
except BaseException as error:report.update(verdict='FAIL',error=repr(error))
finally:
 report['files']={p.relative_to(stage).as_posix():digest(p) for p in stage.rglob('*') if p.is_file()}
 put(stage/'cpu_replay_report.json',(json.dumps(report,sort_keys=True)+'\n').encode())
 for p in sorted(stage.rglob('*'),reverse=True):
  assert not p.is_symlink();p.chmod(0o444 if p.is_file() else 0o555)
 stage.chmod(0o555)
 print(json.dumps({'stage':str(stage),'report_sha256':digest(stage/'cpu_replay_report.json'),'verdict':report.get('verdict'),'error':report.get('error')}),flush=True)
sys.exit(0 if report.get('verdict')=='PASS' else 1)
'''


def main():
    spec = importlib.util.spec_from_file_location('retained_v2_runtime_source', HERE/'t17_continuation_runtime_v2.py')
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    files = {name:(HERE/name).read_bytes() for name in runtime.REQUIRED_SOURCE_FILES}
    files['t17_v2_retained_replay.py'] = (HERE/'t17_v2_retained_replay.py').read_bytes()
    for path in (HERE/'e2d16-readers/scripts/equiv_suite').glob('*.py'):
        files['equiv_suite/'+path.name] = path.read_bytes()
    source = Path(__file__).read_bytes()
    key = hashlib.sha256(source+b''.join(n.encode()+files[n] for n in sorted(files))).hexdigest()[:12]
    payload = {'stage':'/data2/FreeToken/runs/dev_D16/v2_retained_cpu_'+key,
               'files':{n:base64.b64encode(raw).decode() for n,raw in files.items()},
               'source':base64.b64encode(source).decode(),'program':base64.b64encode(PROGRAM.encode()).decode()}
    wire = 'import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
    result = subprocess.run(['ssh','9','/data2/FreeToken/venv/bin/python','-'],input=wire,text=True,capture_output=True)
    with (HERE/('t17_v2_retained_cpu_'+key+'.json')).open('x',encoding='utf-8') as stream:
        json.dump({'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr},stream)
    print(result.stdout); print(result.stderr)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
