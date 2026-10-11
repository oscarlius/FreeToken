import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_startup_requires_explicit_independent_capture_before_imports(monkeypatch):
    startup = load('d16_exact_service_startup')
    monkeypatch.delenv('FT_D16_SERVICE_CAPTURE_DIR', raising=False)
    with pytest.raises(ValueError, match='independent dev_D16'):
        startup.install()


def test_batch_geometry_preserves_live_sha_and_binds_original_admission():
    startup = load('d16_exact_service_startup')
    startup.install_batch_geometry(None)
    adapter = SimpleNamespace(scheduler_batches=[],
        registry=SimpleNamespace(get=lambda uid: {'prompt_sha256': 'a'*64}))
    def native(batch):
        adapter.scheduler_batches.append({'requests': [{'uid': 0, 'input_ids_sha256': 'b'*64}],
            'padded_requests': [{'uid': 0, 'input_ids_sha256': 'b'*64}]})
        return 'native-result'
    adapter.observe_scheduler_batch = native
    startup.install_batch_geometry(adapter)
    batch = SimpleNamespace(reqs=[SimpleNamespace(uid=0, cached_len=23, device_len=24, extend_len=1)],
        input_ids=SimpleNamespace(shape=(1,)))
    assert adapter.observe_scheduler_batch(batch) == 'native-result'
    event = adapter.scheduler_batches[-1]
    assert event['input_shape'] == [1] and event['request_geometry'] == [
        {'uid': 0, 'cached_len': 23, 'device_len': 24, 'extend_len': 1}]
    for row in event['requests'] + event['padded_requests']:
        assert row['input_ids_sha256'] == 'a'*64 and row['live_input_ids_sha256'] == 'b'*64


@pytest.mark.parametrize('capacity', [2, 4])
@pytest.mark.parametrize('host_slots', [0, 5])
def test_service_capacity_uses_actual_argv_and_archives_capture_env(monkeypatch, tmp_path, capacity, host_slots):
    gpu = load('t17_d14_gpu')
    wrapper = tmp_path / 'startup.py'; wrapper.write_text('fixture'); wrapper.chmod(0o444)
    patch = tmp_path / 't17_d14_exact_ids.py'; patch.write_text('fixture'); patch.chmod(0o444)
    monkeypatch.setattr(gpu, 'HERE', tmp_path)
    monkeypatch.setitem(gpu.protocol, 'command', lambda *_: 'fixture')
    calls = []
    def spawn(argv, **kwargs):
        calls.append((argv, kwargs)); return SimpleNamespace(pid=731)
    monkeypatch.setattr(gpu.subprocess, 'Popen', spawn)
    owner = gpu.Run.__new__(gpu.Run)
    owner.directory = tmp_path; owner.proc = None
    owner.gate = lambda *_: 'fixture'
    owner.compiled_extensions = lambda *_: {'fixture': 'sha'}
    owner.environment = lambda *_: {'FT_D16_EXECUTION_ID': 'fixture-execution'}
    owner.startup_wrapper = lambda: wrapper
    owner.set_status = lambda **_: None
    owner.ready_health = lambda *_: None
    owner.parser = lambda *_: {'_unique_suffix': repr('.pid=731'), 'mamba_host_slots': str(host_slots)}
    owner.stop = lambda: None
    assert owner.service('arm', lambda _: 'native callback', health_only=True,
                         max_running_requests=capacity, mamba_host_slots=host_slots) == 'native callback'
    argv, _ = calls[0]
    assert argv[argv.index('--max-running-requests') + 1] == str(capacity)
    assert argv[argv.index('--cuda-graph-max-bs') + 1] == str(capacity)
    assert argv[argv.index('--mamba-host-slots') + 1] == str(host_slots)
    assert json.loads((tmp_path / 'arm/environment.json').read_text())['FT_D16_EXECUTION_ID'] == 'fixture-execution'
    assert 'FT_D16_EXECUTION_ID=fixture-execution' in (tmp_path / 'arm/SERVE_CMD.txt').read_text()


def test_invalid_capacity_fails_before_model_or_directory_access():
    owner = load('t17_d14_gpu').Run.__new__(load('t17_d14_gpu').Run)
    with pytest.raises(ValueError, match='exactly two or four'):
        owner.service('unused', None, max_running_requests=True)


def test_parking_default_does_not_touch_scheduler(monkeypatch):
    startup = load('d16_exact_service_startup')
    monkeypatch.delenv('FT_D16_PARK_RESTORE', raising=False)
    startup.install_parking(object())


