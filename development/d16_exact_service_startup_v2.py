"""Opt-in D16 native sampler/batch capture with retained exact-ID requests.

This entry is frozen separately before any queued model run. The CPU probe
starts only a tokenizer/message child, with CUDA hidden, and grants no model gate.
"""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import sys

_installed = False


def install_batch_geometry(adapter, engine):
    """Bind a scheduled batch, then observe its input geometry at native forward.

    ``Scheduler._schedule_next_batch`` constructs a ``Batch`` before
    ``Scheduler._forward`` assigns ``batch.input_ids``.  This observer must
    therefore never read that field while recording scheduling facts.  It
    carries only the exact batch-object binding to the engine boundary, where
    the production scheduler has already assigned the real input tensor.

    Capture faults are retained as indeterminate evidence, but are never
    allowed to alter scheduling or the native ``forward_batch`` result.
    """
    if adapter is None:
        return
    original_observe = adapter.observe_scheduler_batch
    original_forward = engine.forward_batch
    pending = {}

    def observer_error(prefix, error):
        adapter.record_observer_error(
            f"{prefix}: {type(error).__name__}: {error}"
        )

    def event_identity(event):
        value = {
            'scheduler_sequence': event['scheduler_sequence'],
            'phase': event['phase'],
            'requests': event['requests'],
            'padded_requests': event['padded_requests'],
            'active_table_idx': event['active_table_idx'],
        }
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
        ).hexdigest()

    def event_bytes(event):
        return len((json.dumps(event, sort_keys=True, separators=(',', ':')) + '\n').encode())

    def account_event_delta(event, before):
        """Keep ServiceCaptureAdapter's receipt budget true after augmentation."""
        after = event_bytes(event)
        total = getattr(adapter, '_scheduler_batch_bytes', None)
        if type(total) is not int:
            return
        updated = total + after - before
        maximum = getattr(adapter, '_max_bytes', None)
        adapter._scheduler_batch_bytes = updated
        if type(maximum) is int and updated > maximum:
            raise ValueError('geometry event exceeds scheduler batch capture bytes budget')

    def observe(batch):
        # The capture startup wrapper calls this after native scheduling.  A
        # duplicate object can only be diagnostic corruption, so retain it as
        # failed evidence rather than queueing two ambiguous forward bindings.
        key = id(batch)
        if key in pending:
            adapter.record_observer_error('D16 geometry batch binding duplicated')
            return None
        capacity = getattr(adapter, '_max_captures', None)
        if type(capacity) is int and len(pending) >= capacity:
            adapter.record_observer_error('D16 geometry batch binding exceeds capture budget')
            return None
        try:
            result = original_observe(batch)
            event = adapter.scheduler_batches[-1]
            before = event_bytes(event)
            reqs = {req.uid: req for req in batch.reqs}
            for collection in ('requests', 'padded_requests'):
                for row in event[collection]:
                    row['live_input_ids_sha256'] = row['input_ids_sha256']
                    if row['uid'] in reqs:
                        row['input_ids_sha256'] = adapter.registry.get(row['uid'])['prompt_sha256']
            event['request_geometry'] = [
                {'uid': req.uid, 'cached_len': req.cached_len,
                 'device_len': req.device_len, 'extend_len': req.extend_len}
                for req in batch.reqs
            ]
            identity = event_identity(event)
            event['geometry_event_identity'] = identity
            account_event_delta(event, before)
            # Retain the object until its one forward boundary: this prevents
            # Python from recycling its id before an unmatched batch is seen.
            pending[key] = (batch, event, identity)
            return result
        except Exception as error:
            observer_error('D16 geometry scheduling observation failed', error)
            return None

    def forward(batch, *args, **kwargs):
        # This runs after Scheduler._forward has performed
        # ``batch.input_ids = self.token_pool[input_mapping]``.  It neither
        # changes the batch nor intercepts exceptions from the native forward.
        binding = pending.pop(id(batch), None)
        try:
            if binding is None:
                raise RuntimeError('no matching scheduled batch binding')
            bound_batch, event, identity = binding
            if (bound_batch is not batch
                    or event.get('geometry_event_identity') != identity
                    or event_identity(event) != identity):
                raise RuntimeError('matching scheduler event identity changed')
            before = event_bytes(event)
            shape = getattr(batch.input_ids, 'shape')
            dimensions = list(shape)
            if not dimensions or any(type(value) is not int or value < 0 for value in dimensions):
                raise ValueError('input_ids shape is not a non-empty integer dimension list')
            event['input_shape'] = dimensions
            event['geometry_event_identity'] = identity
            event['geometry_input_source'] = 'Scheduler._forward:batch.input_ids'
            account_event_delta(event, before)
        except Exception as error:
            observer_error('D16 geometry forward observation failed', error)
        return original_forward(batch, *args, **kwargs)

    adapter.observe_scheduler_batch = observe
    engine.forward_batch = forward


