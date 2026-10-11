import hashlib
import functools
import importlib.util
import json
import os
from pathlib import Path
import struct
import socket
import threading
import sys
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace, ModuleType

import pytest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


module = load("d16_native_process_collection_test", ROOT / "d16_native_process_collection.py")


@pytest.mark.parametrize('park', [False, True])
def test_parking_query_uses_native_decode_trigger_and_binds_pause(tmp_path, park):
    completed = threading.Event()
    def client(ids, **kwargs):
        root = tmp_path/'capture/sampler/capture-000008'
        root.mkdir(parents=True)
        raw = json.dumps({'rows': [{'uid': 0, 'generation_index': 7}]}).encode()
        (root/'receipt.json').write_bytes(raw)
        (root.parent/'manifest.json').write_text(json.dumps({'captures': [
            {'id': root.name, 'receipt_sha256': hashlib.sha256(raw).hexdigest()}]}))
        assert completed.wait(3)
        return {'status': 200, 'response': {'uid': 0, 'finished': True,
            'input_ids_sha256': hashlib.sha256(struct.pack('<2i', *ids)).hexdigest(),
            'usage': {'completion_tokens': 128}}}
    def pause():
        assert (tmp_path/'parking_trigger.json').exists()
        if park:
            root = tmp_path/'capture/parking'; root.mkdir()
            (root/'roundtrip.json').write_text(json.dumps({'request_id': 'pause-fixture',
                'state_transport_bitwise': True, 'requests': [{'uid': 0}]}))
        completed.set()
        return {'response': {'request_id': 'pause-fixture', 'status': 'accepted'}}
    result = module._parking_query(tmp_path, [11, 12], client=client,
                                   pause_client=pause, park=park, timeout=2)
    assert result['response']['uid'] == 0
    assert (tmp_path/'pause_ack.json').exists()


def test_parking_rejects_query_that_finishes_before_trigger(tmp_path):
    with pytest.raises(RuntimeError, match='finished before live decode'):
        module._parking_query(tmp_path, [11], client=lambda *a, **k: {},
                              pause_client=lambda: pytest.fail('must not pause'), park=True, timeout=1)


def test_interleave_starts_long_only_after_native_short_decode(tmp_path):
    long_started = threading.Event()
    def client(ids, **kwargs):
        short = ids == [11]
        if short:
            root = tmp_path/'capture/sampler/capture-000008'; root.mkdir(parents=True)
            raw = json.dumps({'rows': [{'uid': 0, 'generation_index': 7}]}).encode()
            (root/'receipt.json').write_bytes(raw)
            (root.parent/'manifest.json').write_text(json.dumps({'captures': [
                {'id': root.name, 'receipt_sha256': hashlib.sha256(raw).hexdigest()}]}))
            assert long_started.wait(3)
        else:
            assert (tmp_path/'interleave_trigger.json').exists()
            long_started.set()
        return {'status': 200, 'response': {'uid': 0 if short else 1, 'finished': True,
            'input_ids_sha256': hashlib.sha256(struct.pack('<%di' % len(ids), *ids)).hexdigest(),
            'usage': {'completion_tokens': 128}}}
    result = module._interleave_queries(tmp_path, [[11], [22]*4097], client=client, repetition=0)
    assert [row['uid'] for row in result['batch'][0]] == [0, 1]
    assert [row['label'] for row in result['batch'][0]] == ['batch-0-slot-0', 'batch-0-slot-1']
    assert result['physical_batch_verified'] is False
    for row in result['batch'][0]:
        assert (tmp_path/'collection'/row['request']).exists()


@pytest.mark.parametrize('inputs,slots', [([[11], [22]], 2), ([[11]*4096, [22]*4097], 2),
    ([[11], [22]*4097, [33], [44]], 4)])
def test_interleave_geometry_rejected_before_source_gate_or_directory(tmp_path, inputs, slots):
    owner = Owner(tmp_path)
    with pytest.raises(ValueError, match='short decode input and a long prefill'):
        module.collect_native_processes(owner, inputs, slots=slots, wrapper='unused', interleave=True)
    assert not (tmp_path/'dev_D16').exists()


