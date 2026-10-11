"""One remaining W128K service; immutable W98K receipts are reused verbatim."""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, socket, subprocess, time
from pathlib import Path
import window_runner as w

def prior_rows(prior, packet, hashes):
    for name, digest in hashes.items():
        p=prior/name
        if p.is_symlink() or not p.is_file() or w.sha(p)!=digest or p.stat().st_mode&0o222:
            raise RuntimeError('immutable W98K evidence differs: '+name)
    rows=[json.loads((prior/'W98K'/f'A{i}.api.metrics.json').read_text()) for i in range(8)]
    for i,row in enumerate(rows):
        if row['input_sha256']!=packet['input_sha256'][i] or not row['native_token_sha256'] or row['completion_tokens']<2:
            raise RuntimeError('W98K receipt binding differs')
    slots=w.slot_check(prior/'W98K/serve.log',2700)
    if slots['actual_slots']!=2700:raise RuntimeError('W98K slots differ')
    return {'A':rows,'slots':slots}

def finish_owned(p, log, record, deps, root):
    """A stop exception remains recorded; recovery requires all cleanup proofs."""
    errors=[]
    try:
        log.close()
        deps.lifecycle.stop_owned_process(p,term_timeout=90,kill_timeout=30)
    except BaseException as exc:errors.append(repr(exc))
    end=time.monotonic()+120
    while time.monotonic()<end:
        try:
            dead=not deps.lifecycle.owned_group_alive(p.pid)
            free=True
            for port in (record['port'],record['master_port']):
                with socket.socket() as sock:
                    sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
                    sock.bind(('127.0.0.1',port))
            if dead and free and deps.gpu_idle():
                w.put(root/'cleanup_receipt.json',{'written_at':datetime.datetime.now().astimezone().isoformat(),'group_dead':True,'ports_free':True,'gpu_idle':True,'stop_errors_preserved':errors})
                return True
        except BaseException as exc:
            if repr(exc) not in errors:errors.append(repr(exc))
        time.sleep(.2)
    w.put(root/'unsafe_cleanup.json',{'stop_errors':errors,'phase':'W128K','owned_pid':p.pid})
    return False

