"""E2-R049 ordinary-SSE T21 runner; owned lifecycle and no pause ACK path."""
from __future__ import annotations
import argparse, ast, hashlib, importlib.util, json, math, os, runpy, socket, subprocess, sys, time, urllib.request
from pathlib import Path

RID='E2-R049b'; CANDIDATE='988c9e183c8dca4415fd9b5d02318b26664da619'; PARENT='effb9969706922ddad9e59b96377e46469ebe97f'
T06_RID='E2-R046g'; T06_MANIFEST_SCHEMA='ft_r046c_route_manifest/v1'
T06_CANDIDATE='4fc2320dc0a29422ab61e383e5e1579460e9926e'
R046G_ROUND_SHA='3f50a0ffb69e24e65eb10df1b925ed9bbf75c74e51ddd385f05369947134f54d'
R046G_MANIFEST_SHA='282f1a046a33d46345c9b3f72630a2f0971c3d4f92839c2e0d6f100e6232c9f1'
R049_FAILED_RID='E2-R049'; R049_FAILED_ROUND_SHA='3d32cac2536c17d83434a161bb97f11d431b7bc3e9079eb274506efd6c2d8615'; R049_FAILED_MANIFEST_SHA='57e0db63448dc52531a54477cd76d8326010431421dac273fb9810aab66dc862'; R049_FAILED_PIN_SHA='be8d8294d20f132e49064f9a0a2cc5e7fb4079cfe66610ab520fed7c6d27e360'; R049_FAILED_D04_RECEIPT=Path('/data2/FreeToken/runs/dev_T21/r049_d04_failed_closure_receipt_v1.json'); R049_FAILED_D04_SHA='0a4fbde5740ab3924b7a996d402ea68ca2cce8cdd3e1db828979dc5a10591663'; R049_FAILED_REVIEW_SHA='a53aa10090e0b18bac9f559371feb4adfa2822fd276554b2f125ab2a9961a018';
R049A_FAILED_RID='E2-R049a'; R049A_FAILED_ROUND_SHA='6b0fd937bb2095d734b8d74b66ffb01d508933052ea40af221a95238e4f87337'; R049A_FAILED_MANIFEST_SHA='34e1f6b58139fda67504b9a35921fd50592af79e24691314c2644aaecdaa2191'; R049A_FAILED_PIN_SHA='d8ac8d5c9815672c1a53f4ab90442f75f2e1519e27cc61a493e16ae1e4b89399'; R049A_FAILED_D04_RECEIPT=Path('/data2/FreeToken/runs/dev_T21/r049a_d04_failed_closure_receipt_v1.json'); R049A_FAILED_D04_SHA='dae049b141af5b22ac3987a0e265828cda1d121f114e504cfbbec9dbd5113af4'; R049A_FAILED_REVIEW_REL=Path('metadata/independent_failed_review.json'); R049A_FAILED_REVIEW_SHA='e8759ebd95d6a444b37c553271e01a2029fe84c1881be3d9f99710da48a81e1a'
R050_RID='E2-R050-gate-D15'; R050_ROUND_SHA='f707de8963172619ad932ff25b931d29e139eaedcdc88f4eff105b36a420dc4d'; R050_MANIFEST_SHA='ae2e0e0e48f15a2b869fa15b90959513a4c74574bafae01b53a0d41774a01110'
PREPARE_SCHEMA='ft_t21_r049_prepare/v5'; DRY_RUN_SCHEMA='ft_r049_dry_run/v5'; REVIEW_SCHEMA='ft_t21_startup_review/v5'
ROOT=Path('/data2/FreeToken'); ROUNDS=Path('/data2/_shared/runs/ft_rounds'); WT=ROOT/'wt/e2d15'; VENV=ROOT/'venv'; HERE=Path(__file__).resolve().parent
PROFILE_TOOL=WT/'tools/build_expert_profile.py'; FRONTEND_RENDER=WT/'python/freetoken/tokenizer/tokenize.py'; CANDIDATE_API_MODELS=WT/'python/freetoken/server/api_models.py'; CANDIDATE_OPENAI_API=WT/'python/freetoken/server/openai_api.py'; CANDIDATE_MODEL_META=WT/'python/freetoken/server/model_meta.py'; CANDIDATE_CORE=WT/'python/freetoken/core.py'; CANDIDATE_SCHEDULER=WT/'python/freetoken/scheduler/scheduler.py'; CANDIDATE_MESSAGE=WT/'python/freetoken/message/__init__.py'; TRAIN_ROUTE=ROUNDS/'E2-R046g/G_seed12k/route'
HELDOUT={'seed_45k':ROUNDS/'E2-R046g/G_seed_45k/trace_seed_45k.json','seed_real':ROUNDS/'E2-R046g/G_seed_real/trace_seed_real.json'}
SEEDS={'seed12k':(Path('/data2/FreeToken/wt/e1r003/seed12k.txt'),'1bcb7214c78f16258c8689e8f57f2d72f0930f9924c58ae1a18763e18c364153'),'seed_45k':(Path('/data2/FreeToken/wt/e1r003/seed_45k.txt'),'499c39e4e601d8c61e8305265569c5055083eb14e5da9940b10c656f5e9c97e9'),'seed_real':(Path('/data2/FreeToken/wt/e1r003/seed_real.txt'),'8fe6b36da6c19eabb4a259535a9835f20e41921d4d7023ec7aaa0063c8b50bf3')}
MODEL_PATH=ROOT/'models/Qwen3.8-Flash-Next-NVFP4-overlay'
# This bound qwen4_exp model has text_config.num_experts=512.
MODEL_NUM_EXPERTS=512
WINDOW=98304
D0_HELPER=HERE/'r049_d0_startup.py'
D0_CACHE=WT/'python/freetoken/moe/offload_cache.py'
D0_STARTUP=WT/'scripts/equiv_suite/service_capture_startup.py'
AGENT_TRACE_RAW=WT/'scripts/_agent_trace_original.py'; TWO_DECODE_PROBE=HERE/'r049_t21_ordinary_adapter_v9.py'
ORDINARY_CLIENT=HERE/'r049_t21_ordinary_client_v9.py'; ORDINARY_STARTUP=HERE/'r046c_t06_ordinary_startup_v4.py'
ORDINARY_D0_STARTUP=HERE/'r049_t21_ordinary_d0_startup_v3.py'
FRONTEND_DRIVER=HERE/'r046c_ordinary_seed_driver_v3.py'
D07_LEAF=HERE/'d07_g3g4_prepare.py'; ARGS_PARSER=HERE/'d04_original/serve_args_diff.py'
class T21NotMet(RuntimeError): pass
POLICIES={'L':'lru','P':'profile','PA':'profile+adapt'}; PROCESS_ORDER=('P1','PA1','L2','P2','PA2','L_D0','P_D0','PA_D0')

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write_new(path, value):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8') as f: json.dump(value,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n')
ENV_RECORD_KEYS=('CUDA_VISIBLE_DEVICES','PYTHONPATH','VIRTUAL_ENV','PYTHONDONTWRITEBYTECODE','PYTHONUNBUFFERED','FT_DEV_EXPERT_POLICY','FT_DEV_EXPERT_PROFILE','FT_DEV_EXPERT_ADAPT_EVERY','FT_DEV_EXPERT_ADAPT_SWAPS','FT_DEV_D0','FT_DEV_D0_PATH','FT_T21_DIAG_JOURNAL')
def file_probe(path,purpose):
 path.parent.mkdir(parents=True,exist_ok=True);write_new(path,{'schema':'ft_r049_cpu_file_probe/v1','kind':'CPU_FILE_PROBE','not_measurement':True,'purpose':purpose});return sha(path)
def service_files(d,directory,port,policy,profile,d0,*,file_dry_run=False):
 env=env_for(d,policy,profile,d0);base_argv=d.serve_argv(port);journal=directory/'d0_journal.jsonl'
 if any(flag in base_argv for flag in ('--route-trace','--enable-route-trace')): raise RuntimeError('T21 §13 must not enable route trace')
 if d0:
  if journal.exists() or journal.is_symlink(): raise RuntimeError('T21 D0 journal path is not fresh')
  env['FT_T21_DIAG_JOURNAL']=str(journal);env['FT_DEV_D0_PATH']=str(directory/'d0_native');argv=[str(VENV/'bin/python'),str(ORDINARY_D0_STARTUP),'--observer-dir',str(directory/'ordinary_observer'),'--',*base_argv]
 else:
  if 'FT_T21_DIAG_JOURNAL' in env or 'FT_DEV_D0' in env: raise RuntimeError('T21 production must not load D0 hook')
  observer=directory/'ordinary_observer'
  argv=[str(VENV/'bin/python'),str(ORDINARY_STARTUP),'--observer-dir',str(observer),'--',*base_argv[1:]]
 directory.mkdir(parents=True,exist_ok=True)
 recorded={key:env[key] for key in ENV_RECORD_KEYS if key in env}
 (directory/'ENV.json').write_text(json.dumps(recorded,sort_keys=True)+'\n',encoding='utf-8');(directory/'ENV.txt').write_text(''.join(f'{k}={recorded[k]}\n' for k in sorted(recorded)),encoding='utf-8')
 (directory/'SERVE_CMD.txt').write_text(json.dumps({'argv':argv,'policy':policy,'d0':d0,'journal':str(journal) if d0 else None,'ordinary_observer':str(directory/'ordinary_observer') if not d0 else None}),encoding='utf-8')
 write_new(directory/'serve_args_diff.json',arm_difference_declaration(policy,d0))
 (directory/'serve.log').open('x',encoding='utf-8').close()
 if file_dry_run:
  # Service-owned paths are prepared here.  Client writers own their output
  # paths below, so the dry path exercises the same exclusive-create boundary.
  for name in ('owned_process.json','health.json','serve_args.txt','serve_args_actual.json','serve_args_actual_diff.json') : file_probe(directory/name,'formal T21 service output')
  if d0:file_probe(journal,'formal D0 journal')
 return env,argv,journal
