#!/usr/bin/env python3
"""CPU-only E2-R061 OOM fault protocol; no product worker is imported here."""
from __future__ import annotations
import argparse, getpass, hashlib, importlib.util, json, os, shutil, subprocess, sys, threading, time, urllib.error, urllib.request
from pathlib import Path

RID='E2-R061-OOM'; BASE='0aa23431e5b800797543bdecbf35a01045131d7d'; HERE=Path(__file__).resolve().parent
ORDINARY=HERE/'r046c_t06_ordinary_client_v3.py'; STARTUP=HERE/'r046c_t06_ordinary_startup_v4.py'; R060=HERE/'r060_oom_t16_prepare_v1.py'; D07=HERE/'d07_g3g4_prepare.py'
ROOT=Path('/data2/FreeToken'); ROUNDS=Path('/data2/_shared/runs/ft_rounds'); VENV=ROOT/'venv'; RECEIPT_SCHEMA='ft_r061_owned_launch/v1'; QUEUE_TIMEOUT_SECONDS=900

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def source_hashes(): return {x.name:sha(x) for x in (Path(__file__),ORDINARY,STARTUP,R060,D07)}
def md5(path): return hashlib.md5(Path(path).read_bytes()).hexdigest()

def ordinary_binding(value):
    if not isinstance(value,dict) or value.get('schema') not in {'ft_t06_ordinary_binding/v3','ft_r049_t21_ordinary_binding/v2'} or value.get('verdict')!='worker_input_uid_token_bound': raise RuntimeError('R061 requires ordinary UserMsg/Detokenize binding')
    api,tokens=value.get('api'),value.get('token_sidecar')
    if not isinstance(api,dict) or type(api.get('uid')) is not int or not isinstance(tokens,dict) or not isinstance(tokens.get('events'),list): raise RuntimeError('R061 ordinary UID/token evidence differs')
    api_path=Path(api.get('path','')); api_doc=json.loads(api_path.read_text(encoding='utf-8')) if api_path.is_file() else {}
    if api_path.is_symlink() or not api_path.is_file(): raise RuntimeError('R061 ordinary raw API receipt is unavailable')
    raw_path=Path(api_doc.get('sse',''))
    if raw_path.is_symlink() or not raw_path.is_file(): raise RuntimeError('R061 ordinary raw SSE is unavailable')
    parts=[]
    for line in raw_path.read_text(encoding='utf-8',errors='strict').splitlines():
        if not line.startswith('data: ') or line=='data: [DONE]': continue
        row=json.loads(line[6:]); delta=((row.get('choices') or [{}])[0].get('delta') or {})
        parts.append({key:delta[key] for key in ('content','reasoning_content','tool_calls') if key in delta})
    token_ids=[row.get('next_token') for row in tokens['events']]
    if not parts or not token_ids or any(type(token) is not int for token in token_ids): raise RuntimeError('R061 ordinary SSE/token sidecar lacks physical output')
    return {'uid':api['uid'],'token_ids_sha256':hashlib.sha256(json.dumps(token_ids,separators=(',',':')).encode()).hexdigest(),'fulltext_sha256':hashlib.sha256(json.dumps(parts,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()}

def ordinary_sidecar_binding(client, input_path, api_path, input_sidecar, token_sidecar):
    """Bind ordinary API/SSE and worker sidecars without route, pause, or D0."""
    api=json.loads(Path(api_path).read_text(encoding='utf-8'))
    source=api.get('payload_source')
    if (api.get('schema')!='ft_t06_ordinary_sse/v3' or api.get('pause_enabled') is not False
            or not isinstance(source,dict) or source.get('path')!=str(input_path) or source.get('sha256')!=sha(input_path)):
        raise RuntimeError('R061 ordinary API receipt differs')
    raw=Path(api.get('sse',''))
    if raw.is_symlink() or not raw.is_file() or api.get('sse_sha256')!=sha(raw): raise RuntimeError('R061 raw SSE binding differs')
    v2=client._v2(); uid,usage,finish=v2.parse_sse(raw.read_bytes())
    if api.get('uid')!=uid or api.get('usage')!=usage or api.get('finish_reason')!=finish: raise RuntimeError('R061 raw SSE/API values differ')
    tokens=client._tokens_for_uid(Path(token_sidecar),uid,usage['completion_tokens'],finish)
    actual=client._input_for_uid(Path(input_sidecar),uid,tokens[0]['service_birth'],tokens[0]['worker_birth'])
    if actual['input_tokens']!=usage['prompt_tokens'] or actual['time_ns']>=tokens[0]['time_ns']: raise RuntimeError('R061 worker input/token order differs')
    return ordinary_binding({'schema':'ft_t06_ordinary_binding/v3','verdict':'worker_input_uid_token_bound',
        'api':{'path':str(api_path),'uid':uid},'token_sidecar':{'events':tokens}})

def validate_fault_result(before,after,affected_uid,queued_uid,api_birth_before,api_birth_after):
    required={'pid','start_ticks','execution_id','pgid','session'}
    if (not isinstance(api_birth_before,dict) or not isinstance(api_birth_after,dict)
            or set(api_birth_before)!=required or api_birth_before!=api_birth_after
            or before['uid']==affected_uid or after['uid']!=queued_uid): raise RuntimeError('R061 API/UID fault isolation differs')
    if before['token_ids_sha256']!=after['token_ids_sha256'] or before.get('fulltext_sha256')!=after.get('fulltext_sha256'): raise RuntimeError('R061 restart output differs from cold reference')
    return {'api_birth_unchanged':True,'cold_token_ids_equal':True,'cold_full_text_equal':True}

def plan(candidate=None):
    return {'schema':'ft_r061_oom_fault_prepare/v1','rid':RID,'state':'pending_candidate_commit' if candidate is None else 'candidate_bound','candidate_commit':candidate,'queue_protocol':{'mode':'queue_during_restart','timeout_seconds':QUEUE_TIMEOUT_SECONDS,'max_waiters':128,'required_live_health':'maintenance=restarting and restart_waiters>=1'},'epoch_protocol':'old epoch replies rejected after replacement readiness','ordinary_sidecar_required':True,'source_sha256':source_hashes()}

# Real execution wiring added after the CPU-only protocol validators above.
def _load(path,name):
    if path.is_symlink() or not path.is_file(): raise RuntimeError(f'R061 source unavailable: {path.name}')
    spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);assert spec.loader;sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
def ordinary_client(): return _load(ORDINARY,'r061_ordinary')
def r060(): return _load(R060,'r061_r060')
def recovery_contract(worktree):
    api=Path(worktree)/'python/freetoken/server/api_server.py'; control=Path(worktree)/'python/freetoken/server/control_api.py'; stats=Path(worktree)/'python/freetoken/server/stats.py'; sup=Path(worktree)/'python/freetoken/server/supervisor.py'; eng=Path(worktree)/'python/freetoken/engine/engine.py'
    texts=[]
    for path in (api,sup,eng):
        if path.is_symlink() or not path.is_file(): raise RuntimeError('R061 recovery source absent')
        texts.append(path.read_text(encoding='utf-8'))
    required=((0,'maintenance_state = "restarting"'),(0,'backend_epoch += 1'),(1,'restart_backend'),(1,'max_restarts'),(2,'def forward_batch'))
    if any(token not in texts[index] for index,token in required): raise RuntimeError('R061 product restart contract differs')
    # The small legacy fixture intentionally has no HTTP-control modules.  A real candidate must
    # carry both modules, and then their exact fields are part of the admission binding.
    optional=[path for path in (control,stats) if path.exists()]
    if optional and len(optional)!=2: raise RuntimeError('R061 product control surface is incomplete')
    for path in optional:
        if path.is_symlink() or not path.is_file(): raise RuntimeError('R061 product control surface is unavailable')
    if optional:
        control_text,stats_text=(path.read_text(encoding='utf-8') for path in optional)
        if 'RESTART_READY_TIMEOUT_S = 900.0' not in texts[0] or 'RESTART_QUEUE_MAX = 128' not in texts[0] or '@app.get("/health")' not in control_text or 'restart_waiters' not in control_text or '"recovery"' not in stats_text or 'restart_waiters' not in stats_text: raise RuntimeError('R061 product recovery control fields differ')
    return {str(path):sha(path) for path in (api,*optional,sup,eng)}
def injection_contract(worktree):
    path=Path(worktree)/'python/freetoken/scheduler/scheduler.py'
    if path.is_symlink() or not path.is_file(): raise RuntimeError('R061 scheduler injection source absent')
    text=path.read_text(encoding='utf-8')
    required=('FT_DEV_OOM_INJECT', 'FT_DEV_OOM_UID', 'FT_DEV_OOM_POINT', 'FT_DEV_OOM_RECEIPT_PATH', 'before_forward', '_dev_oom_used', 'torch.cuda.OutOfMemoryError')
    if any(token not in text for token in required): raise RuntimeError('R061 product DEV OOM injection contract differs')
    return {str(path):sha(path)}
def write_fault_startup(directory):
    """Freeze only the ordinary-v4 observer; product scheduler owns OOM injection."""
    runtime=Path(directory)/'runtime';runtime.mkdir(mode=0o700,parents=True,exist_ok=False);observer=runtime/STARTUP.name;shutil.copyfile(STARTUP,observer);observer.chmod(0o600)
    if sha(observer)!=sha(STARTUP): raise RuntimeError('R061 observer copy differs')
    target=runtime/'r061_fault_startup.py'
    text=('import os,runpy,sys\n'
          'if __name__ == "__mp_main__":\n'
          '    os.environ["R046C_T06_OBSERVER_DIR"]=os.path.join(os.environ["R046C_T06_OBSERVER_DIR"],"workers",str(os.getpid()))\n'
          '    runpy.run_path(%r,run_name="__mp_main__")\n'
          'elif __name__ == "__main__":\n'
          '    sys.argv=[%r,"--observer-dir",os.environ["R046C_T06_OBSERVER_DIR"],"--",*sys.argv[1:]]\n'
          '    runpy.run_path(%r,run_name="__main__")\n') % (str(observer),str(observer),str(observer))
    with target.open('x',encoding='utf-8') as h:h.write(text)
    target.chmod(0o600);return {'startup':str(target),'startup_sha256':sha(target),'observer':str(observer),'observer_sha256':sha(observer),'product_fault_injection':True}
def require_injection_event(path,uid):
    path=Path(path)
    if path.is_symlink() or not path.is_file(): raise RuntimeError('R061 product OOM receipt is unavailable')
    row=json.loads(path.read_text(encoding='utf-8'))
    required={'schema':'ft_dev_oom_receipt/v1','uid':uid,'point':'before_forward','count':1}
    if any(row.get(k)!=v for k,v in required.items()) or type(row.get('epoch')) is not int or row['epoch'] < 0 or type(row.get('pid')) is not int or type(row.get('wall_time_ns')) is not int or type(row.get('monotonic_ns')) is not int: raise RuntimeError('R061 product OOM receipt differs')
    return row
def require_sealed_admission(path, *, commit, label):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError(f'R061 {label} is absent, symlinked, or writable')
    try: value=json.loads(path.read_text(encoding='utf-8'))
    except (OSError,json.JSONDecodeError) as exc: raise RuntimeError(f'R061 {label} is unreadable') from exc
    if value.get('rid') != RID or value.get('candidate_commit') != commit or not isinstance(value.get('source_sha256'),dict):
        raise RuntimeError(f'R061 {label} binding differs')
    return {'path':str(path),'sha256':sha(path),'schema':value.get('schema')}

def admission(commit,worktree,dry_receipt,startup_review):
    r=r060();r.candidate_binding(commit,worktree); proof=getattr(r,'require_r060_native_provenance',None); native=proof() if callable(proof) else {'candidate_commit':commit}
    return {'native_provenance':{'path':str(getattr(r,'NATIVE_PROVENANCE','test-only-unbound')),'sha256':getattr(r,'NATIVE_PROVENANCE_SHA256',None),'candidate_commit':native['candidate_commit']},
            'file_dry':require_sealed_admission(dry_receipt,commit=commit,label='file-dry receipt'),
            'startup_review':require_sealed_admission(startup_review,commit=commit,label='startup review')}

def _copy_source(source, target):
    source,target=Path(source),Path(target)
    if source.is_symlink() or not source.is_file(): raise RuntimeError('R061 source capsule input is unavailable')
    target.parent.mkdir(mode=0o700,parents=True,exist_ok=True); shutil.copyfile(source,target); target.chmod(0o600)
    if sha(source)!=sha(target) or md5(source)!=md5(target): raise RuntimeError('R061 source capsule copy differs')
    return {'source':str(source),'target':str(target),'sha256':sha(target),'md5':md5(target),'mode':oct(target.stat().st_mode & 0o777)}

def file_dry(directory,commit,worktree,reference,affected,queued):
    """Run the formal file-writer path without a listener, request, lock, batch, or RID directory."""
    root=Path(directory)
    if root.exists() or root.is_symlink(): raise RuntimeError('R061 file-dry directory already exists')
    r=r060();r.candidate_binding(commit,worktree); recovery=recovery_contract(worktree); injection=injection_contract(worktree)
    if any(Path(x).is_symlink() or not Path(x).is_file() for x in (reference,affected,queued)): raise RuntimeError('R061 file-dry inputs must be regular files')
    root.mkdir(mode=0o700,parents=True); runtime=root/'runtime'; wrapper=write_fault_startup(root)
    copies=[_copy_source(path,runtime/path.name) for path in (Path(__file__),ORDINARY,STARTUP,R060,D07,r.PORT_PAIR)]
    pair=r.private_port_pair()
    probes={}
    try:
        for name in ('ENV.json','SERVE_CMD.txt','serve.log','owned_process.json','health.before.json','health.restarting.json','health.ready.json','affected.api.sse','reference.api.json','queued.api.json','result.json'):
            path=root/'output_probes'/name; path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            with path.open('x',encoding='utf-8') as handle: handle.write(json.dumps({'schema':'ft_r061_file_probe/v1','path':name,'service_started':False,'requests_sent':False},sort_keys=True)+'\n')
            path.chmod(0o600); probes[name]={'sha256':sha(path),'md5':md5(path),'mode':oct(path.stat().st_mode & 0o777)}
        receipt={'schema':'ft_r061_file_dry/v1','rid':RID,'candidate_commit':commit,'worktree':str(Path(worktree).resolve()),'formal_entry':str(Path(__file__).resolve()),'dry_runner':str(Path(__file__).resolve()),'cwd':os.getcwd(),'uid':getattr(os,'getuid',lambda:-1)(),'user':getpass.getuser(),'source_sha256':source_hashes(),'source_copies':copies,'fault_startup':wrapper,'product_sources':{'recovery':recovery,'injection':injection},'inputs':{name:{'path':str(path),'sha256':sha(path),'md5':md5(path)} for name,path in {'reference':reference,'affected':affected,'queued':queued}.items()},'port_pair':pair,'output_probes':probes,'service_started':False,'requests_sent':False,'gpu_lock_taken':False,'batch_allocated':False,'formal_rid_directory_created':False,'passed':True}
        r.write_new(root/'receipt.json',receipt); (root/'receipt.json').chmod(0o444)
        return receipt
    except BaseException:
        raise

def _health(base):
    root=base[:-3] if base.endswith('/v1') else base
    with urllib.request.urlopen(root+'/health',timeout=3) as response:
        value=json.load(response)
    required=('maintenance','backend_epoch','restart_attempts','restart_waiters')
    if not isinstance(value,dict) or any(key not in value for key in required) or value['maintenance'] not in {'serving','restarting','failed'} or any(type(value[key]) is not int or value[key]<0 for key in required[1:]): raise RuntimeError('R061 /health recovery fields differ')
    return value

def _wait_for_restarting(base, thread, deadline):
    while time.monotonic()<deadline:
        if not thread.is_alive(): raise RuntimeError('R061 queued request completed before restart queue evidence')
        try:
            health=_health(base)
            if health['maintenance']=='restarting' and health['restart_waiters']>=1: return health
        except (OSError,ValueError,urllib.error.URLError): pass
        time.sleep(.05)
    raise TimeoutError('R061 never observed a live queued restart waiter')

def _api_error(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or not path.read_bytes(): raise RuntimeError('R061 affected request has no raw API error')
    raw=path.read_bytes()
    try:
        rows=[json.loads(line[6:]) for line in raw.decode('utf-8',errors='strict').splitlines() if line.startswith('data: ') and line!='data: [DONE]']
        document=rows[-1] if rows else json.loads(raw.decode('utf-8',errors='strict'))
    except (UnicodeDecodeError,json.JSONDecodeError) as exc: raise RuntimeError('R061 affected response is not a raw API error document') from exc
    error=document.get('error') if isinstance(document,dict) else None
    if isinstance(error,dict): message=error.get('message') or error.get('detail')
    else: message=error
    if not isinstance(message,str) or not message: raise RuntimeError('R061 affected response lacks API error detail')
    return {'path':str(path),'sha256':sha(path),'api_error':message}

def _worker_births(lifecycle, pgid, api_pid):
    rows=[]
    for pid in _group_pids(pgid):
        if pid == api_pid: continue
        birth=lifecycle.process_identity(pid)
        if birth is None: raise RuntimeError('R061 old worker disappeared before birth capture')
        rows.append(birth)
    if not rows: raise RuntimeError('R061 service has no capturable worker births')
    return rows

def _require_old_workers_exited(lifecycle, births):
    for birth in births:
        current=lifecycle.process_identity(birth['pid'])
        if current is not None and current.get('start_ticks')==birth['start_ticks']: raise RuntimeError('R061 old worker birth remains after replacement ready')
    return {'all_old_worker_births_exited':True,'count':len(births)}

def _epoch_observer(root, epoch, uid):
    root=Path(root); candidates=[]
    workers=root/'workers'
    for directory in sorted(workers.iterdir()) if workers.is_dir() else ():
        inputs,tokens=directory/'inputs.jsonl',directory/'tokens.jsonl'
        if inputs.is_file() and tokens.is_file() and any(json.loads(line).get('uid')==uid for line in inputs.read_text(encoding='utf-8').splitlines() if line.strip()): candidates.append(directory)
    if len(candidates)!=1: raise RuntimeError('R061 cannot uniquely bind UID to worker observer snapshot')
    target=root/f'epoch-{epoch}'
    if target.exists() or target.is_symlink(): raise RuntimeError('R061 epoch observer destination already exists')
    candidates[0].rename(target); return target

def child_argv(batch,receipt,commit,worktree,reference,affected,queued,dry_receipt,startup_review): return [str(VENV/'bin/python'),str(Path(__file__).resolve()),'--run','--owned-child','--batch',str(batch),'--launch-receipt',str(receipt),'--candidate-commit',commit,'--worktree',str(worktree),'--reference-input',str(reference),'--affected-input',str(affected),'--queued-input',str(queued),'--file-dry-receipt',str(dry_receipt),'--startup-review',str(startup_review)]
def controller(commit,worktree,reference,affected,queued,dry_receipt,startup_review):
    if sys.platform!='linux': raise RuntimeError('R061 controller requires Linux')
    r=r060();admission(commit,worktree,dry_receipt,startup_review);d=r.load_d07(commit,Path(worktree))
    if d.LOCK.exists() or d.LOCK.is_symlink(): raise RuntimeError('foreign GPU lock exists before R061 reservation')
    owned=d.load_owned_lifecycle();helper=owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py',d.ATOMIC_HELPER_SHA,'r061_atomic');batch=helper.next_batch(ROUNDS);receipt=ROOT/'runs/dev_OOM'/f'launch_{RID}_batch{batch}.json';receipt.parent.mkdir(parents=True,exist_ok=True);argv=child_argv(batch,receipt,commit,worktree,reference,affected,queued,dry_receipt,startup_review)
    value=owned.reserve_process(helper,batch,RID,argv,receipt,{'schema':RECEIPT_SCHEMA,'state':'reserved','rid':RID,'batch':batch,'candidate_commit':commit,'argv_sha256':d.argv_sha256(argv),'controller':d.process_birth()});birth=owned.process_identity(value['batch_pid'])
    if birth is None: raise RuntimeError('R061 child birth unavailable')
    return d.publish_child_binding(receipt,value,{'pid':birth['pid'],'start_ticks':birth['start_ticks'],'execution_id':f"{birth['pid']}:{birth['start_ticks']}"},lifecycle=owned)
def _group_pids(pgid):
    result=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit(): continue
        try:
            fields=(proc/'stat').read_text().rpartition(') ')[2].split()
            if int(fields[2])==pgid: result.append(int(proc.name))
        except (OSError,ValueError,IndexError): pass
    return sorted(result)
def run_fault_protocol(batch,commit,worktree,reference,affected,queued,d):
    """Real API/SSE path; product scheduler performs its one-shot before-forward injection."""
    r=r060();run=ROUNDS/RID
    if run.exists() or run.is_symlink(): raise RuntimeError('R061 round directory already exists')
    if any(Path(x).is_symlink() or not Path(x).is_file() for x in (reference,affected,queued)): raise RuntimeError('R061 inputs must be immutable regular files')
    input_sha={name:sha(path) for name,path in {'reference':reference,'affected':affected,'queued':queued}.items()}
    if len(set(input_sha.values()))!=1: raise RuntimeError('R061 reference/fault/queued payload SHA differs')
    recovery_contract(worktree);pair=r.private_port_pair();owner=d.take_d07_gpu_lock(RID,batch);process=None;release=True
    try:
        d.require_gpu_idle();run.mkdir(mode=0o700,parents=True);wrapper=write_fault_startup(run);event=run/'fault_receipt.json';observer=run/'ordinary_observer'
        clean,argv=d.clean_environment,d.serve_argv
        def env_for(wt,**_ignored):
            # Recovery measurement must not inherit route tracing, pause, or D0.
            env=clean(wt)
            for key in ('FT_DEV_ROUTE_TRACE','FT_DEV_PAUSE_ENDPOINT','FT_DEV_D0','FT_DEV_D0_PATH'):
                env.pop(key,None)
            env.update(FT_DEV_OOM_INJECT='1',FT_DEV_OOM_UID='1',FT_DEV_OOM_POINT='before_forward',
                       FT_DEV_OOM_RECEIPT_PATH=str(event),R046C_T06_OBSERVER_DIR=str(observer))
            return env
        d.clean_environment=env_for;d.serve_argv=lambda port:[str(VENV/'bin/python'),wrapper['startup'],*argv(port)[1:]]
        try: process=d.start_server(run,Path(worktree),pair['api'],None)
        finally: d.clean_environment=clean;d.serve_argv=argv
        lifecycle=d.load_owned_lifecycle();api_birth=lifecycle.process_identity(process.pid)
        if api_birth is None: raise RuntimeError('R061 API birth unavailable after readiness')
        client=ordinary_client();base=f"http://127.0.0.1:{pair['api']}/v1";client.ordinary_request(base,Path(reference),run/'reference.api.json')
        health_before=_health(base)
        if health_before['maintenance']!='serving': raise RuntimeError('R061 API was not serving before fault injection')
        old_workers=_worker_births(lifecycle,process.pid,process.pid); errors=[]
        def request_fault():
            try: client.ordinary_request(base,Path(affected),run/'affected.api.json',timeout=QUEUE_TIMEOUT_SECONDS+60)
            except BaseException: errors.append(True)
        thread=threading.Thread(target=request_fault,daemon=True);thread.start();deadline=time.monotonic()+QUEUE_TIMEOUT_SECONDS
        while time.monotonic()<deadline and not event.is_file(): time.sleep(.05)
        marker=require_injection_event(event,1);queued_result=[]
        def request_queued():
            try: queued_result.append(client.ordinary_request(base,Path(queued),run/'queued.api.json',timeout=QUEUE_TIMEOUT_SECONDS+60))
            except BaseException as error: queued_result.append(error)
        queued_thread=threading.Thread(target=request_queued,daemon=True);queued_thread.start()
        health_restarting=_wait_for_restarting(base,queued_thread,time.monotonic()+QUEUE_TIMEOUT_SECONDS)
        thread.join(QUEUE_TIMEOUT_SECONDS+60);queued_thread.join(QUEUE_TIMEOUT_SECONDS+60)
        if queued_thread.is_alive() or len(queued_result)!=1 or isinstance(queued_result[0],BaseException): raise RuntimeError('R061 queued restart request did not complete')
        queued_api=queued_result[0]
        if thread.is_alive() or not errors: raise RuntimeError('R061 affected request did not terminate with an API error')
        affected_error=_api_error(run/'affected.api.sse')
        health_ready=_health(base)
        if health_ready['maintenance']!='serving' or health_ready['backend_epoch'] <= marker['epoch']: raise RuntimeError('R061 replacement did not become serving in a new epoch')
        r.write_new(run/'health.before.json',health_before)
        r.write_new(run/'health.restarting.json',health_restarting)
        r.write_new(run/'health.ready.json',health_ready)
        # Do not use the v3 route/D0 binder: recovery keeps trace and D0 off.
        old_snapshot=_epoch_observer(observer,marker['epoch'],0)
        fresh_snapshot=_epoch_observer(observer,health_ready['backend_epoch'],queued_api['uid'])
        ref=ordinary_sidecar_binding(client,Path(reference),run/'reference.api.json',old_snapshot/'inputs.jsonl',old_snapshot/'tokens.jsonl')
        fresh=ordinary_sidecar_binding(client,Path(queued),run/'queued.api.json',fresh_snapshot/'inputs.jsonl',fresh_snapshot/'tokens.jsonl')
        worker_exit=_require_old_workers_exited(lifecycle,old_workers)
        api_birth_after=lifecycle.process_identity(process.pid)
        if api_birth_after is None: raise RuntimeError('R061 API process disappeared after replacement')
        outcome=validate_fault_result(ref,fresh,marker['uid'],queued_api['uid'],api_birth,api_birth_after)
        value={'schema':'ft_r061_raw_measurement/v1','rid':RID,'batch':batch,'candidate_commit':commit,'verdict':'pending_review','proposed_verdict':'measured','queue_timeout_seconds':QUEUE_TIMEOUT_SECONDS,'input_sha256':input_sha,'fault':marker,'old_worker_births':old_workers,'affected_error':affected_error,'queue_observation':health_restarting,'health_before':health_before,'health_ready':health_ready,'observer_epochs':{'reference':str(old_snapshot),'queued':str(fresh_snapshot)},**worker_exit,**outcome};r.write_new(run/'result.json',value);return value
    finally:
        if process is not None:
            try:d.load_owned_lifecycle().stop_owned_process(process)
            except BaseException:release=False
        if release:d.release_d07_gpu_lock(owner)
def child(batch,receipt,commit,worktree,reference,affected,queued,dry_receipt,startup_review,*,body=None):
    if sys.platform!='linux': raise RuntimeError('R061 child requires Linux')
    r=r060();d=r.load_d07(commit,Path(worktree));d.require_child_receipt(receipt,batch,Path(worktree),ROUNDS,rid=RID,expected_argv=child_argv(batch,receipt,commit,worktree,reference,affected,queued,dry_receipt,startup_review),schema=RECEIPT_SCHEMA);admission(commit,worktree,dry_receipt,startup_review)
    return run_fault_protocol(batch,commit,worktree,reference,affected,queued,d) if body is None else body()
def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--prepare',action='store_true');p.add_argument('--file-dry-run',type=Path);p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);p.add_argument('--candidate-commit');p.add_argument('--worktree',type=Path);p.add_argument('--reference-input',type=Path);p.add_argument('--affected-input',type=Path);p.add_argument('--queued-input',type=Path);p.add_argument('--file-dry-receipt',type=Path);p.add_argument('--startup-review',type=Path);a=p.parse_args(argv)
    if a.file_dry_run:
      if a.run or a.owned_child or not a.candidate_commit or a.worktree is None or not all((a.reference_input,a.affected_input,a.queued_input)): p.error('file dry requires candidate/worktree/three ordinary inputs and no run')
      print(json.dumps(file_dry(a.file_dry_run,a.candidate_commit,a.worktree,a.reference_input,a.affected_input,a.queued_input),sort_keys=True));return 0
    if not a.run:
      if a.owned_child or a.batch is not None or a.launch_receipt is not None or a.candidate_commit or a.worktree:p.error('launch arguments require --run')
      print(json.dumps(plan(a.candidate_commit if a.prepare else None),sort_keys=True));return 0
    if not a.candidate_commit or a.worktree is None or not all((a.reference_input,a.affected_input,a.queued_input,a.file_dry_receipt,a.startup_review)):p.error('--run requires candidate/worktree/three ordinary inputs/file-dry receipt/startup review')
    result=child(a.batch,a.launch_receipt,a.candidate_commit,a.worktree,a.reference_input,a.affected_input,a.queued_input,a.file_dry_receipt,a.startup_review) if a.owned_child and a.batch and a.launch_receipt else controller(a.candidate_commit,a.worktree,a.reference_input,a.affected_input,a.queued_input,a.file_dry_receipt,a.startup_review)
    print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__': raise SystemExit(main())
