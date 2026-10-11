"""D16 independent service arms under an already reviewed owned lifecycle.

No CLI or automatic launch is provided. Callers must freeze this adapter into
their independently reviewed queued source package before model execution.
"""
from __future__ import annotations

from contextlib import contextmanager
import functools
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import types
import time
from concurrent.futures import ThreadPoolExecutor

import d16_service_workloads as workloads
import t17_d14_runner as retained
from d16_native_capture_shutdown_v3 import read_sealed_service_delivery


def regular(path):
    path = Path(path)
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('D16 source/output ancestor is a symbolic link')
    return path


def verify_source_review(wrapper, review, review_sha256):
    """Bind actual execution dependencies to a separately pinned sealed review."""
    review = regular(review)
    if not review.is_file() or review.stat().st_mode & 0o222:
        raise ValueError('sealed D16 source review required')
    if review.parent.stat().st_mode & 0o222 or any(p.is_symlink() or p.stat().st_mode & 0o222 for p in review.parent.rglob('*')):
        raise ValueError('D16 source review tree must be sealed')
    raw = review.read_bytes()
    if hashlib.sha256(raw).hexdigest() != review_sha256:
        raise ValueError('D16 source review SHA differs')
    document = json.loads(raw)
    if (document.get('schema') != 'ft_d16_collector_source_review/v1'
            or document.get('scope') != 'owned-gpu-test-startup-only'
            or document.get('source_execution_ready') is not True
            or document.get('model_admitted') is not False):
        raise ValueError('D16 source readiness review cannot substitute model acceptance')
    import t17_d14_gpu as gpu
    from equiv_suite import service_capture, service_capture_startup, sampler_capture, native_workloads
    here = Path(__file__).resolve().parent
    actual = {'adapter':Path(__file__), 'startup_wrapper':Path(wrapper), 'shutdown_wrapper':here/'d16_native_capture_shutdown_v3.py', 'parking_wrapper':here/'d16_exact_service_startup_v4.py', 'exact_startup_base':here/'d16_exact_service_startup.py',
              'workloads':Path(workloads.__file__),
              'runner':Path(retained.__file__), 'gpu_run':Path(gpu.__file__),
              'observe':here/'t17_d14_observe.py', 'artifacts':here/'t17_d14_artifacts.py',
              'exact_ids':here/'t17_d14_exact_ids.py', 'base_lifecycle':here/'t16_full_tail_base_runner.py',
              'launch_protocol':here/retained.T16_LAUNCH_PROTOCOL,
              'capture':Path(service_capture.__file__), 'capture_startup':Path(service_capture_startup.__file__),
              'sampler_capture':Path(sampler_capture.__file__), 'reader':Path(native_workloads.__file__)}
    declared = document.get('source_files')
    if not isinstance(declared, dict) or set(declared) != set(actual):
        raise ValueError('D16 source review omits execution dependencies')
    bindings = {}
    for name, path in actual.items():
        path = regular(path)
        item = declared[name]
        if (not path.is_file() or path.stat().st_mode & 0o222 or not isinstance(item,dict)
                or Path(item.get('path','')).resolve() != path.resolve()):
            raise ValueError('D16 dependency origin differs: '+name)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if item.get('sha256') != digest:
            raise ValueError('D16 dependency SHA differs: '+name)
        bindings[name] = {'path':str(path.resolve()),'sha256':digest}
    if Path(wrapper).resolve() != (here/'d16_native_capture_shutdown_v3.py').resolve():
        raise ValueError('D16 source review must bind the R040a shutdown startup entry')
    lifecycle = retained.verify_t16_lifecycle(actual['base_lifecycle'],actual['launch_protocol'])
    report = regular(document.get('cpu_report',''))
    if not report.is_file() or report.stat().st_mode & 0o222:
        raise ValueError('sealed D16 CPU source report required')
    if report.parent.stat().st_mode & 0o222:
        raise ValueError('D16 CPU source report directory must be sealed')
    if hashlib.sha256(report.read_bytes()).hexdigest() != document.get('cpu_report_sha256'):
        raise ValueError('D16 CPU source report SHA differs')
    cpu = json.loads(report.read_text())
    if cpu.get('schema') != 'ft_d16_exact_startup_cpu/v1' or cpu.get('verdict') != 'PASS':
        raise ValueError('D16 CPU source package failed')
    inventory = cpu.get('files')
    if not isinstance(inventory,dict) or not inventory:
        raise ValueError('nonempty D16 CPU source inventory required')
    for name,digest in inventory.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('D16 CPU inventory path differs')
        path = regular(report.parent/name)
        if not path.is_file() or path.stat().st_mode & 0o222 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('D16 CPU source inventory differs')
    for name, binding in bindings.items():
        relative = declared[name].get('cpu_inventory_path')
        if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
                or '..' in Path(relative).parts or inventory.get(relative) != binding['sha256']):
            raise ValueError('D16 execution source differs from CPU-tested inventory: '+name)
        binding['cpu_inventory_path'] = relative
    return {'review':str(review),'review_sha256':review_sha256,'source_files':bindings,'lifecycle':lifecycle,
            'cpu_report':str(report),'cpu_report_sha256':document['cpu_report_sha256'], 'model_admitted':False}


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True)