def test_expert_cache_default_is_disabled_and_invalid_mode_rejected(monkeypatch):
    startup = load('d16_exact_service_startup')
    monkeypatch.delenv('FT_D16_CACHE_INIT', raising=False)
    startup.configure_expert_cache(object())
    monkeypatch.setenv('FT_D16_CACHE_INIT', 'invalid')
    with pytest.raises(ValueError, match='cold or warm'):
        startup.configure_expert_cache(object())


@pytest.mark.parametrize('mode', ['cold', 'warm'])
def test_expert_cache_initialization_uses_native_transport_without_requests(tmp_path, monkeypatch, mode):
    import contextlib
    torch = pytest.importorskip('torch')
    startup = load('d16_exact_service_startup')
    monkeypatch.setenv('FT_D16_CACHE_INIT', mode)
    monkeypatch.setenv('FT_D16_SERVICE_CAPTURE_DIR', str(tmp_path/'dev_D16/capture'))
    monkeypatch.setenv('FT_D16_EXECUTION_ID', 'fixture:cache')
    calls = []
    class Cache:
        num_layers = 4
        cache_size = 4
        device = 'cpu'
        prefill_hit_rows = 7
        prefill_total_rows = 128
        def __init__(self): self.id_of_slot = torch.full((4,), 99, dtype=torch.int32)
        def is_cpu_layer(self, layer): return layer == 1
        def is_unpinned_layer(self, layer): return layer == 3
        def reset(self): calls.append('reset'); self.id_of_slot.fill_(-1)
        def ensure_experts(self, layer, ids):
            assert ids.tolist() == [[0]]
            calls.append(('ensure', layer)); self.id_of_slot[layer] = layer*384
        def copy_missing(self): calls.append('copy')
        def reset_stats(self): calls.append('reset_stats')
        def decode_miss_stats(self): return {'native_fixture': True}
    cache = Cache()
    states = torch.arange(12, dtype=torch.float32).reshape(2, 3, 2)
    state_pool = SimpleNamespace(conv_states=states, recurrent_states=states.clone(),
        slot_states={'ple_conv': states.clone(), 'ple_ngram_ctx': states.to(torch.int64)})
    forward_calls = []
    scheduler = SimpleNamespace(engine=SimpleNamespace(moe_offload_cache=cache, linear_state_pool=state_pool,
        forward_batch=lambda batch, args: forward_calls.append('native') or 'original-output',
        stream=SimpleNamespace(synchronize=lambda: None)), engine_stream_ctx=contextlib.nullcontext(),
        shutdown=lambda: calls.append('shutdown'), request_state={'unchanged': True})
    startup.configure_expert_cache(scheduler)
    batch = SimpleNamespace(is_decode=True, reqs=[SimpleNamespace(uid=0, table_idx=1, linear_slot_idx=1)])
    for _ in range(127):
        assert scheduler.engine.forward_batch(batch, None) == 'original-output'
    scheduler.shutdown()
    root = tmp_path/'dev_D16/capture/expert_cache'
    init = json.loads((root/'initialization.json').read_text())
    assert init['priming_requests'] == 0 and init['eligible_layers'] == [0, 2]
    assert init['resident_count'] == (2 if mode == 'warm' else 0)
    assert (root/'initial_residency.pt').exists()
    assert len(forward_calls) == 127
    before = json.loads((root/'0.before_decode.json').read_text())
    after = json.loads((root/'0.after_decode127.json').read_text())
    assert before['states'] == after['states'] and len(before['states']) == 4
    assert json.loads((root/'terminal_stats.json').read_text())['prefill_hit_rows'] == 7
    expected = ['reset', ('ensure', 0), 'copy', ('ensure', 2), 'copy', 'reset_stats', 'shutdown'] if mode == 'warm' else ['reset', 'reset_stats', 'shutdown']
    assert calls == expected and scheduler.request_state == {'unchanged': True}


def test_parking_requires_explicit_pause(monkeypatch):
    startup = load('d16_exact_service_startup')
    monkeypatch.setenv('FT_D16_PARK_RESTORE', '1')
    with pytest.raises(RuntimeError, match='explicit development pause'):
        startup.install_parking(SimpleNamespace(_dev_pause_enabled=False))


def test_parking_runs_before_accepted_reply_only(monkeypatch):
    startup = load('d16_exact_service_startup')
    monkeypatch.setenv('FT_D16_PARK_RESTORE', '1')
    calls = []
    scheduler = SimpleNamespace(_dev_pause_enabled=True,
        _reply_dev_pause=lambda msg, status, error, **kwargs: calls.append(('reply', status, kwargs)))
    monkeypatch.setattr(startup, 'parking_roundtrip', lambda owner, request_id: calls.append(('restore', request_id)))
    startup.install_parking(scheduler)
    msg = SimpleNamespace(request_id='pause-17')
    scheduler._reply_dev_pause(msg, 'expired')
    scheduler._reply_dev_pause(msg, 'accepted', started_wallclock=123)
    assert calls == [('reply', 'expired', {}), ('restore', 'pause-17'),
                     ('reply', 'accepted', {'started_wallclock': 123})]


