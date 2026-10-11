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
    v4 = load(DEV/'d16_native_process_collection_v6.py', 'new_probe_collection')
    monkeypatch.setitem(sys.modules, 'd16_native_process_collection_v4', v4)
    v3 = load(DEV/'d16_native_process_collection_v5.py', 'new_public_collection')
    adapter = load(DEV/'r040f_d16_process_collection_v2.py', 'new_private_collection')
    monkeypatch.setattr(adapter, '_frozen', lambda: v3)
    cpu_report = tmp_path / 'cpu_report.json'
    cpu_report.write_text('{}')
    proof = lambda *args: {'fixture': 'sealed-review', 'source_files': {}, 'review': str(review), 'cpu_report': str(cpu_report)}
    monkeypatch.setattr(v4, 'verify_source_review', proof)
    monkeypatch.setattr(v3, 'verify_source_review', proof)
    owner = helpers.owner(tmp_path, dry=dry)
    owner.options.rid = 'E2-R040f'
    body = {'schema': 'ft_r040d_retained_batch0/v1', 'candidate_commit': 'c'*40,
            'review_sha256': 'a'*64, 'pin_sha256': 'b'*64,
            'terminal': 'retained_batch0', 'round': 'E2-R040d'}
    body['metadata_sha256'] = hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    path = tmp_path/'retained_metadata.json'; path.write_text(json.dumps(body)); path.chmod(0o444)
    owner._r040e_retained_batch0 = {**body, 'binding_file': str(path)}
    return helpers, frozen, v3, adapter, owner, helpers.common(wrapper, review), checked

def test_frozen_loader_rejects_tampered_v4_before_import_time_marker(tmp_path, monkeypatch):
    package = tmp_path / 'sealed'; package.mkdir()
    marker_path = tmp_path / 'v4-imported'
    (package / 'r040f_d16_process_collection_v2.py').write_bytes(
        (DEV / 'r040f_d16_process_collection_v2.py').read_bytes())
    (package / 'd16_native_process_collection_v6.py').write_text(
        f"from pathlib import Path\nPath({str(marker_path)!r}).write_text('executed')\n")
    v5 = package / 'd16_native_process_collection_v5.py'
    v5.write_bytes((DEV / 'd16_native_process_collection_v5.py').read_bytes())
    import hashlib
    (package / 'MANIFEST.sha256').write_text(
        '0' * 64 + '  d16_native_process_collection_v6.py\n' +
        hashlib.sha256(v5.read_bytes()).hexdigest() + '  d16_native_process_collection_v5.py\n')
    for path in package.iterdir(): path.chmod(0o444)
    package.chmod(0o555)
    local = load(package / 'r040f_d16_process_collection_v2.py', 'tampered_r040f_loader')
    with pytest.raises(ValueError, match='source SHA differs: d16_native_process_collection_v6.py'):
        local._frozen()
    assert not marker_path.exists()


def test_public_filedry_writes_actual_remaining_14_scopes_without_measurement(tmp_path, monkeypatch):
    helpers, frozen, v3, adapter, owner, common, checked = setup(tmp_path, monkeypatch)
    original = owner.directory
    original_loop = frozen._collect_arms
    ids = [[i]*512 for i in range(1, 5)]
    values = [
        adapter.collect_parking_processes(owner, ids[0], file_dry_run=True, **common),
        adapter.collect_cache_processes(owner, ids[0], file_dry_run=True, **common),
        adapter.collect_native_processes(owner, [ids[0], [5]*5000], slots=2,
                                         interleave=True, file_dry_run=True, **common)]
    assert [len(value['arms']) for value in values] == [4, 4, 6]
    assert len(owner.calls) == 14 and frozen._collect_arms is original_loop
    assert owner.directory == original and owner.first_args == {'original': 'suite'}
    assert all(value['not_measurement'] for value in values)
    assert all('dev_D16_4_' not in name for name, *_ in owner.calls)
    for arm in original.rglob('file_permission_probe.json'):
        assert (arm.parent/'capture/admissions/.cpu_write_probe').is_file()
        assert (arm.parent/'expected_capture.json').is_file()
        assert not (arm.parent/'capture/service_delivery.json').exists()
    assert len(list(original.rglob('file_permission_probe.json'))) == 14

@pytest.mark.parametrize('supplied', ['http://127.0.0.1:8095', 'http://127.0.0.1:51450'])
def test_public_private_endpoint_rejects_before_any_loop(tmp_path, monkeypatch, supplied):
    _, _, _, adapter, owner, common, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='endpoint differs'):
        adapter.collect_native_processes(owner, [[1]*512]*2, slots=2, interleave=True,
            file_dry_run=True, base_url=supplied, **common)
    assert owner.calls == []

