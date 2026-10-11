"""CPU source-package readiness for one owned D17 GPU test.

This verifier never starts a service or grants model acceptance. Actual T17,
queue, process ownership and post-run independent D04 review remain separate.
"""
import argparse, hashlib, importlib.util, json, re, subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
CANDIDATE='0aa23431e5b800797543bdecbf35a01045131d7d'
CONTROL='a9dca443cd07e1f60d1533e0a678935a09d21636'
CANDIDATE_WT=Path('/data2/FreeToken/wt/e2base1-ordinary-rewind')
CONTROL_WT=Path('/data2/FreeToken/wt/e2d14-ordinary-rewind')
SCENARIOS=('success','cold_not_met','warm_not_met','request_error','cold_stop_error','warm_stop_error')
TESTS=('tests/test_d17_gate_case.py','tests/test_d17_gpu_gate_runner.py','tests/test_d17_frozen_helpers.py','tests/test_d17_source_admission.py')
PY='/data2/FreeToken/venv/bin/python'
class AdmissionError(ValueError):pass

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def sealed_tree(root):
 if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o222:raise AdmissionError('sealed evidence directory required')
 if any(p.is_symlink() or p.stat().st_mode & 0o222 for p in root.rglob('*')):raise AdmissionError('evidence tree is not sealed')
def file(root,name):
 if not isinstance(name,str) or name.startswith(('/', '\\')) or Path(name).is_absolute() or '..' in Path(name).parts:raise AdmissionError('unsafe evidence path')
 p=root/name
 if any(x.is_symlink() for x in (p,*p.parents)) or not p.is_file() or p.stat().st_mode & 0o222 or not p.resolve().is_relative_to(root.resolve()):raise AdmissionError('sealed regular evidence path required')
 return p

def load(path):
 p=file(path.parent,path.name);value=json.loads(p.read_text())
 if not isinstance(value,dict):raise AdmissionError('evidence object required')
 return value

def verify_map(root,values):
 if not isinstance(values,dict) or not values:raise AdmissionError('nonempty evidence inventory required')
 for name,digest in values.items():
  if not isinstance(digest,str) or re.fullmatch('[0-9a-f]{64}',digest) is None or sha(file(root,name))!=digest:raise AdmissionError('evidence SHA differs: '+str(name))

def cpu_flags(report):
 expected={'runtime_lifecycle_verified':False,'admitted':False,'gpu_started':False,'requests_sent':False,'fixture_only':True,'synthetic_endpoints':True,'synthetic_states':True,'cpu_lifecycle_contract_verified':True,'real_gpu_lock_unchanged':True}
 if report.get('schema')!='ft_d17_gate_cpu_stage/v2' or report.get('verdict')!='PASS' or any(report.get(k) is not v for k,v in expected.items()):raise AdmissionError('CPU source contract cannot substitute model acceptance')

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

def git_tree(root,commit):
 if root.is_symlink():raise AdmissionError('regular worktree required')
 head=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
 dirty=subprocess.check_output(['git','-C',str(root),'status','--porcelain','--untracked-files=no'],text=True).strip()
 if head!=commit or dirty:raise AdmissionError('candidate/control worktree differs')

