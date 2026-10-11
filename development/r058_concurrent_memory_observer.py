"""External-only R058 model-worker memory observer; installed by the launch wrapper."""
from __future__ import annotations

import json
import os
from pathlib import Path
import time
import functools
import sys
import threading

def birth():
    pid=os.getpid(); fields=(Path('/proc')/str(pid)/'stat').read_text().rpartition(') ')[2].split(); ticks=int(fields[19])
    return {'pid':pid,'start_ticks':ticks,'execution_id':f'{pid}:{ticks}'}


def sample(event: str, uid=None, **extra) -> dict:
    import torch
    free, total = torch.cuda.mem_get_info(0)
    return {'schema': 'ft_r058_model_memory/v1', 'event': event, 'uid': None if uid is None else str(uid),
            'time_ns': time.time_ns(), 'free_bytes': int(free), 'total_bytes': int(total),
            'allocated_bytes': int(torch.cuda.memory_allocated(0)), 'reserved_bytes': int(torch.cuda.memory_reserved(0)),
            'peak_allocated_bytes':int(torch.cuda.max_memory_allocated(0)), 'peak_reserved_bytes':int(torch.cuda.max_memory_reserved(0)),
            'worker_birth':birth(), 'service_birth':json.loads(os.environ['R058_SERVICE_BIRTH']), **extra}


def append(event: str, uid=None, **extra) -> None:
    row = sample(event, uid, **extra)
    with Path(os.environ['R058_MODEL_MEMORY']).open('a', encoding='utf-8') as out:
        out.write(json.dumps(row, sort_keys=True) + '\n')


def install() -> None:
    """Install external worker hooks before the real service imports its target."""
    from freetoken.engine.engine import Engine
    from freetoken.scheduler.scheduler import Scheduler
    from freetoken.scheduler.io import SchedulerIOMixin
    initialize, receive, deliver = Engine.__init__, Scheduler._process_one_msg, SchedulerIOMixin._reply_tokenizer_rank0

    @functools.wraps(initialize)
    def loaded(self, *args, **kwargs):
        result = initialize(self, *args, **kwargs)
        buffer = self.kv_cache._kv_buffer
        append('model_loaded', kv_storage_bytes=int(buffer.numel() * buffer.element_size()),
               kv_storage_shape=list(buffer.shape), num_pages=int(self.num_pages), max_seq_len=int(self.max_seq_len))
        interval = float(os.environ.get('R058_MEMORY_SAMPLE_INTERVAL_SECONDS', '0.25'))
        def periodic():
            while True:
                try: append('periodic')
                except BaseException as error:
                    with Path(os.environ['R058_MODEL_MEMORY']).open('a',encoding='utf-8') as out: out.write(json.dumps({'event':'observer_error','error':repr(error),'time_ns':time.time_ns()})+'\n')
                    return
                time.sleep(interval)
        threading.Thread(target=periodic, name='r058-memory-observer', daemon=True).start()
        return result

    @functools.wraps(receive)
    def request(self, msg, *args, **kwargs):
        if type(msg).__name__ == 'UserMsg':
            append('request_before', msg.uid)
        return receive(self, msg, *args, **kwargs)

    @functools.wraps(deliver)
    def response(self, messages, *args, **kwargs):
        for msg in messages:
            if type(msg).__name__ == 'DetokenizeMsg' and bool(msg.finished):
                append('request_after', msg.uid)
        return deliver(self, messages, *args, **kwargs)

    Engine.__init__, Scheduler._process_one_msg, SchedulerIOMixin._reply_tokenizer_rank0 = loaded, request, response


if __name__ in ('__main__', '__mp_main__'):
    os.environ.setdefault('R058_SERVICE_BIRTH',json.dumps(birth(),sort_keys=True))
    install()
    if __name__ == '__main__':
        from freetoken.cli import main
        sys.argv = ['ft', *sys.argv[1:]]
        main()