def birth(pid):
    fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': pid, 'start_ticks': int(fields[19]), 'pgid': os.getpgid(pid)}


@contextmanager
def configured(owner, wrapper, *, execution_id, request_count, parking=None, cache_init=None):
    """Retain the owner's lifecycle; restore its methods on every failure path."""
    wrapper = Path(wrapper)
    if wrapper.is_symlink() or not wrapper.is_file() or wrapper.stat().st_mode & 0o222:
        raise ValueError('D16 startup source must be frozen')
    old_env = owner.environment
    previous = {key: owner.__dict__.get(key) for key in ('environment', 'startup_wrapper')}
    present = {key: key in owner.__dict__ for key in previous}
    def environment(self, wt, arm=None, d0=False):
        env = old_env(wt, arm, d0)
        if arm is None:
            return env
        expected = arm / 'expected_capture.json'
        write(expected, [{'uid': uid, 'generation_index': generation,
                          'logical_label': f'{execution_id}:uid-{uid}'}
                         for uid in range(request_count) for generation in range(128)])
        expected.chmod(0o444)
        env.update(FT_D16_SERVICE_CAPTURE_DIR=str(arm/'capture'), FT_D16_EXECUTION_ID=execution_id,
                   FT_D16_SERVICE_CAPTURE_EXPECTED_JSON=str(expected),
                   FT_D16_SERVICE_CAPTURE_MAX_CAPTURES=str(128*request_count+1024),
                   FT_D16_SERVICE_CAPTURE_MAX_BYTES='2147483648')
        # Load the reviewed collector/reader modules from the actual source
        # package; FreeToken product imports still come from the candidate WT.
        env['PYTHONPATH'] = str(wrapper.parent)+':'+str(wt/'scripts')+':'+env['PYTHONPATH']
        for key in list(env):
            if key.startswith('FT_T17_OPERATOR'):
                env.pop(key)
        if parking is not None:
            env['FT_DEV_PAUSE_ENDPOINT'] = '1'
            env['FT_D16_PARK_RESTORE'] = '1' if parking else '0'
        if cache_init is not None:
            if cache_init not in ('cold', 'warm'):
                raise ValueError('D16 cache initialization must be cold or warm')
            env['FT_D16_CACHE_INIT'] = cache_init
        return env
    owner.environment = types.MethodType(environment, owner)
    owner.startup_wrapper = lambda: wrapper
    try:
        yield
    finally:
        for key in previous:
            if present[key]: setattr(owner, key, previous[key])
            else: owner.__dict__.pop(key, None)


