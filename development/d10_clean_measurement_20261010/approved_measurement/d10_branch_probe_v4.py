"""External observation; sample only after Scheduler's existing copy drain."""
from __future__ import annotations
import json, os, time
from pathlib import Path

def _birth():
    stat=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':os.getpid(),'start_ticks':int(stat[19])}

def install():
    from freetoken.engine.engine import Engine
    from freetoken.scheduler.scheduler import Scheduler
    if getattr(Engine,'_d10_v4_probe_installed',False): return
    branch=Engine._forward_d10_staggered_decode
    forward=Engine.forward_batch
    drain=Scheduler._process_last_data
    event=Path(os.environ['FT_D10_BRANCH_EVENT'])
    trace=Path(os.environ['FT_D10_METRICS_TRACE'])
    samples=trace.with_name('raw_d10_samples.jsonl')
    pending={}
    def emit(path,rows):
        if not rows:return
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a',encoding='utf-8') as h:
            for row in rows:h.write(json.dumps(row,sort_keys=True)+'\n')
    def observed(self,batch,*args,**kwargs):
        result=branch(self,batch,*args,**kwargs)
        uids=[int(r.uid) for r in batch.reqs]
        step=getattr(self,'_d10_measure_step',0)
        self._d10_measure_step=step+1
        self._d10_measure_tag={'step':step,'uids':uids}
        if not event.exists():
            event.parent.mkdir(parents=True,exist_ok=True)
            event.write_text(json.dumps({'schema':'ft_d10_branch_event/v4',
                'method':'Engine._forward_d10_staggered_decode','entered':True,
                'actual_batch_reqs':len(batch.reqs),
                'actual_can_use_d10_staggered':bool(self._can_use_d10_staggered(batch,getattr(self.ctx,'route_tracer',None))),
                'candidate_commit':os.environ['FT_D10_CANDIDATE'],
                'engine_birth':_birth(),'engine_pgid':os.getpgid(os.getpid()),
                'at_unix':time.time()},sort_keys=True)+'\n',encoding='utf-8')
        return result
    def bound_forward(self,*args,**kwargs):
        self._d10_measure_tag=None
        result=forward(self,*args,**kwargs)
        tag=self._d10_measure_tag
        if tag is not None:pending[id(result)]=dict(tag)
        return result
    def observed_drain(self,last_data):
        tag=None if last_data is None else pending.pop(id(last_data[1]),None)
        before=[]
        if tag is not None:
            batch=last_data[0].batch
            before=[(r,int(r.uid),int(r.input_ids.numel())) for r in batch.reqs]
        # Original method already waits for copy_done, samples CPU IDs, and
        # appends only emitted tokens. No added CUDA wait/synchronization.
        result=drain(self,last_data)
        if tag is not None:
            tokens=[]
            for req,uid,n in before:
                after=int(req.input_ids.numel())
                if after==n+1:tokens.append({'uid':uid,'token_id':int(req.input_ids[-1].item())})
                elif after!=n:raise RuntimeError('D10 emitted length is not a single token')
            emit(samples,[{**tag,'tokens':tokens,'completed_monotonic_ns':time.monotonic_ns(),
                'timestamp_source':'after_existing_scheduler_copy_done_and_host_append'}])
            emit(trace,self.engine.collect_d10_step_metrics(wait=False))
        return result
    Engine._forward_d10_staggered_decode=observed
    Engine.forward_batch=bound_forward
    Scheduler._process_last_data=observed_drain
    Engine._d10_v4_probe_installed=True