def check_cpu_package(report_path):
 report_path=Path(report_path)
 if report_path.resolve()!=HERE/'cpu_validation.json':raise AdmissionError('executor must use its own CPU package')
 root=HERE;stage=root.parent;sealed_tree(stage);report=load(report_path);cpu_flags(report)
 if report.get('candidate_commit')!=CANDIDATE or report.get('control_commit')!=CONTROL or report.get('candidate_worktree')!=str(CANDIDATE_WT) or report.get('control_worktree')!=str(CONTROL_WT):raise AdmissionError('CPU candidate/control binding differs')
 files=report.get('files');outputs=report.get('output_files');verify_map(root,files);verify_map(stage,outputs)
 actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
 if actual!=set(files)|{'cpu_validation.json'}:raise AdmissionError('CPU source map is not complete')
 actual_out={p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file() and not p.is_relative_to(root)}
 if actual_out!=set(outputs):raise AdmissionError('CPU output map is not complete')
 runtime=module('d17_admission_runtime',root/'t17_continuation_runtime_v2.py')
 required=set(runtime.REQUIRED_SOURCE_FILES)|set(runtime.GENERATED_SOURCE_FILES)|set(TESTS)|{'d17_gate_case.py','d17_gpu_gate_runner.py','d17_frozen_helpers.py','d17_gate_cpu_stage.py','d17_gate_cpu_replay.py','d17_source_admission.py','t17_continuation_review.py','t17_continuation_close.py','helper_versions/probe_ft_cold32k.py','cpu_guard/sitecustomize.py','batchNN_E2-R041_v3.sh'}
 required|={'helpers/'+prefix+name for prefix in ('','raw/') for name in ('cold_eq.py','probe_ft_cold32k.py','ft_probe_ckpt_tax.py','serve_args_diff.py')}
 if not required<=set(files):raise AdmissionError('CPU required source inventory incomplete')
 if sha(root/'helper_versions/probe_ft_cold32k.py')!='68e6c3f707fc97a6d04e4d9ac2bb582888af5b13b39584e863fe6be649cc306d':raise AdmissionError('original T16 helper version differs')
 expected_argv=[PY,'-m','pytest','-q','-p','no:cacheprovider',*TESTS]
 log=file(root,report.get('log_path'))
 if report.get('argv')!=expected_argv or report.get('pytest_returncode')!=0 or sha(log)!=report.get('log_sha256'):raise AdmissionError('CPU test invocation/log differs')
 text=log.read_text();counts=re.findall(r'(\d+) passed',text)
 if len(counts)!=1 or int(counts[0])<22 or re.search(r'\d+ (failed|skipped|error)',text):raise AdmissionError('complete CPU tests did not pass')
 expected_import=[PY,'-c',"import pathlib,torch,freetoken,d17_gpu_gate_runner,sitecustomize,socket; assert sitecustomize.FT_CPU_FIXTURE_NETWORK_GUARD is True; assert socket.socket.connect is sitecustomize.connect; assert socket.socket.connect_ex is sitecustomize.connect_ex; assert pathlib.Path(freetoken.__file__).resolve().is_relative_to(pathlib.Path('/data2/FreeToken/wt/e2base1-ordinary-rewind/python')); assert not torch.cuda.is_initialized(); print(freetoken.__file__)"]
 if report.get('import_argv')!=expected_import:raise AdmissionError('CPU import invocation differs')
 import_log=file(root,'import.log')
 if report.get('import_returncode')!=0 or sha(import_log)!=report.get('import_log_sha256') or import_log.read_text().strip()!=str(CANDIDATE_WT/'python/freetoken/__init__.py'):raise AdmissionError('actual candidate import differs')
 steps=report.get('steps')
 if not isinstance(steps,dict) or set(steps)!=set(SCENARIOS):raise AdmissionError('six lifecycle scenarios required')
 for name in SCENARIOS:
  row=steps[name];log=file(stage,name+'.log');receipt=load(file(stage,name+'_lifecycle.json'))
  if row.get('argv')!=[PY,str(root/'d17_gate_cpu_replay.py'),'--stage',str(stage),'--scenario',name] or row.get('returncode')!=0 or sha(log)!=row.get('log_sha256'):raise AdmissionError('lifecycle step/log differs: '+name)
  expected={'verdict':'PASS','fixture_only':True,'synthetic_endpoints':True,'synthetic_states':True,'admitted':False,'gpu_started':False,'model_generation':False,'scenario':name}
  if any(receipt.get(k)!=v for k,v in expected.items()):raise AdmissionError('CPU lifecycle receipt scope differs')
  identities=[x.get('identity',{}) for x in receipt.get('calls',[]) if x.get('kind')=='spawn']
  for identity in identities:
   pid,ticks=identity.get('pid'),identity.get('start_ticks')
   if type(pid) is not int or type(ticks) is not int or min(pid,ticks)<=0 or identity.get('execution_id')!=f'{pid}:{ticks}':raise AdmissionError('typed CPU child birth binding differs')
  births=[x['execution_id'] for x in identities]
  if not births or len(set(births))!=len(births) or name=='success' and len(births)!=10:raise AdmissionError('owned CPU child birth set differs')
 git_tree(CANDIDATE_WT,CANDIDATE);git_tree(CONTROL_WT,CONTROL)
 names=subprocess.check_output(['git','-C',str(CANDIDATE_WT),'ls-tree','-r','--name-only',CANDIDATE,'scripts/equiv_suite'],text=True).splitlines()
 expected_equiv={'equiv_suite/'+Path(n).name for n in names if n.endswith('.py')}
 if len(expected_equiv)!=14 or expected_equiv!={n for n in files if n.startswith('equiv_suite/') and n.endswith('.py')}:raise AdmissionError('candidate equiv source set differs')
 for n in names:
  if not n.endswith('.py'):continue
  blob=subprocess.check_output(['git','-C',str(CANDIDATE_WT),'show',CANDIDATE+':'+n])
  if hashlib.sha256(blob).hexdigest()!=files['equiv_suite/'+Path(n).name]:raise AdmissionError('candidate equiv Git blob differs')
 protocol=module('d17_admission_protocol',root/'t16_full_tail_base_runner.py')
 helpers=module('d17_admission_helpers',root/'d17_frozen_helpers.py');helpers.bind_protocol(protocol,root/'helpers')
 return {'schema':'ft_d17_cpu_source_check/v1','stage_report_sha256':sha(report_path),'candidate_commit':CANDIDATE,'control_commit':CONTROL,'source_execution_ready':False,'model_admitted':False}

