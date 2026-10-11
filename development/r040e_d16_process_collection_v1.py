"""R040e private-endpoint adapter for the bounded D16 collector v3.

Formal measurements retain v2 capture and source checks with one skipped sealed batch. The file dry-run retains its native
source verification/archive preamble and configured service writer, stopping
before process launch and producing explicitly typed permission probes.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _frozen():
    path = Path(__file__).with_name('d16_native_process_collection_v3.py')
    spec = importlib.util.spec_from_file_location('r040e_retained_collection_v3', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _endpoint(owner, supplied=None):
    port = getattr(owner, 'port', None)
    if type(port) is not int or not 1024 <= port <= 65535 or port == 8095:
        raise ValueError('R040a collector requires its owner private port')
    expected = f'http://127.0.0.1:{port}'
    if owner.base_url != expected or supplied not in (None, expected):
        raise ValueError('R040a collector endpoint differs from its owner')
    return expected


def _mode(owner, dry):
    if type(dry) is not bool or dry != getattr(owner, '_r040a_file_dry_run', False):
        raise ValueError('R040a collector dry mode differs from its owner')


def _probe_outputs(module, arm, inputs, *, kind, execution):
    """Check worker-owned output parent permissions without inventing raw data."""
    folders = ['collection', 'capture/admissions', 'capture/native',
               'capture/sampler', 'inputs', 'dump']
    if kind == 'parking':
        folders += ['capture/parking']
    if kind == 'cache':
        folders += ['capture/expert_cache']
    for relative in folders:
        directory = arm / relative
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / '.cpu_write_probe').open('xb') as stream:
            stream.write(b'CPU_FILE_PROBE_ONLY\n')
    expected = arm / 'expected_capture.json'
    if not expected.is_file() or expected.stat().st_mode & 0o222:
        raise ValueError('actual configured capture expectation is missing or writable')
    value = {'schema': 'ft_r040a_cpu_file_probe/v1', 'kind': 'CPU_FILE_PROBE',
             'not_measurement': True, 'arm': arm.name, 'execution_id': execution,
             'planned_input_lengths': [len(ids) for ids in inputs],
             'planned_kind': kind, 'service_started': False, 'requests_sent': False}
    module.write(arm / 'file_permission_probe.json', value)
    return value


def _file_native_arms(module, owner, inputs, *, slots, wrapper, base_url, root,
                      request_factory, interleave=False):
    if request_factory is not None:
        raise ValueError('file dry-run does not accept a measurement client')
    arms = []
    schedule, plan = module.arm_schedule(owner, slots=slots, interleave=interleave)
    for kind, repetition, slot in schedule:
        name = f'dev_D16_{slots}_{kind}_{repetition}_{slot}'
        execution = f'{owner.options.rid}:{name}'
        chosen = inputs if slot is None else [inputs[slot]]
        with module.configured(owner, wrapper, execution_id=execution,
                               request_count=len(chosen)):
            arms.append(owner.service(name, lambda arm: _probe_outputs(
                module, arm, chosen, kind='interleave' if interleave else kind,
                execution=execution), health_only=True, max_running_requests=4))
    result = {'schema': 'ft_r040a_cpu_file_probe/v1', 'kind': 'CPU_FILE_PROBE',
              'not_measurement': True, 'arms': arms, 'service_started': False,
              'requests_sent': False}
    result = module.annotate_slots4_result(result, plan)
    module.write(root / 'file_collection_probe.json', result)
    return result


def collect_native_processes(owner, inputs, *, slots, wrapper,
                             file_dry_run=False, base_url=None, **kwargs):
    _mode(owner, file_dry_run)
    endpoint = _endpoint(owner, base_url)
    if kwargs.get('fixture_only') or kwargs.get('request_factory') is not None:
        raise ValueError('R040a collection requires the owner client and real source review')
    module = _frozen()
    if file_dry_run:
        module._collect_arms = lambda *args, **options: _file_native_arms(module, *args, **options)
    return module.collect_native_processes(owner, inputs, slots=slots,
                                          wrapper=wrapper, base_url=endpoint, **kwargs)


def _file_state(module, owner, ids, *, kind, wrapper, source_review,
                source_review_sha256):
    if (not isinstance(ids, list) or not ids
            or any(type(token) is not int or not -(2**31) <= token < 2**31 for token in ids)):
        raise ValueError('D16 state path requires typed signed-int32 input IDs')
    proof = module.verify_source_review(wrapper, source_review, source_review_sha256)
    original = owner.directory
    root = module.regular(original) / ('dev_D16/native_' + kind)
    root.mkdir(parents=True, exist_ok=False)
    module.write(root / 'execution_source.json', proof)
    had_args = hasattr(owner, 'first_args')
    previous = getattr(owner, 'first_args', None)
    if had_args:
        del owner.first_args
    owner.directory = root
    arms = []
    try:
        for enabled in (False, True):
            for repeat in (0, 1):
                prefix = ('restore' if enabled else 'control') if kind == 'parking' else ('warm' if enabled else 'cold')
                name = f'{prefix}_{repeat}'
                execution = f'{owner.options.rid}:{kind}:{name}'
                with module.configured(owner, wrapper, execution_id=execution,
                        request_count=1, parking=enabled if kind == 'parking' else None,
                        cache_init=('warm' if enabled else 'cold') if kind == 'cache' else None):
                    arms.append(owner.service(name, lambda arm: _probe_outputs(
                        module, arm, [ids], kind=kind, execution=execution),
                        health_only=True, max_running_requests=4,
                        mamba_host_slots=5 if kind == 'parking' else 0))
        result = {'schema': 'ft_r040a_cpu_file_probe/v1', 'kind': 'CPU_FILE_PROBE',
                  'not_measurement': True, 'arms': arms, 'service_started': False,
                  'requests_sent': False}
        module.write(root / 'file_collection_probe.json', result)
        return result
    finally:
        owner.directory = original
        if had_args:
            owner.first_args = previous
        elif hasattr(owner, 'first_args'):
            del owner.first_args


def collect_parking_processes(owner, ids, *, wrapper, file_dry_run=False,
                              base_url=None, **kwargs):
    _mode(owner, file_dry_run)
    endpoint = _endpoint(owner, base_url)
    module = _frozen()
    if file_dry_run:
        return _file_state(module, owner, ids, kind='parking', wrapper=wrapper, **kwargs)
    return module.collect_parking_processes(owner, ids, wrapper=wrapper,
                                           base_url=endpoint, **kwargs)


def collect_cache_processes(owner, ids, *, wrapper, file_dry_run=False,
                            base_url=None, **kwargs):
    _mode(owner, file_dry_run)
    endpoint = _endpoint(owner, base_url)
    module = _frozen()
    if file_dry_run:
        return _file_state(module, owner, ids, kind='cache', wrapper=wrapper, **kwargs)
    return module.collect_cache_processes(owner, ids, wrapper=wrapper,
                                         base_url=endpoint, **kwargs)
