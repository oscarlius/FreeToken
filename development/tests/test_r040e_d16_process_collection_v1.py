"""CPU public-loop checks; simulated I/O never establishes model acceptance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace
import urllib.request

import pytest

DEV = Path(__file__).parents[1]

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

@pytest.fixture(autouse=True)
def deny_process_network(monkeypatch):
    def denied(*args, **kwargs): pytest.fail('CPU public loop attempted network/process')
    for method in ('connect', 'connect_ex'): monkeypatch.setattr(socket.socket, method, denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    monkeypatch.setattr(subprocess, 'Popen', denied)
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES', '')

def setup(tmp_path, monkeypatch, *, dry=True):
    helpers = load(DEV/'tests/test_r040a_d16_process_collection_v4.py', 'old_private_helpers')
    frozen, wrapper, review, _, _, checked = helpers.frozen_cpu_module(monkeypatch, tmp_path)
    monkeypatch.setitem(sys.modules, 'd16_native_process_collection_v2', frozen)
    v3 = load(DEV/'d16_native_process_collection_v3.py', 'new_public_collection')
    adapter = load(DEV/'r040e_d16_process_collection_v1.py', 'new_private_collection')
    monkeypatch.setattr(adapter, '_frozen', lambda: v3)
    owner = helpers.owner(tmp_path, dry=dry)
    owner.options.rid = 'E2-R040e'
    body = {'schema': 'ft_r040d_retained_batch0/v1', 'candidate_commit': 'c'*40,
            'review_sha256': 'a'*64, 'pin_sha256': 'b'*64,
            'terminal': 'retained_batch0', 'round': 'E2-R040d'}
    body['metadata_sha256'] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    path = tmp_path/'retained_metadata.json'; path.write_text(json.dumps(body)); path.chmod(0o444)
    owner._r040e_retained_batch0 = {**body, 'binding_file': str(path)}
    return helpers, frozen, v3, adapter, owner, helpers.common(wrapper, review), checked

def test_public_filedry_writes_actual_23_scopes_without_batch0_or_measurement(tmp_path, monkeypatch):
    helpers, frozen, v3, adapter, owner, common, checked = setup(tmp_path, monkeypatch)
    original = owner.directory
    original_loop = frozen._collect_arms
    ids = [[i]*512 for i in range(1, 5)]
    values = [
        adapter.collect_native_processes(owner, ids, slots=4, file_dry_run=True, **common),
        adapter.collect_parking_processes(owner, ids[0], file_dry_run=True, **common),
        adapter.collect_cache_processes(owner, ids[0], file_dry_run=True, **common),
        adapter.collect_native_processes(owner, [ids[0], [5]*5000], slots=2,
                                         interleave=True, file_dry_run=True, **common)]
    assert [len(value['arms']) for value in values] == [9, 4, 4, 6]
    assert len(owner.calls) == 23 and frozen._collect_arms is original_loop
    assert owner.directory == original and owner.first_args == {'original': 'suite'}
    assert values[0]['partial'] is True and values[0]['needs_terminal_combination'] is True
    assert all(value['not_measurement'] for value in values)
    assert not any('dev_D16_4_batch_0_' in name for name, *_ in owner.calls)
    assert len(checked) == 4
    for arm in original.rglob('file_permission_probe.json'):
        assert (arm.parent/'capture/admissions/.cpu_write_probe').is_file()
        assert (arm.parent/'expected_capture.json').is_file()
        assert not (arm.parent/'capture/service_delivery.json').exists()
    assert len(list(original.rglob('file_permission_probe.json'))) == 23

@pytest.mark.parametrize('supplied', ['http://127.0.0.1:8095', 'http://127.0.0.1:51450'])
def test_public_private_endpoint_rejects_before_any_loop(tmp_path, monkeypatch, supplied):
    _, _, _, adapter, owner, common, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='endpoint differs'):
        adapter.collect_native_processes(owner, [[1]*512]*4, slots=4,
            file_dry_run=True, base_url=supplied, **common)
    assert owner.calls == []

def test_formal_public_loop_consumes_nine_actual_service_results_and_reports_missing_file(tmp_path, monkeypatch):
    _, frozen, v3, adapter, owner, common, _ = setup(tmp_path, monkeypatch, dry=False)
    owner.proc = SimpleNamespace(pid=700)
    monkeypatch.setattr(v3, 'birth', lambda pid: {
        'pid': pid, 'start_ticks': 2 if pid == 700 else 3, 'pgid': 700})
    def collect(client, chosen, *, repetitions, repetition_start, slot_offset, root, mode, **kwargs):
        assert client.args[0] == owner.base_url and repetitions == 1
        root.mkdir()
        rows = [{'request': f'request-{i}.json', 'response_path': f'response-{i}.json'}
                for i in range(len(chosen))]
        return {mode if mode == 'batch' else 'alone': [rows]}
    monkeypatch.setattr(v3.workloads, 'collect', collect)
    monkeypatch.setattr(v3.retained, 'exact_id_request', lambda *a, **kw: None)
    def service(name, operation, **kwargs):
        arm = owner.directory/name; arm.mkdir()
        env = owner.environment(owner.worktree, arm, True)
        count = len({row['uid'] for row in json.loads((arm/'expected_capture.json').read_text())})
        capture = arm/'capture/admissions'; capture.mkdir(parents=True)
        identity = {'pid': 800, 'start_ticks': 3, 'pgid': 700,
                    'execution_id': env['FT_D16_EXECUTION_ID']+':tp0'}
        for uid in range(count):
            (capture/f'{uid}.json').write_text(json.dumps({'process_identity': identity}))
        owner.calls.append((name, kwargs, env, owner.startup_wrapper()))
        result = operation(arm)
        (arm/'capture/service_delivery.json').write_text(json.dumps(
            {'terminal': 'complete', 'process_identity': identity}))
        return result
    owner.service = service
    monkeypatch.setattr(v3, 'read_sealed_service_delivery', lambda arm: json.loads(
        (arm/'capture/service_delivery.json').read_text()))
    original = frozen._collect_arms
    result = adapter.collect_native_processes(owner, [[i]*512 for i in range(1,5)], slots=4, **common)
    assert len(owner.calls) == len(result['arms']) == 9
    assert not any('batch_0_' in name for name, *_ in owner.calls)
    assert result['partial'] is True and result['needs_terminal_combination'] is True
    collection = json.loads((Path(result['root'])/'collection.json').read_text())
    assert collection['batch'][0] == [] and len(collection['batch'][1]) == 4
    assert [len(rows) for rows in collection['alone']] == [4, 4]
    assert frozen._collect_arms is original
    # A new output directory exercises the actual failure boundary without editing old output.
    owner.directory = tmp_path/'failed_output'; owner.directory.mkdir(); owner.calls = []
    def missing(arm): raise FileNotFoundError('sealed file absent')
    monkeypatch.setattr(v3, 'read_sealed_service_delivery', missing)
    with pytest.raises(RuntimeError, match=r'arm=dev_D16_4_batch_1_None path=.*capture[\\/]service_delivery.json'):
        adapter.collect_native_processes(owner, [[i]*512 for i in range(1,5)], slots=4, **common)
    assert frozen._collect_arms is original