def test_formal_interleave_loop_consumes_six_actual_service_results_and_reports_missing_file(tmp_path, monkeypatch):
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
            {'terminal': 'complete', 'process_identity': identity,
             'scheduler_batches': [{'phase': 'prefill',
                 'requests': [{'uid': 0}, {'uid': 1}],
                 'request_geometry': [{'uid': 0, 'extend_len': 1}, {'uid': 1, 'extend_len': 2}],
                 'physical_size': 2, 'padded_size': 2, 'input_shape': [2, 1]}]}))
        return result
    owner.service = service
    def interleave(arm, chosen, *, client, repetition):
        root = arm / 'collection'; root.mkdir()
        return {'batch': [[{'uid': index, 'request': f'request-{index}.json',
                           'response_path': f'response-{index}.json'}
                          for index in range(len(chosen))]]}
    monkeypatch.setattr(sys.modules['d16_native_process_collection_v4'], '_interleave_queries', interleave)
    monkeypatch.setattr(v3, 'read_sealed_service_delivery', lambda arm: json.loads(
        (arm/'capture/service_delivery.json').read_text()))
    original = frozen._collect_arms
    result = adapter.collect_native_processes(owner, [[1]*512, [5]*5000], slots=2, interleave=True, **common)
    assert len(owner.calls) == len(result['arms']) == 6
    collection = json.loads((Path(result['root'])/'collection.json').read_text())
    assert [len(rows) for rows in collection['batch']] == [2, 2]
    assert [len(rows) for rows in collection['alone']] == [2, 2]
    assert frozen._collect_arms is original
    # A new output directory exercises the actual failure boundary without editing old output.
    owner.directory = tmp_path/'failed_output'; owner.directory.mkdir(exist_ok=True); owner.calls = []
    def missing(arm): raise FileNotFoundError('sealed file absent')
    monkeypatch.setattr(v3, 'read_sealed_service_delivery', missing)
    with pytest.raises(RuntimeError, match=r'arm=dev_D16_2_batch_0_None path=.*capture[\\/]service_delivery.json'):
        adapter.collect_native_processes(owner, [[1]*512, [5]*5000], slots=2, interleave=True, **common)
    assert frozen._collect_arms is original


def test_probe_loader_rejects_missing_and_writable_source(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    collection = sys.modules['d16_native_process_collection_v4']
    monkeypatch.setattr(collection, 'HERE', tmp_path)
    with pytest.raises(ValueError, match='absent or writable'):
        collection._multisession_probe('0' * 64)
    source = (DEV / 'multisession_probe.py').read_bytes()
    probe = tmp_path / 'multisession_probe.py'
    probe.write_bytes(source)
    probe.chmod(0o444)
    assert callable(collection._multisession_probe(__import__('hashlib').sha256(source).hexdigest())._dev_pause)
    probe.chmod(0o644)
    with pytest.raises(ValueError, match='absent or writable'):
        collection._multisession_probe('0' * 64)


def test_parking_rejects_tampered_probe_before_module_execution(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    collection = sys.modules['d16_native_process_collection_v4']
    probe_root = tmp_path / 'probe'; probe_root.mkdir()
    marker_path = tmp_path / 'executed-marker'
    probe = probe_root / 'multisession_probe.py'
    probe.write_text(f"from pathlib import Path\nPath({str(marker_path)!r}).write_text('executed')\ndef _dev_pause(*args): return {{}}\n")
    probe.chmod(0o444)
    monkeypatch.setattr(collection, 'HERE', probe_root)
    monkeypatch.setattr(collection, 'verify_source_review', lambda *args: {
        'source_files': {'multisession_probe': {'path': str(probe.resolve()), 'sha256': '0' * 64}}})
    owner = SimpleNamespace(directory=tmp_path / 'output')
    owner.directory.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match='probe SHA differs'):
        collection._collect_state_processes(owner, [1], kind='parking', wrapper=tmp_path / 'wrapper',
                                            source_review=tmp_path / 'review', source_review_sha256='x', base_url='http://127.0.0.1:51449')
    assert not marker_path.exists()


def test_actual_native_archive_rejects_tampered_source_sha_before_service(tmp_path, monkeypatch):
    _, _, collection, adapter, owner, common, _ = setup(tmp_path, monkeypatch)
    source = DEV / 'multisession_probe.py'
    report = tmp_path / 'cpu_report.json'; report.write_text('{}')
    base = sys.modules['d16_native_process_collection_v4']
    proof = lambda *args: {
        'source_files': {'multisession_probe': {'path': str(source), 'sha256': '0' * 64}},
        'review': str(tmp_path / 'review.json'), 'cpu_report': str(report)}
    monkeypatch.setattr(base, 'verify_source_review', proof)
    monkeypatch.setattr(collection, 'verify_source_review', proof)
    (tmp_path / 'review.json').write_text('{}')
    with pytest.raises(ValueError, match='changed while archiving'):
        adapter.collect_native_processes(owner, [[1] * 512, [5] * 5000], slots=2,
                                         interleave=True, file_dry_run=True, **common)
    assert owner.calls == []


def test_r040f_rejects_old_slots4_scope_before_service(tmp_path, monkeypatch):
    _, _, _, adapter, owner, common, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match='remaining two-way interleave'):
        adapter.collect_native_processes(owner, [[1] * 512] * 4, slots=4,
                                         file_dry_run=True, **common)
    assert owner.calls == []