def parking_roundtrip(scheduler, request_id):
    """Exercise native host restore at the drained development-pause boundary.

    Temporary host slots belong only to this test; request/cache ownership and
    KV mappings remain intact. Raw before/host/restored tensors are retained.
    This proves transport parity, not equivalence of the eventual continuation.
    """
    import torch
    pool = scheduler.engine.linear_state_pool
    requests = sorted((req for req in scheduler.decode_manager.running_reqs
                       if req.table_idx >= 0), key=lambda req: req.uid)
    if pool is None or not requests:
        raise RuntimeError('D16 parking requires live hybrid decode requests')
    slots = [req.linear_slot_idx for req in requests]
    if len(set(slots)) != len(slots) or any(type(slot) is not int or slot <= 0 for slot in slots):
        raise RuntimeError('D16 parking live slots must be distinct and non-padding')
    names = ('conv', 'recurrent', 'ple_conv', 'ple_ngram_ctx')
    device = dict(conv=pool.conv_states, recurrent=pool.recurrent_states,
                  ple_conv=pool.slot_states['ple_conv'], ple_ngram_ctx=pool.slot_states['ple_ngram_ctx'])
    host = dict(conv=pool.host_conv_states, recurrent=pool.host_recurrent_states,
                ple_conv=pool.host_slot_states['ple_conv'], ple_ngram_ctx=pool.host_slot_states['ple_ngram_ctx'])
    # Do not evict prefix-cache snapshots to make room for the test.
    if pool.num_free_host_slots < len(requests):
        raise RuntimeError('D16 parking requires already-free host bank slots')
    root = Path(os.environ['FT_D16_SERVICE_CAPTURE_DIR']) / 'parking'
    root.mkdir(parents=True, exist_ok=False)
    def snapshot(tensors, indices):
        return {name: tensors[name][:, indices].detach().cpu().contiguous().clone() for name in names}
    def digest(tensor):
        return hashlib.sha256(tensor.view(torch.uint8).numpy().tobytes()).hexdigest()
    def save(name, values):
        with (root / (name + '.pt')).open('xb') as stream:
            torch.save(values, stream)
        return {key: {'sha256': digest(value), 'shape': list(value.shape), 'dtype': str(value.dtype)}
                for key, value in values.items()}
    bank = pool.alloc_host(len(requests))
    try:
        with scheduler.engine_stream_ctx:
            scheduler.engine.stream.synchronize()
            before = snapshot(device, slots)
            before_meta = save('before', before)
            for src, dst in zip(slots, bank):
                pool.to_host(src, dst)
            scheduler.engine.stream.synchronize()
            archived = snapshot(host, bank)
            archived_meta = save('host', archived)
            if any(digest(before[name]) != digest(archived[name]) for name in names):
                raise RuntimeError('D16 parking D2H state differs')
            pool.clear_slots(slots)
            scheduler.engine.stream.synchronize()
            cleared_meta = save('cleared', snapshot(device, slots))
            for src, dst in zip(bank, slots):
                pool.from_host(src, dst)
            scheduler.engine.stream.synchronize()
            restored_meta = save('restored', snapshot(device, slots))
            if before_meta != restored_meta:
                raise RuntimeError('D16 parking H2D state differs')
        value = {'schema': 'ft_d16_native_parking_roundtrip/v1', 'request_id': request_id,
                 'execution_id': os.environ['FT_D16_EXECUTION_ID'], 'pid': os.getpid(),
                 'requests': [{'uid': req.uid, 'table_idx': req.table_idx,
                               'linear_slot_idx': slot, 'host_slot': bank[index]}
                              for index, (req, slot) in enumerate(zip(requests, slots))],
                 'before': before_meta, 'host': archived_meta, 'cleared': cleared_meta,
                 'restored': restored_meta, 'state_transport_bitwise': True,
                 'continuation_accepted': False, 'model_admitted': False}
        with (root / 'roundtrip.json').open('x') as stream:
            json.dump(value, stream, sort_keys=True)
        return value
    finally:
        # A failed synchronization must not return still-in-flight host memory.
        scheduler.engine.stream.synchronize()
        pool.free_host(bank)