@pytest.mark.parametrize('kind,fault', [('parking', 'none'), ('parking', 'output'),
    ('cache', 'none'), ('cache', 'output'), ('cache', 'state'), ('cache', 'hits')])
def test_state_collection_owns_four_process_arms_and_rejects_differences(tmp_path, monkeypatch, kind, fault):
    probe = ModuleType('multisession_probe')
    probe._dev_pause = lambda *args: None
    monkeypatch.setitem(sys.modules, 'multisession_probe', probe)
    monkeypatch.setattr(module, 'verify_source_review', lambda *args: {'fixture_only': True})
    monkeypatch.setattr(module, 'birth', lambda pid: {'pid': pid, 'start_ticks': pid + 10, 'pgid': 900})
    calls = []
    class ParkingOwner:
        def __init__(self):
            self.directory = tmp_path
            self.options = SimpleNamespace(rid='fixture-parking')
            self.environment = lambda *args: {'PYTHONPATH': 'fixture'}
            self.first_args = {'previous': 'suite'}
        def service(self, name, operation, **kwargs):
            assert kwargs == {'health_only': True, 'max_running_requests': 4,
                              'mamba_host_slots': 5 if kind == 'parking' else 0}
            self.first_args = {'parking': 'stable'}
            self.proc = SimpleNamespace(pid=101 + len(calls))
            arm = self.directory/name; arm.mkdir()
            env = self.environment(tmp_path, arm, False)
            calls.append((name, env['FT_DEV_PAUSE_ENDPOINT'], env['FT_D16_PARK_RESTORE']) if kind == 'parking'
                         else (name, env['FT_D16_CACHE_INIT']))
            worker = {'pid': 201 + len(calls), 'start_ticks': 211 + len(calls),
                      'execution_id': env['FT_D16_EXECUTION_ID'] + ':tp0'}
            root = arm/'capture/admissions'; root.mkdir(parents=True)
            (root/'one.json').write_text(json.dumps({'uid': 0, 'process_identity': worker}))
            if kind == 'cache':
                cache = root.parent/'expert_cache'; cache.mkdir()
                warm = name.startswith('warm')
                (cache/'initialization.json').write_text(json.dumps({'mode': 'warm' if warm else 'cold',
                    'execution_id': worker['execution_id'], 'priming_requests': 0,
                    'resident_count': 2 if warm else 0, 'eligible_layers': [0, 2]}))
                (cache/'terminal_stats.json').write_text(json.dumps({'prefill_hit_rows':
                    (0 if fault == 'hits' else 2) if warm else 0}))
                for label in ('before_decode', 'after_decode127'):
                    states = {name: {'sha256': ('b' if fault == 'state' and warm else 'a')*64,
                        'shape': [2], 'dtype': 'torch.float32'}
                        for name in ('conv', 'recurrent', 'ple_conv', 'ple_ngram_ctx')}
                    (cache/('0.' + label + '.json')).write_text(json.dumps({'uid': 0, 'label': label, 'states': states}))
                    (cache/('0.' + label + '.pt')).write_bytes(b'fixture-only')
            result = operation(arm)
            (root.parent/'service_delivery.json').write_text(json.dumps({'terminal': 'complete',
                'process_identity': worker, 'deliveries': [{'uid': 0, 'generation_index': index,
                    'delivered': True, 'sampled_token_id': index} for index in range(128)]}))
            return result
    monkeypatch.setattr(module, '_parking_query', lambda arm, ids, **kwargs:
        {'response': {'text': 'different' if fault == 'output' and kwargs['park'] else 'same'}})
    def cache_query(base_url, ids, **kwargs):
        return {'status': 200, 'response': {'uid': 0, 'finished': True,
            'text': 'different' if fault == 'output' and kwargs['output_path'].parent.name.startswith('warm') else 'same',
            'input_ids_sha256': hashlib.sha256(struct.pack('<%di' % len(ids), *ids)).hexdigest(),
            'usage': {'completion_tokens': 128}}}
    monkeypatch.setattr(module.retained, 'exact_id_request', cache_query)
    collect = module.collect_parking_processes if kind == 'parking' else module.collect_cache_processes
    owner = ParkingOwner()
    original_environment = owner.environment
    if fault != 'none':
        match = {'output': 'continuation differs', 'state': 'four states differ', 'hits': 'actual hit evidence differs'}[fault]
        with pytest.raises(RuntimeError, match=match):
            collect(owner, [11], wrapper=frozen_wrapper(tmp_path),
                source_review='fixture', source_review_sha256='fixture')
    else:
        result = collect(owner, [11], wrapper=frozen_wrapper(tmp_path),
            source_review='fixture', source_review_sha256='fixture')
        assert len(result['arms']) == 4 and result['admitted'] is False
    expected_calls = [('control_0', '1', '0'), ('control_1', '1', '0'),
                      ('restore_0', '1', '1'), ('restore_1', '1', '1')] if kind == 'parking' else [
                      ('cold_0', 'cold'), ('cold_1', 'cold'), ('warm_0', 'warm'), ('warm_1', 'warm')]
    assert calls == (expected_calls[:3] if fault == 'hits' else expected_calls)
    assert owner.directory == tmp_path and owner.environment is original_environment
    assert owner.first_args == {'previous': 'suite'}