def test_formal_parking_and_cache_run_actual_state_collector_loops(tmp_path, monkeypatch):
    _, _, collection, adapter, owner, common, _ = setup(tmp_path, monkeypatch, dry=False)
    base = sys.modules['d16_native_process_collection_v4']
    probe_root = tmp_path / 'sealed_probe'; probe_root.mkdir()
    probe = probe_root / 'multisession_probe.py'
    probe.write_bytes((DEV / 'multisession_probe.py').read_bytes()); probe.chmod(0o444)
    monkeypatch.setattr(base, 'HERE', probe_root)
    digest = __import__('hashlib').sha256(probe.read_bytes()).hexdigest()
    monkeypatch.setattr(base, 'verify_source_review', lambda *args: {
        'source_files': {'multisession_probe': {'path': str(probe.resolve()), 'sha256': digest}}})
    owner.proc = SimpleNamespace(pid=700)
    monkeypatch.setattr(base, 'birth', lambda pid: {'pid': pid, 'start_ticks': 2 if pid == 700 else 3, 'pgid': 700})
    monkeypatch.setattr(base, '_parking_query', lambda *args, **kwargs: {
        'status': 200, 'response': {'uid': 0, 'finished': True,
        'input_ids_sha256': __import__('hashlib').sha256(__import__('struct').pack('<2i', 7, 8)).hexdigest(),
        'usage': {'completion_tokens': 128}, 'text': 'same'}})
    monkeypatch.setattr(base.retained, 'exact_id_request', lambda _base_url, ids, **kwargs: {
        'status': 200, 'response': {'uid': 0, 'finished': True,
        'input_ids_sha256': __import__('hashlib').sha256(__import__('struct').pack('<2i', *ids)).hexdigest(),
        'usage': {'completion_tokens': 128}, 'text': 'same'}})
    def service(name, operation, **kwargs):
        arm = owner.directory / name; arm.mkdir()
        env = owner.environment(owner.worktree, arm, True)
        identity = {'pid': 800 + len(owner.calls), 'start_ticks': 3, 'pgid': 700,
                    'execution_id': env['FT_D16_EXECUTION_ID'] + ':tp0'}
        admissions = arm / 'capture/admissions'; admissions.mkdir(parents=True)
        (admissions / '0.json').write_text(json.dumps({'uid': 0, 'process_identity': identity}))
        owner.calls.append((name, kwargs, env, owner.startup_wrapper()))
        value = operation(arm)
        cache = arm / 'capture/expert_cache'
        if 'FT_D16_CACHE_INIT' in env:
            cache.mkdir(parents=True)
            warm = env['FT_D16_CACHE_INIT'] == 'warm'
            (cache / 'initialization.json').write_text(json.dumps({'mode': 'warm' if warm else 'cold',
                'execution_id': identity['execution_id'], 'priming_requests': 0,
                'resident_count': 2 if warm else 0, 'eligible_layers': [1, 2]}))
            (cache / 'terminal_stats.json').write_text(json.dumps({'prefill_hit_rows': 1 if warm else 0}))
            for label in ('before_decode', 'after_decode127'):
                (cache / f'0.{label}.pt').write_bytes(b'fixture')
                (cache / f'0.{label}.json').write_text(json.dumps({'uid': 0, 'label': label,
                    'states': {'conv': {}, 'recurrent': {}, 'ple_conv': {}, 'ple_ngram_ctx': {}}}))
        delivery = {'terminal': 'complete', 'process_identity': identity,
                    'deliveries': [{'uid': 0, 'generation_index': index, 'delivered': True,
                                    'sampled_token_id': 100 + index} for index in range(128)]}
        capture = arm / 'capture'; capture.mkdir(exist_ok=True)
        (capture / 'service_delivery.json').write_text(json.dumps(delivery))
        return value
    owner.service = service
    monkeypatch.setattr(base, 'read_sealed_service_delivery', lambda arm: json.loads(
        (arm / 'capture/service_delivery.json').read_text()))
    parking = adapter.collect_parking_processes(owner, [7, 8], **common)
    cache = adapter.collect_cache_processes(owner, [7, 8], **common)
    assert len(parking['arms']) == len(cache['arms']) == 4
    assert [row['arm'] for row in parking['arms']] == ['control_0', 'control_1', 'restore_0', 'restore_1']
    assert [row['arm'] for row in cache['arms']] == ['cold_0', 'cold_1', 'warm_0', 'warm_1']
    assert all(len(row['tokens']) == 128 for row in parking['arms'] + cache['arms'])
    assert all('states' in row for row in cache['arms'])


def test_r040f_probe_loader_is_same_directory_only():
    source = (DEV / 'd16_native_process_collection_v6.py').read_text(encoding='utf-8')
    assert "HERE / 'multisession_probe.py'" in source
    assert "from multisession_probe import" not in source
    assert "'multisession_probe':here/'multisession_probe.py'" in source


