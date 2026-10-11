"""One approved hybrid service. Exact argv gate and birth-bound cleanup."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
from window_measure import write, run as measure

ROOT=Path('/data2/FreeToken')

def load_d07():
    spec=importlib.util.spec_from_file_location('window_d07',ROOT/'development/d07_g3g4_prepare.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def expected_argv(baseline):
    if baseline[:3] != ['taskset','-c','1,3-47']:
        raise ValueError('unexpected baseline affinity prefix')
    tail=list(baseline[3:])
    if tail.count('--moe-strategy') != 1 or tail[tail.index('--moe-strategy')+1] != 'offload':
        raise ValueError('unexpected baseline strategy')
    tail[tail.index('--moe-strategy')+1]='hybrid'
    return ['numactl','--interleave=all','taskset','-c','1,3-23,25,27-47',*tail]

def alive_members(group):
    members=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit(): continue
        try:
            fields=(path/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==group and fields[0]!='Z': members.append(int(path.name))
        except (OSError,ValueError,IndexError):pass
    return members

def capture_birth(proc,d07):
    # Popen owns an unreaped child; the POSIX start_new_session exec handshake
    # completes before Popen returns. Independent OS session checks are fallback
    # evidence if the /proc birth reader transiently fails.
    try:
        identity=d07.process_identity(proc.pid)
    except OSError:
        identity=None
    if identity is not None:return identity
    try:
        pgid,session=os.getpgid(proc.pid),os.getsid(proc.pid)
    except ProcessLookupError:
        return None
    if pgid!=proc.pid or session!=proc.pid:raise RuntimeError('fresh child private session mismatch')
    return {'pid':proc.pid,'pgid':pgid,'session':session,'start_ticks':None,'proof':'Popen_unreaped_child_plus_OS_private_session'}

def idle(d07):
    d07.require_gpu_idle()
    if subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip():
        raise RuntimeError('compute process remains')
    for port in (8095,8096):
        with socket.socket() as sock: sock.bind(('172.16.108.9',port))

def cleanup(proc,birth,d07,output):
    errors=[]
    import signal
    try:
        current=d07.process_identity(proc.pid)
        if current and birth['start_ticks'] is not None and current['start_ticks']!=birth['start_ticks']:
            raise RuntimeError('owned PID recycled')
        if current:
            if current['pgid']!=proc.pid or current['session']!=proc.pid:
                raise RuntimeError('owned process escaped frozen session')
            os.killpg(proc.pid,signal.SIGTERM)
        end=time.monotonic()+30
        while alive_members(proc.pid) and time.monotonic()<end:time.sleep(.2)
        if alive_members(proc.pid):
            # A remaining member must retain the original owned process group/session.
            for pid in alive_members(proc.pid):
                identity=d07.process_identity(pid)
                if not identity or identity['session']!=proc.pid:raise RuntimeError('group ownership changed')
            os.killpg(proc.pid,signal.SIGKILL)
        proc.wait(timeout=10)
        end=time.monotonic()+15
        while True:
            try:
                if alive_members(proc.pid): raise RuntimeError('owned group remains')
                idle(d07);break
            except Exception:
                if time.monotonic()>=end:raise
                time.sleep(.2)
    except Exception as exc:errors.append(repr(exc))
    write(output/'cleanup.json',{'proved':not errors,'pid':proc.pid,'birth':birth,'errors':errors,'remaining_members':alive_members(proc.pid)})
    return not errors

def require_master_context(doc,deadline,d07):
    main_file=getattr(sys.modules.get('__main__'),'__file__',None)
    expected=Path(__file__).with_name('gpu_window.py').resolve()
    if main_file is None or Path(main_file).resolve()!=expected:
        raise RuntimeError('hybrid launch requires the actual GPU master entry')
    if hashlib.sha256(expected.read_bytes()).hexdigest()!=doc['controller_source_pins'][str(expected)]:
        raise RuntimeError('master source pin changed')
    events=[json.loads(line) for line in (Path(doc['output_root'])/'events.jsonl').read_text().splitlines()]
    starts=[row for row in events if row['event']=='window_started']
    if len(starts)!=1 or not any(row['event']=='481_stopped' for row in events):
        raise RuntimeError('master lifecycle has not stopped the frozen production owner')
    identity=d07.process_identity(os.getpid());recorded=starts[0]['master_identity']
    if identity is None or (identity['pid'],identity['start_ticks'])!=(recorded['pid'],recorded['start_ticks']):
        raise RuntimeError('actual master process birth differs')
    if time.time()>=deadline or deadline>starts[0]['deadline_epoch']-600:
        raise RuntimeError('hybrid deadline escapes restoration reserve')

def execute(path,deadline):
    doc=json.loads(Path(path).read_text())
    if Path(path).is_symlink() or Path(path).stat().st_mode&0o222 or not doc.get('admit'):
        raise ValueError('sealed root admission required')
    if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=doc['hybrid_controller_sha256']:
        raise ValueError('hybrid controller source pin changed')
    if doc['hybrid_argv']!=expected_argv(doc['baseline_owner']['argv']):
        raise ValueError('hybrid argv has unapproved differences')
    d07=load_d07();require_master_context(doc,deadline,d07);idle(d07)
    output=Path(doc['output_root'])/'hybrid_service';output.mkdir(exist_ok=False)
    argv=doc['hybrid_argv'];env=dict(os.environ)
    for key in list(env):
        if key.startswith('FT_DEV_'):env.pop(key)
    env.update(PYTHONPATH=doc['baseline_pythonpath'],MASTER_PORT='8096',CUDA_VISIBLE_DEVICES='0',PYTHONDONTWRITEBYTECODE='1')
    write(output/'argv_diff.json',{'baseline':doc['baseline_owner']['argv'],'actual':argv,'allowed_changes':['binding prefix','strategy offload to hybrid'],'exact_diff_passed':True,'commit':doc['commit']})
    proc=birth=None;error=None;safe=False
    log=(output/'serve.log').open('xb')
    owner=d07.take_d07_gpu_lock('D08-HYBRID-20261011',0)
    try:
        proc=subprocess.Popen(argv,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        birth=capture_birth(proc,d07)
        if not birth or birth['pgid']!=proc.pid or birth['session']!=proc.pid:
            raise RuntimeError('hybrid process identity missing')
        write(output/'owner.json',{'birth':birth,'argv':argv,'gpu_owner':owner})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        ready_limit=min(deadline-120,time.time()+240)
        while True:
            if proc.poll() is not None:raise RuntimeError('hybrid exited before readiness')
            if time.time()>=ready_limit:raise TimeoutError('hybrid readiness deadline')
            try:
                with opener.open('http://172.16.108.9:8095/health',timeout=3) as response:
                    health=json.load(response)
                if health.get('status')=='ok' and health.get('maintenance')=='serving':break
            except (OSError,ValueError):pass
            time.sleep(1)
        text=(output/'serve.log').read_text(errors='replace')
        import re
        sizes=re.findall(r'moe_cache_size[\s:=]+(\d+)',text)
        if not sizes:raise RuntimeError('moe_cache_auto actual slot count unavailable')
        actual=int(sizes[-1])
        fetch_lines=[line for line in text.splitlines() if 'moe-hybrid-max-fetch auto:' in line or 'fixed fetch cap' in line]
        if doc['max_fetch']==-1 and not fetch_lines:raise RuntimeError('actual hybrid auto fetch branch unavailable')
        resolved=1 if any('fixed fetch cap of 1' in line for line in fetch_lines) else None
        fraction_match=re.search(r'fetching ([0-9.]+)% of each decode step', '\n'.join(fetch_lines))
        if resolved is None and fraction_match is None and doc['max_fetch']<0:raise RuntimeError('hybrid auto cap semantics not parseable')
        fraction=float(fraction_match.group(1))/100 if fraction_match else None
        max_fetch=resolved if resolved is not None else (512 if fraction is not None else doc['max_fetch'])
        write(output/'runtime_config.json',{'moe_cache_size':actual,'confounded_more_than_5_percent':abs(actual/2700-1)>.05,'requested_moe_hybrid_max_fetch':doc['max_fetch'],'resolved_moe_hybrid_max_fetch':max_fetch,'resolved_fixed_fetch_cap':resolved,'fetch_fraction_rounded_from_log':fraction,'actual_fetch_branch_log':fetch_lines,'max_fetch_semantics':doc['max_fetch_semantics'],'fraction_mode_note':'when fraction is active, max_fetch=num_experts=512 is inert and the fraction determines per-step fetch count; log fraction rounded to 0.1 percent' if fraction is not None else 'fixed per-layer per-step PCIe expert cap; remaining misses run on CPU'})
        subprocess.run(['taskset','-pc',str(proc.pid)],stdout=(output/'affinity.txt').open('x'),check=True)
        subprocess.run(['numastat','-p',str(proc.pid)],stdout=(output/'numastat_before.txt').open('x'),check=True)
        subprocess.run(['ps','-L','-p',str(proc.pid),'-o','pid,tid,psr,pcpu,stat,comm'],stdout=(output/'threads_before.txt').open('x'),check=True)
        for tid in Path(f'/proc/{proc.pid}/task').iterdir():
            with (output/'thread_affinities.txt').open('a') as handle:
                subprocess.run(['taskset','-pc',tid.name],stdout=handle,stderr=subprocess.STDOUT,check=True)
        import threading
        stop_sampling=threading.Event()
        def sample_cpu():
            with (output/'cpu_during_calls.jsonl').open('x') as handle:
                while not stop_sampling.is_set():
                    snapshot=subprocess.run(['ps','-L','-p',str(proc.pid),'-o','pid,tid,psr,pcpu,stat,comm'],capture_output=True,text=True)
                    handle.write(json.dumps({'at':time.time(),'threads':snapshot.stdout,'returncode':snapshot.returncode})+'\n');handle.flush()
                    stop_sampling.wait(2)
        sampling=threading.Thread(target=sample_cpu,daemon=True);sampling.start()
        try:
            one=measure(path,'hybrid_single',proc.pid,birth['start_ticks'],deadline-60)
            if any(x['decode_tps']<7.8 for x in one):raise RuntimeError('abnormal single hybrid speed; stop arm')
            two=measure(path,'hybrid_two',proc.pid,birth['start_ticks'],deadline-60)
        finally:
            stop_sampling.set();sampling.join(timeout=5)
        speeds=[x['decode_tps'] for x in two]
        verdict=('abnormal' if min(speeds)<7.8 else 'valuable' if min(speeds)>=19.6 else 'close_D08' if max(speeds)<=17 else 'inconclusive')
        write(output/'measurement_result.json',{'verdict':verdict,'single':one,'two':two,'offload_two_reference':[16.951013,17.014054]})
        subprocess.run(['numastat','-p',str(proc.pid)],stdout=(output/'numastat_after.txt').open('x'),check=True)
    except BaseException as exc:error=repr(exc)
    finally:
        log.close()
        if proc is not None:
            if birth is None:
                try:birth=capture_birth(proc,d07)
                except Exception:pass
            if birth is not None:safe=cleanup(proc,birth,d07,output)
            elif proc.poll() is not None and not alive_members(proc.pid):
                try:idle(d07);safe=True
                except Exception:pass
        elif proc is None:
            try:idle(d07);safe=True
            except Exception:pass
        if safe:d07.release_d07_gpu_lock(owner)
        write(output/'terminal.json',{'measurement_error':error,'cleanup_proved':safe,'lock_retained':not safe,'status':'complete' if error is None and safe else 'failed_harness'})
    if not safe:raise RuntimeError('owned cleanup failed, preserve lock and inspect')
    return error is None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');parser.add_argument('--admission');parser.add_argument('--deadline',type=float);args=parser.parse_args()
    if not args.run:print('inert');return
    parser.error('hybrid is a master-only component; use the root-admitted gpu_window entry')

if __name__=='__main__':main()
