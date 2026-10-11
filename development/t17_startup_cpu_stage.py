"""Freeze real T17 CPU controls and retained lifecycle before independent startup review."""
import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import base64,hashlib,json,os,pathlib,re,shutil,subprocess,sys
x=json.load(sys.stdin);stage=pathlib.Path(x['stage']);stage.mkdir(exist_ok=False)
root=stage/'source_tools';root.mkdir()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def put(p,b):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('xb') as f:f.write(b)
def seal(p):
 for q in sorted(p.rglob('*'),reverse=True):q.chmod(0o444 if q.is_file() else 0o555)
 p.chmod(0o555)
lock=pathlib.Path('/data2/_shared/gpu.lock')
def lock_identity():
 if not lock.exists():return None
 st=lock.stat();return [sha(lock),st.st_dev,st.st_ino,st.st_mtime_ns,st.st_ctime_ns]
before=lock_identity()
try:
 for name,raw in x['files'].items():put(root/name,base64.b64decode(raw))
 sys.path.insert(0,str(root));import t17_d14_runner as helper,t17_source_admission as admission,d17_frozen_helpers
 admission=admission.for_run(x['run_kind'])
 helper.freeze_startup_wrapper(root)
 if x['run_kind']=='t20':
  inputs=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R038/real_inputs.json').read_bytes()
  assert hashlib.sha256(inputs).hexdigest()=='90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0'
  put(root/'realinput_28.json',inputs)
 import t16_full_tail_base_runner as protocol
 d17_frozen_helpers.freeze_helpers(root/'helpers',pathlib.Path('/data2/FreeToken/scripts'),protocol.TOOL_MD5,
  overrides={'probe_ft_cold32k.py':(root/'helper_versions/probe_ft_cold32k.py').read_bytes()})
 admission._verify_snapshot(stage)
 env={k:v for k,v in os.environ.items() if k not in ('PYTHONPATH','PYTHONOPTIMIZE') and not k.startswith('FT_')}
 import_paths=[str(root),str(root/'scripts'),str(admission.WORKTREE/'python')]
 if x['run_kind']=='t20':import_paths.insert(0,str(root/'cpu_guard'))
 else:import_paths.insert(1,'/data2/FreeToken/runs/dev_D16/exact_startup_cpu_3cc07ea9a740/sources')
 env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=':'.join(import_paths),FT_D16_D03_TOOL=str(root/'d03_tools/logits_probe.py'))
 imported=subprocess.run(list(admission.IMPORT_ARGV),cwd=root,env=env,capture_output=True,text=True)
 put(root/'import.log',(imported.stdout+imported.stderr).encode())
 archive={'schema':'ft_v2_fixture_source_archive/v1','fixture_only':True,'admitted':False,'verdict':'NOT_EXECUTION_ADMISSION','runtime_lifecycle_verified':False,'files':{p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file()}}
 put(root/'cpu_validation.json',(json.dumps(archive,sort_keys=True)+'\n').encode());seal(root)
 argv=[admission.PY,'-m','pytest','-q','-p','no:cacheprovider',*admission.TEST_MODULES]
 tested=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True);put(stage/'pytest.log',(tested.stdout+tested.stderr).encode())
 print(json.dumps({'pytest_returncode':tested.returncode,'tail':(tested.stdout+tested.stderr)[-3500:]}),flush=True)
 assert tested.returncode==0 and imported.returncode==0
 steps={}
 for name in admission.SCENARIOS:
  command=[admission.PY,str(root/'t17_v2_retained_replay.py'),'--stage',str(stage),'--scenario',name]
  replay=subprocess.run(command,cwd=stage,env=env,capture_output=True,text=True,timeout=600)
  put(stage/(name+'.log'),(replay.stdout+replay.stderr).encode())
  steps[name]={'argv':command,'returncode':replay.returncode,'log_sha256':sha(stage/(name+'.log'))}
  print(json.dumps({'scenario':name,'returncode':replay.returncode,'tail':(replay.stdout+replay.stderr)[-1600:]}),flush=True)
  assert replay.returncode==0
 assert lock_identity()==before and not list(stage.glob('*.cpu_fixture.lock'))
 counts=re.findall(r'(\d+) passed',tested.stdout);assert len(counts)==1
 report={'schema':'ft_t17_gpu_source_cpu/v1','verdict':'PASS','candidate_commit':admission.CANDIDATE,'parent_commit':admission.PARENT,'candidate_worktree':str(admission.WORKTREE),'runtime_lifecycle_verified':False,'model_admitted':False,'admitted':False,'gpu_started':False,'requests_sent':False,'fixture_only':True,'real_gpu_lock_unchanged':True,'cpu_lifecycle_contract_verified':True,'argv':argv,'pytest_returncode':tested.returncode,'passed':int(counts[0]),'log_path':'pytest.log','log_sha256':sha(stage/'pytest.log'),'import_argv':list(admission.IMPORT_ARGV),'import_returncode':imported.returncode,'import_log_sha256':sha(root/'import.log'),'steps':steps,'files':{p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file()},'output_files':{p.relative_to(stage).as_posix():sha(p) for p in stage.rglob('*') if p.is_file() and not p.is_relative_to(root)}}
 report['schema']=admission.CPU_SCHEMA
 put(stage/'startup_cpu_report.json',(json.dumps(report,sort_keys=True)+'\n').encode());seal(stage)
 checked=subprocess.run([admission.PY,str(root/'t17_source_admission.py'),'--report',str(stage/'startup_cpu_report.json'),'--run-kind',x['run_kind']],cwd=stage,env=env,capture_output=True,text=True)
 print(json.dumps({'structural_returncode':checked.returncode,'stdout':checked.stdout,'stderr':checked.stderr[-3000:]}),flush=True)
 assert checked.returncode==0
 print(json.dumps({'stage':str(stage),'report_sha256':sha(stage/'startup_cpu_report.json'),'passed':report['passed'],'verdict':'PASS','model_admitted':False}),flush=True)