def _await_decode_trigger(arm, future, *, output, timeout):
    deadline = time.monotonic() + timeout
    while True:
        if future.done():
            future.result()
            raise RuntimeError('D16 query finished before live decode trigger')
        manifest = Path(arm)/'capture/sampler/manifest.json'
        if manifest.exists():
            captures = json.loads(manifest.read_text())['captures']
            if captures:
                latest = captures[-1]['id']
                if Path(latest).name != latest or not latest.startswith('capture-'):
                    raise RuntimeError('D16 decode capture identity differs')
                raw = (manifest.parent/latest/'receipt.json').read_bytes()
                if hashlib.sha256(raw).hexdigest() != captures[-1]['receipt_sha256']:
                    raise RuntimeError('D16 decode trigger receipt SHA differs')
                receipt = json.loads(raw)
                rows = receipt['rows']
                if len(rows) == 1 and rows[0]['uid'] == 0 and 7 <= rows[0]['generation_index'] < 126:
                    write(Path(arm)/output, receipt)
                    return
        if time.monotonic() >= deadline:
            raise TimeoutError('D16 live decode trigger timed out')
        time.sleep(0.01)


def _interleave_queries(arm, inputs, *, client, repetition):
    """Start long prefill only after UID0 has an actual native decode capture."""
    arm = Path(arm)
    root = arm/'collection'
    root.mkdir(exist_ok=False)
    pool = ThreadPoolExecutor(max_workers=2)
    def query(slot):
        return workloads.collect(client, [inputs[slot]], slots=1, root=root/('slot' + str(slot)),
            observations_path=arm/'observations.jsonl', mode='batch', repetitions=1,
            repetition_start=repetition, slot_offset=slot)
    try:
        short = pool.submit(query, 0)
        _await_decode_trigger(arm, short, output='interleave_trigger.json', timeout=1800)
        long = pool.submit(query, 1)
        groups = [short.result(timeout=1800), long.result(timeout=1800)]
        rows = []
        for slot, group in enumerate(groups):
            row = dict(group['batch'][0][0])
            if row['uid'] != slot:
                raise RuntimeError('D16 interleave native UID admission order differs')
            for field in ('request', 'response_path'):
                row[field] = 'slot' + str(slot) + '/' + row[field]
            rows.append(row)
        value = {'schema': 'ft_d16_exact_id_collection/v1', 'admitted': False,
                 'physical_batch_verified': False, 'mode': 'batch', 'slots': 2,
                 'repetitions': 1, 'observations_path': str(arm/'observations.jsonl'),
                 'batch': [rows], 'alone': []}
        write(root/'collection.json', value)
        return value
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


def _parking_query(arm, ids, *, client, pause_client, park, timeout=1800):
    """Issue one exact-ID query and pause only after native decode capture.

    The control arm uses the same pause duration/host capacity, without state
    transport. Client concurrency alone never proves a scheduler safe point.
    """
    arm = Path(arm)
    write(arm/'parking_input.json', {'input_ids': ids, 'max_tokens': 128})
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(client, ids, max_tokens=128, timeout=timeout,
                         output_path=arm/'parking_response.json',
                         observations_path=arm/'observations.jsonl')
    try:
        _await_decode_trigger(arm, future, output='parking_trigger.json', timeout=timeout)
        pause = pause_client()
        write(arm/'pause_ack.json', pause)
        response = pause['response']
        if response.get('status') != 'accepted':
            raise RuntimeError('D16 parking pause was not accepted')
        roundtrip = arm/'capture/parking/roundtrip.json'
        if park:
            proof = json.loads(roundtrip.read_text())
            if (proof.get('request_id') != response.get('request_id')
                    or proof.get('state_transport_bitwise') is not True
                    or [req['uid'] for req in proof.get('requests', [])] != [0]):
                raise RuntimeError('D16 parking raw proof does not bind the paused query')
        elif roundtrip.exists():
            raise RuntimeError('D16 parking control unexpectedly restored state')
        result = future.result(timeout=timeout)
        reply = result.get('response', {})
        import struct
        expected = hashlib.sha256(struct.pack('<%di' % len(ids), *ids)).hexdigest()
        if (result.get('status') != 200 or reply.get('uid') != 0 or reply.get('finished') is not True
                or reply.get('input_ids_sha256') != expected
                or reply.get('usage', {}).get('completion_tokens') != 128):
            raise RuntimeError('D16 parking terminal exact-ID binding differs')
        return result
    finally:
        # On failure the enclosing owned service exits immediately, closing the
        # outstanding HTTP request; never wait here before service cleanup.
        pool.shutdown(wait=False, cancel_futures=True)


