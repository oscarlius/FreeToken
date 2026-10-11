from pathlib import Path
import importlib.util
import socket
import sys

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import ft_batch_port_pair_v1 as ports


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pair_rejects_occupied_store_without_using_free_api():
    port = ports.dynamic_port()
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', port + 1))
        with pytest.raises(OSError):
            ports.probe_pair(port)
        with socket.socket() as api:
            api.bind(('127.0.0.1', port))
    ports.probe_pair(port)


def test_pair_rejects_protected_ports():
    for port in (8094, 8095, 8098, 8099, 65535):
        with pytest.raises(ValueError):
            ports.probe_pair(port)


def test_allocator_avoids_ephemeral_range_and_retries_collision(monkeypatch):
    available = ports.dynamic_port()
    candidate = ports.dynamic_port()
    while abs(candidate - available) <= 1:
        candidate = ports.dynamic_port()
    with socket.socket() as occupied:
        occupied.bind(('127.0.0.1', candidate + 1))
        sequence = iter((candidate, available))
        class Rng:
            def randrange(self, *_):
                return next(sequence)
        monkeypatch.setattr(ports.random, 'SystemRandom', Rng)
        assert ports.dynamic_port() == available
    low, high = ports.ephemeral_range()
    assert not (low <= available <= high or low <= available + 1 <= high)


def test_r057a_retains_completed_arms_and_exact_original_input():
    module = load('r057a_oom_remaining_prepare_v2')
    assert module.RID == 'E2-R057a'
    assert module.COLD_ID == 'E2-R057'
    assert [a['name'] for a in module.ARMS] == ['C_trace_on_pause_on', 'D_trace_off_pause_off_graph_off']
    assert module.EXPECTED_INPUT_SHA == 'cd003af3d6f2713fbcf896fe756fb3baf79e38100f10ae5eb4bdcbc937710632'
    module.self_test()
    source = (HERE / 'r057a_oom_remaining_prepare_v2.py').read_text()
    assert 'require_closed_round("E2-R057", "failed_harness")' in source
    assert 'E2-R057a_startup_review_v2.json' in source


def test_r057a_changed_payload_stops_before_transport(tmp_path, monkeypatch):
    module = load('r057a_oom_remaining_prepare_v2')
    calls = []
    monkeypatch.setattr(module.urllib.request, 'urlopen', lambda *_a, **_k: calls.append('transport'))
    class D07:
        def invoke_cold_eq(self, _wt, port, cold_id, _output):
            assert cold_id == 'E2-R057'
            req = module.urllib.request.Request(f'http://127.0.0.1:{port}/v1/chat/completions', data=b'changed')
            module.urllib.request.urlopen(req)
    with pytest.raises(RuntimeError, match='input differs'):
        module.invoke_bound_cold(D07(), tmp_path, ports.dynamic_port())
    assert calls == []
    assert (tmp_path / 'cold_request_payload.json').read_bytes() == b'changed'


def test_new_r058_version_checks_pair_and_does_not_reuse_old_signature():
    source = (HERE / 'r058_concurrent_memory_prepare_v2.py').read_text()
    assert 'reviews/E2-R058-v2' in source
    assert '.dryrun_R058_v2_E2-R058' in source
    assert 'd07.dynamic_fixture_port()' not in source
    assert 'PORT_SOURCE, r056.PROBE' in source
