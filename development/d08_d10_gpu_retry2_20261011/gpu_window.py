"""Explicit root-admitted <=45 minute window, with mandatory restore/rollback."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from hybrid_service import load_d07, idle, cleanup, capture_birth, alive_members, execute as hybrid
from window_measure import write, run as measure

ROOT=Path('/data2/FreeToken');HERE=Path(__file__).resolve().parent
RESTORE=ROOT/'development/morning_restore07_20261011'
OLD_RESTORE=ROOT/'development/morning_restore06_20261011'

def validate_controller_pins(doc):
    required={str(HERE/name) for name in (
        'gpu_window.py','hybrid_service.py','window_measure.py','d0_service.py','warmup_client.py')}
    pins=doc.get('controller_source_pins',{})
    if set(pins)!=required:raise ValueError('controller source pin set incomplete or unexpected')
    for file,digest in pins.items():
        if hashlib.sha256(Path(file).read_bytes()).hexdigest()!=digest:
            raise ValueError('controller source pin differs')

def append_event(output,event,**values):
    import datetime
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    record={'at':now,'event':event,**values}
    with (output/'events.jsonl').open('a') as handle:handle.write(json.dumps(record)+'\n')
    line='\n- '+now+' | D08_D10_GPU_WINDOW | '+event+' | '+json.dumps(values,ensure_ascii=False)+'\n'
    with (ROOT/'plan/COORDINATION_LOG.md').open('a',encoding='utf8') as handle:handle.write(line)
    print(json.dumps(record),flush=True)

def command(name):return [sys.executable,str(RESTORE/name)]

def truncate_observer(owner,output,d07):
    directory=Path(owner['run_dir'])/'overnight_observation'
    start=json.loads((directory/'start.json').read_text());pid=start['observer_pid']
    cmdline=Path(f'/proc/{pid}/cmdline').read_bytes().decode(errors='replace')
    if str(OLD_RESTORE/'observe_overnight.py') not in cmdline or str(directory) not in cmdline:
        raise RuntimeError('observer exact task identity differs')
    before=d07.process_identity(pid)
    if before is None:raise RuntimeError('observer missing before truncate')
    os.kill(pid,signal.SIGTERM)
    end=time.monotonic()+5
    while d07.process_identity(pid) is not None and time.monotonic()<end:time.sleep(.1)
    current=d07.process_identity(pid)
    if current and current['start_ticks']==before['start_ticks'] and current['state']!='Z':
        raise RuntimeError('observer did not stop')
    last=json.loads((directory/'samples.jsonl').read_text().splitlines()[-1])
    value={'classification':'truncated','started_at':start['at'],'stopped_at':time.time(),
           'planned_until':start['until'],'reason':'user-approved eta/hybrid window',
           'observer_identity':before,'last_observed_sample':last,
           'eligible_to_request_push_approval':False,'push_approved':False}
    write(directory/'terminal_truncated_d08_d10.json',value);write(output/'observation_truncation.json',value)

def eta(doc,admission,output,deadline,d07):
    proc=birth=None;safe=False;error=None
    eta_dir=output/'eta';eta_dir.mkdir();log=(eta_dir/'engine.log').open('xb')
    def environment_snapshot():
        states=subprocess.check_output(['ps','-eLo','stat='],text=True).splitlines()
        return {'at':time.time(),'uptime':subprocess.check_output(['uptime'],text=True).strip(),
                'system_rthreads':sum(s.strip().startswith('R') for s in states)}
    owner=d07.take_d07_gpu_lock('D10-ETA-20261011',0)
    try:
        write(eta_dir/'environment_before.json',environment_snapshot())
        idle(d07)
        argv=[sys.executable,doc['eta_path'],'--run-gpu','--baseline-owner',doc['baseline_owner_path'],
              '--worktree',doc['eta_worktree'],'--input-x',doc['input_x_path'],'--fixed-token','1',
              '--sealed-admission',str(admission),'--cpu-review',doc['eta_review_path'],
              '--out',str(eta_dir/'result.json')]
        write(eta_dir/'command.json',argv)
        env={**os.environ,'CUDA_VISIBLE_DEVICES':'0','PYTHONDONTWRITEBYTECODE':'1'}
        for key in list(env):
            if key.startswith('FT_DEV_'):env.pop(key)
        proc=subprocess.Popen(argv,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        birth=capture_birth(proc,d07)
        if not birth or birth['pgid']!=proc.pid or birth['session']!=proc.pid:raise RuntimeError('eta owned identity unavailable')
        write(eta_dir/'owner.json',{'birth':birth,'gpu_owner':owner})
        timeout=min(600,max(1,deadline-time.time()))
        code=proc.wait(timeout=timeout)
        if code:raise RuntimeError('eta engine/measurement failed, inspect sealed raw log')
    except BaseException as exc:error=repr(exc)
    finally:
        log.close()
        if proc is not None:
            if birth is None:
                try:birth=capture_birth(proc,d07)
                except Exception:pass
            if birth is not None:safe=cleanup(proc,birth,d07,eta_dir)
            elif proc.poll() is not None and not alive_members(proc.pid):
                try:idle(d07);safe=True
                except Exception:pass
        elif proc is None:
            try:idle(d07);safe=True
            except Exception:pass
        if safe:d07.release_d07_gpu_lock(owner)
        try:write(eta_dir/'environment_after.json',environment_snapshot())
        except Exception as exc:
            error=error or repr(exc)
            write(eta_dir/'environment_error.json',{'error':repr(exc)})
        write(eta_dir/'terminal.json',{'error':error,'cleanup_proved':safe,'lock_retained':not safe,'status':'measured' if error is None and safe else 'failed_harness'})
    if not safe:raise RuntimeError('eta cleanup failed; no later GPU until exact recovery')
    return error

def bounded_restore_command(argv,output,name,deadline,max_seconds):
    seconds=min(max_seconds,deadline-time.time())
    if seconds<=0:raise TimeoutError('45-minute deadline leaves no '+name+' budget')
    d07=load_d07()
    with (output/(name+'.log')).open('xb') as log:
        proc=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        birth=capture_birth(proc,d07)
        if birth is None:raise RuntimeError('restore helper identity unavailable')
        try:
            code=proc.wait(timeout=seconds)
            return subprocess.CompletedProcess(argv,code)
        except subprocess.TimeoutExpired:
            if os.getpgid(proc.pid)!=proc.pid or os.getsid(proc.pid)!=proc.pid:raise RuntimeError('restore helper private session changed')
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=2)
            return subprocess.CompletedProcess(argv,124)

def restore(output,deadline):
    spec=importlib.util.spec_from_file_location('restore06_deploy',RESTORE/'deploy_conditional.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    approval=module.load();module.require_root_final_review(approval)
    # Reserve 300 seconds for exact stop-before-rollback on release timeout.
    release_deadline=deadline-600
    started=bounded_restore_command(command('start_approved_release.py'),output,'restore_start',release_deadline,90)
    smoke=bounded_restore_command(command('wait_release_and_smoke.py'),output,'restore_smoke',release_deadline,600) if started.returncode==0 else None
    if started.returncode or smoke.returncode:
        def recovery_runner(argv):
            return bounded_restore_command(argv,output,'recovery_'+Path(argv[-1]).stem,deadline-5,150 if Path(argv[-1]).name=='stop_approved_restore.py' else 90)
        code=module.recover_after_restore_failure(recovery_runner)
        write(output/'restoration.json',{'rollback184':True,'all_later_gpu_stopped':True,'code':code})
        return False
    with (output/'observer.log').open('xb') as handle:
        observer=subprocess.Popen(command('post_night_observer.py'),stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
    write(output/'restoration.json',{'rollback184':False,'smoke_passed':True,'observer_parent_pid':observer.pid,'observation_still_open':True})
    return True

def execute(path):
    path=Path(path);doc=json.loads(path.read_text())
    if path.is_symlink() or path.stat().st_mode&0o222 or not doc.get('admit'):
        raise ValueError('sealed root admission required')
    if doc.get('schema')!='ft_d08_d10_eta_retry2_admission/v1' or doc.get('cpu_lanes_finished') is not True:
        raise ValueError('CPU prerequisites incomplete')
    validate_controller_pins(doc)
    if set(doc['cpu_review_pins'])!={'D05_D09','eta'}:raise ValueError('both independent CPU review pins required')
    for item in doc['cpu_review_pins'].values():
        if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('CPU review pin differs')
        reviewed=json.loads(Path(item['path']).read_text())
        if reviewed.get(item['status_key'])!=item['accepted_status']:raise ValueError('CPU independent review is not accepted')
    active=json.loads((ROOT/'run/production.active.json').read_text())
    if active!=doc['baseline_owner']:raise ValueError('production exact owner changed')
    d07=load_d07();output=Path(doc['output_root']);output.mkdir(exist_ok=False)
    started=time.time();deadline=started+2700;stopped=False;error=None
    append_event(output,'window_started',deadline_epoch=deadline,expected_end_epoch=started+2400,master_identity=d07.process_identity(os.getpid()))
    try:
        append_event(output,'offload_reference_reused',tps=30.170995740493964)
        truncate_observer(active,output,d07)
        stopped=True
        result=bounded_restore_command([sys.executable,str(OLD_RESTORE/'stop_approved_restore.py')],output,'stop481',deadline-900,180)
        if result.returncode:raise RuntimeError('481 exact stop failed')
        idle(d07);append_event(output,'481_stopped')
        eta_error=eta(doc,path,output,min(deadline-1500,time.time()+600),d07)
        append_event(output,'eta_terminal',error=eta_error)
        hybrid(path,min(deadline-1200,time.time()+900))
        append_event(output,'hybrid_terminal')
        from d0_service import execute as single_d0
        single_d0(path,min(deadline-900,time.time()+780))
        append_event(output,'d0_single_terminal')
    except BaseException as exc:error=repr(exc);append_event(output,'measurement_stopped',error=error)
    finally:
        if stopped:
            # Restore only after unambiguous GPU cleanup; retained owner locks fail closed.
            try:
                idle(d07)
                if Path('/data2/_shared/gpu.lock').exists():raise RuntimeError('GPU owner lock remains')
                okay=restore(output,deadline);append_event(output,'restore_terminal',passed=okay)
            except BaseException as exc:
                append_event(output,'restore_requires_owned_recovery',error=repr(exc));error=repr(exc)
        write(output/'terminal.json',{'error':error,'elapsed_seconds':time.time()-started,'window_limit_seconds':2700,'deadline_exceeded':time.time()>deadline,'production_stop_attempted':stopped,'push_executed':False})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');parser.add_argument('--admission');args=parser.parse_args()
    if not args.execute:print('inert');return
    execute(args.admission)

if __name__=='__main__':main()