def load_d07():
 p=HERE/'d07_g3g4_prepare.py';spec=importlib.util.spec_from_file_location('r049_d07',p);m=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(m)
 original=m.serve_argv
 def argv(port):
  result=list(original(port))
  for flag,value in (('--memory-ratio','0.88'),('--kv-reserve-tokens',str(WINDOW)),('--max-seq-len-override',str(WINDOW))):result[result.index(flag)+1]=value
  return result
 m.serve_argv=argv;return m
def arms():
 return [{'name':name,'policy':POLICIES[name.removesuffix('_D0').rstrip('12')],'d0':name.endswith('_D0'),'production':not name.endswith('_D0'),'workloads':['cold32k_1','cold32k_2','seed_45k','seed_real','two_decode_diff512']} for name in PROCESS_ORDER]
def assert_plan(rows):
 if [x['name'] for x in rows]!=list(PROCESS_ORDER): raise RuntimeError('T21 retained-L1 process order differs')
 if [x['policy'] for x in rows[:5]]!=['profile','profile+adapt','lru','profile','profile+adapt']: raise RuntimeError('T21 retained-L1 production policy order differs')
 if any(x['d0'] for x in rows[:5]) or any(not x['d0'] for x in rows[5:]): raise RuntimeError('T21 retained-L1 D0 split differs')
 if any(x['workloads']!=rows[0]['workloads'] for x in rows): raise RuntimeError('T21 workload shape differs')
 return rows
def require_section13_runtime_tooling():
    adapter = _ordinary_adapter()
    if any(not callable(getattr(adapter, name, None)) for name in ('run_pair', 'ordinary_stream_request', 'ordinary_binding', 'timing_from_sse')):
        raise RuntimeError('T21 ordinary runtime entrypoints are unavailable')
    for path in (ORDINARY_CLIENT, ORDINARY_STARTUP, ORDINARY_D0_STARTUP):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('T21 ordinary runtime source unavailable')
def arm_difference_declaration(policy,d0):
 """Declare every variable allowed to differ from the L reference in its stratum."""
 if policy not in POLICIES.values(): raise RuntimeError('T21 unknown policy declaration')
 variables={'FT_DEV_EXPERT_POLICY':policy}
 if policy!='lru': variables['FT_DEV_EXPERT_PROFILE']='seed12k_only.strp'
 if policy=='profile+adapt': variables.update(FT_DEV_EXPERT_ADAPT_EVERY='1',FT_DEV_EXPERT_ADAPT_SWAPS='1')
 if d0: variables['FT_DEV_D0']='1'
 return {'schema':'ft_t21_serve_args_diff/v1','comparison_stratum':'diagnostic_d0' if d0 else 'production','reference_arm':'L_D0' if d0 else 'L1','allowed_difference_keys':sorted(variables),'target_values':variables,'common_contract':{'memory_ratio':'0.88','kv_reserve_tokens':WINDOW,'max_seq_len_override':WINDOW,'route_trace_enabled':False,'pause_endpoint_enabled':False},'single_variable_rule':'within a stratum, policy is the only scientific variable; profile and adaptation fields are required consequences of that policy'}
def source_hashes():
    paths = (Path(__file__), PROFILE_TOOL, FRONTEND_RENDER, D07_LEAF, D0_HELPER,
             D0_CACHE, D0_STARTUP, AGENT_TRACE_RAW, WT/'scripts/multisession_probe.py',
             CANDIDATE_API_MODELS, CANDIDATE_OPENAI_API, CANDIDATE_MODEL_META, CANDIDATE_CORE, CANDIDATE_SCHEDULER, CANDIDATE_MESSAGE,
             WT/'python/freetoken/moe/expert_profile.py', TWO_DECODE_PROBE, FRONTEND_DRIVER,
             ORDINARY_CLIENT, ORDINARY_STARTUP, ORDINARY_D0_STARTUP,
             HERE/'r046e_t06_ordinary_client_v6.py', HERE/'r046c_route_analyze_ordinary_v2.py', HERE/'r046c_t06_ordinary_client_v2.py',
             HERE/'r046c_t06_ordinary_startup_v4.py',
             HERE/'r058_concurrent_request.py', HERE/'ft_batch_port_pair_v1.py', ARGS_PARSER)
    d = load_d07()
    fixed = (d.OWNED_SOURCE/'t17_owned_launch_protocol.py',
             ROOT/'runs/plan_batches/e2_launch.py',
             d.OWNED_SOURCE/'helpers/raw/probe_ft_cold32k.py')
    all_paths=(*paths,*fixed)
    if any(path.is_symlink() or not path.is_file() for path in all_paths):raise RuntimeError('T21 source closure has missing or linked member')
    return {str(path): sha(path) for path in all_paths}

def require_candidate():
 if WT.is_symlink():raise RuntimeError('T21 candidate worktree is linked')
 head=subprocess.check_output(['git','-C',str(WT),'rev-parse','HEAD'],text=True).strip()
 dirty=subprocess.check_output(['git','-C',str(WT),'status','--porcelain','--untracked-files=no'],text=True)
 if head!=CANDIDATE or dirty:raise RuntimeError('D15 candidate differs or is dirty')
 return {'path':str(WT),'commit':head}

def require_seed(role):
 path,digest=SEEDS[role]
 if path.is_symlink() or not path.is_file() or sha(path)!=digest: raise RuntimeError('T21 raw seed source binding differs')
 return path,digest

def ordinary_record_binding(record):
    binding = record.get('actual_input_binding') if isinstance(record, dict) else None
    return _ordinary_adapter().ordinary_binding(binding)