except BaseException as error:
 if stage.stat().st_mode&0o222:put(stage/'failed_stage.json',json.dumps({'verdict':'FAIL','error':repr(error),'model_admitted':False}).encode())
 seal(stage);raise
'''

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-kind',choices=('t17','t20'),default='t17')
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('startup_runtime',HERE/'t17_continuation_runtime_v2.py')
    runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
    files={name:(HERE/name).read_bytes() for name in runtime.REQUIRED_SOURCE_FILES}
    for name in ('t17_source_admission.py','d17_frozen_helpers.py','t17_v2_retained_replay.py','t17_continuation_launch_v3.py',
                 't20_r041_sample4_closure.py'):
        files[name]=(HERE/name).read_bytes()
    files['batchNN_T17_v3.sh']=(HERE.parent/'plan/01_测试与调研/batches/batchNN_T17_v3.sh').read_bytes()
    for p in (HERE/'e2d16-readers/scripts/equiv_suite').glob('*.py'):
        files['equiv_suite/'+p.name]=p.read_bytes();files['scripts/equiv_suite/'+p.name]=p.read_bytes()
    spec=importlib.util.spec_from_file_location('startup_admission',HERE/'t17_source_admission.py')
    admission=importlib.util.module_from_spec(spec);spec.loader.exec_module(admission)
    admission=admission.for_run(args.run_kind)
    if args.run_kind=='t20':
        files['cpu_guard/sitecustomize.py']=(HERE/'d16_cpu_sitecustomize.py').read_bytes()
        batches=HERE.parent/'plan/01_测试与调研/batches'
        for name in admission.T20_SOURCE_FILES:
            if name.startswith('equiv_suite/'):
                source=HERE/'e2d16-readers/scripts'/name
            else:
                source=next(path for path in (HERE/name,batches/name,HERE.parent/'scripts'/name) if path.is_file())
            files[name]=source.read_bytes()
    for name in admission.TEST_MODULES:
        source=(HERE/'e2d16-readers'/name if name.startswith('tests/scripts/') else
                HERE/name if (HERE/name).is_file() else HERE.parent/name)
        files[name]=source.read_bytes()
    files['tests/conftest.py']=(HERE/'e2d16-readers/tests/conftest.py').read_bytes()
    files['d03_tools/logits_probe.py']=(HERE/'e2d03/scripts/logits_probe.py').read_bytes()
    files['helper_versions/probe_ft_cold32k.py']=(HERE.parent/'plan/02_开发任务/d18_artifacts/probe_ft_cold32k.py.pre_d18').read_bytes()
    files['t17_continuation_inputs_cpu_fd6362813705.json']=(HERE/'t17_continuation_inputs_cpu_fd6362813705.json').read_bytes()
    files['stage_source.py']=Path(__file__).read_bytes();files['stage_program.py']=PROGRAM.encode()
    key=hashlib.sha256(b''.join(n.encode()+files[n] for n in sorted(files))).hexdigest()[:12]
    payload={'stage':'/data2/FreeToken/runs/dev_D16/'+args.run_kind+'_startup_cpu_'+key,'run_kind':args.run_kind,'files':{n:base64.b64encode(b).decode() for n,b in files.items()}}
    wire='import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
    completed=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-'],input=wire,text=True,capture_output=True)
    with (HERE/(args.run_kind+'_startup_cpu_'+key+'.json')).open('x',encoding='utf-8') as f:
        json.dump({'returncode':completed.returncode,'stdout':completed.stdout,'stderr':completed.stderr},f,indent=2)
    print(completed.stdout);print(completed.stderr);raise SystemExit(completed.returncode)

if __name__=='__main__':main()