def measure(packet, admission, deps, previous, deadline):
    record=packet['arms'][1];run=deps.root/'W128K';p=log=None
    out={'W98K':previous,'W128K':{'A':[]},'actual_new_services':1,'previous_actual_services':1}
    def call(payload,target,obs,born):
        return w.invoke(deps.adapter,deps.client,f"http://127.0.0.1:{record['port']}/v1",payload,target,obs,deadline,born,deps.system_uptime,frontend=deps.frontend,sampler=deps.sampler,window=record['window'],deadline_abort=lambda:deps.lifecycle.stop_owned_process(deps.active_process,term_timeout=90,kill_timeout=30))
    try:
        p,log,obs,born=deps.start(record,run,deps.lifecycle,deadline);deps.active_process=p
        for i,path in enumerate(deps.seed_payloads):
            if w.sha(path)!=packet['input_sha256'][i]:raise RuntimeError('frozen payload differs')
            row,_=call(path,run/f'A{i}.api.json',obs,born);out['W128K']['A'].append(row)
            if row['native_token_sha256']!=previous['A'][i]['native_token_sha256']:
                raise RuntimeError(f'not_met A token mismatch {i+1}; B/cold suppressed')
        out['W128K']['slots']=deps.slot_check(run/'serve.log',record['expected_auto_slots'])
        payload=deps.window_payload(run/'B09.payload.json');brows=[]
        for k in range(9,13):
            planned=deps.frontend(json.loads(payload.read_text()));reserve=json.loads(payload.read_text())['max_tokens']
            if k==9 and len(planned)!=100223:raise RuntimeError('B09 frontend differs from 100223')
            if len(planned)+reserve>record['window']:
                out['W128K']['B_boundary']={'request':k,'reason':'capacity_limit_before_dispatch','planned_input_tokens':len(planned),'max_tokens':reserve,'window':record['window']};break
            row,_=call(payload,run/f'B{k:02d}.api.json',obs,born);brows.append(row)
            if k<12:payload=deps.next_b_payload(payload,run/f'B{k+1:02d}.payload.json',deps.producer,k-1)
        out['W128K']['B']=brows
        cold=deps.cold_payload(run/'cold.payload.json');crow,_=call(cold,run/'cold.api.json',obs,born)
        if crow['cached_tokens']!=0 or crow['min_free_gpu_mib'] is None:raise RuntimeError('cold receipt missing')
        out['W128K']['cold']=crow
        rates={arm:sum(r['completion_tokens']-1 for r in value['A'])/sum(r['decode_elapsed_s'] for r in value['A']) for arm,value in out.items() if arm in ('W98K','W128K')}
        decline=(1-rates['W128K']/rates['W98K'])*100
        out['comparison']={'aggregation':'pooled completion_tokens_minus_one / sum network first-output-to-terminal time, same native outputs','decode_tok_s':rates,'decode_decline_pct':decline,'model_prediction_decline_pct':4.0,'decision':'128K release configuration candidate' if decline<=6 else ('128K feasible; revise slope and pair with replacement strategy' if decline<=12 else '128K temporarily not feasible')}
        return out
    except BaseException as exc:
        if isinstance(exc,w.UnsafeCleanupError):
            deps.cleanup_safe=False
            if not (deps.root/'unsafe_cleanup.json').exists():
                w.put(deps.root/'unsafe_cleanup.json',{'phase':'W128K','error':repr(exc)})
        raise
    finally:
        if p is not None and not finish_owned(p,log,record,deps,deps.root):
            deps.cleanup_safe=False;raise w.UnsafeCleanupError('resume cleanup proofs missing; retain lock')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--approval',type=Path,required=True);args=parser.parse_args()
    approval=json.loads(w.sealed(args.approval).read_text());packet=w.prepare()
    if approval['verdict']!='root_approved_remaining_one_service':raise RuntimeError('resume approval absent')
    if w.sha(Path(__file__))!=approval['resume_source_sha256']:raise RuntimeError('resume source differs')
    admission=w.require_seal(approval['original_admission'],packet)
    previous=prior_rows(Path(approval['prior_run']),packet,approval['prior_hashes'])
    if w.sha(w.sealed(approval['independent_review']['path']))!=approval['independent_review']['sha256']:raise RuntimeError('resume review differs')
    seconds=datetime.datetime.fromisoformat(approval['absolute_measurement_end']).timestamp()-time.time()
    if seconds<600:raise RuntimeError('insufficient remaining original measurement budget')
    deadline=time.monotonic()+seconds;d07=w.load('/data2/FreeToken/development/d07_g3g4_prepare.py','resume_lock');owner=d07.take_d07_gpu_lock('D15-window-ab-resume-W128K',0)
    root=Path(approval['run_dir']);root.mkdir(exist_ok=False);deps=None
    try:
        d07.require_gpu_idle();deps=w.actual_deps(admission,root)
        result=measure(packet,admission,deps,previous,deadline);w.put(root/'result.json',{'verdict':'completed','result':result,'original_failed_round_preserved':approval['prior_run']})
    except BaseException as exc:
        logs=[{'path':str(p),'sha256':w.sha(p),'oom_marker':True} for p in root.glob('*/serve.log') if any(x in p.read_text(errors='replace').lower() for x in ('out of memory','cuda oom'))]
        w.put(root/'failure.json',{'verdict':'not_met' if logs or 'not_met' in repr(exc) else 'failed_harness','error':repr(exc),'oom_source_evidence':logs,'product_acceptance':False})
        raise
    finally:
        if deps is not None and not deps.sampler.close():deps.cleanup_safe=False
        if (deps is None or deps.cleanup_safe) and not (root/'unsafe_cleanup.json').exists():d07.release_d07_gpu_lock(owner)

if __name__=='__main__':main()
