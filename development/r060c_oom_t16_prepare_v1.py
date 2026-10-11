#!/usr/bin/env python3
"""CPU-only E2-R060 OOM recovery T16 gate preparation.

The candidate commit is intentionally unresolved until the OOM product worker
lands.  This file never reserves a batch, lock, port listener, or formal RID.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

RID='E2-R060c-gate-OOM'; BASE='0aa23431e5b800797543bdecbf35a01045131d7d'; CANDIDATE='4c878f6b3251cca273d8548e7f5cf58a56711d3a'
WINDOW=98304; MEMORY_RATIO='0.88'; HERE=Path(__file__).resolve().parent
PORT_PAIR=HERE/'ft_batch_port_pair_v1.py'
ROOT=Path('/data2/FreeToken'); NATIVE_PROVENANCE=ROOT/'runs/dev_OOM/r060c_4c878f6_native_provenance_20261008.json'; NATIVE_PROVENANCE_SHA256='e9cd249ad68029528688644a575d3b9411e69ba6a259b35b133346ecf2785ee8'; ROUNDS=Path('/data2/_shared/runs/ft_rounds'); VENV=ROOT/'venv'
D07_SOURCE=HERE/'d07_g3g4_prepare.py'; R059_ADAPTER=HERE/'t16_r059_d07_candidate.py'; RECEIPT_SCHEMA='ft_r060_owned_launch/v1'
R059_BASE=HERE/'t16_r059_private_port_base_v3.py'; FROZEN_HELPERS=HERE/'t16_frozen_helpers_v1'
COLD={'requested_tokens':32052,'expected_input_tokens':32064,'completion_tokens':128,'temperature':0}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def source_hashes():
    """Bind the complete reviewed R059 closure, not a cold-only substitute."""
    paths=(Path(__file__),R059_ADAPTER,R059_BASE,D07_SOURCE,PORT_PAIR,
           *(FROZEN_HELPERS/name for name in ('cold_eq.py','probe_ft_cold32k.py','ft_probe_ckpt_tax.py','serve_args_diff.py')))
    for path in paths:
        if path.is_symlink() or not path.is_file(): raise RuntimeError('R060 execution source is unavailable')
    return {str(path.resolve()):sha(path) for path in paths}
def write_new(path, value):
    """Formal-artifact writer: exclusive, JSON-canonical, and writable by its owner."""
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as handle:
        json.dump(value,handle,sort_keys=True,separators=(',',':')); handle.write('\n')
    path.chmod(0o600)
def candidate_binding(commit, worktree):
    if not isinstance(commit,str) or not re.fullmatch(r'[0-9a-f]{40}',commit):
        raise RuntimeError('R060 candidate commit is not yet a stable full SHA')
    root=Path(worktree)
    if root.is_symlink() or not root.is_dir(): raise RuntimeError('R060 candidate worktree is unavailable')
    return {'candidate_commit':commit,'worktree':str(root.resolve()),'base_commit':BASE}

def four_arms():
    return [{'tree':tree,'d0':d0,'name':f'{tree}_d0_{int(d0)}'} for tree in ('base','candidate') for d0 in (False,True)]

def private_port_pair(loader=None):
    if loader is None:
        spec=importlib.util.spec_from_file_location('r060_port_pair',PORT_PAIR); loader=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(loader)
    port=loader.dynamic_port(); receipt=loader.port_receipt(port)
    if receipt.get('api')!=port or receipt.get('tcpstore')!=port+1: raise RuntimeError('R060 API/TCPStore pair differs')
    return receipt

def memory_sample(cuda):
    free,total=cuda.mem_get_info(0)
    values={'free_bytes':free,'total_bytes':total,'allocated_bytes':cuda.memory_allocated(0),'reserved_bytes':cuda.memory_reserved(0)}
    if any(type(value) is not int or value<0 for value in values.values()) or not values['total_bytes']:
        raise RuntimeError('R060 memory sample differs')
    return values

def validate_cold(record):
    if not isinstance(record,dict): raise RuntimeError('R060 cold record differs')
    required={'input_tokens':COLD['expected_input_tokens'],'completion_tokens':128,'temperature':0,'cached_tokens':0}
    if any(record.get(key)!=value for key,value in required.items()): raise RuntimeError('R060 cold32K contract differs')
    text,tokens=record.get('full_text'),record.get('token_ids')
    if not isinstance(text,str) or not text or not isinstance(tokens,list) or len(tokens)!=128 or any(type(x) is not int for x in tokens):
        raise RuntimeError('R060 cold output lacks fulltext/token evidence')
    return {'fulltext_sha256':hashlib.sha256(text.encode()).hexdigest(),'token_ids_sha256':hashlib.sha256(json.dumps(tokens,separators=(',',':')).encode()).hexdigest(),**required}

def compare_cold(base,candidate):
    left,right=validate_cold(base),validate_cold(candidate)
    if left['fulltext_sha256']!=right['fulltext_sha256'] or left['token_ids_sha256']!=right['token_ids_sha256']:
        raise RuntimeError('R060 candidate cold output is not bitwise identical')
    return {'token_ids_equal':True,'full_text_equal':True,'evidence':left}

def validate_d0(record):
    if not isinstance(record,dict) or not isinstance(record.get('prefill'),list) or not record['prefill']:
        raise RuntimeError('R060 D0 prefill evidence is absent')
    for row in record['prefill']:
        if not isinstance(row,dict) or type(row.get('h2d_bytes')) is not int or type(row.get('d2d_bytes')) is not int:
            raise RuntimeError('R060 D0 H2D/D2D evidence differs')
    return {'rows':len(record['prefill']),'h2d_bytes':sum(x['h2d_bytes'] for x in record['prefill']),'d2d_bytes':sum(x['d2d_bytes'] for x in record['prefill'])}

def plan(commit=None, worktree=None):
    if commit is None or worktree is None:
        return {'schema':'ft_r060_oom_t16_prepare/v1','rid':RID,'state':'pending_candidate_commit','default_recovery_enabled':True,'no_side_effects':True,'arms':four_arms(),'cold':COLD}
    return {'schema':'ft_r060_oom_t16_prepare/v1','rid':RID,'binding':candidate_binding(commit,worktree),'default_recovery_enabled':True,'fault_injection_enabled':False,'arms':four_arms(),'cold':COLD,'multi_probe':{'same_prompt':True,'reps':5,'completion_tokens_each':128,'ordinary_sidecar_required':True},'serve_args':{'window':WINDOW,'memory_ratio':MEMORY_RATIO},'source_sha256':source_hashes()}

def file_dry(directory, commit, worktree, writer=write_new):
    """Use the real writer seam but never launch a service or allocate a batch."""
    root=Path(directory)
    if root.exists() or root.is_symlink(): raise RuntimeError('R060 dry directory already exists')
    value=plan(commit,worktree); root.mkdir(parents=True)
    try:
        writer(root/'plan.json',value)
        for arm in value['arms']: writer(root/arm['name']/'service_plan.json',{'arm':arm,'window':WINDOW,'memory_ratio':MEMORY_RATIO,'service_started':False})
        receipt={'schema':'ft_r060_file_dry/v1','rid':RID,'plan_sha256':sha(root/'plan.json'),'service_started':False,'gpu_lock_taken':False,'batch_allocated':False}
        writer(root/'receipt.json',receipt); return receipt
    except BaseException: raise

def load_d07(commit: str, worktree: Path):
    """Scope shared lifecycle constants only in the loaded module."""
    if D07_SOURCE.is_symlink() or not D07_SOURCE.is_file(): raise RuntimeError('R060 shared D07 lifecycle source is unavailable')
    spec=importlib.util.spec_from_file_location('r060_d07',D07_SOURCE); module=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    module.CANDIDATE=commit; module.WORKTREE=Path(worktree); module.RID=RID
    return module

def _replace(argv, flag, value):
    if flag not in argv: raise RuntimeError(f'R060 service argv lacks {flag}')
    argv[argv.index(flag)+1]=str(value)

def arm_environment(d07, worktree, arm_dir, d0):
    env=d07.clean_environment(Path(worktree))
    env.pop('FT_DEV_ROUTE_TRACE',None); env.pop('FT_DEV_PAUSE_ENDPOINT',None)
    if d0: env.update(FT_DEV_D0='1',FT_DEV_D0_PATH=str(arm_dir/'d0'))
    return env

def arm_argv(d07, port):
    argv=list(d07.serve_argv(port))
    for flag in ('--kv-reserve-tokens','--max-seq-len-override'): _replace(argv,flag,WINDOW)
    _replace(argv,'--memory-ratio',MEMORY_RATIO)
    return argv

def copy_runtime_source(source: Path, target: Path):
    if source.is_symlink() or not source.is_file(): raise RuntimeError('R060 runtime source unavailable')
    target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,target); target.chmod(0o600)
    if sha(source)!=sha(target): raise RuntimeError('R060 runtime source copy differs')
    return {'source':str(source),'source_sha256':sha(source),'copy':str(target),'copy_sha256':sha(target),'mode':oct(target.stat().st_mode&0o777)}

def write_arm_files(d07, arm, worktree, pair, d0, *, file_dry=False):
    arm.mkdir(mode=0o700,parents=True,exist_ok=False)
    env=arm_environment(d07,worktree,arm,d0); argv=arm_argv(d07,pair['api'])
    selected={k:env[k] for k in sorted(env) if k in {'CUDA_VISIBLE_DEVICES','FT_DEV_D0','FT_DEV_D0_PATH','PYTHONPATH','VIRTUAL_ENV'}}
    write_new(arm/'ENV.json',selected); write_new(arm/'serve_argv.json',{'argv':argv,'environment':selected,'api_port':pair['api'],'tcpstore_port':pair['tcpstore']})
    (arm/'SERVE_CMD.txt').write_text('env '+' '.join(f'{k}={selected[k]!r}' for k in selected)+' '+' '.join(argv)+'\n',encoding='utf-8')
    (arm/'serve.log').open('x',encoding='utf-8').close()
    copies=[copy_runtime_source(Path(__file__),arm/'runtime'/Path(__file__).name)]
    if file_dry:
        for name in ('owned_process.json','health.json','serve_args.txt','cold.json','multi_probe.json','memory_before.json','memory_after.json','result.json'):
            write_new(arm/name,{'schema':'ft_r060_file_probe/v1','service_started':False,'requests_sent':False,'path':name})
    return env,argv,copies

def start_arm(d07, arm, worktree, pair, d0):
    env,argv,copies=write_arm_files(d07,arm,worktree,pair,d0)
    lifecycle=d07.load_owned_lifecycle(); process=None
    with (arm/'serve.log').open('a',encoding='utf-8') as log: process=subprocess.Popen(argv,cwd=worktree,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:
        birth=lifecycle.process_identity(process.pid)
        if birth is None or birth.get('pgid')!=process.pid or birth.get('session')!=process.pid: raise RuntimeError('R060 service lacks an owned PGID/session')
        write_new(arm/'owned_process.json',{'pid':process.pid,'birth':birth,'port_pair':pair,'runtime_sources':copies})
        deadline=time.monotonic()+900
        while time.monotonic()<deadline:
            if process.poll() is not None: raise RuntimeError('R060 service exited before ready')
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{pair['api']}/health",timeout=3) as response: health=json.load(response)
                if health.get('status')=='ok': write_new(arm/'health.json',health); break
            except (OSError,ValueError,urllib.error.URLError): pass
            time.sleep(2)
        else: raise TimeoutError('R060 service readiness timeout')
        text=(arm/'serve.log').read_text(encoding='utf-8',errors='replace'); pos=text.find('Parsed arguments')
        if pos<0: raise RuntimeError('R060 service lacks parsed ServerArgs')
        (arm/'serve_args.txt').write_text('\n'.join(text[pos:].splitlines()[:2])+'\n',encoding='utf-8')
        return process
    except BaseException:
        try: lifecycle.stop_owned_process(process)
        except BaseException as error: error.owned_process=process; error.owned_cleanup_failed=True; raise
        raise

def stop_arm(d07, process):
    lifecycle=d07.load_owned_lifecycle(); lifecycle.stop_owned_process(process)
    if lifecycle.owned_group_alive(process.pid): raise RuntimeError('R060 owned service group remains alive')

def _cold_record(d07, worktree, port, cold_id, output):
    d07.invoke_cold_eq(Path(worktree),port,cold_id,output)
    value=json.loads(Path(output).read_text(encoding='utf-8')); record=value.get('record',{})
    canonical={'input_tokens':record.get('prompt_tokens'),'completion_tokens':record.get('completion_tokens'),'temperature':record.get('temperature',0),'cached_tokens':record.get('cached_tokens',0),'full_text':value.get('text'),'token_ids':value.get('token_ids')}
    return validate_cold(canonical)

def d0_file_evidence(arm):
    path=Path(arm)/'d0_prefill.jsonl'
    if path.is_symlink() or not path.is_file(): raise RuntimeError('R060 D0 prefill file is absent')
    rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]
    return validate_d0({'prefill':rows})

def require_r060_native_provenance(path=NATIVE_PROVENANCE):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222 or sha(path)!=NATIVE_PROVENANCE_SHA256:
        raise RuntimeError('R060 native provenance is absent, writable, symlinked, or mismatched')
    doc=json.loads(path.read_text(encoding='utf-8'))
    if doc.get('schema')!='ft_r060_oom_native_provenance/v1' or doc.get('candidate_commit')!=CANDIDATE or doc.get('parent_commit')!=BASE or doc.get('candidate_worktree')!=str(ROOT/'wt/e2oom-recovery-r061fix') or doc.get('parent_worktree')!=str(ROOT/'wt/e2base1-ordinary-rewind') or doc.get('native_sources_unchanged') is not True:
        raise RuntimeError('R060 native provenance identity differs')
    for name in ('_cpu_moe','_pinned_tensor'):
        row=(doc.get('native') or {}).get(name,{})
        if not row.get('regular_copy') or row.get('parent_is_symlink') is not True or not isinstance(row.get('parent_resolved_path'),str) or type(row.get('size')) is not int or len(row.get('sha256',''))!=64:
            raise RuntimeError('R060 parent symlink/candidate native proof differs')
    return doc

def _r060_validate_extensions(extensions, parent_wt, new_wt):
    doc=require_r060_native_provenance()
    for role,wt,key in (('parent',Path(parent_wt),'parent_path'),('new',Path(new_wt),'candidate_path')):
        for name,row in extensions.get(role,{}).items():
            wanted=doc['native'].get(name,{})
            path=wt/'python/freetoken/kernel'/(name+'.cpython-310-x86_64-linux-gnu.so')
            if str(path)!=wanted.get(key) or row.get('sha256')!=wanted.get('sha256') or row.get('size')!=wanted.get('size'):
                raise RuntimeError('R060 imported extension proof differs')
            if role=='parent' and not path.is_symlink(): raise RuntimeError('R060 parent extension must retain declared symlink provenance')
            if role=='new' and path.is_symlink(): raise RuntimeError('R060 candidate extension must be a regular copy')

def build_r059_oom_runner(candidate_commit, candidate_worktree, batch, native_provenance):
    """Bind the reviewed complete R059 runner without copying its probe closure."""
    if R059_ADAPTER.is_symlink() or not R059_ADAPTER.is_file(): raise RuntimeError('R060 complete T16 adapter is unavailable')
    spec=importlib.util.spec_from_file_location('r060_r059_complete',R059_ADAPTER);mod=importlib.util.module_from_spec(spec);assert spec.loader;sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    parent=ROOT/'wt/e2base1-ordinary-rewind';candidate=Path(candidate_worktree)
    if candidate.parent != parent.parent: raise RuntimeError('R060 candidate must be a dedicated /wt worktree')
    if not callable(native_provenance): raise RuntimeError('R060 requires sealed candidate native provenance before full T16 execution')
    mod.ASSIGNED_RID=RID
    mod.CASES['D07']={'card':'OOM','parent_wt':parent.name,'new_wt':candidate.name,'parent_commit':BASE,'new_commit':candidate_commit,'ordinary_prefill':False}
    mod.require_native_provenance=native_provenance
    mod.validate_extensions=_r060_validate_extensions
    options=type('R060Options',(),{'case':'D07','rid':RID,'batch':batch,'candidate_commit':candidate_commit,'run':True,'file_dry_run':False})()
    return mod.CandidateRunner(options)

def run_t16_arms(candidate_commit, candidate_worktree, *, batch, native_provenance=None, **_ignored):
    """Execute the reviewed R059 four-arm cold/multi-probe/D0 closure under R060 identity."""
    candidate_binding(candidate_commit,candidate_worktree)
    if candidate_commit != CANDIDATE: raise RuntimeError('R060c requires final OOM candidate 4c878f6')
    runner=build_r059_oom_runner(candidate_commit,candidate_worktree,batch,native_provenance or require_r060_native_provenance)
    return runner.execute()

def child_argv(batch,receipt,commit,worktree,native_provenance=NATIVE_PROVENANCE):
    return [str(VENV/'bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt),'--candidate-commit',commit,'--worktree',str(worktree),'--native-provenance',str(native_provenance)]

def controller(commit,worktree,native_provenance=NATIVE_PROVENANCE):
    if sys.platform!='linux': raise RuntimeError('R060 controller requires Linux')
    if commit != CANDIDATE: raise RuntimeError('R060 controller requires final candidate')
    require_r060_native_provenance(native_provenance); d07=load_d07(commit,worktree); candidate_binding(commit,worktree)
    if d07.LOCK.exists() or d07.LOCK.is_symlink(): raise RuntimeError('foreign GPU lock exists before R060 batch reservation')
    owned=d07.load_owned_lifecycle(); helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d07.ATOMIC_HELPER_SHA,'r060_atomic'); batch=helper.next_batch(ROUNDS)
    path=ROOT/'runs/dev_OOM'/f'launch_{RID}_batch{batch}.json'; path.parent.mkdir(parents=True,exist_ok=True); argv=child_argv(batch,path,commit,worktree,native_provenance)
    reserved={'schema':RECEIPT_SCHEMA,'state':'reserved','rid':RID,'batch':batch,'candidate_commit':commit,'argv_sha256':d07.argv_sha256(argv),'controller':d07.process_birth()}
    receipt=owned.reserve_process(helper,batch,RID,argv,path,reserved); birth=owned.process_identity(receipt['batch_pid'])
    if birth is None: raise RuntimeError('R060 child birth is unavailable')
    return d07.publish_child_binding(path,receipt,{'pid':birth['pid'],'start_ticks':birth['start_ticks'],'execution_id':f"{birth['pid']}:{birth['start_ticks']}"},lifecycle=owned)

def child(batch,receipt,commit,worktree,native_provenance=NATIVE_PROVENANCE):
    if sys.platform!='linux': raise RuntimeError('R060 child requires Linux')
    require_r060_native_provenance(native_provenance); d07=load_d07(commit,worktree); d07.require_child_receipt(receipt,batch,Path(worktree),ROUNDS,rid=RID,expected_argv=child_argv(batch,receipt,commit,worktree,native_provenance),schema=RECEIPT_SCHEMA)
    return run_t16_arms(commit,worktree,batch=batch,native_provenance=lambda:require_r060_native_provenance(native_provenance))

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--candidate-commit');p.add_argument('--worktree',type=Path);p.add_argument('--prepare',action='store_true');p.add_argument('--file-dry-run',type=Path);p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);p.add_argument('--native-provenance',type=Path,default=NATIVE_PROVENANCE);a=p.parse_args(argv)
    if a.run or a.file_dry_run:
        p.error('R060 execution/file-dry is only available through r060_oom_owned_launch_v2.py')
    if a.file_dry_run:
        if a.run or a.owned_child or not a.candidate_commit or a.worktree is None: p.error('file dry requires candidate/worktree and no run')
        print(json.dumps(file_dry(a.file_dry_run,a.candidate_commit,a.worktree),sort_keys=True)); return 0
    if a.run:
        if not a.candidate_commit or a.worktree is None: p.error('--run requires candidate/worktree')
        value=child(a.batch,a.launch_receipt,a.candidate_commit,a.worktree,a.native_provenance) if a.owned_child and a.batch and a.launch_receipt else controller(a.candidate_commit,a.worktree,a.native_provenance)
        print(json.dumps(value,sort_keys=True)); return 0
    if not a.prepare and (a.candidate_commit or a.worktree): p.error('--candidate-commit/worktree require --prepare')
    print(json.dumps(plan(a.candidate_commit,a.worktree) if a.prepare else plan(),sort_keys=True));return 0
if __name__=='__main__': raise SystemExit(main())