def install_parking(scheduler):
    if os.environ.get('FT_D16_PARK_RESTORE') != '1':
        return
    if not scheduler._dev_pause_enabled:
        raise RuntimeError('D16 parking requires the explicit development pause endpoint')
    original = scheduler._reply_dev_pause
    def reply(msg, status, error=None, **kwargs):
        if status == 'accepted':
            parking_roundtrip(scheduler, msg.request_id)
        return original(msg, status, error, **kwargs)
    scheduler._reply_dev_pause = reply


def configure_expert_cache(scheduler):
    """Cold/warm expert residency without any prefix-warming request."""
    mode = os.environ.get('FT_D16_CACHE_INIT', '')
    if not mode:
        return
    if mode not in ('cold', 'warm'):
        raise ValueError('D16 expert cache initial state must be cold or warm')
    import torch
    cache = scheduler.engine.moe_offload_cache
    if cache is None:
        raise RuntimeError('D16 expert cache requires the native offload cache')
    root = Path(os.environ['FT_D16_SERVICE_CAPTURE_DIR'])/'expert_cache'
    root.mkdir(parents=True, exist_ok=False)
    with scheduler.engine_stream_ctx:
        scheduler.engine.stream.synchronize()
        cache.reset()
        eligible = [layer for layer in range(cache.num_layers)
                    if not cache.is_cpu_layer(layer) and not cache.is_unpinned_layer(layer)]
        if not eligible or cache.cache_size < len(eligible):
            raise RuntimeError('D16 expert cache requires one resident expert per eligible layer')
        if mode == 'warm':
            # One expert per eligible layer is enough to produce a distinct
            # residency. Native prefill materialization can reuse these banks.
            for layer in eligible:
                ids = torch.zeros((1, 1), dtype=torch.int64, device=cache.device)
                cache.ensure_experts(layer, ids)
                cache.copy_missing()
        scheduler.engine.stream.synchronize()
        resident = cache.id_of_slot.detach().cpu().clone()
        count = int((resident >= 0).sum())
        if count != (len(eligible) if mode == 'warm' else 0):
            raise RuntimeError('D16 expert cache native residency does not match initialization')
        cache.reset_stats()
    with (root/'initial_residency.pt').open('xb') as stream:
        torch.save(resident, stream)
    value = {'schema': 'ft_d16_expert_cache_initialization/v1', 'mode': mode,
             'eligible_layers': eligible, 'primed_expert_id': 0 if mode == 'warm' else None,
             'resident_count': count, 'cache_size': cache.cache_size,
             'execution_id': os.environ['FT_D16_EXECUTION_ID'],
             'priming_requests': 0, 'admitted': False}
    with (root/'initialization.json').open('x') as stream:
        json.dump(value, stream, sort_keys=True)
    original_forward = scheduler.engine.forward_batch
    decode_counts = {}
    def state_record(req, label):
        pool = scheduler.engine.linear_state_pool
        slot = req.linear_slot_idx
        tensors = {'conv': pool.conv_states, 'recurrent': pool.recurrent_states,
                   'ple_conv': pool.slot_states['ple_conv'], 'ple_ngram_ctx': pool.slot_states['ple_ngram_ctx']}
        scheduler.engine.stream.synchronize()
        states = {name: tensor[:, slot].detach().cpu().contiguous().clone() for name, tensor in tensors.items()}
        target = root/(str(req.uid) + '.' + label + '.pt')
        with target.open('xb') as stream:
            torch.save(states, stream)
        record = {'uid': req.uid, 'label': label, 'table_idx': req.table_idx, 'linear_slot_idx': slot,
                  'states': {name: {'sha256': hashlib.sha256(tensor.view(torch.uint8).numpy().tobytes()).hexdigest(),
                                    'shape': list(tensor.shape), 'dtype': str(tensor.dtype)}
                             for name, tensor in states.items()}, 'admitted': False}
        with target.with_suffix('.json').open('x') as stream:
            json.dump(record, stream, sort_keys=True)
    def forward(batch, args):
        if batch.is_decode:
            for req in batch.reqs:
                if req.uid not in decode_counts:
                    state_record(req, 'before_decode')
        output = original_forward(batch, args)
        if batch.is_decode:
            for req in batch.reqs:
                count = decode_counts.get(req.uid, 0) + 1
                decode_counts[req.uid] = count
                if count == 127:
                    state_record(req, 'after_decode127')
        return output
    scheduler.engine.forward_batch = forward
    original_shutdown = scheduler.shutdown
    def shutdown():
        # Capture actual native counters before the existing shutdown releases
        # device memory. The original shutdown still executes on any failure.
        try:
            with scheduler.engine_stream_ctx:
                scheduler.engine.stream.synchronize()
                stats = {'prefill_hit_rows': cache.prefill_hit_rows,
                         'prefill_total_rows': cache.prefill_total_rows,
                         'decode': cache.decode_miss_stats(), 'admitted': False}
            with (root/'terminal_stats.json').open('x') as stream:
                json.dump(stats, stream, sort_keys=True)
        finally:
            original_shutdown()
    scheduler.shutdown = shutdown