def frozen_wrapper(tmp_path):
    wrapper = tmp_path / "capture_startup.py"
    wrapper.write_text("# frozen fixture\n")
    wrapper.chmod(0o444)
    return wrapper


class Owner:
    def __init__(self, directory, *, wrong_pgid=False, delivery="complete"):
        self.directory = directory
        self.options = SimpleNamespace(rid="R-test")
        self.proc = SimpleNamespace(pid=os.getpid())
        self.wrong_pgid = wrong_pgid
        self.delivery = delivery
        self.environment = lambda wt, arm=None, d0=False: {"PYTHONPATH": "base"}
        self.startup_wrapper = lambda: Path("old")
        self.calls = []

    def service(self, name, operation, **kwargs):
        arm = self.directory / name
        arm.mkdir(parents=True)
        # Synthetic lifecycle owner: each arm has a fresh real Linux process
        # birth; the local HTTP server only supplies exact-ID client receipts.
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        previous_proc = self.proc
        self.proc = SimpleNamespace(pid=child.pid)
        try:
            env = self.environment(self.directory, arm, None)
            expected = json.loads((arm / "expected_capture.json").read_text())
            expected_count = 128 * (2 if "_batch_" in name else 1)
            assert len(expected) == expected_count
            assert env["FT_D16_EXECUTION_ID"].endswith(name)
            identity = module.birth(child.pid)
            identity["execution_id"] = env["FT_D16_EXECUTION_ID"] + ":tp0"
            if self.wrong_pgid:
                identity["start_ticks"] += 1
            admissions = arm / "capture" / "admissions"
            admissions.mkdir(parents=True)
            for uid in range(expected_count // 128):
                (admissions / f"{uid}.json").write_text(json.dumps({"uid": uid, "process_identity": identity}))
            (arm / "observations.jsonl").write_text("")

            state = {"uid": 0}
            class Handler(BaseHTTPRequestHandler):
                def do_POST(handler):
                    assert handler.path == "/internal/t17/exact-ids"
                    payload = json.loads(handler.rfile.read(int(handler.headers["Content-Length"])))
                    uid = state["uid"]; state["uid"] += 1
                    digest = hashlib.sha256(struct.pack("<%di" % len(payload["input_ids"]), *payload["input_ids"])).hexdigest()
                    body = json.dumps({"uid": uid, "finished": True, "text": "fixture",
                        "input_ids_sha256": digest, "usage": {"completion_tokens": 128}}).encode()
                    handler.send_response(200); handler.end_headers(); handler.wfile.write(body)
                def log_message(self, *args):
                    pass
            server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            thread = threading.Thread(target=server.serve_forever); thread.start()
            self.fixture_base_url = "http://127.0.0.1:" + str(server.server_port)
            self.calls.append((name, kwargs, state, server.server_port, child.pid))
            try:
                result = operation(arm)
                if self.delivery != "missing":
                    (arm / "capture" / "service_delivery.json").write_text(json.dumps({"terminal": self.delivery, "process_identity": result[1]}))
                return result
            finally:
                server.shutdown(); thread.join(); server.server_close()
        finally:
            self.proc = previous_proc
            child.terminate(); child.wait(timeout=5)


def fixture_guard_active():
    guard = sys.modules.get("sitecustomize")
    return bool(guard and getattr(guard, "FT_CPU_FIXTURE_NETWORK_GUARD", False)
                and socket.socket.connect is getattr(guard, "connect", None)
                and socket.socket.connect_ex is getattr(guard, "connect_ex", None)
                and socket.socket.listen is getattr(guard, "listen", None))


def fixture_client_kwargs(owner):
    if not fixture_guard_active():
        pytest.skip("requires the real isolated CPU fixture network guard")
    endpoints = []
    def factory(arm):
        endpoint = owner.fixture_base_url
        assert endpoint != "http://127.0.0.1:8095"
        endpoints.append(endpoint)
        return functools.partial(module.retained.exact_id_request, endpoint)
    return {"fixture_only": True, "request_factory": factory}, endpoints


def test_configured_binds_capture_environment_and_restores_on_error(tmp_path):
    owner = Owner(tmp_path)
    original_environment, original_wrapper = owner.environment, owner.startup_wrapper
    wrapper = frozen_wrapper(tmp_path)
    with pytest.raises(RuntimeError, match="fixture"):
        with module.configured(owner, wrapper, execution_id="R:arm", request_count=2):
            # The legacy compile/base gate calls this before an arm exists.
            assert owner.environment(tmp_path) == {"PYTHONPATH": "base"}
            (tmp_path / "arm").mkdir()
            env = owner.environment(tmp_path, tmp_path / "arm", None)
            assert env["FT_D16_SERVICE_CAPTURE_MAX_CAPTURES"] == str(128 * 2 + 1024)
            assert env["FT_D16_EXECUTION_ID"] == "R:arm"
            expected = json.loads((tmp_path / "arm" / "expected_capture.json").read_text())
            assert len(expected) == 256 and expected[0]["logical_label"] == "R:arm:uid-0"
            raise RuntimeError("fixture")
    assert owner.environment is original_environment
    assert owner.startup_wrapper is original_wrapper


@pytest.mark.skipif(sys.platform != "linux", reason="requires actual /proc process birth and PGID")
def test_collects_two_batch_and_two_alone_repetitions_with_raw_http_receipts(tmp_path, monkeypatch):
    owner = Owner(tmp_path)
    original_directory = owner.directory
    kwargs, endpoints = fixture_client_kwargs(owner)
    result = module.collect_native_processes(owner, [[11, 12], [21, 22]], slots=2,
                                             wrapper=frozen_wrapper(tmp_path), **kwargs)
    root = Path(result["root"])
    assert owner.directory == original_directory
    assert result["model_admitted"] is False and result["requires_independent_raw_review"] is True
    assert len(owner.calls) == 6  # 2 batch + (2 slots * 2 independent alone arms)
    collection = json.loads((root / "collection.json").read_text())
    assert [len(group) for group in collection["batch"]] == [2, 2]
    assert [len(group) for group in collection["alone"]] == [2, 2]
    labels = [row["label"] for group in collection["batch"] + collection["alone"] for row in group]
    assert labels == ["batch-0-slot-0", "batch-0-slot-1", "batch-1-slot-0", "batch-1-slot-1",
                      "alone-0-slot-0", "alone-0-slot-1", "alone-1-slot-0", "alone-1-slot-1"]
    for row in [row for group in collection["batch"] + collection["alone"] for row in group]:
        assert (root / row["request"]).is_file()
        assert (root / row["response_path"]).with_suffix(".response.bin").is_file()
    assert len({call[4] for call in owner.calls}) == 6
    assert len(endpoints) == 6 and all(not endpoint.endswith(":8095") for endpoint in endpoints)
    assert sum(call[2]["uid"] for call in owner.calls) == 8
    evidence = json.loads(Path(result["evidence_map"]).read_text())
    assert evidence["files"] and result["evidence_map_sha256"] == hashlib.sha256(Path(result["evidence_map"]).read_bytes()).hexdigest()


@pytest.mark.skipif(sys.platform != "linux", reason="requires actual /proc process birth and PGID")
def test_native_birth_or_group_violation_restores_owner_directory(tmp_path, monkeypatch):
    owner = Owner(tmp_path, wrong_pgid=True)
    original_directory = owner.directory
    kwargs, _ = fixture_client_kwargs(owner)
    with pytest.raises(ValueError, match="outside the owned process birth/group"):
        module.collect_native_processes(owner, [[1], [2]], slots=2, wrapper=frozen_wrapper(tmp_path), **kwargs)
    assert owner.directory == original_directory


@pytest.mark.parametrize("inputs, slots, message", [
    ([[1]], 2, "exactly two or four"), ([[1], [2], [3]], 2, "exactly two or four"), ([[1], [2]], 3, "exactly two or four"),
    ([[], [2]], 2, "signed-int32"), ([[True], [2]], 2, "signed-int32"), ([[2**31], [2]], 2, "signed-int32")])
def test_rejects_invalid_slot_input_shape_before_arms(tmp_path, inputs, slots, message):
    owner = Owner(tmp_path)
    with pytest.raises(ValueError, match=message):
        module.collect_native_processes(owner, inputs, slots=slots, wrapper=frozen_wrapper(tmp_path))
    assert owner.calls == [] and not (tmp_path / "dev_D16").exists()


def test_non_fixture_source_gate_rejects_before_directory_and_no_gpu_callback(tmp_path):
    owner = Owner(tmp_path)
    with pytest.raises(ValueError, match="pinned independent execution-source review"):
        module.collect_native_processes(owner, [[1], [2]], slots=2, wrapper=frozen_wrapper(tmp_path))
    assert owner.calls == [] and not (tmp_path / "dev_D16").exists()


def test_fixture_gate_rejects_flag_only_fake_guard_before_directory(tmp_path, monkeypatch):
    owner = Owner(tmp_path)
    fake = ModuleType("sitecustomize"); fake.FT_CPU_FIXTURE_NETWORK_GUARD = True
    monkeypatch.setitem(sys.modules, "sitecustomize", fake)
    with pytest.raises(ValueError, match="active CPU network guard"):
        module.collect_native_processes(owner, [[1], [2]], slots=2, wrapper=frozen_wrapper(tmp_path),
                                        fixture_only=True, request_factory=lambda arm: None)
    assert owner.calls == [] and not (tmp_path / "dev_D16").exists()


@pytest.mark.skipif(os.name == "nt", reason="ancestor symlink contract is exercised in Linux stage")
def test_ancestor_symlink_rejected_before_directory(tmp_path):
    target = tmp_path / "target"; target.mkdir()
    linked = tmp_path / "linked"; linked.symlink_to(target, target_is_directory=True)
    owner = Owner(linked)
    with pytest.raises(ValueError, match="ancestor is a symbolic link"):
        module.collect_native_processes(owner, [[1], [2]], slots=2, wrapper=frozen_wrapper(tmp_path))
    assert not (target / "dev_D16").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="requires actual /proc process birth and PGID")
@pytest.mark.parametrize("delivery, message", [("missing", "No such file"), ("failed", "did not produce complete")])
def test_post_stop_delivery_failure_restores_owner_methods_and_directory(tmp_path, monkeypatch, delivery, message):
    owner = Owner(tmp_path, delivery=delivery)
    original_directory, original_environment, original_wrapper = owner.directory, owner.environment, owner.startup_wrapper
    kwargs, _ = fixture_client_kwargs(owner)
    with pytest.raises((ValueError, FileNotFoundError), match=message):
        module.collect_native_processes(owner, [[1], [2]], slots=2, wrapper=frozen_wrapper(tmp_path), **kwargs)
    assert owner.directory == original_directory
    assert owner.environment is original_environment and owner.startup_wrapper is original_wrapper
