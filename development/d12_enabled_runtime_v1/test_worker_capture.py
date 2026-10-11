"""D12 worker integration: admission, import order, failure and cleanup contracts."""
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

import segment_capture
import worker_capture
from test_segment_capture import Pool, batch, request


def configure(tmp_path, monkeypatch):
    root = tmp_path / "dev_D16" / "capture"
    for key, value in {"FT_D12_DIAGNOSTIC": "1", "FT_D16_SERVICE_CAPTURE_DIR": str(root),
                       "FT_D12_MAX_EVENTS": "1024", "FT_D12_MAX_EVENT_BYTES": "1000000"}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("FT_DEV_STATE_DUMP", raising=False)
    monkeypatch.delenv("FT_DEV_ROUTE_TRACE", raising=False)
    monkeypatch.delenv("FT_D16_CACHE_INIT", raising=False)
    monkeypatch.delenv("FT_D16_PARK_RESTORE", raising=False)
    monkeypatch.delenv("FT_D12_REPLAY_INPUT_DIR", raising=False)
    monkeypatch.delenv("FT_D12_REPLAY_INPUT_SHA256", raising=False)
    monkeypatch.delenv("FT_D12_CAPTURE_POLICY", raising=False)
    monkeypatch.delenv("FT_D12_PROMPT_TAIL", raising=False)
    monkeypatch.delenv("FT_DEV_LOGITS_DUMP", raising=False)
    monkeypatch.delenv("FT_D12_D0_COVERAGE", raising=False)
    # Register absent keys too: prepare_environment writes these directly.
    for key in ("FT_DEV_D0", "FT_DEV_D0_PATH"):
        monkeypatch.setenv(key, os.environ.get(key, ""))
        monkeypatch.delenv(key)
    monkeypatch.delitem(sys.modules, "freetoken.kvcache.linear_state_pool", raising=False)
    return root


def fixture(tmp_path, monkeypatch, *, limits=(10, 100000)):
    root = configure(tmp_path, monkeypatch)
    capture, dump, _ = worker_capture.prepare_environment()
    monkeypatch.setattr(segment_capture, "_configured_dump_path", lambda: str(dump))

    class Cache:
        quant_format = "nvfp4"
        prefill_overlap = False
        prefill_routed_only_max_tokens = 0

        def prepare_prefill_routed_only(self, *_):
            raise AssertionError("threshold-zero CPU fixture must never prepare routed banks")

    cache = Cache()
    pool = Pool(dump)
    engine = SimpleNamespace(ctx=SimpleNamespace(route_tracer=None), moe_offload_cache=cache,
                             linear_state_pool=pool, forward_batch=lambda _: "forward")
    shutdown_calls = []
    scheduler = SimpleNamespace(engine=engine, shutdown=lambda: shutdown_calls.append(1) or "shutdown")
    errors = []
    adapter = SimpleNamespace(destination=capture, expected_queries=[{"uid": 0}],
        registry=SimpleNamespace(get=lambda uid: {"event_identity": "admission", "prompt_sha256": "prompt-sha"}),
        capture=SimpleNamespace(process_identity={"pid": 1, "start_ticks": 2, "execution_id": "cpu"}),
        record_observer_error=errors.append)
    originals = (engine.forward_batch, scheduler.shutdown, Cache.prepare_prefill_routed_only)
    close = worker_capture.install_worker_capture(scheduler, adapter, capture, dump, limits)
    return root, scheduler, adapter, close, originals, shutdown_calls, errors


