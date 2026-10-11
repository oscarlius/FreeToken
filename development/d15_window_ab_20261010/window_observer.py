"""D15 multiprocessing-safe entry for R046c native token receipts."""
from __future__ import annotations
import importlib.util, json, os, time, threading
from pathlib import Path
SOURCE=Path('/data2/FreeToken/development/r046c_t06_ordinary_startup_v4.py')
if not SOURCE.is_file() or SOURCE.is_symlink(): raise RuntimeError('R046c observer source unavailable')
spec=importlib.util.spec_from_file_location('d15_r046c_observer',SOURCE); module=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
install=module.install
def install_prefill_events(directory: Path) -> None:
    """Async CUDA stream intervals; never synchronizes Engine.forward_batch."""
    import torch
    from freetoken.engine.engine import Engine
    original=Engine.forward_batch
    pending=[]; lock=threading.Lock(); started=False
    def drain():
        while True:
            with lock:
                ready=[row for row in pending if row[1].query()]
                for row in ready:pending.remove(row)
            for start,end,metadata in ready:
                metadata.update(elapsed_ms=start.elapsed_time(end),completed_monotonic_ns=time.monotonic_ns())
                with (directory/'prefill_events.jsonl').open('a') as f:f.write(json.dumps(metadata,sort_keys=True)+'\n')
            time.sleep(.01)
    def observed(self,batch,*args,**kwargs):
        nonlocal started
        if not getattr(batch,'is_prefill',False): return original(self,batch,*args,**kwargs)
        start,end=torch.cuda.Event(enable_timing=True),torch.cuda.Event(enable_timing=True)
        start.record(self.stream);value=original(self,batch,*args,**kwargs);end.record(self.stream)
        uids=[getattr(x,'uid',None) for x in getattr(batch,'reqs',())]
        with lock:pending.append((start,end,{'schema':'d15_prefill_stream_interval/v2','uids':uids,'recorded_time_ns':time.time_ns(),'scope':'Engine.forward_batch including sampling/copy enqueue and CPU waits','additional_synchronization':False}))
        if not started:
            started=True;threading.Thread(target=drain,daemon=True,name='d15_event_receipts').start()
        return value
    Engine.forward_batch=observed
if __name__=='__mp_main__':
    target=os.environ.get('R046C_T06_OBSERVER_DIR')
    if not target: raise RuntimeError('D15 worker lacks observer directory binding')
    install(Path(target));install_prefill_events(Path(target))
elif __name__=='__main__': raise SystemExit(module.main())
