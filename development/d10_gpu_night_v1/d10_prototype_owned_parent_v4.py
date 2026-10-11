"""One-service D10 v4 prototype with real `ft serve` and spawn-worker proof."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken'); WT = ROOT / 'wt/d10-staggered-v1'
RID = 'E2-D10-PROTOTYPE-night-20261010-v4'
CANDIDATE = '22ff3a389eae3724cdca9a45f2e19577082a2032'; PARENT = '481d3a7074818b0b41f27d90a5cb0de6c6f2cf9'
FLAG = '--d10-staggered-decode'; MAX_CALLS = 8
PROVENANCE = HERE / 'd10_native_provenance_v2.json'

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def put(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as out: json.dump(value, out, sort_keys=True, indent=2); out.write('\n')
def load(path, name):
    spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
def d07():
    mod=load(HERE/'d07_g3g4_prepare.py','d10v4_d07'); mod.CANDIDATE=CANDIDATE; mod.RID=RID; return mod
def runner(): return load(HERE/'d10_aiperf_runner_v5.py','d10v4_runner')
def parser(): return load(HERE/'d10_aiperf_parse_v4.py','d10v4_parser')
def birth(pid=None):
    pid=os.getpid() if pid is None else pid; return {'pid':pid,'start_ticks':int(Path(f'/proc/{pid}/stat').read_text().split()[21])}
def reserve(port):
    s=socket.socket(); s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); s.bind(('127.0.0.1',port)); return s
def service_argv(service):
    argv=service['argv']; api=service['api_port']
    if argv[:2] != ['ft','serve'] or argv.count('--port') != 1 or int(argv[argv.index('--port')+1]) != api or FLAG not in argv:
        raise RuntimeError('service must be frozen ft serve argv with API port and D10 flag')
    if service.get('tcpstore_port') != api + 1 or service.get('endpoint') != f'http://127.0.0.1:{api}':
        raise RuntimeError('candidate TCPStore is API port + 1, not a CLI/env setting')
    if any('tcpstore' in str(x).lower() for x in argv): raise RuntimeError('TCPStore is not a server CLI parameter')
    return argv
def require_admission(path, run):
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222: raise RuntimeError('sealed root admission required')
    doc=run.require_admission(path)
    want={'admit':True,'prototype_rid':RID,'candidate':CANDIDATE,'d10_flag':FLAG,'calls_max':MAX_CALLS,'services_max':1}
    if any(doc.get(k)!=v for k,v in want.items()): raise RuntimeError('v4 admission binding differs')
    service_argv(doc['service'])
    # All injected/bootstrap/probe sources are pinned, as are native/T16 and D09 terminals.
    files=doc.get('source_sha256',{})
    for name in ('d10_prototype_owned_parent_v4.py','d10_branch_startup_v4.py','d10_branch_probe_v4.py','d10_aiperf_parse_v4.py','d10_aiperf_runner_v5.py'):
        if files.get(name)!=sha(HERE/name): raise RuntimeError('source admission SHA differs: '+name)
    if doc.get('native_provenance_sha256') != sha(PROVENANCE) or not doc.get('t16_closure'): raise RuntimeError('native/T16 closure missing')
    terms=doc.get('d09_completed_terminals')
    if not isinstance(terms,list) or not terms: raise RuntimeError('prior D09 terminal safe-cleanup binding missing')
    return doc
def child_argv(admission,batch,receipt): return [str(ROOT/'venv/bin/python'),str(HERE/'d10_prototype_owned_parent_v4.py'),'--run','--owned-child','--admission',str(admission),'--batch',str(batch),'--launch-receipt',str(receipt)]
def controller(admission,deps=None):
    gate=deps.gate if deps else d07(); run=deps.run if deps else runner(); doc=require_admission(admission,run)
    if gate.LOCK.exists() or gate.LOCK.is_symlink(): raise RuntimeError('foreign GPU lock exists')
    life=gate.load_owned_lifecycle(); helper=life.verified_module(ROOT/'runs/plan_batches/e2_launch.py',gate.ATOMIC_HELPER_SHA,'d10v4')
    batch=helper.next_batch(gate.ROUNDS); receipt=(deps.root/'launch.json') if deps else ROOT/'runs/dev_D10'/f'prototype_{batch}.json'
    # reserve_process owns publication; after it returns, accept only launched child birth.
    reserved={'schema':'ft_d10_prototype_launch/v4','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,'controller':gate.process_birth(),'argv_sha256':gate.argv_sha256(child_argv(admission,batch,receipt))}
    got=life.reserve_process(helper,batch,RID,child_argv(admission,batch,receipt),receipt,reserved)
    expected=gate.process_identity(got['batch_pid'])
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if receipt.is_file():
            value=json.loads(receipt.read_text())
            if value.get('state')=='launched' and value.get('batch_pid')==got['batch_pid'] and value.get('child')==expected: return value
        time.sleep(.05)
    raise RuntimeError('reserved receipt was not atomically published with child birth')
class Default:
    def __init__(self): self.gate=d07(); self.run=runner()
    def start(self,argv,cwd,env,log):
        with log.open('xb') as out:return subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
    def health(self,endpoint):
        with build_opener(ProxyHandler({})).open(endpoint+'/health',timeout=10) as r:return json.loads(r.read())
    def aiperf(self,admission,endpoint,out):
        self.run.require_admission(admission); out.mkdir()
        for i in range(4):
            command=self.run.argv(endpoint,str(out/f'profile{i}'),self.run.ORIGINAL if i<2 else self.run.INPUT); put(out/f'profile{i}.command.json',{'argv':command})
            with (out/f'profile{i}.stdout.log').open('xb') as log: result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=1800,env=dict(os.environ,NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost'))
            put(out/f'profile{i}.exit.json',{'exit_code':result.returncode});
            if result.returncode: raise RuntimeError('AIPerf request error')
    def stop(self,p): self.gate.load_owned_lifecycle().stop_owned_process(p,120,30)
    def alive(self,p): return self.gate.load_owned_lifecycle().owned_group_alive(p)
def child(admission,batch,receipt,deps=None):
    deps=deps or Default(); gate=deps.gate; doc=require_admission(admission,deps.run); service=doc['service']; argv=service_argv(service); output=Path(doc['prototype_output'])
    if output.exists() or output.is_symlink(): raise RuntimeError('fresh output directory required')
    data=json.loads(receipt.read_text()); expected=gate.process_birth()
    if data.get('state')!='launched' or data.get('batch')!=batch or data.get('child')!=expected: raise RuntimeError('launch receipt child-birth mismatch')
    owner=gate.take_d07_gpu_lock(RID,batch); proc=None; held=None; error=None; cleanup=None
    try:
        output.mkdir(); put(output/'admission_snapshot.json',doc)
        held=reserve(service['api_port']); put(output/'port_reservation.json',{'api_port':service['api_port'],'tcpstore_port':service['api_port']+1}); held.close(); held=None
        env=gate.clean_environment(WT); event=output/'d10_branch_event.json'; env.update({'PYTHONPATH':str(HERE)+os.pathsep+str(WT/'python'),'FT_D10_BRANCH_EVENT':str(event),'FT_D10_CANDIDATE':CANDIDATE,'PYTHONDONTWRITEBYTECODE':'1'})
        launch=[str(ROOT/'venv/bin/python'),str(HERE/'d10_branch_startup_v4.py'),*argv[2:]]
        proc=deps.start(launch,service['cwd'],env,output/'serve.log'); put(output/'service_identity.json',{'group_leader_birth':gate.process_identity(proc.pid),'launch_argv':launch,'service_argv':argv})
        deadline=time.monotonic()+1800
        while time.monotonic()<deadline:
            if proc.poll() is not None: raise RuntimeError('owned service exited before health')
            try:
                if deps.health(service['endpoint']).get('status')=='ok': break
            except OSError: time.sleep(2)
        else: raise TimeoutError('health readiness timeout')
        deps.aiperf(admission,service['endpoint'],output/'aiperf'); rows=parser().validate_profiles(output/'aiperf')
        event_doc=json.loads(event.read_text())
        if event_doc.get('method')!='Engine._forward_d10_staggered_decode' or event_doc.get('actual_batch_reqs')!=2 or not event_doc.get('actual_can_use_d10_staggered') or event_doc.get('candidate_commit')!=CANDIDATE or event_doc.get('engine_pgid')!=proc.pid: raise RuntimeError('actual D10 engine-worker branch/group proof absent')
        put(output/'raw_response_records.json',{'profiles':rows,'actual_generation_calls':8,'engine_birth':event_doc['engine_birth']})
    except BaseException as exc: error=repr(exc)
    finally:
        try:
            if proc: deps.stop(proc); assert not deps.alive(proc.pid)
            if held: held.close()
            gate.require_gpu_idle(); check=reserve(service['api_port']); check.close()
        except BaseException as exc: cleanup=repr(exc)
        terminal={'rid':RID,'verdict':'not_met' if not error and not cleanup else 'failed_harness','error':error,'cleanup_error':cleanup,'actual_services':1,'actual_generation_calls':8,'product_acceptance':False,'independent_terminal_review_required':True,'lock_retained':bool(cleanup)}
        if output.exists(): put(output/'terminal.json',terminal)
        if not cleanup: gate.release_d07_gpu_lock(owner)
    if cleanup: raise RuntimeError('unsafe cleanup preserves GPU lock: '+cleanup)
    if error: raise RuntimeError(error)
    return output/'terminal.json'
def main():
    p=argparse.ArgumentParser(); p.add_argument('--run',action='store_true');p.add_argument('--owned-child',action='store_true');p.add_argument('--admission',type=Path);p.add_argument('--batch',type=int);p.add_argument('--launch-receipt',type=Path);a=p.parse_args()
    if a.run and a.owned_child and a.admission and a.batch and a.launch_receipt: child(a.admission,a.batch,a.launch_receipt)
    elif a.run and a.admission and not a.owned_child: controller(a.admission)
    else:p.error('select guarded --run --admission')
if __name__=='__main__':main()