def test_installed_capture_binds_existing_admission_and_restores(tmp_path, monkeypatch):
    root, scheduler, adapter, close, originals, shutdown_calls, errors = fixture(tmp_path, monkeypatch)
    assert scheduler.engine.forward_batch(batch([request(uid=0)])) == "forward"
    rows = [json.loads(line) for line in (root / "d12_events.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["physical_event_identity"] == "admission"
    assert rows[0]["prompt_ids_sha256"] == "prompt-sha"
    assert rows[0]["process_identity"] == adapter.capture.process_identity
    assert rows[0]["evidence"]["schema"] == "ft_d12_post_prefill_state/v1"
    assert scheduler.shutdown() == "shutdown"
    close()  # Owned teardown is idempotent; it cannot seal twice.
    assert scheduler.engine.forward_batch is originals[0] and scheduler.shutdown is originals[1]
    assert type(scheduler.engine.moe_offload_cache).prepare_prefill_routed_only is originals[2]
    assert shutdown_calls == [1] and errors == []


def test_event_budget_failure_is_registered_before_native_shutdown(tmp_path, monkeypatch):
    root, scheduler, _, close, _, shutdown_calls, errors = fixture(tmp_path, monkeypatch, limits=(1, 1))
    with pytest.raises(ValueError, match="budget exhausted"):
        scheduler.engine.forward_batch(batch([request(uid=0)]))
    assert errors and "budget exhausted" in errors[0]
    assert (root / "d12_events.jsonl").read_bytes() == b""
    scheduler.shutdown()
    close()
    assert shutdown_calls == [1]


@pytest.mark.parametrize("fault", ["disabled", "trace", "dump_conflict", "late_import", "limit", "cache_init", "parking", "tail_mode",
                                  "d0_mode", "d0_disabled", "d0_path"])
def test_invalid_startup_is_rejected_before_worker_imports(tmp_path, monkeypatch, fault):
    root = configure(tmp_path, monkeypatch)
    if fault == "disabled":
        monkeypatch.setenv("FT_D12_DIAGNOSTIC", "0")
    elif fault == "trace":
        monkeypatch.setenv("FT_DEV_ROUTE_TRACE", "1")
    elif fault == "dump_conflict":
        monkeypatch.setenv("FT_DEV_STATE_DUMP", str(tmp_path / "different"))
    elif fault == "late_import":
        monkeypatch.setitem(sys.modules, "freetoken.kvcache.linear_state_pool", SimpleNamespace(DUMP_PATH=""))
    elif fault == "cache_init":
        monkeypatch.setenv("FT_D16_CACHE_INIT", "warm")
    elif fault == "parking":
        monkeypatch.setenv("FT_D16_PARK_RESTORE", "1")
    elif fault == "tail_mode":
        monkeypatch.setenv("FT_D12_PROMPT_TAIL", "unknown")
    elif fault == "d0_mode":
        monkeypatch.setenv("FT_D12_D0_COVERAGE", "unknown")
    elif fault in ("d0_disabled", "d0_path"):
        monkeypatch.setenv("FT_D12_D0_COVERAGE", "1")
        monkeypatch.setenv("FT_DEV_D0" if fault == "d0_disabled" else "FT_DEV_D0_PATH",
                           "0" if fault == "d0_disabled" else str(tmp_path / "elsewhere"))
    else:
        monkeypatch.setenv("FT_D12_MAX_EVENTS", "0")
    with pytest.raises(ValueError):
        worker_capture.prepare_environment()
    assert not root.exists()


def test_d0_configuration_preserves_decode_graph_timeline_setting(tmp_path, monkeypatch):
    root = configure(tmp_path, monkeypatch)
    monkeypatch.setenv("FT_D12_D0_COVERAGE", "1")
    monkeypatch.setenv("FT_DEV_D0_TIMELINE", "0")
    worker_capture.prepare_environment()
    assert os.environ["FT_DEV_D0"] == "1"
    assert os.environ["FT_DEV_D0_PATH"] == str(root / "d12_d0")
    assert os.environ["FT_DEV_D0_TIMELINE"] == "0"


def test_worker_function_is_spawn_picklable_and_rejects_tp_before_delegate():
    assert pickle.loads(pickle.dumps(worker_capture.run_scheduler)) is worker_capture.run_scheduler
    with pytest.raises(ValueError, match="TP=1"):
        worker_capture.run_scheduler(SimpleNamespace(tp_info=SimpleNamespace(size=2)), None)


@pytest.mark.parametrize("native_fails", [False, True])
def test_cleanup_error_does_not_replace_native_failure(monkeypatch, tmp_path, caplog, native_fails):
    package = ModuleType("equiv_suite")
    startup = ModuleType("equiv_suite.service_capture_startup")
    original = lambda scheduler: object()
    startup.install_scheduler_capture = original
    package.service_capture_startup = startup
    native = ModuleType("d16_native_capture_shutdown_v3")
    primary = ValueError("primary-native-error")

    def native_worker(args, queue):
        startup.install_scheduler_capture(object())
        if native_fails:
            raise primary
        return "native-result"

    def bad_close():
        raise RuntimeError("cleanup-error")

    native.run_scheduler = native_worker
    monkeypatch.setitem(sys.modules, "equiv_suite", package)
    monkeypatch.setitem(sys.modules, "equiv_suite.service_capture_startup", startup)
    monkeypatch.setitem(sys.modules, "d16_native_capture_shutdown_v3", native)
    monkeypatch.setattr(worker_capture, "prepare_environment", lambda: (tmp_path, tmp_path, (1, 1)))
    monkeypatch.setattr(worker_capture, "install_worker_capture", lambda *args: bad_close)
    args = SimpleNamespace(tp_info=SimpleNamespace(size=1, is_primary=lambda: True))
    with pytest.raises(ValueError if native_fails else RuntimeError,
                       match="primary-native-error" if native_fails else "cleanup-error") as error:
        worker_capture.run_scheduler(args, None)
    assert startup.install_scheduler_capture is original
    if native_fails:
        assert error.value is primary
        assert "cleanup-error" in caplog.text


@pytest.mark.parametrize("cleanup_failure,bind_inputs,natural", [
    (False, False, False), (True, False, False), (False, True, False), (False, True, True), (True, True, True)])
def test_real_d16_worker_entry_with_native_state_pool_cpu_fixture(tmp_path, cleanup_failure, bind_inputs, natural):
    source = os.environ.get("FT_D12_NATIVE_SOURCE")
    runtime = os.environ.get("FT_D12_D16_RUNTIME")
    if not source or not runtime:
        pytest.skip("requires actual Linux candidate and frozen D16 shutdown module")
    root = tmp_path / "dev_D16" / "capture"
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps([{"uid": uid, "generation_index": 0, "logical_label": f"cpu-native-entry-{uid}"}
                                    for uid in range(3 if bind_inputs else 1)]))
    env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "FT_D12_DIAGNOSTIC": "1",
           "FT_D16_SERVICE_CAPTURE_DIR": str(root), "FT_D16_SERVICE_CAPTURE_EXPECTED_JSON": str(expected),
           "FT_D16_SERVICE_CAPTURE_MAX_CAPTURES": "4", "FT_D16_SERVICE_CAPTURE_MAX_BYTES": "1000000",
           "FT_D16_EXECUTION_ID": "d12-cpu-worker", "FT_D12_MAX_EVENTS": "16", "FT_D12_MAX_EVENT_BYTES": "1000000",
           "FT_D12_CPU_FIXTURE_CLEANUP_FAILURE": "1" if cleanup_failure else "0",
           "PYTHONPATH": os.pathsep.join([str(Path(__file__).parent), str(Path(source) / "python"),
                                        str(Path(source) / "scripts"), runtime])}
    env.pop("FT_DEV_STATE_DUMP", None)
    env.pop("FT_DEV_ROUTE_TRACE", None)
    env.pop("FT_D12_REPLAY_INPUT_DIR", None)
    env.pop("FT_D12_REPLAY_INPUT_SHA256", None)
    env.pop("FT_D12_CAPTURE_POLICY", None)
    env.pop("FT_D12_PROMPT_TAIL", None)
    env.pop("FT_DEV_LOGITS_DUMP", None)
    env.pop("FT_D12_D0_COVERAGE", None)
    env.pop("FT_DEV_D0", None)
    env.pop("FT_DEV_D0_PATH", None)
    if bind_inputs:
        from test_replay_binding import BUNDLE, BUNDLE_SHA
        env["FT_D12_REPLAY_INPUT_DIR"] = str(BUNDLE)
        env["FT_D12_REPLAY_INPUT_SHA256"] = BUNDLE_SHA
    if natural:
        env["FT_D12_CAPTURE_POLICY"] = "natural-terminal-v1"
        env.pop("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON")
        env["FT_D16_SERVICE_CAPTURE_MAX_CAPTURES"] = "8"
        env["FT_D16_SERVICE_CAPTURE_MAX_BYTES"] = "2000000"
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("native_worker_cpu_fixture.py"))],
                            env=env, text=True, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((root / "cpu_fixture_result.json").read_text())
    assert report["cuda_initialized"] is False and report["native_shutdown_calls"] == 1
    assert report["service_terminal"] == ("failed" if cleanup_failure else "complete")
    assert report["primary_error"] == ("cpu-fixture-primary-error" if cleanup_failure else None)
    assert report["event_schemas"] == ["ft_d12_routed_bank_fallback/v1", "ft_d12_post_prefill_state/v1"] * (3 if bind_inputs else 1)
    assert report["frozen_admission_count"] == (3 if bind_inputs else 0)
    assert report["bank_equality_claimed"] is False
    assert report["capture_mode"] == ("natural-terminal-v1" if natural else "fixed-generation")
    if natural and not cleanup_failure:
        assert report["natural_reader"]["delivered_counts"] == {"0": 1, "1": 2, "2": 3}
        assert report["natural_reader"]["output_equivalence_verified"] is False