def require_review(dry_receipt=None):
 p=ROOT/'runs/dev_T21'/f'{RID}_startup_review_v11.json'
 if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222: raise RuntimeError('T21 startup review absent or writable')
 d=json.loads(p.read_text()); want={'schema':REVIEW_SCHEMA,'rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'approved':True,'verdict':'PASS','source_sha256':source_hashes()}
 if any(d.get(k)!=v for k,v in want.items()): raise RuntimeError('T21 startup review binding differs')
 if dry_receipt is not None and (d.get('dry_run_receipt')!=dry_receipt['path'] or d.get('dry_run_receipt_sha256')!=dry_receipt['sha256']):raise RuntimeError('T21 review binds a different dry-run receipt')
 return p
def require_r046g_closure():
 """Read only the sealed R046g closure metadata, pin, and D04 history."""
 directory=ROUNDS/T06_RID; pin=ROOT/'runs/plan_batches/closed_round_pins'/f'{T06_RID}.json'
 round_json=directory/'round.json'; manifest_sha=directory/'MANIFEST.sha256'; checker=directory/'round_json_append.py'
 for path in (directory,pin,round_json,manifest_sha,checker):
  if path.is_symlink() or not path.exists() or path.stat().st_mode&0o222:raise RuntimeError('R046g sealed closure is missing, linked, or writable')
 if not directory.is_dir() or any(not path.is_file() for path in (pin,round_json,manifest_sha,checker)):raise RuntimeError('R046g sealed closure types differ')
 if sha(round_json)!=R046G_ROUND_SHA or sha(manifest_sha)!=R046G_MANIFEST_SHA:raise RuntimeError('R046g round or MANIFEST SHA differs')
 try: pin_doc=json.loads(pin.read_text());round_doc=json.loads(round_json.read_text())
 except (OSError,json.JSONDecodeError) as error:raise RuntimeError('R046g sealed closure metadata unreadable') from error
 if (pin_doc.get('rid')!=T06_RID or pin_doc.get('verdict')!='measured' or pin_doc.get('round_sha256')!=R046G_ROUND_SHA or pin_doc.get('manifest_sha256')!=R046G_MANIFEST_SHA or round_doc.get('round_id')!=T06_RID or round_doc.get('verdict')!='measured'):
  raise RuntimeError('R046g sealed closure identity differs')
 checked=subprocess.run([str(VENV/'bin/python'),str(checker),str(directory),'check'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if checked.returncode:raise RuntimeError('R046g D04 history check failed')
 return {'round':str(round_json),'manifest':str(manifest_sha),'pin':str(pin),'round_sha256':R046G_ROUND_SHA,'manifest_sha256':R046G_MANIFEST_SHA}

def require_r049_failure_closure():
 directory=ROUNDS/R049_FAILED_RID;pin=ROOT/'runs/plan_batches/closed_round_pins'/f'{R049_FAILED_RID}.json';round_json=directory/'round.json';manifest=directory/'MANIFEST.sha256';checker=directory/'round_json_append.py';receipt=R049_FAILED_D04_RECEIPT
 for path in (directory,pin,round_json,manifest,checker,receipt):
  if path.is_symlink() or not path.exists() or path.stat().st_mode&0o222:raise RuntimeError('R049 failed closure is missing, linked, or writable')
 if any(not path.is_file() for path in (pin,round_json,manifest,checker,receipt)):raise RuntimeError('R049 failed closure types differ')
 if sha(round_json)!=R049_FAILED_ROUND_SHA or sha(manifest)!=R049_FAILED_MANIFEST_SHA or sha(pin)!=R049_FAILED_PIN_SHA or sha(receipt)!=R049_FAILED_D04_SHA:raise RuntimeError('R049 failed closure SHA differs')
 try: pd=json.loads(pin.read_text());rd=json.loads(round_json.read_text());dd=json.loads(receipt.read_text())
 except (OSError,json.JSONDecodeError) as error:raise RuntimeError('R049 failed closure unreadable') from error
 if (pd.get('rid')!=R049_FAILED_RID or pd.get('verdict')!='failed_harness'
     or rd.get('round_id')!=R049_FAILED_RID or rd.get('verdict')!='failed_harness'
     or dd.get('rid')!=R049_FAILED_RID or dd.get('verdict')!='failed_harness'
     or dd.get('round_sha256')!=R049_FAILED_ROUND_SHA or dd.get('manifest_sha256')!=R049_FAILED_MANIFEST_SHA
     or dd.get('pin_sha256')!=R049_FAILED_PIN_SHA or dd.get('candidate_commit')!=CANDIDATE
     or dd.get('readonly') is not True or dd.get('d04_check',{}).get('ok') is not True
     or dd.get('independent_review_sha256')!=R049_FAILED_REVIEW_SHA
     or dd.get('accepted_full_groups')!=0 or dd.get('partial_unaccepted_workloads')!=4
     or dd.get('expected_tokens_per_stream')!=512 or dd.get('observed_tokens_per_stream')!=[20,20]
     or dd.get('measurement_retry_authorized') is not False):
  raise RuntimeError('R049 failed closure identity/reuse policy differs')
 if subprocess.run([str(VENV/'bin/python'),str(checker),str(directory),'check'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:raise RuntimeError('R049 failed D04 history check failed')
 return {'round':str(round_json),'manifest':str(manifest),'pin':str(pin),'d04_receipt':str(receipt),
         'independent_review_sha256':R049_FAILED_REVIEW_SHA,'accepted_full_groups':0,
         'partial_unaccepted_workloads':4,'measurement_retry_authorized':False,
         'performance_reuse_forbidden':True}


RETAINED_L1_REVIEW=ROOT/'runs/dev_T21/reviews/E2-R049a_L1_recompute_v1/review.json'; RETAINED_L1_REVIEW_SHA='736e8cb50fe93dba781e371ca5d937eb55fa212cd83c2281b522654044d32b06'
def require_retained_l1_review():
 p=RETAINED_L1_REVIEW
 if p.is_symlink() or not p.is_file() or p.stat().st_mode&0o222 or p.parent.stat().st_mode&0o222 or sha(p)!=RETAINED_L1_REVIEW_SHA: raise RuntimeError('T21 retained L1 recompute review differs')
 d=json.loads(p.read_text()); expected={'schema':'ft_r049a_l1_recompute_review/v1','candidate_commit':CANDIDATE,'verdict':'PASS_L1_RETAINABLE_RAW_ONLY'}
 if any(d.get(k)!=v for k,v in expected.items()) or d.get('completeness',{}).get('complete') is not True or d.get('completeness',{}).get('expected_requests')!=24 or d.get('completeness',{}).get('observed_requests')!=24 or d.get('completeness',{}).get('uid_coverage')!='0..23 exact' or d.get('not_accepted',{}).get('other_eight_services') is not True: raise RuntimeError('T21 retained L1 recompute conclusion differs')
 return {'path':str(p),'sha256':RETAINED_L1_REVIEW_SHA,'requests':24,'complete_L1_retained':True,'remaining_services':list(PROCESS_ORDER)}

def require_r049a_failure_closure():
 """Bind b102's sealed D04 failure and independent retention review; no partial L1 reuse."""
 directory=ROUNDS/R049A_FAILED_RID;pin=ROOT/'runs/plan_batches/closed_round_pins'/f'{R049A_FAILED_RID}.json';round_json=directory/'round.json';manifest=directory/'MANIFEST.sha256';receipt=R049A_FAILED_D04_RECEIPT;review=directory/R049A_FAILED_REVIEW_REL;history=directory/'round_history';sums=history/'SHA256SUMS';prior=history/'round.v001.json';closed=history/'round.v002.json'
 for path in (directory,pin,round_json,manifest,receipt,review,history,sums,prior,closed):
  if path.is_symlink() or not path.exists() or path.stat().st_mode&0o222:raise RuntimeError('R049a failed closure is missing, linked, or writable')
 if not directory.is_dir() or not history.is_dir() or any(not path.is_file() for path in (pin,round_json,manifest,receipt,review,sums,prior,closed)):raise RuntimeError('R049a failed closure types differ')
 if sha(round_json)!=R049A_FAILED_ROUND_SHA or sha(manifest)!=R049A_FAILED_MANIFEST_SHA or sha(pin)!=R049A_FAILED_PIN_SHA or sha(receipt)!=R049A_FAILED_D04_SHA or sha(review)!=R049A_FAILED_REVIEW_SHA:raise RuntimeError('R049a failed closure SHA differs')
 try: pd=json.loads(pin.read_text());rd=json.loads(round_json.read_text());dd=json.loads(receipt.read_text());rv=json.loads(review.read_text());before=json.loads(prior.read_text());after=json.loads(closed.read_text())
 except (OSError,json.JSONDecodeError) as error:raise RuntimeError('R049a failed closure unreadable') from error
 partial=['L1/cold32k_1','L1/cold32k_2','L1/seed_45k_replay','L1/seed_real_replay']
 if (pd.get('rid')!=R049A_FAILED_RID or pd.get('verdict')!='failed_harness' or pd.get('closure_receipt_sha256')!=R049A_FAILED_D04_SHA
     or rd.get('round_id')!=R049A_FAILED_RID or rd.get('verdict')!='failed_harness' or rd.get('base',{}).get('commit')!=CANDIDATE
     or rd.get('partial_scope',{}).get('accepted_performance_arm') is not False or rd.get('partial_scope',{}).get('completed_full_groups')!=[]
     or rd.get('partial_scope',{}).get('preserved_raw_workloads')!=partial or dd.get('rid')!=R049A_FAILED_RID or dd.get('verdict')!='failed_harness'
     or dd.get('round_sha256')!=R049A_FAILED_ROUND_SHA or dd.get('manifest_sha256')!=R049A_FAILED_MANIFEST_SHA
     or dd.get('candidate_commit')!=CANDIDATE or dd.get('readonly') is not True or dd.get('d04_check',{}).get('ok') is not True
     or dd.get('independent_review_sha256')!=R049A_FAILED_REVIEW_SHA or dd.get('accepted_full_groups')!=0 or dd.get('partial_unaccepted_workloads')!=4
     or dd.get('measurement_retry_authorized') is not False or rv.get('schema')!='ft_r049a_failed_harness_review/v1' or rv.get('rid')!=R049A_FAILED_RID
     or rv.get('verdict')!='failed_harness' or rv.get('reviewer')!='independent_R' or rv.get('partial_scope',{}).get('accepted_performance_arm') is not False
     or rv.get('partial_scope',{}).get('completed_full_groups')!=[] or rv.get('partial_scope',{}).get('preserved_raw_workloads')!=partial
     or 'fresh service/cache' not in rv.get('retry_scope_recommendation','') or 'complete nine-service scope' not in rv.get('retry_scope_recommendation','')
     or before.get('round_id')!=R049A_FAILED_RID or before.get('verdict')!='pending_review' or before.get('verdict_history')!=[]
     or after!=rd or after.get('verdict_history',[{}])[-1].get('old')!='pending_review' or after.get('verdict_history',[{}])[-1].get('new')!='failed_harness'
     or sums.read_text().splitlines()!=[f'{sha(prior)}  round.v001.json',f'{R049A_FAILED_ROUND_SHA}  round.v002.json']):
  raise RuntimeError('R049a failed closure identity/reuse policy differs')
 return {'round':str(round_json),'manifest':str(manifest),'pin':str(pin),'d04_receipt':str(receipt),'independent_retention_review':str(review),'round_sha256':R049A_FAILED_ROUND_SHA,'manifest_sha256':R049A_FAILED_MANIFEST_SHA,'independent_review_sha256':R049A_FAILED_REVIEW_SHA,'accepted_full_groups':0,'partial_unaccepted_workloads':4,'measurement_retry_authorized':False,'complete_L1_retained':False,'fresh_full_nine_required':True}

def require_r050_d15_closure():
 """Bind only R050's sealed kept metadata and its D04 history."""
 directory=ROUNDS/R050_RID;pin=ROOT/'runs/plan_batches/closed_round_pins'/f'{R050_RID}.json'
 round_json=directory/'round.json';manifest_sha=directory/'MANIFEST.sha256';checker=directory/'round_json_append.py'
 for path in (directory,pin,round_json,manifest_sha,checker):
  if path.is_symlink() or not path.exists() or path.stat().st_mode&0o222:raise RuntimeError('R050 D15 closure is missing, linked, or writable')
 if not directory.is_dir() or any(not path.is_file() for path in (pin,round_json,manifest_sha,checker)):raise RuntimeError('R050 D15 closure types differ')
 if sha(round_json)!=R050_ROUND_SHA or sha(manifest_sha)!=R050_MANIFEST_SHA:raise RuntimeError('R050 D15 round or MANIFEST SHA differs')
 try:pin_doc=json.loads(pin.read_text());round_doc=json.loads(round_json.read_text())
 except (OSError,json.JSONDecodeError) as error:raise RuntimeError('R050 D15 closure metadata unreadable') from error
 if (pin_doc.get('rid')!=R050_RID or pin_doc.get('verdict')!='kept' or pin_doc.get('candidate_commit')!=CANDIDATE or pin_doc.get('round_sha256')!=R050_ROUND_SHA or pin_doc.get('manifest_sha256')!=R050_MANIFEST_SHA or round_doc.get('round_id')!=R050_RID or round_doc.get('verdict')!='kept'):raise RuntimeError('R050 D15 closure identity differs')
 checked=subprocess.run([str(VENV/'bin/python'),str(checker),str(directory),'check'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if checked.returncode:raise RuntimeError('R050 D15 D04 history check failed')
 return {'round':str(round_json),'manifest':str(manifest_sha),'pin':str(pin),'round_sha256':R050_ROUND_SHA,'manifest_sha256':R050_MANIFEST_SHA}

def require_t06_metadata(closure=None):
 manifest=ROUNDS/T06_RID/'manifest.json'
 if manifest.is_symlink() or not manifest.is_file(): raise RuntimeError('R046g T06 route manifest absent')
 d=json.loads(manifest.read_text())
 if d.get('schema')!=T06_MANIFEST_SCHEMA or d.get('rid')!=T06_RID or d.get('candidate_commit')!=T06_CANDIDATE: raise RuntimeError('R046g T06 route manifest identity differs')
 if d.get('memory_ratio')!='0.88': raise RuntimeError('R046g T06 performance ratio differs')
 if d.get('window')!={'kv_reserve_tokens':WINDOW,'max_seq_len_override':WINDOW,'completion_reserve_tokens':2048,'max_prompt_tokens':WINDOW-2048}:raise RuntimeError('R046g T06 release window differs')
 arms=d.get('arms'); heldout=d.get('heldout_routes')
 if not isinstance(arms,list) or len(arms)!=4 or any(not isinstance(arm,dict) for arm in arms): raise RuntimeError('R046g T06 arm training binding differs')
 roles={arm.get('role'):arm for arm in arms}
 if d.get('d15_training_route')!='G_seed12k/route' or not isinstance(heldout,list) or len(heldout)!=3 or set(heldout)!={'G_seed_45k/route','G_seed_real/route','G_two/route'}: raise RuntimeError('R046g T06 train/heldout partition differs')
 if set(roles)!={'seed12k','seed_45k','seed_real','two'} or any(roles[role].get('directory')!=f'G_{role}' or roles[role].get('d15_training_input') is not (role=='seed12k') for role in roles): raise RuntimeError('R046g T06 arm training binding differs')
 if closure is not None:
  round_doc_sha=json.loads((ROUNDS/T06_RID/'round.json').read_text()).get('measurement_manifest',{}).get('sha256')
  if not isinstance(round_doc_sha,str) or sha(manifest)!=round_doc_sha:raise RuntimeError('R046g manifest JSON SHA differs from D04 closure')
 return manifest
def admission(dry_receipt=None):
 d=load_d07()
 if d.LOCK.exists() or d.LOCK.is_symlink(): raise RuntimeError('foreign GPU lock exists; T21 remains queued')
 closures={T06_RID:require_r046g_closure(),R050_RID:require_r050_d15_closure(),R049_FAILED_RID:require_r049_failure_closure(),R049A_FAILED_RID:require_r049a_failure_closure(),'retained_L1':require_retained_l1_review()}
 require_candidate()
 if subprocess.run(['git','-C',str(WT),'merge-base','--is-ancestor',PARENT,'HEAD']).returncode: raise RuntimeError('D15 candidate lacks eff measurement ancestry')
 return d,closures,require_t06_metadata(closures[T06_RID]),require_review(dry_receipt)
def child_argv(batch,receipt):
 return [str(VENV/'bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt)]
def receipt_sha(d,argv): return d.argv_sha256(argv)
def require_receipt(d,batch,path):
 mine=d.process_birth(); expected=receipt_sha(d,child_argv(batch,path)); deadline=time.monotonic()+30
 static={'schema':'ft_t21_owned_launch/v1','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':expected}
 while time.monotonic()<deadline:
  if path.is_symlink(): raise RuntimeError('T21 child receipt is symlinked')
  if not path.is_file(): time.sleep(.05);continue
  try: row=json.loads(path.read_text())
  except (OSError,json.JSONDecodeError) as error: raise RuntimeError('T21 child receipt unreadable') from error
  if any(row.get(k)!=v for k,v in static.items()): raise RuntimeError('T21 child receipt binding differs')
  if row.get('state')=='reserved' or (row.get('state')=='launched' and row.get('child') is None): time.sleep(.05);continue
  if row.get('state')!='launched': raise RuntimeError('T21 child receipt state unknown')
  if row.get('batch_pid')!=mine['pid'] or row.get('child')!=mine: raise RuntimeError('T21 child receipt binding differs')
  return row
 raise RuntimeError('T21 child receipt did not reach launched state')
def controller():
 if sys.platform!='linux': raise RuntimeError('T21 controller requires Linux')
 require_section13_runtime_tooling()
 dry_receipt=require_dry_run_receipt();d,_,_,_=admission(dry_receipt); owned=d.load_owned_lifecycle(); helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d.ATOMIC_HELPER_SHA,'r049_atomic')
 batch=helper.next_batch(ROUNDS); receipt=ROOT/'runs/dev_T21'/f'launch_{RID}_batch{batch}.json';receipt.parent.mkdir(parents=True,exist_ok=True); argv=child_argv(batch,receipt)
 reserved={'schema':'ft_t21_owned_launch/v1','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'argv_sha256':receipt_sha(d,argv),'controller':d.process_birth()}
 got=owned.reserve_process(helper,batch,RID,argv,receipt,reserved); child=owned.process_identity(got['batch_pid'])
 if child is None or child.get('pid')!=got['batch_pid'] or type(child.get('start_ticks')) is not int: raise RuntimeError('T21 reserved child birth unavailable')
 child={'pid':child['pid'],'start_ticks':child['start_ticks'],'execution_id':f"{child['pid']}:{child['start_ticks']}"}
 return d.publish_child_binding(receipt,got,child,lifecycle=owned)
def start_service(d,directory,port,policy,profile,d0):
 env,argv,journal=service_files(d,directory,port,policy,profile,d0)
 log=(directory/'serve.log').open('a',encoding='utf-8');process=subprocess.Popen(argv,cwd=WT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 try:
  birth=d.load_owned_lifecycle().process_identity(process.pid)
  if birth is None or birth.get('pgid')!=process.pid or birth.get('session')!=process.pid:raise RuntimeError('T21 service lacks private PGID/session')
  deadline=time.monotonic()+900
  while time.monotonic()<deadline:
   if process.poll() is not None:raise RuntimeError('T21 service died during startup')
   try:
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as response:
     if json.load(response).get('status')=='ok':
      write_new(directory/'owned_process.json',{'pid':process.pid,'birth':birth,'port':port,'d0_journal':str(journal) if d0 else None});write_new(directory/'health.json',{'status':'ok'})
      text=(directory/'serve.log').read_text(encoding='utf-8',errors='replace');at=text.find('Parsed arguments')
      if at<0:raise RuntimeError('T21 service did not emit Parsed arguments')
      parsed=runpy.run_path(str(ARGS_PARSER))['parse'](str(directory/'serve.log'))
      validate_actual_args(directory,parsed,port)
      return process
   except (OSError,ValueError):pass
   time.sleep(2)
  raise TimeoutError('T21 service readiness exceeded')
 except BaseException as error:
  try:stop_service(d,process)
  except BaseException as cleanup:cleanup.owned_process=process;cleanup.owned_cleanup_failed=True;raise cleanup from error
  error.owned_process=process;raise
def stop_service(d,process):
 try:d.load_owned_lifecycle().stop_owned_process(process)
 except BaseException as error:error.owned_process=process;error.owned_cleanup_failed=True;raise

def dynamic_private_port():
 return _ordinary_adapter().load(HERE/'ft_batch_port_pair_v1.py','r049_ports').dynamic_port()

def validate_actual_args(directory,parsed,port):
 expected={'server_port':port,'memory_ratio':0.88,'kv_reserve_tokens':WINDOW,
           'max_seq_len_override':WINDOW,'max_running_req':2,'prefill_layer_major':True,
           'max_extend_tokens':4096,'cuda_graph_max_bs':2}
 for key,want in expected.items():
  try: actual=ast.literal_eval(parsed[key])
  except (KeyError,ValueError,SyntaxError) as error:raise RuntimeError('T21 actual args lack '+key) from error
  if actual!=want:raise RuntimeError('T21 actual args differ: '+key)
 write_new(directory/'serve_args_actual.json',{'parsed':parsed,'required':expected})
 (directory/'serve_args.txt').write_text(json.dumps(parsed,sort_keys=True)+'\n',encoding='utf-8')

def compare_actual_configuration(directory,reference):
 right=json.loads((directory/'serve_args_actual.json').read_text())['parsed']
 left=json.loads((reference/'serve_args_actual.json').read_text())['parsed']
 parsed_diff={key:[left.get(key),right.get(key)] for key in left.keys()|right.keys() if left.get(key)!=right.get(key)}
 if set(parsed_diff)-{'server_port','_unique_suffix'}:raise RuntimeError('T21 parsed args differ beyond declared process metadata')
 left_env=json.loads((reference/'ENV.json').read_text());right_env=json.loads((directory/'ENV.json').read_text())
 raw_diff={key:[left_env.get(key),right_env.get(key)] for key in left_env.keys()|right_env.keys() if left_env.get(key)!=right_env.get(key)}
 declared=json.loads((directory/'serve_args_diff.json').read_text())
 for key,want in declared['target_values'].items():
  actual=right_env.get(key)
  if key=='FT_DEV_EXPERT_PROFILE' and actual is not None:actual=Path(actual).name
  if actual!=want:raise RuntimeError('T21 actual environment target differs: '+key)
 paths={'FT_T21_DIAG_JOURNAL','FT_DEV_D0_PATH'}
 allowed=set(declared['allowed_difference_keys'])|paths
 if set(raw_diff)-allowed:raise RuntimeError('T21 actual environment differs beyond policy and output paths')
 write_new(directory/'serve_args_actual_diff.json',{'reference':reference.name,
           'parsed_differences':parsed_diff,'raw_environment_differences':raw_diff,
           'process_metadata_keys':['server_port','_unique_suffix'],
           'declared_output_path_keys':sorted(paths),'single_scientific_variable':'expert_policy'})
def _token_sha256(ids):
 if not isinstance(ids,list) or not ids or any(type(item) is not int or item < 0 for item in ids): raise RuntimeError('T21 tokenizer did not produce request input IDs')
 return hashlib.sha256(b''.join(int(item).to_bytes(4,'little',signed=True) for item in ids)).hexdigest()
def _load_tokenizer(path):
 from transformers import AutoTokenizer
 return AutoTokenizer.from_pretrained(str(path),trust_remote_code=True)
def _frontend_contract():
 if FRONTEND_RENDER.is_symlink() or not FRONTEND_RENDER.is_file(): raise RuntimeError('T21 candidate FrontendManager renderer is unavailable')
 raw=FRONTEND_RENDER.read_text(encoding='utf-8')
 required=('self.tokenizer.apply_chat_template(','tokenize=False,','add_generation_prompt=True,','add_special_tokens=not templated','chat_template_kwargs = {**chat_template_kwargs, "tools": tools}')
 if any(marker not in raw for marker in required): raise RuntimeError('T21 candidate FrontendManager rendering contract differs')
 return {'frontend_renderer_path':str(FRONTEND_RENDER),'frontend_renderer_sha256':sha(FRONTEND_RENDER),'frontend_template_contract':'TokenizeManager._render: tokenize=False, add_generation_prompt=True, tools injected into chat_template_kwargs; TokenizeManager.tokenize: add_special_tokens=False'}
def _frontend_ids(tokenizer,messages,*,tools=None,chat_template_kwargs=None):
 kwargs=dict(chat_template_kwargs or {})
 if tools is not None: kwargs['tools']=tools
 try: rendered=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,**kwargs)
 except Exception as error: raise RuntimeError('T21 could not reconstruct the exact chat-template request') from error
 if not isinstance(rendered,str): raise RuntimeError('T21 chat template did not render request text')
 ids=tokenizer.encode(rendered,add_special_tokens=False)
 if hasattr(ids,'tolist'): ids=ids.tolist()
 _token_sha256(ids)
 return ids
def _wire_ids(payload):
 spec=importlib.util.spec_from_file_location('r049_candidate_frontend',FRONTEND_DRIVER);driver=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(driver)
 return driver.input_ids_for_payload(driver.candidate_frontend(WT,MODEL_PATH),payload)

def _two_decode_payload(original, messages):
    """Construct the one T21 workload that requires a hard 512-token decode."""
    payload = original.build_payload(messages, 'Qwen3.8-Flash-Next-NVFP4', None, False, 512)
    payload['max_tokens'] = 512
    payload['ignore_eos'] = True
    payload.pop('stop', None)
    if (payload.get('max_tokens') != 512 or payload.get('ignore_eos') is not True
            or payload.get('stop') is not None):
        raise RuntimeError('T21 two-decode sampling contract differs')
    return payload

def _two_decode_candidate_contract(payload):
    """Use the candidate API adapter and TokenizeMsg, not a template reconstruction."""
    if (payload.get('max_tokens') != 512 or payload.get('ignore_eos') is not True
            or payload.get('stop') is not None):
        raise RuntimeError('T21 two-decode wire sampling contract differs')
    candidate_python = str(WT/'python')
    if candidate_python not in sys.path:
        sys.path.insert(0, candidate_python)
    from freetoken.message import TokenizeMsg
    from freetoken.server.api_models import ChatCompletionRequest
    from freetoken.server.openai_api import chat_request_to_genspec
    from freetoken.tokenizer.tokenize import TokenizeManager
    wire = json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    request = ChatCompletionRequest.model_validate(wire)
    spec = chat_request_to_genspec(request, {})
    sampling = spec.sampling_params
    if (getattr(sampling, 'max_tokens', None) != 512
            or getattr(sampling, 'ignore_eos', None) is not True
            or getattr(sampling, 'stop_strs', None) not in ([], ())):
        raise RuntimeError('T21 candidate GenSpec sampling contract differs')
    tokenizer = _load_tokenizer(MODEL_PATH)
    message = TokenizeMsg(uid=0, text=spec.messages, tools=spec.template_tools,
                          chat_template_kwargs=spec.chat_template_kwargs,
                          sampling_params=sampling, images=None)
    ids = TokenizeManager(tokenizer).tokenize([message])[0].input_ids
    ids = ids.tolist() if hasattr(ids, 'tolist') else ids
    _token_sha256(ids)
    return ids, {'max_tokens': sampling.max_tokens, 'ignore_eos': sampling.ignore_eos,
                 'stop_strs': list(sampling.stop_strs), 'token_count': len(ids)}
def _usage_prompt_tokens(record):
 usage=record.get('usage') if isinstance(record,dict) else None
 value=usage.get('prompt_tokens') if isinstance(usage,dict) else (record.get('prompt_tokens') if isinstance(record,dict) else None)
 if type(value) is not int or value <= 0: raise RuntimeError('T21 response lacks service prompt_tokens')
 return value
def _client_binding_digest(digest,frontend_token_count,service_prompt_tokens,*,kind):
 if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest): raise RuntimeError('T21 request input digest is invalid')
 if type(frontend_token_count) is not int or frontend_token_count<=0: raise RuntimeError('T21 frontend request token count is invalid')
 if service_prompt_tokens!=frontend_token_count: raise RuntimeError('T21 service prompt_tokens differs from reconstructed request IDs; possible truncation/frontend drift')
 return {'schema':'ft_t21_request_input_binding/v1','kind':kind,'input_ids_sha256':digest,'frontend_token_count':frontend_token_count,'service_prompt_tokens':service_prompt_tokens,'service_prompt_tokens_equal_frontend':True,'truncation_check':'service_prompt_tokens_equal_frontend','binding_origin':'candidate_chat_request_genspec_tokenizemanager_wire','server_capture':False}
def _client_binding(ids,service_prompt_tokens,*,kind): return _client_binding_digest(_token_sha256(ids),len(ids),service_prompt_tokens,kind=kind)
def _frozen_probe(d):
 paths=d.verify_frozen_cold_helpers(); probe=Path(paths['probe_raw'])
 spec=importlib.util.spec_from_file_location('r049_frozen_probe',probe); module=importlib.util.module_from_spec(spec); assert spec.loader;spec.loader.exec_module(module);return module
def _cold_request(d, tokenizer, directory, base, cold_id, original):
    probe = _frozen_probe(d)
    text, built = probe.build_text(tokenizer, 32052, cold_id)
    payload = original.build_payload([{'role': 'user', 'content': text}],
                                     'Qwen3.8-Flash-Next-NVFP4', None, False, 128)
    ids = _wire_ids(payload)
    record = _bound_ordinary_request(directory, cold_id, base, payload,
                                     directory.parent/'ordinary_observer', original, ids)
    if record['completion_tokens'] != 128:
        raise RuntimeError('T21 cold request requires 128 completion tokens')
    target = directory.parent/(directory.name+'.json')
    write_new(target, {'schema': 'ft_t21_cold_ordinary/v1', 'cold_id': cold_id,
                       'built_text_tokens': built, 'record': record})
    return target, record
def _timed_agent_replay(port, trace, target, spec, profile):
    """Replay the sealed heldout messages unchanged, in ascending order."""
    role = next((name for name, path in HELDOUT.items() if Path(path) == Path(trace)), None)
    if role is None:
        raise RuntimeError('T21 ordinary heldout source is unregistered')
    _, digest = require_seed(role)
    source = json.loads(Path(trace).read_text(encoding='utf-8'))
    meta, rows = source.get('meta', {}), source.get('rounds')
    if (source.get('schema') != 'ft_r046c_ordinary_seed_trace/v1'
            or meta.get('seed_raw_sha256') != digest or meta.get('window') != WINDOW
            or not isinstance(rows, list) or not 1 <= len(rows) <= 12
            or meta.get('completed_k') != len(rows)):
        raise RuntimeError('T21 heldout trace/seed/window binding differs')
    original = _load_original()
    target = Path(target)
    directory = target.parent/role
    directory.mkdir()
    records = []
    for index, row in enumerate(rows):
        messages = row.get('messages') if isinstance(row, dict) else None
        if not isinstance(messages, list) or not messages:
            raise RuntimeError('T21 sealed replay lacks messages')
        payload = original.build_payload(messages, 'Qwen3.8-Flash-Next-NVFP4',
                                         original.tool_specs(), True, 2048)
        ids = _wire_ids(payload)
        prior = (row.get('record') or {}).get('actual_input_binding') or {}
        prior_input = prior.get('worker_input') or {}
        expected = hashlib.sha256(json.dumps(ids, separators=(',', ':')).encode()).hexdigest()
        if prior_input.get('input_ids_sha256') != expected or prior_input.get('input_tokens') != len(ids):
            raise RuntimeError('T21 sealed replay differs from its original worker input')
        if len(ids) > WINDOW-2048:
            raise RuntimeError('T21 completed heldout request exceeds release window')
        record = _bound_ordinary_request(directory, f'round-{index:02d}',
                                         f'http://127.0.0.1:{port}/v1', payload,
                                         target.parent/'ordinary_observer', original, ids)
        record.update(round=index, ordinary_uid=record['uid'])
        records.append({'messages': messages, 'record': record, 'response': record['response']})
    write_new(target, {'schema': 'ft_r049_ordinary_heldout_replay/v3', 'rounds': records,
                       'meta': meta, 'source_trace': str(trace), 'source_trace_sha256': sha(trace),
                       'raw_seed_sha256': digest, 'transport': 'ordinary_sse_no_ft_dev_ack'})
    return {'source_trace': str(trace), 'source_trace_sha256': sha(trace),
            'raw_seed_sha256': digest, 'transport': 'ordinary_sse_no_ft_dev_ack'}

def _agent_bindings(tokenizer, trace_path, replay_path):
    replay = json.loads(Path(replay_path).read_text(encoding='utf-8'))
    if replay.get('schema') != 'ft_r049_ordinary_heldout_replay/v3':
        raise RuntimeError('T21 ordinary replay schema differs')
    bound = []
    for index, row in enumerate(replay.get('rounds') or []):
        record = row['record']
        entry = ordinary_record_binding(record)
        entry.update(round=index, ordinary_uid=entry['uid'],
                     full_response_sha256=record['full_response_sha256'],
                     model_output_sha256=record['model_output_sha256'])
        bound.append(entry)
    if not bound:
        raise RuntimeError('T21 replay produced no request binding')
    return bound
def _ordinary_adapter():
    spec = importlib.util.spec_from_file_location('r049_adapter', TWO_DECODE_PROBE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module

def _load_original():
    return _ordinary_adapter().load(AGENT_TRACE_RAW, 'r049_original_response')

def _bound_ordinary_request(directory, name, base, payload, observer, original, planned_ids):
    adapter = _ordinary_adapter()
    client = adapter.load(ORDINARY_CLIENT, 'r049_bound_client')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload_path, api_path = directory/(name+'.payload.json'), directory/(name+'.api.json')
    write_new(payload_path, payload)
    client.ordinary_request(base, payload_path, api_path)
    binding = client.bind(payload_path, api_path, None, None,
                          observer/'inputs.jsonl', observer/'tokens.jsonl',
                          directory/(name+'.binding.json'))
    record = adapter.ordinary_binding(binding)
    expected = hashlib.sha256(json.dumps(planned_ids, separators=(',', ':')).encode()).hexdigest()
    if record['input_ids_sha256'] != expected or record['prompt_tokens'] != len(planned_ids):
        raise RuntimeError('T21 actual worker input differs from planned frontend IDs')
    if record['completion_tokens'] > payload['max_tokens']:
        raise RuntimeError('T21 API completion exceeds requested output budget')
    response = adapter.full_response(api_path, original)
    record.update(response=response, actual_input_binding=binding,
                  model_output_sha256=hashlib.sha256(json.dumps(adapter.model_output(response),
                    ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                  response_comparison='model_text_reasoning_tool_functions_excludes_generated_call_id',
                  full_response_sha256=hashlib.sha256(json.dumps(response, ensure_ascii=False,
                    sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                  **adapter.timing_from_sse(api_path))
    return record


def _run_two_decode_bound(directory, base, policy, profile, d0):
    adapter = _ordinary_adapter()
    # Only the candidate's request construction is reused; its ACK transport is not called.
    probe = adapter.load(WT/'scripts/multisession_probe.py', 'r049_prompt_builder')
    tokenizer = _load_tokenizer(MODEL_PATH)
    work = directory/'two_decode'
    work.mkdir()
    payloads, expected = {}, {}
    original = _load_original()
    for name, seed in (('left', 'left-0'), ('right', 'right-0')):
        messages, ids = probe.make_messages(tokenizer, 32000, seed)
        if len(ids) != 32000:
            raise RuntimeError('T21 two-decode context construction differs')
        payload = _two_decode_payload(original, messages)
        actual_ids, contract = _two_decode_candidate_contract(payload)
        if actual_ids != ids:
            raise RuntimeError('T21 two-decode frontend construction differs')
        if contract != {'max_tokens': 512, 'ignore_eos': True, 'stop_strs': [], 'token_count': 32000}:
            raise RuntimeError('T21 two-decode candidate sampling/token contract differs')
        payloads[name] = work/(name+'.payload.json')
        write_new(payloads[name], payload)
        expected[name] = ids
    if expected['left'] == expected['right']:
        raise RuntimeError('T21 two-decode prompts must differ')
    observer = directory/'ordinary_observer'
    value = adapter.run_pair(base, payloads['left'], payloads['right'], work/'streams',
                             observer/'inputs.jsonl', observer/'tokens.jsonl', expected, original)
    bindings = []
    for record in value['records']:
        record['full_response_sha256'] = hashlib.sha256(json.dumps(record['response'],
            ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        record['model_output_sha256'] = hashlib.sha256(json.dumps(adapter.model_output(record['response']),
            ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        bindings.append(record)
    target = directory/'two_decode.json'
    write_new(target, value)
    return target, bindings

def _request_binding_only(value):
    if isinstance(value, list):
        return [_request_binding_only(item) for item in value]
    keys = ('input_ids_sha256', 'prompt_tokens', 'completion_tokens', 'finish_reason',
            'token_ids_sha256', 'model_output_sha256')
    if not isinstance(value, dict) or any(key not in value for key in keys):
        raise RuntimeError('T21 comparable request lacks actual input/output evidence')
    return {key: value[key] for key in keys}
def _checked_output(directory,name,path,binding,baseline,texts,bindings):
 text=_full_text_sha256(json.loads(path.read_text())); texts[name]=text;bindings[name]=binding
 comparable=_request_binding_only(binding)
 if baseline is not None and (text!=baseline['texts'].get(name) or comparable!=_request_binding_only(baseline['request_input_bindings'].get(name))):
  evidence={'schema':'ft_t21_not_met/v1','kind':'not_met','arm':directory.name,'workload':name,'text_sha256':text,'baseline_text_sha256':baseline['texts'].get(name),'request_input_binding':comparable,'baseline_request_input_binding':_request_binding_only(baseline['request_input_bindings'].get(name))}
  write_new(directory/'not_met.json',evidence);raise T21NotMet('T21 first workload text/input binding differs')

def run_workloads(directory, port, spec, baseline=None, *, file_dry_run=False):
    if file_dry_run:
        outputs = {}
        for name in ('cold32k_1', 'cold32k_2', 'seed_45k', 'seed_real', 'two_decode_diff512'):
            path = directory/({'seed_45k': 'seed_45k_replay.json', 'seed_real': 'seed_real_replay.json',
                               'two_decode_diff512': 'two_decode.json'}.get(name, name+'.json'))
            file_probe(path, 'formal workload output')
            outputs[name] = path
        _request_file_probes(directory)
        return {'d0_enabled': spec['d0'], 'outputs': {k: v.name for k, v in outputs.items()}, 'cpu_file_probe': True}
    d = load_d07()
    base = f'http://127.0.0.1:{port}/v1'
    outputs, texts, bindings = {}, {}, {}
    tokenizer, original = _load_tokenizer(MODEL_PATH), _load_original()
    for index in (1, 2):
        name = f'cold32k_{index}'
        target, binding = _cold_request(d, tokenizer, directory/name, base, f'{RID}-cold{index}', original)
        outputs[name] = target
        _checked_output(directory, name, target, binding, baseline, texts, bindings)
    for role, trace in HELDOUT.items():
        target = directory/f'{role}_replay.json'
        _timed_agent_replay(port, trace, target, spec, directory.parent/'seed12k_only.strp')
        binding = _agent_bindings(tokenizer, trace, target)
        outputs[role] = target
        _checked_output(directory, role, target, binding, baseline, texts, bindings)
    name = 'two_decode_diff512'
    target, binding = _run_two_decode_bound(directory, base, spec['policy'], directory.parent/'seed12k_only.strp', spec['d0'])
    outputs[name] = target
    _checked_output(directory, name, target, binding, baseline, texts, bindings)
    return {'timing': _timing_metrics(outputs), 'd0_enabled': spec['d0'], 'texts': texts,
            'request_input_bindings': bindings, 'outputs': {k: v.name for k, v in outputs.items()},
            'd0_journal_path': 'd0_journal.jsonl' if spec['d0'] else None, 'generated_tokens': _output_tokens(outputs)}

def _request_file_probes(directory):
    """Exercise each formal writer family, without dispatching a request."""
    layouts = [(directory/f'cold32k_{i}', [f'{RID}-cold{i}']) for i in (1, 2)]
    layouts += [(directory/role, [f'round-{i:02d}' for i in range(12)]) for role in HELDOUT]
    layouts += [(directory/'two_decode', ['left', 'right']),
                (directory/'two_decode/streams', ['left', 'right'])]
    for folder, names in layouts:
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            for suffix in ('.payload.json', '.api.json', '.api.sse', '.api.events.jsonl', '.binding.json'):
                file_probe(folder/(name+suffix), 'formal request writer')
    file_probe(directory/'two_decode/streams/result.json', 'formal two-stream result')
    observer = directory/'ordinary_observer'
    for name in ('inputs.jsonl', 'tokens.jsonl', 'input_ids.cpu_probe.json'):
        file_probe(observer/name, 'formal ordinary worker observer')
def _input_ids_sha256(document):
 # Legacy reader retained only for old raw evidence; R049 writes explicit request bindings above.
 found=[]
 def visit(value):
  if isinstance(value,dict):
   for key,item in value.items():
    if key in {'input_ids_sha256','prompt_sha256'} and isinstance(item,str) and len(item)==64:found.append(item)
    else:visit(item)
  elif isinstance(value,list):
   for item in value:visit(item)
 visit(document)
 if not found:raise RuntimeError('T21 client result lacks actual input_ids SHA binding')
 return sorted(set(found))
def _workload_rows(document):
    schema = document.get('schema')
    if schema == 'ft_t21_cold_ordinary/v1':
        rows = [document['record']]
    elif schema == 'ft_r049_ordinary_heldout_replay/v3':
        rows = [row['record'] for row in document['rounds']]
    elif schema == 'ft_r049_ordinary_two_decode/v3':
        rows = document['records']
    elif schema == 'ft_r049_ordinary_two_decode/v9':
        if (document.get('pause_enabled') is not False
                or document.get('ft_dev_ack') is not False
                or document.get('simultaneous_barrier') is not True
                or document.get('overlap_basis') != 'network_first_nonempty_and_terminal_only'):
            raise RuntimeError('T21 v9 two-decode transport contract differs')
        rows = document['records']
    else:
        raise RuntimeError('T21 workload output schema differs')
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise RuntimeError('T21 workload output has no request rows')
    return rows

def _full_text_sha256(document):
    adapter = _ordinary_adapter()
    responses = [adapter.model_output(row['response']) for row in _workload_rows(document)]
    return hashlib.sha256(json.dumps(responses, ensure_ascii=False,
                        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
def _finite_metric(value,name):
 if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<=0: raise RuntimeError(f'T21 lacks actual {name}')
 return float(value)
def _timing_from_document(path, name):
    rows = _workload_rows(json.loads(Path(path).read_text(encoding='utf-8')))
    ttft, rates, tokens = [], [], 0
    for row in rows:
        ttft.append(_finite_metric(row.get('ttft_s'), 'TTFT'))
        rate = _finite_metric(row.get('decode_tps'), 'decode tok/s')
        count = row.get('completion_tokens')
        if type(count) is not int or count < 2:
            raise RuntimeError('T21 lacks actual decode completion count')
        rates.append((rate, count)); tokens += count
    return {'samples': len(rows), 'completion_tokens': tokens, 'ttft_s': sum(ttft)/len(ttft),
            'decode_tps': sum(rate*count for rate, count in rates)/tokens,
            'basis': 'ordinary_sse_first_nonempty_to_terminal_with_api_completion_count',
            'backend_token_timestamps_used_for_speed': False}
def _timing_metrics(outputs):
 return {name:metric for name,path in outputs.items() if (metric:=_timing_from_document(path,name)) is not None}
def _require_production_timing(metrics):
 missing=set(('cold32k_1','cold32k_2','seed_45k','seed_real','two_decode_diff512'))-set(metrics)
 if missing: raise RuntimeError('T21 production lacks actual stream timing: '+','.join(sorted(missing)))
 return metrics

def _d0_rows(directory):
 path=directory/'d0_journal.jsonl'
 if path.is_symlink() or not path.is_file(): raise RuntimeError('T21 D0 journal absent')
 rows=[]
 for line in path.read_text().splitlines():
  try: rows.append(json.loads(line))
  except json.JSONDecodeError as error: raise RuntimeError('T21 D0 journal invalid JSON') from error
 if not rows or [row.get('seq') for row in rows]!=list(range(1,len(rows)+1)): raise RuntimeError('T21 D0 journal sequence differs')
 births={json.dumps(row.get('worker_birth'),sort_keys=True) for row in rows}
 if len(births)!=1 or not isinstance(rows[0].get('worker_birth'),dict) or type(rows[0]['worker_birth'].get('pid')) is not int: raise RuntimeError('T21 D0 worker birth differs')
 if rows[0].get('kind')!='install' or rows[-1].get('kind')!='terminal' or rows[-1].get('status')!='complete': raise RuntimeError('T21 D0 journal lacks complete install/terminal')
 decode=[row for row in rows if row.get('kind')=='decode'];adapt=[row for row in rows if row.get('kind')=='adapt']
 if not decode: raise RuntimeError('T21 D0 journal lacks decode rows')
 for row in decode:
  rids=row.get('rids')
  if any(type(row.get(key)) is not int or row[key]<0 for key in ('active','missing','fetched','hits','h2d_bytes','expert_row_bytes','step')) or not isinstance(rids,list) or not rids or any(type(uid) is not int for uid in rids) or row['active']<row['missing'] or row['hits']!=row['active']-row['missing'] or row['h2d_bytes']!=row['fetched']*row['expert_row_bytes']: raise RuntimeError('T21 D0 decode counter evidence differs')
 for row in adapt:
  rids=row.get('rids')
  if type(row.get('policy_swap_bytes_delta')) is not int or row['policy_swap_bytes_delta']<0 or type(row.get('step')) is not int or not isinstance(rids,list) or not rids or any(type(uid) is not int for uid in rids): raise RuntimeError('T21 D0 adaptation evidence differs')
 return {'path':str(path.name),'sha256':sha(path),'worker_birth':rows[0]['worker_birth'],'decode':decode,'adapt':adapt}
def _output_tokens(outputs):
    total = 0
    for path in outputs.values():
        for row in _workload_rows(json.loads(Path(path).read_text(encoding='utf-8'))):
            count = row.get('completion_tokens')
            if type(count) is not int or count <= 0:
                raise RuntimeError('T21 workload lacks actual completion count')
            total += count
    if total <= 0:
        raise RuntimeError('T21 outputs lack actual generated token count')
    return total
def run_measurements(batch=None,*,file_dry_run=False,output_root=None,file_dry_run_path=None):
 output_root=ROUNDS if output_root is None else output_root
 d=load_d07();run=Path(file_dry_run_path) if file_dry_run_path is not None else (output_root/f'.dryrun_{RID}' if file_dry_run else output_root/RID)
 if run.exists() and not file_dry_run:raise RuntimeError('T21 round already exists; no overwrite')
 rows=assert_plan(arms());run.mkdir(parents=True,exist_ok=file_dry_run);profile=None;process=None
 try:
  profile,build_cmd=build_profile(run,file_dry_run=True) if file_dry_run else build_profile(run);write_new(run/'profile_binding.json',{'training_route':'E2-R046g/G_seed12k/route','profile_derived_from_seed12k':True,'prior_r049_b101':'diagnostic_only_failed_harness_not_reused','fresh_nine_arm_service_measurement_required':True,'heldout_tuning_forbidden':['seed_45k','seed_real','two_decode_diff512'],'profile':'seed12k_only.strp','profile_sha256':sha(profile),'build_argv':build_cmd,'adapt_parameters':{'every':1,'swaps':1,'status':'configured_default_not_tuned'}})
  production={};diagnostic={}
  for spec in rows:
   directory=run/spec['name'];port=dynamic_private_port();diagnostic_value=None
   if file_dry_run:
    service_files(d,directory,port,spec['policy'],profile,spec['d0'],file_dry_run=True);run_workloads(directory,port,spec,file_dry_run=True);continue
   directory.mkdir();process=start_service(d,directory,port,spec['policy'],profile,spec['d0'])
   try:
    reference=run/('L_D0' if spec['d0'] else 'L1')
    compare_actual_configuration(directory,reference)
    value=run_workloads(directory,port,spec,production.get('L1') if production else None)
    if spec['production']:
     if value.get('d0_enabled') is not False:raise RuntimeError('T21 production arm leaked D0')
     _require_production_timing(value.get('timing') or {})
     production[spec['name']]=value
    else:
     if value.get('d0_enabled') is not True:raise RuntimeError('T21 diagnostic arm lacks D0')
     diagnostic_value=value
   finally:
    owned_process=process;process=None
    try:stop_service(d,owned_process)
    except BaseException as cleanup:cleanup.owned_process=owned_process;cleanup.owned_cleanup_failed=True;raise
   if diagnostic_value is not None:
    # Read terminal journal only after the owned service group has exited.
    role_uids={role:sorted({binding['ordinary_uid'] for binding in diagnostic_value['request_input_bindings'][role]}) for role in HELDOUT}
    role_tokens={role:diagnostic_value['timing'][role]['completion_tokens'] for role in HELDOUT}
    diagnostic[spec['name']]=diagnostic_metrics(_d0_rows(directory),role_tokens,role_uids)
  if file_dry_run:
   file_probe(run/'measurement_journal.json','formal measurement journal');file_probe(run/'result.json','formal result');return {'schema':'ft_r049_cpu_file_dry_run/v1','rid':RID,'run':str(run),'arms':[row['name'] for row in rows],'profile':str(profile),'build_argv':build_cmd}
  assert_bitwise(production);benefit=benefit_gate(production,diagnostic);result={'schema':'ft_t21_raw_measurement/v1','round_id':RID,'card':'T21','batch':batch,'candidate_commit':CANDIDATE,'verdict':'pending_review','proposed_verdict':'measured','production':production,'diagnostic_only':diagnostic,'production_speed_excludes_d0':True,'benefit_claimed':True,'heldout_benefit':benefit};write_new(run/'result.json',result);return result
 except T21NotMet as error:
  if not (run/'not_met.json').exists(): write_new(run/'not_met.json',{'schema':'ft_t21_not_met/v1','kind':'not_met','round_id':RID,'candidate_commit':CANDIDATE,'reason':str(error)})
  raise
 except BaseException as error:
  if process is not None:
   try:stop_service(d,process)
   except BaseException as cleanup:cleanup.owned_process=process;cleanup.owned_cleanup_failed=True;raise cleanup from error
  raise
def _write_child_terminal(run, error, owner, *, release_state, cleanup_error=None):
    """Preserve the raw failure while recording only public owned-lifecycle facts."""
    run = Path(run)
    if run.is_symlink():
        raise RuntimeError('T21 terminal directory is linked')
    run.mkdir(parents=True, exist_ok=True)
    failure = {'schema':'ft_t21_failed_harness/v1','round_id':RID,'candidate_commit':CANDIDATE,
               'error_type':type(error).__name__,'error':str(error)}
    cleanup = {'schema':'ft_t21_owned_cleanup/v1','round_id':RID,
               'owner':owner,'lock_release':release_state,
               'service_cleanup_failed':bool(getattr(error,'owned_cleanup_failed',False))}
    if cleanup_error is not None:
        cleanup.update(cleanup_error_type=type(cleanup_error).__name__, cleanup_error=str(cleanup_error))
    for path, value in ((run/'failed_harness.json', failure), (run/'owned_cleanup.json', cleanup)):
        if path.exists():
            raise RuntimeError('T21 terminal evidence already exists')
        write_new(path, value)

def child(batch,receipt):
 if sys.platform!='linux': raise RuntimeError('T21 child requires Linux')
 require_section13_runtime_tooling()
 dry_receipt=require_dry_run_receipt();d=load_d07(); admission(dry_receipt); require_receipt(d,batch,receipt); owner=d.take_d07_gpu_lock(RID,batch)
 try:
  return run_measurements(batch)
 except BaseException as error:
  if getattr(error,'owned_cleanup_failed',False):
   _write_child_terminal(ROUNDS/RID,error,owner,release_state='not_attempted_service_cleanup_failed')
   raise
  try:
   d.release_d07_gpu_lock(owner)
  except BaseException as cleanup:
   _write_child_terminal(ROUNDS/RID,error,owner,release_state='failed',cleanup_error=cleanup)
   raise cleanup from error
  _write_child_terminal(ROUNDS/RID,error,owner,release_state='released')
  raise
 else:
  d.release_d07_gpu_lock(owner)
def build_profile(run,*,file_dry_run=False):
 out=run/'seed12k_only.strp'; cmd=[str(VENV/'bin/python'),str(PROFILE_TOOL),str(TRAIN_ROUTE),str(out),'--num-experts',str(MODEL_NUM_EXPERTS)]
 subprocess.run(cmd,cwd=WT,check=True)
 # The builder's exit status is insufficient: make the candidate's STRP
 # reader parse the bytes and require the cache's expert geometry.
 verify=[str(VENV/'bin/python'),'-c',f"import sys; sys.path.insert(0, sys.argv[2]); from freetoken.moe.expert_profile import read_profile; p=read_profile(sys.argv[1], num_experts={MODEL_NUM_EXPERTS}); assert p.ranked",str(out),str(WT/'python')]
 subprocess.run(verify,cwd=WT,check=True)
 return out,cmd
def env_for(d,policy,profile,d0):
 env=d.clean_environment(WT);env['FT_DEV_EXPERT_POLICY']=policy
 if policy!='lru': env['FT_DEV_EXPERT_PROFILE']=str(profile)
 if policy=='profile+adapt': env.update(FT_DEV_EXPERT_ADAPT_EVERY='1',FT_DEV_EXPERT_ADAPT_SWAPS='1')
 if d0: env.update(FT_DEV_D0='1')
 if 'FT_DEV_ROUTE_TRACE' in env or 'FT_DEV_PAUSE_ENDPOINT' in env: raise RuntimeError('T21 §13 requires route trace and pause endpoint disabled')
 return env
def assert_bitwise(production):
 baseline=production['L1']['texts']
 for arm in ('P1','PA1','L2','P2','PA2'):
  if production[arm]['texts']!=baseline: raise RuntimeError('T21 policy changed full text; stop')
 return True
def diagnostic_metrics(journal,role_tokens,role_uids):
 if set(role_tokens)!={'seed_45k','seed_real'} or any(type(value) is not int or value<=0 for value in role_tokens.values()) or set(role_uids)!={'seed_45k','seed_real'}: raise RuntimeError('invalid D0 generated token/role binding')
 decode=journal['decode'];adapt=journal['adapt'];report={'role_completion_tokens':role_tokens,'journal_sha256':journal['sha256'],'worker_birth':journal['worker_birth'],'roles':{}}
 used=set()
 for role,uids in role_uids.items():
  expected=set(uids)
  if not expected: raise RuntimeError('T21 heldout role lacks ACK UID')
  own=[]
  for index,row in enumerate(decode):
   actual=set(row.get('rids') or [])
   if actual & expected:
    if not actual<=expected: raise RuntimeError('T21 D0 decode mixes heldout role UIDs')
    own.append((index,row));used.add(index)
  if not own: raise RuntimeError('T21 D0 decode lacks heldout UID evidence for '+role)
  boundaries={row['step'] for _,row in own};swaps=[]
  for row in adapt:
   actual=set(row.get('rids') or [])
   if actual & expected:
    if not actual<=expected or row.get('step') not in boundaries: raise RuntimeError('T21 D0 swap lacks unique heldout UID/boundary binding')
    swaps.append(row)
  active=sum(row['active'] for _,row in own);missing=sum(row['missing'] for _,row in own);h2d=sum(row['h2d_bytes'] for _,row in own);swap=sum(row['policy_swap_bytes_delta'] for row in swaps)
  if active<=0 or missing>active: raise RuntimeError('invalid D0 counters')
  report['roles'][role]={'active':active,'missing':missing,'hits':sum(row['hits'] for _,row in own),'common_miss_rate':missing/active,'h2d_bytes':h2d,'swap_bytes':swap,'h2d_plus_swap_bytes':h2d+swap,'decode_steps':len(own),'swap_steps':len(swaps),'uids':sorted(expected),'completion_tokens':role_tokens[role],'h2d_plus_swap_bytes_per_token':(h2d+swap)/role_tokens[role]}
 return report
def _mean(values):
 if not values: raise RuntimeError('T21 missing replicate metrics')
 return sum(values)/len(values)
def benefit_gate(production,diagnostic):
 if set(production)!={'L1','P1','PA1','L2','P2','PA2'} or set(diagnostic)!={'L_D0','P_D0','PA_D0'}: raise RuntimeError('T21 missing required production/diagnostic replicates')
 report={'replicates':2,'heldout':{}}
 for policy in ('P','PA'):
  base=[production['L1'],production['L2']];trial=[production[policy+'1'],production[policy+'2']];by_role={}
  for role in HELDOUT:
   base_speed=_mean([arm['timing'][role]['decode_tps'] for arm in base]);trial_speed=_mean([arm['timing'][role]['decode_tps'] for arm in trial]);ldiag=diagnostic['L_D0']['roles'][role];pdiag=diagnostic[policy+'_D0']['roles'][role]
   outcome={'baseline_decode_tps':base_speed,'candidate_decode_tps':trial_speed,'baseline_common_miss_rate':ldiag['common_miss_rate'],'candidate_common_miss_rate':pdiag['common_miss_rate'],'baseline_h2d_plus_swap_bytes_per_token':ldiag['h2d_plus_swap_bytes_per_token'],'candidate_h2d_plus_swap_bytes_per_token':pdiag['h2d_plus_swap_bytes_per_token'],'production_completion_tokens':[arm['timing'][role]['completion_tokens'] for arm in base+trial],'baseline_d0_completion_tokens':ldiag['completion_tokens'],'candidate_d0_completion_tokens':pdiag['completion_tokens']}
   outcome['met']=trial_speed>base_speed and pdiag['common_miss_rate']<ldiag['common_miss_rate'] and pdiag['h2d_plus_swap_bytes_per_token']<ldiag['h2d_plus_swap_bytes_per_token'];by_role[role]=outcome
  report['heldout'][policy]=by_role
 if not all(row['met'] for policies in report['heldout'].values() for row in policies.values()): raise T21NotMet('T21 heldout cache benefit criterion not met')
 return report

def packet():
 return {'schema':PREPARE_SCHEMA,'rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'window':{'kv_reserve_tokens':WINDOW,'max_seq_len_override':WINDOW,'completion_reserve_tokens':2048,'max_prompt_tokens':WINDOW-2048},'memory_ratio':'0.88','assigned':True,'requests_sent':False,'gpu_lock_taken':False,'training_route':'E2-R046g/G_seed12k/route','heldout_routes':['E2-R046g/G_seed_45k','E2-R046g/G_seed_real','E2-R046g/G_two'],'arms':assert_plan(arms()),'cuda_visible_devices_cpu_guard':'','source_binding_schema':'ft_r049_t21_ordinary_binding/v9','r046g_closure':{'round_sha256':R046G_ROUND_SHA,'manifest_sha256':R046G_MANIFEST_SHA},'r050_d15_closure':{'round_sha256':R050_ROUND_SHA,'manifest_sha256':R050_MANIFEST_SHA},'r049a_failed_closure':{'round_sha256':R049A_FAILED_ROUND_SHA,'manifest_sha256':R049A_FAILED_MANIFEST_SHA,'accepted_full_groups':0},'retained_l1_review':{'sha256':RETAINED_L1_REVIEW_SHA,'requests':24,'complete_L1_retained':True},'run_requires':['explicit --run','R046g measured and D04 history','R050 D15 kept and D04 history','R049a failed-harness D04 and independent retention review','R startup review','foreign GPU lock deny','owned controller receipt','GPU idle','retained L1 referenced read-only; no replay or raw copy','fresh remaining eight-service measurement']}
def dry_run():
 """Nine-arm file path rehearsal; no Popen, request, lock, or batch."""
 if sys.platform!='linux':raise RuntimeError('T21 dry-run requires Linux')
 candidate=require_candidate();closure=require_r046g_closure();d15_closure=require_r050_d15_closure();r049a_closure=require_r049a_failure_closure();require_t06_metadata(closure)
 target=dry_run_directory()
 if target.exists():raise RuntimeError('T21 dry-run sibling already exists')
 target.mkdir(mode=0o700);target.chmod(0o700);rows=assert_plan(arms())
 port=dynamic_private_port()
 dry=run_measurements(file_dry_run=True,output_root=ROUNDS,file_dry_run_path=target)
 receipt={'schema':DRY_RUN_SCHEMA,'rid':RID,'candidate_commit':CANDIDATE,'parent_commit':PARENT,'passed':True,'owner':{'path':str(Path(__file__).resolve()),'uid':getattr(os,'getuid',lambda:None)(),'user':os.environ.get('USER') or os.environ.get('LOGNAME')},'cwd':os.getcwd(),'candidate_worktree':candidate,'source_sha256':source_hashes(),'r046g_closure':closure,'r050_d15_closure':d15_closure,'r049_failed_closure':require_r049_failure_closure(),'r049a_failed_closure':r049a_closure,'retained_l1_review':require_retained_l1_review(),'formal_directory':str(ROUNDS/RID),'formal_rid_directory_created':False,'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'port':port,'arms':[x['name'] for x in rows],'file_dry_run':dry}
 write_new(target/'dry_run_receipt.json',receipt);(target/'dry_run_receipt.json').chmod(0o444);return receipt
# The first v9 sibling was retained after its source-closure failure; never overwrite it.
def dry_run_directory(): return ROUNDS/f'.filedry_{RID}_v11_retained_l1_r1'
def require_dry_run_receipt():
 receipt=dry_run_directory()/'dry_run_receipt.json'
 if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_mode&0o222:raise RuntimeError('T21 dry-run receipt absent or writable')
 value=json.loads(receipt.read_text());owner={'path':str(Path(__file__).resolve()),'uid':getattr(os,'getuid',lambda:None)(),'user':os.environ.get('USER') or os.environ.get('LOGNAME')}
 if (value.get('schema')!=DRY_RUN_SCHEMA or value.get('rid')!=RID or value.get('candidate_commit')!=CANDIDATE or value.get('parent_commit')!=PARENT or value.get('passed') is not True or value.get('owner')!=owner or value.get('cwd')!=str(ROOT) or value.get('candidate_worktree')!=require_candidate() or value.get('source_sha256')!=source_hashes() or value.get('r046g_closure')!=require_r046g_closure() or value.get('r050_d15_closure')!=require_r050_d15_closure() or value.get('r049_failed_closure')!=require_r049_failure_closure() or value.get('r049a_failed_closure')!=require_r049a_failure_closure() or value.get('retained_l1_review')!=require_retained_l1_review() or any(value.get(k) is not False for k in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated'))):raise RuntimeError('T21 dry-run receipt binding differs')
 return {'path':str(receipt),'sha256':sha(receipt)}
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--owned-child',action='store_true',help=argparse.SUPPRESS);p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);a=p.parse_args(argv)
 if a.run and a.dry_run:p.error('--run and --dry-run are mutually exclusive')
 if a.dry_run and (a.owned_child or a.batch is not None or a.launch_receipt is not None):p.error('--dry-run does not accept controller or child arguments')
 if a.dry_run:print(json.dumps(dry_run(),ensure_ascii=False,sort_keys=True));return 0
 if not a.run: print(json.dumps(packet(),ensure_ascii=False,sort_keys=True));return 0
 if a.owned_child:
  if a.batch is None or a.launch_receipt is None:p.error('owned child requires batch and receipt')
  child(a.batch,a.launch_receipt);return 0
 if a.batch is not None or a.launch_receipt is not None:p.error('controller does not accept child arguments')
 controller();return 0
if __name__=='__main__': raise SystemExit(main())