def test_failed_parking_does_not_acknowledge_acceptance(monkeypatch):
    startup = load('d16_exact_service_startup')
    monkeypatch.setenv('FT_D16_PARK_RESTORE', '1')
    calls = []
    scheduler = SimpleNamespace(_dev_pause_enabled=True,
        _reply_dev_pause=lambda *args, **kwargs: calls.append('reply'))
    def fail(*args):
        raise RuntimeError('restore failed')
    monkeypatch.setattr(startup, 'parking_roundtrip', fail)
    startup.install_parking(scheduler)
    with pytest.raises(RuntimeError, match='restore failed'):
        scheduler._reply_dev_pause(SimpleNamespace(request_id='pause-17'), 'accepted')
    assert calls == []


@pytest.mark.parametrize('corrupt', [False, True])
def test_parking_roundtrip_moves_all_four_states_and_frees_only_test_slots(tmp_path, monkeypatch, corrupt):
    import contextlib
    torch = pytest.importorskip('torch')
    startup = load('d16_exact_service_startup')
    monkeypatch.setenv('FT_D16_SERVICE_CAPTURE_DIR', str(tmp_path / 'dev_D16' / 'capture'))
    monkeypatch.setenv('FT_D16_EXECUTION_ID', 'fixture:parking')
    class Pool:
        def __init__(self):
            self.conv_states = torch.arange(12, dtype=torch.float32).reshape(2, 3, 2)
            self.recurrent_states = self.conv_states.clone() + 16
            self.slot_states = {'ple_conv': self.conv_states.clone() + 32,
                                'ple_ngram_ctx': torch.arange(12, dtype=torch.int64).reshape(2, 3, 2)}
            self.host_conv_states = torch.zeros_like(self.conv_states)
            self.host_recurrent_states = torch.zeros_like(self.recurrent_states)
            self.host_slot_states = {key: torch.zeros_like(value) for key, value in self.slot_states.items()}
            self.num_free_host_slots = 1
            self.calls = []
        def alloc_host(self, n):
            assert n == 1
            self.calls.append('alloc'); return [2]
        def free_host(self, ids):
            assert ids == [2]
            self.calls.append('free')
        def to_host(self, src, dst):
            self.calls.append('to_host')
            for device, host in [(self.conv_states, self.host_conv_states),
                                 (self.recurrent_states, self.host_recurrent_states),
                                 *[(self.slot_states[key], self.host_slot_states[key]) for key in self.slot_states]]:
                host[:, dst].copy_(device[:, src])
        def clear_slots(self, slots):
            self.calls.append('clear')
            for value in [self.conv_states, self.recurrent_states, *self.slot_states.values()]:
                value[:, slots] = 0
        def from_host(self, src, dst):
            self.calls.append('from_host')
            for device, host in [(self.conv_states, self.host_conv_states),
                                 (self.recurrent_states, self.host_recurrent_states),
                                 *[(self.slot_states[key], self.host_slot_states[key]) for key in self.slot_states]]:
                device[:, dst].copy_(host[:, src])
            if corrupt:
                self.slot_states['ple_ngram_ctx'][0, dst, 0] += 1
    pool = Pool()
    req = SimpleNamespace(uid=17, table_idx=3, linear_slot_idx=1, mamba_host_tracks=[9])
    scheduler = SimpleNamespace(engine=SimpleNamespace(linear_state_pool=pool,
        stream=SimpleNamespace(synchronize=lambda: pool.calls.append('sync'))),
        engine_stream_ctx=contextlib.nullcontext(),
        decode_manager=SimpleNamespace(running_reqs=[req, SimpleNamespace(uid=18, table_idx=-1)]))
    if corrupt:
        with pytest.raises(RuntimeError, match='H2D state differs'):
            startup.parking_roundtrip(scheduler, 'pause-17')
    else:
        value = startup.parking_roundtrip(scheduler, 'pause-17')
        assert value['before'] == value['host'] == value['restored']
        assert value['state_transport_bitwise'] and not value['continuation_accepted']
        assert value['cleared'] != value['before']
    assert [call for call in pool.calls if call != 'sync'] == ['alloc', 'to_host', 'clear', 'from_host', 'free']
    assert req.table_idx == 3 and req.linear_slot_idx == 1 and req.mamba_host_tracks == [9]
    root = tmp_path / 'dev_D16' / 'capture' / 'parking'
    assert len(list(root.glob('*.pt'))) == 4
    assert (root / 'roundtrip.json').exists() is not corrupt
