"""Run the actual R061 v7 child protocol with CPU service boundaries.

All epoch, raw SSE, physical sidecar, worker retirement and output checks run
unchanged. Only model startup and HTTP lifecycle are simulated.
"""
import hashlib
import os
import importlib.util
import json
import sys
import threading
from pathlib import Path

import pytest

DEV = Path(os.environ.get("R061E_RUNTIME_PACK", Path(__file__).parents[1] / "r061e_oom_runtime_v1"))


def load(name):
    path = DEV / name
    spec = importlib.util.spec_from_file_location("fixture_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def protocol_case(tmp_path, monkeypatch, *, retained_worker=False,
                  token_difference=False, text_difference=False):
    v5 = load("r061e_oom_runtime_prepare_v1.py")
    module, runtime = v5.runtime()
    rounds = tmp_path / "rounds"
    monkeypatch.setattr(v5, "ROUNDS", rounds)
    module.ROUNDS = rounds
    run = rounds / module.RID
    monkeypatch.setattr(v5, "runtime", lambda: (module, runtime))
    client = load("r046c_t06_ordinary_client_v3.py")
    lifecycle_source = load("d07_g3g4_prepare.py")
    inputs = []
    for role in ("reference", "affected", "queued"):
        path = tmp_path / (role + ".json")
        path.write_text(json.dumps({"stream": True, "stream_options": {
            "include_usage": True}, "messages": [
                {"role": "user", "content": "fixture"}]}))
        path.chmod(0o444)
        inputs.append(path)

    def birth(pid):
        return {"pid": pid, "start_ticks": pid, "execution_id": f"{pid}:{pid}",
                "pgid": 10, "session": 10}

    class Life:
        live = {10, 20, 30, 40}
        stopped = False

        def process_identity(self, pid):
            return birth(pid) if pid in self.live else None

        def stop_owned_process(self, process):
            assert process.pid == 10
            self.stopped = True

    life = Life()
    fault = threading.Event()
    prequeue_observed = threading.Event()
    stale_serving_read = [False]
    queued_started = threading.Event()
    queue_ready = threading.Event()
    queued_finished = threading.Event()

    class Backend:
        LOCK = tmp_path / "fixture.lock"
        serve_argv = staticmethod(lifecycle_source.serve_argv)

        def __init__(self):
            self.released = False
            self.startup_environment = None
            self.startup_command = None

        def take_d07_gpu_lock(self, rid, batch):
            assert rid == module.RID and batch == 1 and not self.LOCK.exists()
            self.LOCK.write_text("fixture-owner")
            return {"fixture": True}

        def release_d07_gpu_lock(self, owner):
            assert owner == {"fixture": True}
            self.LOCK.unlink()
            self.released = True

        def require_gpu_idle(self):
            pass

        def clean_environment(self, *args, **kwargs):
            return {"CUDA_VISIBLE_DEVICES": "", "FT_DEV_D0": "1",
                    "FT_DEV_PAUSE_ENDPOINT": "1", "FT_DEV_ROUTE_TRACE": "fixture"}

        def start_server(self, directory, worktree, port, trace):
            self.startup_environment = self.clean_environment(worktree)
            self.startup_command = self.serve_argv(port)
            handles = directory / "ordinary_observer" / "backend_handles"
            handles.mkdir(parents=True)
            (handles / "epoch-0.json").write_text(json.dumps({
                "schema": "ft_r061_backend_handle/v1", "epoch": 0,
                "workers": [{**birth(pid), "name": name} for pid, name in [
                    (20, "SchedulerTP"), (30, "Detokenizer"), (40, "Tokenizer")]]}))
            return type("Process", (), {"pid": 10})()

        def load_owned_lifecycle(self):
            return life

    backend = Backend()
    monkeypatch.setattr(runtime, "load_d07", lambda *args: backend)
    monkeypatch.setattr(module, "recovery_contract", lambda *_: {})
    monkeypatch.setattr(module, "ordinary_client", lambda: client)

    def write_output(input_path, output, uid, worker):
        output.parent.mkdir(parents=True, exist_ok=True)
        raw_directory = run / "ordinary_observer" / "workers" / str(worker)
        raw_directory.mkdir(parents=True)
        ids = raw_directory / f"input-{uid}.json"
        ids.write_bytes(b"[1,2]")
        input_digest = hashlib.sha256(ids.read_bytes()).hexdigest()
        service_birth, worker_birth = birth(10), birth(worker)
        (raw_directory / "inputs.jsonl").write_text(json.dumps({
            "schema": "ft_t06_ordinary_input/v3", "uid": uid,
            "input_tokens": 2, "canonical_encoding": "utf8-json-int-array-separators=,:",
            "input_ids_sha256": input_digest, "input_ids_path": str(ids),
            "input_ids_file_sha256": input_digest,
            "source": "Scheduler._process_one_msg(UserMsg)", "time_ns": 1,
            "service_birth": service_birth, "worker_birth": worker_birth}) + "\n")
        tokens = [99, 101 if uid == 2 and token_difference else 100]
        rows = [{"schema": "ft_t06_ordinary_token/v3", "uid": uid,
                 "request_seq": seq, "next_token": token,
                 "completion_tokens_delta": 1, "completion_tokens_cumulative": seq,
                 "finished": seq == 2, "finish_reason": "stop" if seq == 2 else None,
                 "time_ns": seq + 1, "service_birth": service_birth,
                 "worker_birth": worker_birth}
                for seq, token in enumerate(tokens, 1)]
        (raw_directory / "tokens.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows))
        raw = output.with_suffix(".sse")
        content = "changed" if uid == 2 and text_difference else "ok"
        raw.write_text("data: " + json.dumps({
            "id": f"chatcmpl-{uid}", "choices": [
                {"delta": {"content": content}, "finish_reason": "stop"}]}) + "\n"
            + "data: " + json.dumps({"id": f"chatcmpl-{uid}", "choices": [],
                "usage": {"prompt_tokens": 2, "completion_tokens": 2}}) + "\n"
            + "data: [DONE]\n")
        output.write_text(json.dumps({
            "schema": "ft_t06_ordinary_sse/v3", "pause_enabled": False,
            "payload_source": {"path": str(input_path), "sha256": module.sha(input_path)},
            "sse": str(raw), "sse_sha256": module.sha(raw), "uid": uid,
            "usage": {"prompt_tokens": 2, "completion_tokens": 2},
            "finish_reason": "stop"}))
        return {"uid": uid}

    def request(base, input_path, output, **kwargs):
        if input_path == inputs[1]:
            output.with_suffix(".sse").write_text(
                'data: {"error":{"message":"CUDA out of memory"}}\n')
            (run / "fault_receipt.json").write_text(json.dumps({
                "schema": "ft_dev_oom_receipt/v1", "uid": 1, "epoch": 0,
                "point": "before_forward", "count": 1, "pid": 20,
                "wall_time_ns": 1, "monotonic_ns": 1}))
            fault.set()
            raise RuntimeError("fixture API reports injected OOM")
        if input_path == inputs[2]:
            assert prequeue_observed.is_set(), "queued request sent before API restart state"
            assert json.loads((run / "health.prequeue.json").read_text())["maintenance"] == "restarting"
            queued_started.set()
            assert queue_ready.wait(3), "fixture queue was never observed"
            value = write_output(input_path, output, 2, 21)
            life.live = {10, 21, 31, 41} | ({40} if retained_worker else set())
            queued_finished.set()
            return value
        return write_output(input_path, output, 0, 20)

    def health(base):
        if queued_finished.is_set():
            return {"maintenance": "serving", "backend_epoch": 1,
                    "restart_attempts": 1, "restart_waiters": 0}
        if fault.is_set() and queued_started.is_set():
            value = {"maintenance": "restarting", "backend_epoch": 0,
                     "restart_attempts": 1, "restart_waiters": 1}
            queue_ready.set()
            return value
        if fault.is_set():
            if stale_serving_read[0]:
                prequeue_observed.set()
                return {"maintenance": "restarting", "backend_epoch": 0,
                        "restart_attempts": 1, "restart_waiters": 0}
            stale_serving_read[0] = True
        return {"maintenance": "serving", "backend_epoch": 0,
                "restart_attempts": 0, "restart_waiters": 0}

    monkeypatch.setattr(client, "ordinary_request", request)
    monkeypatch.setattr(module, "_health", health)
    try:
        result = v5.child(1, tmp_path, *inputs)
        assert result["all_old_worker_births_exited"] and result["count"] == 3
        assert result["api_birth_unchanged"] and result["cold_token_ids_equal"]
        assert result["cold_full_text_equal"]
        for epoch, uid in [(0, 0), (1, 2)]:
            index = run / "ordinary_observer" / f"epoch-{epoch}-uid-{uid}.json"
            binding = json.loads(index.read_text())
            raw = Path(binding["worker_dir"])
            assert raw.is_dir() and binding["input_ids_paths_preserved"]
            ids = Path(json.loads((raw / "inputs.jsonl").read_text())["input_ids_path"])
            assert ids.is_file() and raw.name in str(ids)
        env = backend.startup_environment
        assert env["FT_DEV_OOM_INJECT"] == "1" and env["FT_DEV_OOM_UID"] == "1"
        assert not any(k in env for k in (
            "FT_DEV_D0", "FT_DEV_ROUTE_TRACE", "FT_DEV_PAUSE_ENDPOINT"))
        argv = backend.startup_command
        assert argv[argv.index("--kv-reserve-tokens") + 1] == "98304"
        assert argv[argv.index("--memory-ratio") + 1] == "0.88"
        assert Path(argv[1]).is_file()
        assert (run / "runtime/r061_oom_backend_handle_hook_v1.py").is_file()
        return result
    finally:
        assert backend.released and life.stopped and not backend.LOCK.exists()


def test_actual_v5_child_and_fault_protocol_success(tmp_path, monkeypatch):
    result = protocol_case(tmp_path, monkeypatch)
    assert (tmp_path / "rounds" / result["rid"] / "result.json").is_file()


def test_actual_protocol_rejects_surviving_old_tokenizer(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="old worker birth remains"):
        protocol_case(tmp_path, monkeypatch, retained_worker=True)


@pytest.mark.parametrize("difference", ["token_difference", "text_difference"])
def test_actual_protocol_rejects_changed_restart_output(tmp_path, monkeypatch, difference):
    with pytest.raises(RuntimeError, match="restart output differs"):
        protocol_case(tmp_path, monkeypatch, **{difference: True})