def verify(report_path,review_path,expected_review_sha256=None):
 checked=check_cpu_package(report_path);review_path=Path(review_path)
 if review_path.resolve().is_relative_to(HERE.parent):raise AdmissionError('independent review must be external to the immutable CPU package')
 # The caller pins bytes from the actual independent workflow. Identity labels
 # describe provenance; they do not authenticate a reviewer by themselves.
 sealed_tree(review_path.parent)
 if not isinstance(expected_review_sha256,str) or re.fullmatch('[0-9a-f]{64}',expected_review_sha256) is None:
  raise AdmissionError('caller-pinned independent review SHA required')
 review_file=file(review_path.parent,review_path.name)
 raw=review_file.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=expected_review_sha256:
  raise AdmissionError('independent review SHA differs')
 review=json.loads(raw)
 if not isinstance(review,dict):raise AdmissionError('independent review object required')
 required={'schema':'ft_d17_gpu_test_source_admission/v1','scope':'owned-gpu-test-startup-only','verdict':'PASS','stage_report_sha256':checked['stage_report_sha256'],'candidate_commit':CANDIDATE,'control_commit':CONTROL,'runtime_lifecycle_verified':False,'model_admitted':False,'admitted':False,'gpu_started':False,'requests_sent':False}
 if any(review.get(k)!=v for k,v in required.items()) or not isinstance(review.get('reviewer_identity'),str) or review['reviewer_identity']!='/root/r_overlap_review':
  raise AdmissionError('independent CPU source-startup review binding differs')
 return {**checked,'source_execution_ready':True,'independent_review_sha256':expected_review_sha256,'scope':'owned-gpu-test-startup-only'}

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True);parser.add_argument('--review',type=Path);parser.add_argument('--review-sha256');args=parser.parse_args()
 result=verify(args.report,args.review,args.review_sha256) if args.review else check_cpu_package(args.report)
 print(json.dumps(result,sort_keys=True))