def collect_parking_processes(owner, ids, *, wrapper, source_review, source_review_sha256,
                             base_url='http://127.0.0.1:8095'):
    """Two fresh no-restore controls and two fresh native host-restore arms."""
    return _collect_state_processes(owner, ids, kind='parking', wrapper=wrapper,
        source_review=source_review, source_review_sha256=source_review_sha256, base_url=base_url)


def collect_cache_processes(owner, ids, *, wrapper, source_review, source_review_sha256,
                           base_url='http://127.0.0.1:8095'):
    """Two fresh cold and two fresh expert-prewarmed processes, no warmup query."""
    return _collect_state_processes(owner, ids, kind='cache', wrapper=wrapper,
        source_review=source_review, source_review_sha256=source_review_sha256, base_url=base_url)


def _collect_state_processes(owner, ids, *, kind, wrapper, source_review, source_review_sha256, base_url):
    import struct
    if kind not in ('parking', 'cache'):
        raise ValueError('D16 state path must be parking or cache')
    if kind == 'parking':
        from multisession_probe import _dev_pause
    if not isinstance(ids, list) or not ids or any(type(token) is not int or not -(2**31) <= token < 2**31 for token in ids):
        raise ValueError('D16 state path requires typed signed-int32 input IDs')
    proof = verify_source_review(wrapper, source_review, source_review_sha256)
    original_directory = owner.directory
    root = regular(original_directory)/('dev_D16/native_' + kind)
    root.mkdir(parents=True, exist_ok=False)
    write(root/'execution_source.json', proof)
    expected = hashlib.sha256(struct.pack('<%di' % len(ids), *ids)).hexdigest()
    results = []
    had_first_args = hasattr(owner, 'first_args')
    previous_first_args = getattr(owner, 'first_args', None)
    if had_first_args:
        del owner.first_args
    owner.directory = root
    try:
        for park in (False, True):
            for repeat in (0, 1):
                name = (('restore' if park else 'control') if kind == 'parking' else ('warm' if park else 'cold')) + '_' + str(repeat)
                execution = owner.options.rid + ':' + kind + ':' + name
                def operation(arm):
                    frontend = birth(owner.proc.pid)
                    write(arm/'owned_frontend.json', frontend)
                    client = functools.partial(retained.exact_id_request, base_url)
                    if kind == 'parking':
                        result = _parking_query(arm, ids, client=client,
                            pause_client=lambda: _dev_pause(base_url, 1.0, 10.0), park=park)
                    else:
                        write(arm/'cache_input.json', {'input_ids': ids, 'max_tokens': 128})
                        result = client(ids, max_tokens=128, output_path=arm/'cache_response.json',
                                        observations_path=arm/'observations.jsonl')
                        reply = result.get('response', {})
                        if (result.get('status') != 200 or reply.get('uid') != 0 or reply.get('finished') is not True
                                or reply.get('input_ids_sha256') != expected
                                or reply.get('usage', {}).get('completion_tokens') != 128):
                            raise RuntimeError('D16 cache terminal exact-ID binding differs')
                    admissions = [json.loads(path.read_text()) for path in (arm/'capture/admissions').glob('*.json')]
                    if len(admissions) != 1 or admissions[0]['uid'] != 0:
                        raise RuntimeError('D16 parking native admission differs')
                    worker = admissions[0]['process_identity']
                    live = birth(worker['pid'])
                    if (live['start_ticks'] != worker['start_ticks'] or live['pgid'] != frontend['pgid']
                            or worker['execution_id'] != execution + ':tp0' or birth(owner.proc.pid) != frontend):
                        raise RuntimeError('D16 parking scheduler is outside the owned service birth')
                    write(arm/'owned_native_worker.json', {'identity': worker, 'live_birth': live, 'frontend': frontend})
                    return result, worker
                with configured(owner, wrapper, execution_id=execution, request_count=1,
                                parking=park if kind == 'parking' else None,
                                cache_init=('warm' if park else 'cold') if kind == 'cache' else None):
                    result, worker = owner.service(name, operation, health_only=True,
                                                  max_running_requests=4, mamba_host_slots=5 if kind == 'parking' else 0)
                arm = root/name
                delivery = read_sealed_service_delivery(arm)
                rows = delivery.get('deliveries', [])
                if (delivery.get('terminal') != 'complete' or delivery.get('process_identity') != worker
                        or len(rows) != 128 or any(row['uid'] != 0 or row['generation_index'] != index
                            or row.get('delivered') is not True for index, row in enumerate(rows))):
                    raise RuntimeError('D16 parking native terminal delivery differs')
                results.append({'arm': name, 'worker': worker, 'input_ids_sha256': expected,
                                'tokens': [row['sampled_token_id'] for row in rows],
                                'text': result['response']['text']})
                if kind == 'cache':
                    cache_root = arm/'capture/expert_cache'
                    init = json.loads((cache_root/'initialization.json').read_text())
                    stats = json.loads((cache_root/'terminal_stats.json').read_text())
                    if (init.get('mode') != ('warm' if park else 'cold')
                            or init.get('execution_id') != worker['execution_id']
                            or init.get('priming_requests') != 0
                            or init.get('resident_count') != (len(init['eligible_layers']) if park else 0)
                            or (not park and stats['prefill_hit_rows'] != 0)
                            or (park and stats['prefill_hit_rows'] <= 0)):
                        raise RuntimeError('D16 cache initial residency or actual hit evidence differs')
                    results[-1]['cache_initialization'] = init
                    results[-1]['cache_stats'] = stats
                    states = {}
                    for label in ('before_decode', 'after_decode127'):
                        if not (cache_root/('0.' + label + '.pt')).is_file():
                            raise RuntimeError('D16 cache raw four-state tensor is missing')
                        document = json.loads((cache_root/('0.' + label + '.json')).read_text())
                        if (document.get('uid') != 0 or document.get('label') != label
                                or set(document.get('states', {})) != {'conv', 'recurrent', 'ple_conv', 'ple_ngram_ctx'}):
                            raise RuntimeError('D16 cache four-state capture is incomplete')
                        states[label] = document['states']
                    results[-1]['states'] = states
        if len({(row['worker']['pid'], row['worker']['start_ticks']) for row in results}) != 4:
            raise RuntimeError('D16 state arms must have four independent process births')
        if any((row['tokens'], row['text']) != (results[0]['tokens'], results[0]['text']) for row in results[1:]):
            raise RuntimeError('D16 state continuation differs from repeated control')
        if kind == 'cache' and any(row['states'] != results[0]['states'] for row in results[1:]):
            raise RuntimeError('D16 cache four states differ from repeated cold control')
        value = {'schema': 'ft_d16_native_' + kind + '_collection/v1', 'arms': results,
                 'measurement_verdict': 'bitwise_pending_independent_review', 'admitted': False}
        write(root/'collection.json', value)
        return value
    finally:
        owner.directory = original_directory
        if had_first_args:
            owner.first_args = previous_first_args
        elif hasattr(owner, 'first_args'):
            del owner.first_args


