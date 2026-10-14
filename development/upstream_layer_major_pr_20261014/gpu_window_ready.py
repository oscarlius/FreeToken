"""Approved one-shot measurement window with owned cleanup and E3 restoration."""
from __future__ import annotations

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
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
ACTIVE = Path('/data2/FreeToken/run/production.active.json')
HELPER_SHA = 'c4a28aaa602536b3c1f5b94a77f9e18cd48443867f3c0cc8a029ab0531bbddd0'
MODEL = 'Qwen3.8-Flash-Next-NVFP4'
MODEL_PATH = '/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay'
OLD_PYTHON = '/data2/FreeToken/venv/bin/python'
NEW_PYTHON = str(ROOT/'main-venv/bin/python')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_tree(archive, source, expected_sha, expected_commit, native_modules=None):
    if archive.is_symlink() or source.is_symlink() or sha(archive)!=expected_sha:
        raise RuntimeError('Authorized archive or source root differs')
    with zipfile.ZipFile(archive) as bundle:
        members={entry.filename for entry in bundle.infolist() if not entry.is_dir()}
        if bundle.comment.decode()!=expected_commit:
            raise RuntimeError('Git archive commit binding differs')
        for entry in bundle.infolist():
            if entry.is_dir():continue
            path=source/entry.filename
            if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
                raise RuntimeError('Source path escaped archive')
            if hashlib.sha256(path.read_bytes()).digest()!=hashlib.sha256(bundle.read(entry)).digest():
                raise RuntimeError('Source changed: '+entry.filename)
        for path in (source/'python').rglob('*'):
            if path.is_dir():continue
            name=path.relative_to(source).as_posix()
            if name in members:continue
            expected=(native_modules or {}).get(name)
            if path.is_symlink() or expected is None or sha(path)!=expected:
                raise RuntimeError('Unexpected or unpinned importable file: '+name)
    return {'commit':expected_commit,'archive_sha256':expected_sha}


def remaining(deadline):
    value = deadline-time.time()
    if value <= 0:
        raise TimeoutError('Absolute window deadline reached')
    return value


def service_command(enabled=False):
    argv = ['taskset','-c','1,3-47',NEW_PYTHON,'-m','freetoken.cli','serve',
        '--model-path',MODEL_PATH,'--served-model-name',MODEL,'--host','127.0.0.1','--port','8095',
        '--memory-ratio','0.88','--moe-cache-auto','--moe-prefill-hit-d2d',
        '--ple-backend','pinned','--moe-strategy','offload','--quant-backend','moe.nvfp4=triton',
        '--max-running-requests','2','--cuda-graph-max-bs','2','--kv-reserve-tokens','98304',
        '--max-seq-len-override','98304','--max-prefill-length','4096','--enable-cache-report']
    if enabled: argv.append('--prefill-layer-major')
    return argv


