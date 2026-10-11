"""CPU-only admission checks for the isolated R059 D07 T16 entrypoint."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest


HERE = Path(__file__).resolve().parent


def load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_entry_exposes_only_r059_and_file_dry_dispatch(monkeypatch):
    module = load('r059_d07_owned_launch.py', 'r059_entry_dispatch')
    seen = []
    monkeypatch.setattr(module, 'file_dry_run', lambda card: seen.append(card))
    monkeypatch.setattr(module, 'controller', lambda card: pytest.fail('file dry must not reserve a batch'))
    assert module.main(['--file-dry-run', '--card', 'D07']) == 0
    assert seen == ['D07']
    with pytest.raises(SystemExit):
        module.main(['--dry-run', '--card', 'D07'])
    assert module.SPECS == {'D07': ('E2-R059-gate-D07', '151ee718b88882b57dba75317bb53c697d5f235f',
                                    't16_r059_d07_candidate.py')}
    assert module.required_rounds('D07') == (('E2-R041-gate-D17', 'kept'),)


def test_candidate_identity_rejects_wrong_commit_before_any_arm():
    module = load('t16_r059_d07_candidate.py', 'r059_bad_candidate')
    valid = SimpleNamespace(case='D07', rid='E2-R059-gate-D07', batch=1,
                            candidate_commit=module.CASES['D07']['new_commit'])
    assert module.validate_identity(valid) == module.CASES['D07']
    valid.candidate_commit = '0' * 40
    with pytest.raises(ValueError, match='candidate commit differs'):
        module.validate_identity(valid)


def test_exact_sources_include_new_port_helper_and_reject_review_hash_drift(monkeypatch, tmp_path):
    module = load('r059_d07_owned_launch.py', 'r059_source_review')
    sources = module.source_hashes('D07')
    assert {'r059_d07_owned_launch.py', 't16_r059_d07_candidate.py',
            't16_r059_private_port_base_v3.py', 'ft_batch_port_pair_v1.py', str(module.CPU_GUARD)} <= set(sources)
    review, dry = tmp_path / 'review.json', tmp_path / 'dry.json'
    dry.write_text('{}', encoding='utf-8')
    dry.chmod(0o444)
    monkeypatch.setattr(module, 'review_path', lambda _: review)
    monkeypatch.setattr(module, 'require_file_dry_run', lambda _: dry)
    expected = {'schema': 'ft_t16_leaf_startup_review/v1', 'rid': 'E2-R059-gate-D07', 'card': 'D07',
                'candidate_commit': module.SPECS['D07'][1], 'parent_commit': module.PARENT_COMMIT,
                'verdict': 'PASS', 'approved': True, 'source_sha256': sources,
                'file_dry_run_sha256': hashlib.sha256(dry.read_bytes()).hexdigest()}
    review.write_text(json.dumps(expected), encoding='utf-8'); review.chmod(0o444)
    try:
        assert module.require_leaf_review('D07') == review
        review.chmod(0o644); expected['source_sha256']['ft_batch_port_pair_v1.py'] = '0' * 64
        review.write_text(json.dumps(expected), encoding='utf-8'); review.chmod(0o444)
        with pytest.raises(RuntimeError, match='binding differs'):
            module.require_leaf_review('D07')
    finally:
        for path in (review, dry):
            if path.exists(): path.chmod(0o644)


def test_cpu_guard_uses_fixed_data2_path_and_reads_bound_bytes(monkeypatch, tmp_path):
    module = load('r059_d07_owned_launch.py', 'r059_cpu_guard')
    assert str(module.CPU_GUARD).replace('\\', '/') == '/data2/FreeToken/runs/dev_R046/r046b_section12_source_v4/cpu_guard/sitecustomize.py'
    guard = tmp_path / 'sitecustomize.py'; guard.write_bytes(b'fixed CPU socket guard')
    guard.chmod(0o444)
    monkeypatch.setattr(module, 'CPU_GUARD', guard)
    monkeypatch.setattr(module, 'CPU_GUARD_SHA256', hashlib.sha256(guard.read_bytes()).hexdigest())
    module.require_cpu_guard()
    guard.chmod(0o644); guard.write_bytes(b'drifted')
    guard.chmod(0o444)
    with pytest.raises(RuntimeError, match='SHA differs'):
        module.require_cpu_guard()
    guard.chmod(0o644)


def test_foreign_lock_held_is_preserved_and_owner_finish_is_not_harness(monkeypatch, tmp_path):
    module = load('r059_d07_owned_launch.py', 'r059_foreign_lock')
    lock = tmp_path / 'gpu.lock'; lock.write_text(json.dumps({'pid': 7}), encoding='utf-8')
    life = SimpleNamespace(process_identity=lambda pid: {'pid': pid, 'start_ticks': 1})
    before = module.foreign_lock_snapshot(lock, life)
    assert module.foreign_lock_after(lock, before, life) == 'preserved'
    lock.unlink()
    ended = SimpleNamespace(process_identity=lambda _pid: None)
    assert module.foreign_lock_after(lock, before, ended) == 'foreign_owner_finished'


def test_file_dry_gate_rejects_source_drift_without_gpu_scan(monkeypatch, tmp_path):
    module = load('t16_r059_d07_candidate.py', 'r059_file_dry_gate')
    runner = object.__new__(module.CandidateRunner)
    runner.options = SimpleNamespace(file_dry_run=True)
    wt = tmp_path / 'wt'; (wt / 'python/freetoken').mkdir(parents=True)
    (wt / 'python/freetoken/__init__.py').write_text('', encoding='utf-8')
    calls = []
    def command(argv, **_kwargs):
        calls.append(argv)
        if argv[-1] == 'HEAD': return module.CASES['D07']['parent_commit']
        if argv[-1] == '--untracked-files=no': return 'dirty'
        pytest.fail('native import must not follow source drift')
    monkeypatch.setitem(module.base, 'command', command)
    with pytest.raises(RuntimeError, match='dirty'):
        runner.gate(wt, module.CASES['D07']['parent_commit'])
    assert not any('nvidia-smi' in argv for argv in calls)


def test_pair_probe_rejects_adjacent_occupied_port_without_listening(monkeypatch):
    base = load('t16_r059_private_port_base_v3.py', 'r059_pair_probe')
    port = base.dynamic_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
        occupied.bind(('127.0.0.1', port + 1))
        with pytest.raises(OSError):
            base._port_pair.probe_pair(port)
    receipt = base.port_receipt(port)
    assert receipt['api'] == port and receipt['tcpstore'] == port + 1
    assert receipt['probe'] == 'simultaneous wildcard bind; no listen/connect'


def test_readonly_source_copy_does_not_make_actual_output_readonly(tmp_path):
    source, output = tmp_path / 'source.sh', tmp_path / 'round' / 'batch.sh'
    source.write_text('# immutable source\n', encoding='utf-8'); source.chmod(0o444)
    output.parent.mkdir()
    with output.open('xb') as target:
        target.write(source.read_bytes())
    with output.open('a', encoding='utf-8') as target:
        target.write('# actual output remains writable\n')
    assert output.read_text(encoding='utf-8').endswith('writable\n')


def test_candidate_binds_root_native_provenance_and_zeroes_trace_pause(monkeypatch, tmp_path):
    module = load('t16_r059_d07_candidate.py', 'r059_native')
    parent, candidate = tmp_path / 'parent.json', tmp_path / 'candidate.json'
    root = tmp_path / 'root'; source = root / 'wt/e2d07-trace-lm/python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp'
    source.parent.mkdir(parents=True); source.write_bytes(b'fixture')
    parent_value = {'schema': 'ft_r051_parent_native_provenance/v1',
                    'business_python_parent': {'commit': module.CASES['D07']['parent_commit']},
                    'native_artifact_origin': {'commit': module.PARENT_NATIVE_COMMIT}}
    parent.write_text(json.dumps(parent_value), encoding='utf-8')
    kernel = root / 'wt/e2d07-trace-lm/python/freetoken/kernel'
    parent_kernel = root / 'wt/e2base1-p1/python/freetoken/kernel'
    candidate_value = {'schema': 'ft_r059_d07_native_provenance/v1',
                       'candidate_commit': module.CASES['D07']['new_commit'],
                       'parent_commit': module.CASES['D07']['parent_commit'],
                       'native_artifact_origin_commit': module.PARENT_NATIVE_COMMIT,
                       'parent_provenance': str(parent),
                       'parent_provenance_sha256': hashlib.sha256(parent.read_bytes()).hexdigest(),
                       'worktree': str(root / 'wt/e2d07-trace-lm'), 'native_sources_unchanged': True,
                       'existing_trees_modified': False, 'gpu_api_called': False, 'model_endpoints_connected': False,
                       'native': {name: {'path': str(kernel / (name + '.cpython-310-x86_64-linux-gnu.so')),
                                         'source': str(parent_kernel / (name + '.cpython-310-x86_64-linux-gnu.so')),
                                         'sha256': module.EXTENSION_SHA256['new'][name],
                                         'size': module.EXTENSION_SIZE['new'][name], 'regular_copy': True}
                                  for name in module.EXTENSION_SHA256['new']}}
    candidate.write_text(json.dumps(candidate_value), encoding='utf-8')
    parent.chmod(0o444); candidate.chmod(0o444)
    monkeypatch.setattr(module, 'ROOT', root)
    monkeypatch.setattr(module, 'PARENT_NATIVE_PROVENANCE', parent)
    monkeypatch.setattr(module, 'CANDIDATE_NATIVE_PROVENANCE', candidate)
    monkeypatch.setattr(module, 'PARENT_NATIVE_PROVENANCE_SHA256', hashlib.sha256(parent.read_bytes()).hexdigest())
    monkeypatch.setattr(module, 'CANDIDATE_NATIVE_PROVENANCE_SHA256', '0' * 64)
    with pytest.raises(ValueError, match='SHA binding differs'):
        module.require_native_provenance()
    monkeypatch.setattr(module, 'CANDIDATE_NATIVE_PROVENANCE_SHA256', hashlib.sha256(candidate.read_bytes()).hexdigest())
    assert module.require_native_provenance() == parent
    runner = object.__new__(module.CandidateRunner)
    runner.options = SimpleNamespace(file_dry_run=True)
    env = runner.environment(tmp_path, None, False)
    assert env['CUDA_VISIBLE_DEVICES'] == ''
    assert 'FT_DEV_ROUTE_TRACE' not in env and 'FT_DEV_PAUSE_ENDPOINT' not in env
    parent.chmod(0o644); candidate.chmod(0o644)