def collect_native_processes(owner, inputs, *, slots, wrapper, base_url='http://127.0.0.1:8095', request_factory=None,
                             source_review=None, source_review_sha256=None, fixture_only=False, interleave=False):
    """Two fresh batch processes and two fresh single repeats per input.

    All arms use capacity four so parsed model arguments stay identical while
    actual physical batch size is proven by the independent raw reader.
    """
    if type(slots) is not int or slots not in (2,4) or len(inputs) != slots:
        raise ValueError('D16 requires exactly two or four input slots')
    if any(not isinstance(ids,list) or not ids or any(type(token)is not int or not -(2**31)<=token<2**31 for token in ids) for ids in inputs):
        raise ValueError('D16 requires nonempty typed signed-int32 inputs before service start')
    if type(interleave) is not bool or (interleave and (slots != 2 or len(inputs[0]) >= 4096 or len(inputs[1]) <= 4096)):
        raise ValueError('D16 interleave requires a short decode input and a long prefill input')
    regular(owner.directory)
    if fixture_only:
        guard = sys.modules.get('sitecustomize')
        active = (getattr(guard,'FT_CPU_FIXTURE_NETWORK_GUARD',False)
                  and socket.socket.connect is getattr(guard,'connect',None)
                  and socket.socket.connect_ex is getattr(guard,'connect_ex',None)
                  and socket.socket.listen is getattr(guard,'listen',None))
        if not active or request_factory is None:
            raise ValueError('D16 fixture collection requires active CPU network guard and explicit fixture client')
        proof = {'fixture_only':True,'model_admitted':False,'gpu_execution_permitted':False}
    else:
        if source_review is None or source_review_sha256 is None:
            raise ValueError('D16 queued collection requires a pinned independent execution-source review')
        proof = verify_source_review(wrapper,source_review,source_review_sha256)
    root = owner.directory / 'dev_D16' / ('native_interleave' if interleave else f'native_slots_{slots}')
    root.mkdir(parents=True, exist_ok=False)
    write(root/'execution_source.json',proof)
    if not fixture_only:
        source_root = root/'execution_sources';source_root.mkdir()
        for name,item in proof['source_files'].items():
            raw = Path(item['path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=item['sha256']:
                raise ValueError('D16 execution source changed while archiving')
            with (source_root/(name+'.py')).open('xb') as stream:stream.write(raw)
        for name,key in (('independent_review.json','review'),('cpu_report.json','cpu_report')):
            with (source_root/name).open('xb') as stream:stream.write(Path(proof[key]).read_bytes())
    original_directory = owner.directory
    owner.directory = root
    had_first_args = hasattr(owner, 'first_args')
    previous_first_args = getattr(owner, 'first_args', None)
    if had_first_args:
        del owner.first_args
    try:
        return _collect_arms(owner, inputs, slots=slots, wrapper=wrapper, base_url=base_url, root=root,
                             request_factory=request_factory, interleave=interleave)
    finally:
        owner.directory = original_directory
        if had_first_args:
            owner.first_args = previous_first_args
        elif hasattr(owner, 'first_args'):
            del owner.first_args


def _collect_arms(owner, inputs, *, slots, wrapper, base_url, root, request_factory, interleave=False):
    batch, alone, runs = [[],[]], [[],[]], []
    interleave_shape = None
    for kind, repetition, slot in [('batch',r,None) for r in (0,1)] + [('single',r,s) for r in (0,1) for s in range(slots)]:
        name = f'dev_D16_{slots}_{kind}_{repetition}_{slot}'
        execution = f'{owner.options.rid}:{name}'
        chosen = inputs if slot is None else [inputs[slot]]
        def operation(arm):
            frontend = birth(owner.proc.pid)
            write(arm/'owned_frontend.json',frontend)
            client = (request_factory(arm) if request_factory is not None
                      else functools.partial(retained.exact_id_request,base_url))
            result = (_interleave_queries(arm, chosen, client=client, repetition=repetition)
                      if interleave and slot is None else workloads.collect(client, chosen,
                        slots=len(chosen),root=arm/'collection',observations_path=arm/'observations.jsonl',
                        mode='batch' if slot is None else 'alone', repetitions=1,
                        repetition_start=repetition,slot_offset=0 if slot is None else slot))
            identities = [json.loads(path.read_text())['process_identity']
                          for path in (arm/'capture/admissions').glob('*.json')]
            if len(identities) != len(chosen) or any(identity != identities[0] for identity in identities):
                raise ValueError('native admissions do not bind one live scheduler process')
            worker = identities[0]
            actual = birth(worker['pid'])
            if actual['start_ticks'] != worker['start_ticks'] or actual['pgid'] != frontend['pgid']:
                raise ValueError('native scheduler is outside the owned process birth/group')
            if worker['execution_id'] != execution+':tp0' or birth(owner.proc.pid) != frontend:
                raise ValueError('native worker execution or frontend birth differs')
            write(arm/'owned_native_worker.json', {'identity':worker,'live_birth':actual,'frontend':frontend})
            return result,worker
        with configured(owner,wrapper,execution_id=execution,request_count=len(chosen)):
            result, identity = owner.service(name,operation,health_only=True,max_running_requests=4)
        arm = owner.directory/name
        delivery = read_sealed_service_delivery(arm)
        if delivery.get('terminal') != 'complete' or delivery.get('process_identity') != identity:
            raise ValueError('owned service stop did not produce complete native delivery')
        if interleave and slot is None:
            mixed = [event for event in delivery.get('scheduler_batches', [])
                     if event.get('phase') == 'prefill'
                     and {req['uid'] for req in event.get('requests', [])} == {0, 1}
                     and {req['uid']: req['extend_len'] == 1 for req in event.get('request_geometry', [])} == {0: True, 1: False}]
            if not mixed:
                raise ValueError('D16 interleave has no native long-prefill/active-decode batch')
            write(arm/'interleave_scheduler_events.json', mixed)
            shape = [{key: event[key] for key in ('phase', 'physical_size', 'padded_size',
                                                   'input_shape', 'request_geometry')} for event in mixed]
            if interleave_shape is not None and shape != interleave_shape:
                raise ValueError('D16 repeat interleave native batch geometry differs')
            interleave_shape = shape
        group = result['batch' if slot is None else 'alone'][0]
        target = batch if slot is None else alone
        for row in group:
            row = dict(row)
            for field in ('request','response_path'):
                row[field] = str((arm/'collection'/row[field]).relative_to(owner.directory))
            target[repetition].append(row)
        runs.append({'kind':kind,'repeat':repetition,'slot':slot,'process_identity':identity,
                     'service_capture':str((arm/'capture/service_delivery.json').relative_to(owner.directory)),
                     'sampler_root':str((arm/'capture/sampler').relative_to(owner.directory))})
    collection = root/'collection.json'
    write(collection,{'schema':'ft_d16_exact_id_collection/v1','admitted':False,'physical_batch_verified':False,
                      'slots':slots,'batch':batch,'alone':alone, 'interleave':interleave})
    # Publish a map after every owned process has stopped and sealed capture.
    # Its SHA must be externally frozen/reviewed before the reader consumes it.
    mapping = root/'evidence.json'
    files = {}
    for path in owner.directory.rglob('*'):
        if path.is_symlink(): raise ValueError('owned native collection contains a symlink')
        if path.is_file() and path != mapping:
            files[path.relative_to(owner.directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    write(mapping,{'schema':'ft_d16_native_workload_map/v1','collection':str(collection.relative_to(owner.directory)),
                   'runs':runs,'files':files})
    return {'root':str(root),'evidence_map':str(mapping),'evidence_map_sha256':hashlib.sha256(mapping.read_bytes()).hexdigest(),
            'model_admitted':False,'requires_independent_raw_review':True}