def install():
    global _installed
    if _installed:
        return
    destination = os.environ.get('FT_D16_SERVICE_CAPTURE_DIR', '')
    if 'dev_D16' not in Path(destination).parts or not os.environ.get('FT_D16_EXECUTION_ID'):
        raise ValueError('D16 capture requires an independent dev_D16 destination and execution identity')
    if not os.environ.get('FT_D16_SERVICE_CAPTURE_EXPECTED_JSON'):
        raise ValueError('D16 capture requires explicit expected UID/generation input')
    import t17_d14_runner as retained
    header, separator, _ = retained.STARTUP_WRAPPER.partition('from freetoken.cli import main\n')
    if not separator:
        raise ValueError('retained exact-ID startup boundary differs')
    # Retain the existing endpoint and observation source exactly. The CLI below
    # dispatches once; spawn children install this same endpoint/message protocol.
    exec(compile(header, str(Path(retained.__file__)), 'exec'), {'__name__': __name__})
    from equiv_suite import service_capture_startup
    original_capture = service_capture_startup.install_scheduler_capture
    def capture(scheduler):
        adapter = original_capture(scheduler)
        install_batch_geometry(adapter, scheduler.engine)
        install_parking(scheduler)
        configure_expert_cache(scheduler)
        return adapter
    service_capture_startup.install_scheduler_capture = capture
    from freetoken.server import launch
    launch._run_scheduler = service_capture_startup.run_scheduler
    _installed = True


def cpu_probe(queue):
    import t17_d14_exact_ids
    from equiv_suite.service_capture_startup import run_scheduler, install_scheduler_capture
    from freetoken.server import launch
    from freetoken.scheduler.scheduler import Scheduler
    from freetoken.engine.engine import Engine
    from types import SimpleNamespace
    # Allocate neither model nor device buffers. Exercise the actual installer
    # against native instance classes, including the expected-query file/budgets.
    engine = Engine.__new__(Engine)
    engine.sampler = SimpleNamespace(sample=lambda *args, **kwargs: None)
    scheduler = Scheduler.__new__(Scheduler)
    scheduler.engine = engine
    # SchedulerIOMixin.__init__ normally binds this transport callback after
    # establishing ZMQ. The CPU fixture supplies a sink instead of opening IPC.
    scheduler.send_result = lambda reply: None
    original_schedule = scheduler._schedule_next_batch
    adapter = install_scheduler_capture(scheduler)
    installed = adapter is not None and scheduler._schedule_next_batch != original_schedule
    class Reply:
        def put(self, value):
            queue.put({**value, 'd16_scheduler_worker_installed': launch._run_scheduler is run_scheduler,
                       'native_scheduler_capture_attached': installed})
    t17_d14_exact_ids.cpu_probe(Reply())


def main():
    install()
    if sys.argv[1:] == ['--cpu-startup-probe']:
        import multiprocessing
        context = multiprocessing.get_context('spawn')
        queue = context.Queue()
        process = context.Process(target=cpu_probe, args=(queue,))
        process.start()
        try:
            proof = queue.get(timeout=45)
            process.join(45)
            if (process.exitcode != 0 or proof['cuda_initialized']
                    or not proof['d16_scheduler_worker_installed'] or not proof['native_scheduler_capture_attached']):
                raise RuntimeError('D16 CPU child startup contract failed')
            if proof['ids'] != [1469, 17, 198, 248068] or proof['uid'] != 41:
                raise RuntimeError('D16 exact-ID wire protocol differs')
            wrappers = {'scheduler_wrapper': 'restore_observed',
                        'engine_wrapper': 'build_chunks_observed',
                        'reply_wrapper': 'reply_observed',
                        'input_wrapper': 'process_observed'}
            if any(proof.get(key) != value for key, value in wrappers.items()):
                raise RuntimeError('D16 startup lost retained T17 observation hooks')
            print(json.dumps({'schema': 'ft_d16_exact_cpu_startup/v1', 'fixture_only': True,
                              'gpu_started': False, 'model_admitted': False, 'worker': proof}))
        finally:
            if process.is_alive():
                process.terminate(); process.join(10)
    else:
        from freetoken.cli import main as cli_main
        raise SystemExit(cli_main())


if __name__ == '__mp_main__':
    install()
if __name__ == '__main__':
    main()
