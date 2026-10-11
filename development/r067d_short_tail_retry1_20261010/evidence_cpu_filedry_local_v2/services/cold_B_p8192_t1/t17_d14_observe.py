"""Frozen T17 startup instrumentation; generation and scheduling calls remain single."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys


def ids_sha(ids):
    return hashlib.sha256(struct.pack('<%di' % len(ids), *ids)).hexdigest()


def install(scheduler, io_type, engine_type, *, sink):
    """Observe admission, actual sampled tokens, executed prefill and D2D restore."""
    restore = scheduler._restore_linear_states
    process = scheduler._process_one_msg
    forward = scheduler._forward
    reply = io_type._reply_tokenizer_rank0
    build_chunks = engine_type._build_layer_major_chunks

    def restore_observed(self, batch):
        planned = [(str(r.uid), int(r.cached_len), r.mamba_restore_src, r.linear_slot_idx)
                   for r in batch.reqs if batch.is_prefill and r.mamba_restore_src is not None]
        result = restore(self, batch)
        for uid, length, src, dst in planned:
            note = json.dumps({'src': src, 'dst': dst}, sort_keys=True)
            self.engine.linear_state_pool.dump_state(
                'resume-device', dev_slots=[src, dst], length=length, uid=uid, note=note)
            sink({'kind': 'restore-device', 'uid': uid, 'cached_tokens': length,
                  'src': src, 'dst': dst})
        return result

    def process_observed(self, msg):
        if type(msg).__name__ == 'UserMsg':
            ids = msg.input_ids.tolist()
            sampling = msg.sampling_params
            sink({'kind': 'input', 'uid': str(msg.uid), 'input_length': len(ids),
                  'ids_int32le_sha256': ids_sha(ids), 'input_ids': ids,
                  'sampling': {'temperature': float(sampling.temperature),
                               'max_tokens': int(sampling.max_tokens),
                               'top_p': float(sampling.top_p)}})
        return process(self, msg)

    def forward_observed(self, value):
        batch = value.batch
        if batch.is_prefill:
            for index, r in enumerate(batch.reqs):
                metadata = getattr(batch, 'fla_metadata', None)
                flags = None
                if metadata is not None and metadata.has_initial_state is not None:
                    flags = {'cached_tokens': int(r.cached_len), 'device_tokens': int(r.device_len),
                             'has_initial_state': bool(metadata.has_initial_state[index].item()),
                             'fresh_state_indices': ([] if metadata.fresh_state_indices is None
                                                     else metadata.fresh_state_indices.tolist())}
                sink({'kind': 'prefill', 'uid': str(r.uid), 'cached_tokens': int(r.cached_len),
                      'device_length': int(r.device_len), 'extend_tokens': int(r.extend_len),
                      'layer_major': bool(getattr(batch, 'layer_major', False)),
                      'reason': str(getattr(r, 'seg_reason', '')), 'first_child': flags})
        return forward(self, value)

    def reply_observed(self, messages):
        for msg in messages:
            name = type(msg).__name__
            if name == 'DetokenizeMsg':
                sink({'kind': 'token', 'uid': str(msg.uid), 'token': int(msg.next_token),
                      'finished': bool(msg.finished), 'finish_reason': msg.finish_reason})
            elif name == 'PromptAdmittedMsg':
                sink({'kind': 'admitted', 'uid': str(msg.uid),
                      'prompt_tokens': int(msg.prompt_tokens), 'cached_tokens': int(msg.cached_tokens)})
            elif name == 'ErrorReplyMsg':
                sink({'kind': 'error', 'uid': str(msg.uid), 'error': str(msg.error)})
        return reply(self, messages)

    def build_chunks_observed(self, batch):
        """Record the child coordinates actually consumed by layer-major FLA."""
        children = build_chunks(self, batch)
        if batch.is_prefill and children:
            outer = batch.reqs[0]
            observed = []
            for child in children:
                req = child.reqs[0]
                initial = child.fla_metadata.has_initial_state[0]
                observed.append({
                    'cached_tokens': int(req.cached_len),
                    'device_tokens': int(req.device_len),
                    'has_initial_state': bool(initial.item()),
                    'fresh_state_indices': ([] if child.fla_metadata.fresh_state_indices is None
                                            else child.fla_metadata.fresh_state_indices.tolist()),
                })
            sink({'kind': 'layer-children', 'uid': str(outer.uid),
                  'outer_cached_tokens': int(outer.cached_len), 'children': observed})
        return children

    scheduler._restore_linear_states = restore_observed
    scheduler._process_one_msg = process_observed
    scheduler._forward = forward_observed
    io_type._reply_tokenizer_rank0 = reply_observed
    engine_type._build_layer_major_chunks = build_chunks_observed


def startup():
    output = Path(os.environ['FT_T17_OBSERVATIONS'])
    if not os.environ.get('FT_DEV_STATE_DUMP'):
        raise ValueError('T17 state dump must be configured before FreeToken import')
    def sink(row):
        with output.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, sort_keys=True) + '\n')
    from freetoken.scheduler.scheduler import Scheduler
    from freetoken.scheduler.io import SchedulerIOMixin
    from freetoken.engine.engine import Engine
    install(Scheduler, SchedulerIOMixin, Engine, sink=sink)


# spawn re-executes the startup file as __mp_main__; hooks must be installed in
# that process too, while the CLI starts only once in the original parent.
if __name__ in ('__main__', '__mp_main__'):
    startup()
if __name__ == '__main__':
    from freetoken.cli import main
    sys.argv = ['ft', *sys.argv[1:]]
    main()
