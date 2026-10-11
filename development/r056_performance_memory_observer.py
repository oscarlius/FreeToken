"""R056 model-worker memory observations; no route, pause, or D0 hooks."""
import functools
import json
import os
from pathlib import Path
import sys
import time


def birth():
    pid=os.getpid();fields=(Path('/proc')/str(pid)/'stat').read_text().rpartition(') ')[2].split()
    ticks=int(fields[19])
    return {'pid':pid,'start_ticks':ticks,'execution_id':f'{pid}:{ticks}',
            'pgid':int(fields[2]),'session':int(fields[3])}


def memory(event,uid=None,**extra):
    import torch
    worker=birth();row={'schema':'ft_r056_model_memory/v1','event':event,'uid':None if uid is None else str(uid),
                       'time_ns':time.time_ns(),'service_birth':json.loads(os.environ['R056_SERVICE_BIRTH']),
                       'worker_birth':worker,'device':0,**extra}
    try:
        free,total=torch.cuda.mem_get_info(0)
        row.update(free_bytes=int(free),total_bytes=int(total),
                   allocated_bytes=int(torch.cuda.memory_allocated(0)),reserved_bytes=int(torch.cuda.memory_reserved(0)),
                   cumulative_allocated_peak_bytes=int(torch.cuda.max_memory_allocated(0)),
                   cumulative_reserved_peak_bytes=int(torch.cuda.max_memory_reserved(0)))
    except BaseException as error:
        row['error']=repr(error)
    with Path(os.environ['R056_MODEL_MEMORY']).open('a',encoding='utf-8') as out:
        out.write(json.dumps(row,sort_keys=True)+'\n')
    if event=='model_loaded':print('R056_MODEL_LOADED '+json.dumps(row,sort_keys=True),flush=True)


def install():
    from freetoken.engine.engine import Engine
    initialize=Engine.__init__
    @functools.wraps(initialize)
    def loaded(self,*args,**kwargs):
        result=initialize(self,*args,**kwargs)
        buffer=self.kv_cache._kv_buffer
        memory('model_loaded',kv_storage_bytes=int(buffer.numel()*buffer.element_size()),
               kv_storage_shape=list(buffer.shape),num_pages=int(self.num_pages),max_seq_len=int(self.max_seq_len))
        return result
    Engine.__init__=loaded
    if os.environ.get('R056_OBSERVE_REQUESTS')!='1':return
    from freetoken.scheduler.scheduler import Scheduler
    from freetoken.scheduler.io import SchedulerIOMixin
    receive=Scheduler._process_one_msg;deliver=SchedulerIOMixin._reply_tokenizer_rank0
    @functools.wraps(receive)
    def request(self,msg,*args,**kwargs):
        if type(msg).__name__=='UserMsg':memory('request_before',msg.uid)
        return receive(self,msg,*args,**kwargs)
    @functools.wraps(deliver)
    def response(self,messages,*args,**kwargs):
        for msg in messages:
            if type(msg).__name__=='DetokenizeMsg' and bool(msg.finished):memory('request_after',msg.uid)
        return deliver(self,messages,*args,**kwargs)
    Scheduler._process_one_msg=request;SchedulerIOMixin._reply_tokenizer_rank0=response


if __name__ in ('__main__','__mp_main__'):
    # Spawn replays this entry before importing the worker target. Preserve the
    # parent's identity while installing hooks in each model-worker process.
    if 'R056_SERVICE_BIRTH' not in os.environ:
        os.environ['R056_SERVICE_BIRTH']=json.dumps(birth(),sort_keys=True)
    install()
    if __name__=='__main__':
        from freetoken.cli import main
        sys.argv=['ft',*sys.argv[1:]]
        main()
