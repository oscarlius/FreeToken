"""Fresh offload D0 service: the sole generation is frozen X lane0."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import time
import urllib.request

from hybrid_service import load_d07, idle, capture_birth, cleanup, require_master_context
from window_measure import write, run as measure


def execute(path, deadline):
    doc=json.loads(Path(path).read_text())
    own=Path(__file__).resolve()
    if doc.get('controller_source_pins',{}).get(str(own))!=hashlib.sha256(own.read_bytes()).hexdigest():
        raise ValueError('D0 service source pin differs or missing')
    d07=load_d07();require_master_context(doc,deadline,d07);idle(d07)
    output=Path(doc['output_root'])/'d0_service';output.mkdir()
    env={k:v for k,v in os.environ.items() if not k.startswith('FT_DEV_')}
    env.update(PYTHONPATH=doc['baseline_pythonpath'],MASTER_PORT='8096',CUDA_VISIBLE_DEVICES='0',
               FT_DEV_D0='1',FT_DEV_D0_PATH=str(output/'d0'),PYTHONDONTWRITEBYTECODE='1')
    proc=birth=None;safe=False;error=None
    owner=d07.take_d07_gpu_lock('D10-SINGLE-D0-RETRY2-20261011',0)
    log=(output/'serve.log').open('xb')
    try:
        proc=subprocess.Popen(doc['baseline_owner']['argv'],cwd=output,env=env,
                              stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        birth=capture_birth(proc,d07)
        if not birth or birth['pgid']!=proc.pid or birth['session']!=proc.pid:
            raise RuntimeError('D0 owned birth unavailable')
        write(output/'owner.json',{'birth':birth,'gpu_owner':owner,'argv':doc['baseline_owner']['argv'],
                                  'diagnostic_env':{'FT_DEV_D0':'1','FT_DEV_D0_PATH':str(output/'d0')}})
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        ready=min(deadline-120,time.time()+600);progress=0
        while True:
            if proc.poll() is not None:raise RuntimeError('D0 exited before readiness')
            if time.time()>=ready:raise TimeoutError('D0 readiness deadline600s')
            if time.time()-progress>=30:
                with (output/'loading_progress.jsonl').open('a') as handle:
                    handle.write(json.dumps({'at':time.time(),'tail':(output/'serve.log').read_text(errors='replace')[-3000:]})+'\n')
                progress=time.time()
            try:
                with opener.open('http://172.16.108.9:8095/health',timeout=3) as response:health=json.load(response)
                if health.get('status')=='ok' and health.get('maintenance')=='serving':break
            except (OSError,ValueError):pass
            time.sleep(1)
        # No warmup or generation readiness probe is permitted here.
        measure(path,'d0_single',proc.pid,birth['start_ticks'],deadline-60)
    except BaseException as exc:error=repr(exc)
    finally:
        log.close()
        if proc is not None and birth is not None:safe=cleanup(proc,birth,d07,output)
        elif proc is None:
            try:idle(d07);safe=True
            except Exception:pass
        if safe:d07.release_d07_gpu_lock(owner)
        write(output/'terminal.json',{'status':'complete' if error is None and safe else 'failed_harness',
                                      'error':error,'cleanup_proved':safe,'lock_retained':not safe})
    if not safe:raise RuntimeError('D0 cleanup failed; retain exact owner lock')
    return error is None