def measurement_env(source, native):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('FT_','RELEASE_SMOKE_')) or key in ('PYTHONPATH','CUDA_VISIBLE_DEVICES'):
            env.pop(key)
    env.update(PYTHONPATH=':'.join((str(ROOT/'observer'),str(ROOT),str(source/'python'))),
        FT_UPSTREAM_NATIVE_IDS=str(native),CUDA_VISIBLE_DEVICES='0',
        CUDA_HOME='/usr/local/cuda-13.0',VIRTUAL_ENV=str(ROOT/'main-venv'),
        PATH=str(ROOT/'main-venv/bin')+':/usr/local/cuda-13.0/bin:'+env['PATH'],
        PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',MASTER_PORT='8096')
    return env


def json_new(path, value):
    with path.open('x') as handle:json.dump(value,handle,indent=2,ensure_ascii=False)


def log(event, **fields):
    row={'at':time.time(),'event':event,**fields}
    with (ROOT/'window_events.jsonl').open('a') as handle:handle.write(json.dumps(row)+'\n')
    stamp=__import__('datetime').datetime.now(__import__('datetime').timezone(__import__('datetime').timedelta(hours=8))).isoformat()
    with Path('/data2/FreeToken/plan/COORDINATION_LOG.md').open('a') as handle:
        handle.write('\n| '+stamp+' | Codex | UPSTREAM_LM_PR_'+event.upper()+' | '+json.dumps(fields)+' |\n')
    print(json.dumps(row),flush=True)


def snapshot(path):
    threads=0
    for task in Path('/proc').glob('[0-9]*/task/[0-9]*/stat'):
        try:
            if task.read_text().rsplit(')',1)[1].split()[0]=='R':threads+=1
        except OSError:pass
    json_new(path,{'at':time.time(),'uptime':subprocess.check_output(['uptime'],text=True,timeout=5),
        'r_state_threads':threads,'gpu':subprocess.check_output(['nvidia-smi',
        '--query-gpu=memory.used,memory.total,utilization.gpu','--format=csv,noheader'],text=True,timeout=5)})


def wait_ready(process, deadline):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    deadline=min(deadline,time.time()+300)
    while True:
        remaining(deadline)
        if process.poll() is not None:raise RuntimeError('Service exited before readiness: '+str(process.returncode))
        try:
            with opener.open('http://127.0.0.1:8095/health',timeout=min(5,remaining(deadline))) as response:
                value=json.load(response)
            if value.get('status')=='ok' and value.get('maintenance')=='serving':return value
            if value.get('status')=='error':raise RuntimeError('Service health reports error: '+str(value))
        except OSError:pass
        time.sleep(min(1,remaining(deadline)))


def native_receipts(path):
    values=[json.loads(line) for line in path.read_text().splitlines()]
    if len(values)!=9 or not all(v.get('ok') for v in values):raise RuntimeError('Incomplete nine-call arm')
    return {v['label']:v for v in values}


def compare(reference, candidate):
    if set(reference)!=set(candidate):raise RuntimeError('Request label sets differ')
    for label in reference:
        if reference[label]['native_token_ids']!=candidate[label]['native_token_ids']:
            raise ValueError('not_met: native output IDs differ at '+label)


def run():
    sys.path.insert(0,str(ROOT))
    import recovery_guard
    auth=json.loads((ROOT/'WINDOW_AUTHORIZATION_SEALED.json').read_text())
    assert auth['authorized'] is True and auth['measurement_calls']==27 and auth['recovery_sdk_calls']==2
    recovery_guard.verify_sources(auth)
    recovery_guard.verify_active(auth['active_snapshot'],json.loads(ACTIVE.read_text()))
    helper_path=Path(auth['frozen_ops']['path']).parent/'d07_g3g4_prepare.py'
    assert sha(helper_path)==HELPER_SHA
    helper=load(helper_path,'window_d07')
    lifecycle=helper.load_owned_lifecycle()
    for key in ('supervisor','service'):
        wanted=auth['active_snapshot'][key]
        live=helper.process_identity(wanted['pid'])
        assert live and all(live[k]==wanted[k] for k in ('pid','start_ticks','pgid','session','execution_id'))
    restore=ROOT/'restore_e3'
    approval=json.loads((restore/'DEPLOYMENT_APPROVAL.json').read_text())
    gate=load(restore/'deploy_conditional.py','new_restore_gate')
    gate.require_root_final_review(approval)
    assert not Path(approval['run_dir']).exists()
    assert sha(ROOT/'inputs.json')==auth['inputs_sha256']
    source_proofs={
        'main':verify_tree(ROOT/'main_9c635a1.zip',ROOT/'main_9c635a1',auth['main_archive_sha256'],auth['main_commit'],auth['native_modules']),
        'candidate':verify_tree(ROOT/'candidate_63858fa.zip',ROOT/'candidate_63858fa',auth['candidate_archive_sha256'],auth['candidate_commit'],auth['native_modules'])}
    for name in ('WINDOW_RUN_CONSUMED.json','GPU_WINDOW_TERMINAL.json','gpu_results','stop_e3.log',
                 'restore_start.log','restore_smoke.log','window_events.jsonl'):
        if (ROOT/name).exists():raise RuntimeError('One-shot artifact already exists: '+name)
    json_new(ROOT/'WINDOW_RUN_CONSUMED.json',{'at':time.time(),'pid':os.getpid(),
        'authorization_sha256':sha(ROOT/'WINDOW_AUTHORIZATION_SEALED.json'),'source_proofs':source_proofs})
    result={'classification':'pre_gpu_failed','arms':[],'restored':False}
    stop_attempted=False; lock=None; measurement_deadline=None; window_deadline=None
    old_handlers={}

    def control(argv, deadline, output):
        process=None
        try:
            with output.open('xb') as handle:
                process=subprocess.Popen(argv,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
                rc=process.wait(timeout=remaining(deadline))
                if rc:raise RuntimeError('Control command failed: '+str(argv)+' rc='+str(rc))
        finally:
            if process is not None:lifecycle.stop_owned_process(process,10,5)

    def abort(*_):raise KeyboardInterrupt('Window interrupted; restore production')
    for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):old_handlers[sig]=signal.signal(sig,abort)
    try:
        start=time.time();measurement_deadline=start+1800;window_deadline=start+2700
        log('window_start',measurement_deadline=measurement_deadline,window_deadline=window_deadline)
        stop_attempted=True
        control([OLD_PYTHON,auth['old_stop_adapter']],min(measurement_deadline,time.time()+260),ROOT/'stop_e3.log')
        assert not ACTIVE.exists() and not helper.LOCK.exists()
        lock=helper.take_d07_gpu_lock('UPSTREAM-LM-PR-20261014',0)
        helper.require_gpu_idle()
        output=ROOT/'gpu_results';output.mkdir()
        main=None
        for name,source,enabled in (('main',ROOT/'main_9c635a1',False),
                                   ('candidate_off',ROOT/'candidate_63858fa',False),
                                   ('candidate_on',ROOT/'candidate_63858fa',True)):
            remaining(measurement_deadline)
            directory=output/name;directory.mkdir()
            native=directory/'native'
            env=measurement_env(source,native)
            argv=service_command(enabled)
            json_new(directory/'invocation.json',{'argv':argv,'source':str(source),'enabled':enabled})
            service=None
            log('arm_start',arm=name)
            try:
                with (directory/'serve.log').open('xb') as handle:
                    service=subprocess.Popen(argv,cwd=directory,env=env,stdout=handle,stderr=subprocess.STDOUT,start_new_session=True)
                json_new(directory/'owner.json',helper.process_identity(service.pid))
                json_new(directory/'health.json',wait_ready(service,measurement_deadline))
                snapshot(directory/'environment_before.json')
                client=[OLD_PYTHON,str(ROOT/'gpu_client.py'),'run-arm','--base-url','http://127.0.0.1:8095',
                    '--model',MODEL,'--inputs',str(ROOT/'inputs.json'),'--output',str(output),'--arm',name,
                    '--native-dir',str(native),'--deadline-unix',str(measurement_deadline)]
                control(client,measurement_deadline,directory/'client.log')
                values=native_receipts(directory/'receipts.jsonl')
                if main is None:main=values
                else:compare(main,values)
                snapshot(directory/'environment_after.json')
                result['arms'].append({'arm':name,'classification':'kept','calls':9})
                log('arm_terminal',arm=name,classification='kept',calls=9)
            except BaseException as exc:
                result['arms'].append({'arm':name,'classification':'not_met' if isinstance(exc,ValueError) else 'failed_harness','error':repr(exc)})
                raise
            finally:
                if service is not None:lifecycle.stop_owned_process(service,120,30)
                helper.require_gpu_idle()
        result['classification']='kept'
    except BaseException as exc:
        result.update(classification='not_met' if isinstance(exc,ValueError) else 'failed_harness',error=repr(exc))
        log('measurement_terminal',**result)
    finally:
        if lock is not None:
            try:helper.release_d07_gpu_lock(lock)
            except BaseException as exc:
                result['lock_release_error']=repr(exc)
        if stop_attempted:
            for sig in old_handlers:signal.signal(sig,signal.SIG_IGN)
            try:
                if ACTIVE.exists():
                    active=json.loads(ACTIVE.read_text())
                    recovery_guard.verify_active(auth['active_snapshot'],active)
                    result['restored']=False
                    result['original_production_left_running']=True
                else:
                    helper.require_gpu_idle()
                    control([OLD_PYTHON,str(restore/'start_approved_release.py')],window_deadline,ROOT/'restore_start.log')
                    control([OLD_PYTHON,str(restore/'wait_release_and_smoke.py')],window_deadline,ROOT/'restore_smoke.log')
                    result['restored']=True
                    result['recovery_approval_id']=approval['approval_id']
                    log('production_restored',approval_id=approval['approval_id'],sdk_calls=2)
            except BaseException as exc:
                result['restoration_error']=repr(exc)
                result['restored']=False
                log('restoration_failed',error=repr(exc))
        result['finished_at']=time.time()
        json_new(ROOT/'GPU_WINDOW_TERMINAL.json',result)
        for sig,handler in old_handlers.items():signal.signal(sig,handler)
    return 0 if result['classification']=='kept' and result['restored'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if not args.run:raise SystemExit('Inert: supply --run only for the user-approved window')
    raise SystemExit(run())
