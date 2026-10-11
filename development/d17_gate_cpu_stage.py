"""Freeze and run the focused D17 CPU suite on the Linux owner host.

This source/archive stage cannot authorize a GPU run. The retained adapter
lifecycle fixture and canonical accepted T17 remain separate prerequisites.
"""
from pathlib import Path
import base64, hashlib, importlib.util, json, subprocess
HERE=Path(__file__).resolve().parent
CANDIDATE='0aa23431e5b800797543bdecbf35a01045131d7d'
def main():
 spec=importlib.util.spec_from_file_location('d17_archive_runtime',HERE/'t17_continuation_runtime_v2.py')
 runtime=importlib.util.module_from_spec(spec);spec.loader.exec_module(runtime)
 names=set(runtime.REQUIRED_SOURCE_FILES)|{'d17_gate_case.py','d17_gpu_gate_runner.py','d17_gate_cpu_stage.py','d17_gate_cpu_replay.py','d17_frozen_helpers.py','d17_source_admission.py','t17_continuation_review.py','t17_continuation_close.py','tests/test_d17_gate_case.py','tests/test_d17_gpu_gate_runner.py','tests/test_d17_frozen_helpers.py','tests/test_d17_source_admission.py','cpu_guard/sitecustomize.py'}
 files={name:(HERE/('d16_cpu_sitecustomize.py' if name=='cpu_guard/sitecustomize.py' else name)).read_bytes() for name in names}
 files['batchNN_E2-R041_v3.sh']=(HERE.parent/'plan/01_测试与调研/batches/batchNN_E2-R041_v3.sh').read_bytes()
 old=(HERE.parent/'plan/02_开发任务/d18_artifacts/probe_ft_cold32k.py.pre_d18').read_bytes()
 assert hashlib.sha256(old).hexdigest()=='68e6c3f707fc97a6d04e4d9ac2bb582888af5b13b39584e863fe6be649cc306d'
 files['helper_versions/probe_ft_cold32k.py']=old
 for path in (HERE/'e2base1/scripts/equiv_suite').glob('*.py'):
  files['equiv_suite/'+path.name]=subprocess.check_output(['git','-C',str(HERE/'e2base1'),'show',CANDIDATE+':scripts/equiv_suite/'+path.name])
 key=hashlib.sha256(b''.join(n.encode()+files[n] for n in sorted(files))).hexdigest()[:12]
 payload={'stage':'/data2/FreeToken/runs/dev_D16/d17_gate_cpu_'+key,'files':{n:base64.b64encode(b).decode() for n,b in files.items()},'candidate':CANDIDATE}
 program=r'''import base64,hashlib,json,os,pathlib,subprocess,sys
sys.dont_write_bytecode=True
x=json.load(sys.stdin);stage=pathlib.Path(x['stage']);stage.mkdir(exist_ok=False);root=stage/'source_tools';root.mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
gpu_lock=pathlib.Path('/data2/_shared/gpu.lock')
def lock_identity():
 if not gpu_lock.exists():return None
 st=gpu_lock.stat();return {'sha256':sha(gpu_lock),'inode':st.st_ino,'dev':st.st_dev,'size':st.st_size,'mtime_ns':st.st_mtime_ns,'ctime_ns':st.st_ctime_ns}
lock_before=lock_identity()
try:
 for name,raw in x['files'].items():
  p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(base64.b64decode(raw))
 sys.path.insert(0,str(root));import t17_d14_runner
 # Generated exact-ID startup files are part of the executable package.
 t17_d14_runner.freeze_startup_wrapper(root)
 import t16_full_tail_base_runner as protocol
 import d17_frozen_helpers
 d17_frozen_helpers.freeze_helpers(root/'helpers',pathlib.Path('/data2/FreeToken/scripts'),protocol.TOOL_MD5,overrides={'probe_ft_cold32k.py':(root/'helper_versions/probe_ft_cold32k.py').read_bytes()})
 raw_inputs=pathlib.Path('/data2/FreeToken/runs/dev_D16/v2_retained_cpu_f0f3a1abd0fc/snapshot/real_inputs.json')
 assert sha(raw_inputs)=='90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0'
 (stage/'real_inputs.json').write_bytes(raw_inputs.read_bytes())
 wt=pathlib.Path('/data2/FreeToken/wt/e2base1-ordinary-rewind')
 head=subprocess.check_output(['git','-C',str(wt),'rev-parse','HEAD'],text=True).strip()
 assert head==x['candidate'] and not subprocess.check_output(['git','-C',str(wt),'status','--porcelain'],text=True).strip()
 control=pathlib.Path('/data2/FreeToken/wt/e2d14-ordinary-rewind')
 control_head=subprocess.check_output(['git','-C',str(control),'rev-parse','HEAD'],text=True).strip()
 assert control_head=='a9dca443cd07e1f60d1533e0a678935a09d21636' and not subprocess.check_output(['git','-C',str(control),'status','--porcelain','--untracked-files=no'],text=True).strip()
 for p in (root/'equiv_suite').glob('*.py'):
  blob=subprocess.check_output(['git','-C',str(wt),'show',head+':scripts/equiv_suite/'+p.name])
  assert hashlib.sha256(blob).hexdigest()==sha(p)
 env={k:v for k,v in os.environ.items() if k!='PYTHONPATH' and not k.startswith('FT_')}
 env.update(CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH=str(root/'cpu_guard')+':'+str(root)+':'+str(wt/'python'))
 argv=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider','tests/test_d17_gate_case.py','tests/test_d17_gpu_gate_runner.py','tests/test_d17_frozen_helpers.py','tests/test_d17_source_admission.py']
 r=subprocess.run(argv,cwd=root,env=env,capture_output=True,text=True);(root/'pytest.log').write_text(r.stdout+r.stderr)
 probe=[sys.executable,'-c',"import pathlib,torch,freetoken,d17_gpu_gate_runner,sitecustomize,socket; assert sitecustomize.FT_CPU_FIXTURE_NETWORK_GUARD is True; assert socket.socket.connect is sitecustomize.connect; assert socket.socket.connect_ex is sitecustomize.connect_ex; assert pathlib.Path(freetoken.__file__).resolve().is_relative_to(pathlib.Path('/data2/FreeToken/wt/e2base1-ordinary-rewind/python')); assert not torch.cuda.is_initialized(); print(freetoken.__file__)"]
 i=subprocess.run(probe,cwd=root,env=env,capture_output=True,text=True);(root/'import.log').write_text(i.stdout+i.stderr)
 steps={}
 for scenario in ('success','cold_not_met','warm_not_met','request_error','cold_stop_error','warm_stop_error'):
  command=[sys.executable,str(root/'d17_gate_cpu_replay.py'),'--stage',str(stage),'--scenario',scenario]
  replay=subprocess.run(command,cwd=stage,env=env,capture_output=True,text=True,timeout=300)
  logfile=stage/(scenario+'.log');logfile.write_text(replay.stdout+replay.stderr)
  steps[scenario]={'argv':command,'returncode':replay.returncode,'log_sha256':sha(logfile)}
  print(json.dumps({'scenario':scenario,'returncode':replay.returncode,'tail':(replay.stdout+replay.stderr)[-1500:]}),flush=True)
  if replay.returncode:raise RuntimeError('D17 CPU lifecycle fixture failed: '+scenario)
 assert lock_before==lock_identity() and not list(stage.glob('*.cpu_fixture.lock'))
 report={'schema':'ft_d17_gate_cpu_stage/v2','verdict':'PASS' if r.returncode==i.returncode==0 and __import__('re').search(r'\d+ passed',r.stdout) and not __import__('re').search(r'\d+ (failed|skipped|error)',r.stdout) else 'FAIL','candidate_commit':head,'candidate_worktree':str(wt),'control_commit':control_head,'control_worktree':str(control),'runtime_lifecycle_verified':False,'cpu_lifecycle_contract_verified':True,'fixture_only':True,'synthetic_endpoints':True,'synthetic_states':True,'steps':steps,'real_gpu_lock_unchanged':True,'admitted':False,'gpu_started':False,'requests_sent':False,'argv':argv,'pytest_returncode':r.returncode,'log_path':'pytest.log','log_sha256':sha(root/'pytest.log'),'import_argv':probe,'import_returncode':i.returncode,'import_log_sha256':sha(root/'import.log'),'files':{p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file()}}
 report['output_files']={p.relative_to(stage).as_posix():sha(p) for p in stage.rglob('*') if p.is_file() and not p.is_relative_to(root)}
 (root/'cpu_validation.json').write_text(json.dumps(report,sort_keys=True)+'\n')
 for p in sorted(stage.rglob('*'),reverse=True):p.chmod(0o444 if p.is_file() else 0o555)
 stage.chmod(0o555)
 structural_argv=[sys.executable,str(root/'d17_source_admission.py'),'--report',str(root/'cpu_validation.json')]
 structural=subprocess.run(structural_argv,cwd=stage,env=env,capture_output=True,text=True)
 print(json.dumps({'source_check_returncode':structural.returncode,'stdout':structural.stdout,'stderr':structural.stderr[-1500:]}),flush=True)
 if structural.returncode:raise RuntimeError('sealed source-package structural verification failed')
 print(json.dumps({'stage':str(stage),'report_sha256':sha(root/'cpu_validation.json'),'verdict':report['verdict'],'pytest_tail':r.stdout[-700:],'import_tail':i.stderr[-700:]}))
except Exception as error:
 failure={'verdict':'FAIL','error':repr(error),'runtime_lifecycle_verified':False,'admitted':False}
 if stage.stat().st_mode & 0o222:(stage/'failed_precondition.json').write_text(json.dumps(failure))
 for p in sorted(stage.rglob('*'),reverse=True):p.chmod(0o444 if p.is_file() else 0o555)
 stage.chmod(0o555)
 print(json.dumps({'stage':str(stage),**failure}));raise
sys.exit(0 if report['verdict']=='PASS' else 1)
'''
 wire='import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+program
 completed=subprocess.run(['ssh','-o','BatchMode=yes','9','/data2/FreeToken/venv/bin/python','-'],input=wire,text=True,capture_output=True)
 (HERE/('d17_gate_cpu_'+key+'.json')).write_text(json.dumps({'returncode':completed.returncode,'stdout':completed.stdout,'stderr':completed.stderr},indent=2))
 print(completed.stdout);print(completed.stderr);raise SystemExit(completed.returncode)
if __name__=='__main__':main()
