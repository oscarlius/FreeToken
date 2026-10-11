"""CPU-only regression for R061d's restart-before-queue ordering."""
from __future__ import annotations

import os
import hashlib
import importlib.util
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


PACK = Path(os.environ.get("R061D_RUNTIME_PACK", Path(__file__).parents[1] / "r061d_oom_runtime_v1"))


def load():
    path = PACK / "r061d_oom_fault_prepare_v1.py"
    spec = importlib.util.spec_from_file_location("r061d_fault", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_full_protocol_observes_restarting_before_queued_request(tmp_path, monkeypatch):
    """A stale serving health response cannot admit the queued request."""
    module = load()
    rounds = tmp_path / "rounds"
    monkeypatch.setattr(module, "ROUNDS", rounds)
    run = rounds / module.RID
    inputs = []
    for role in ("reference", "affected", "queued"):
        path = tmp_path / f"{role}.json"
        path.write_text(json.dumps({"stream": True, "messages": [{"role": "user", "content": "fixture"}]}))
        inputs.append(path)

    def birth(pid):
        return {"pid": pid, "start_ticks": pid, "execution_id": f"{pid}:{pid}", "pgid": 10, "session": 10}

    class Lifecycle:
        live = {10, 20, 30, 40}

        def process_identity(self, pid):
            return birth(pid) if pid in self.live else None

        def stop_owned_process(self, process):
            assert process.pid == 10
            self.stopped = True

    lifecycle = Lifecycle()
    fault, prequeue_observed, queued_started, restart_waiter_observed, queued_finished = (
        threading.Event(), threading.Event(), threading.Event(), threading.Event(), threading.Event()
    )
    events = []

    class Backend:
        LOCK = tmp_path / "fixture.lock"

        def take_d07_gpu_lock(self, rid, batch):
            assert rid == module.RID and batch == 1
            self.LOCK.write_text("fixture")
            return {"owner": "fixture"}

        def release_d07_gpu_lock(self, owner):
            assert owner == {"owner": "fixture"}
            self.LOCK.unlink()

        def require_gpu_idle(self):
            pass

        def clean_environment(self, *_args, **_kwargs):
            return {"CUDA_VISIBLE_DEVICES": ""}

        def serve_argv(self, port):
            return ["python", "serve", "--port", str(port)]

        def start_server(self, *_args):
            return SimpleNamespace(pid=10)

        def load_owned_lifecycle(self):
            return lifecycle

    backend = Backend()

    def write_new(path, value):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream)

    monkeypatch.setattr(module, "r060", lambda: SimpleNamespace(
        private_port_pair=lambda: {"api": 31234}, write_new=write_new
    ))
    monkeypatch.setattr(module, "recovery_contract", lambda *_: {})
    monkeypatch.setattr(module, "_worker_births", lambda *_: [birth(pid) for pid in (20, 30, 40)])
    monkeypatch.setattr(module, "_require_old_workers_exited", lambda _life, _old: {"all_old_worker_births_exited": True, "count": 3})

    def write_output(input_path, output, uid, worker):
        worker_dir = run / "ordinary_observer" / "workers" / str(worker)
        worker_dir.mkdir(parents=True, exist_ok=True)
        input_ids = worker_dir / f"input-{uid}.json"
        input_ids.write_bytes(b"[1,2]")
        digest = hashlib.sha256(input_ids.read_bytes()).hexdigest()
        service_birth, worker_birth = birth(10), birth(worker)
        (worker_dir / "inputs.jsonl").write_text(json.dumps({
            "uid": uid, "input_tokens": 2, "input_ids_sha256": digest,
            "input_ids_path": str(input_ids), "input_ids_file_sha256": digest,
            "time_ns": 1, "service_birth": service_birth, "worker_birth": worker_birth,
        }) + "\n")
        (worker_dir / "tokens.jsonl").write_text("".join(json.dumps({
            "uid": uid, "request_seq": seq, "next_token": token,
            "completion_tokens_delta": 1, "completion_tokens_cumulative": seq,
            "finished": seq == 2, "finish_reason": "stop" if seq == 2 else None,
            "time_ns": seq + 1, "service_birth": service_birth, "worker_birth": worker_birth,
        }) + "\n" for seq, token in enumerate((99, 100), 1)))
        raw = output.with_suffix(".sse")
        raw.write_text("data: " + json.dumps({"id": f"chatcmpl-{uid}", "choices": [{"delta": {"content": "ok"}, "finish_reason": "stop"}]}) + "\n"
                       + "data: " + json.dumps({"id": f"chatcmpl-{uid}", "choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 2}}) + "\n"
                       + "data: [DONE]\n")
        output.write_text(json.dumps({
            "schema": "ft_t06_ordinary_sse/v3", "pause_enabled": False,
            "payload_source": {"path": str(input_path), "sha256": module.sha(input_path)},
            "sse": str(raw), "sse_sha256": module.sha(raw), "uid": uid,
            "usage": {"prompt_tokens": 2, "completion_tokens": 2}, "finish_reason": "stop",
        }))
        return {"uid": uid}

    client = SimpleNamespace()
    client._v2 = lambda: SimpleNamespace(parse_sse=lambda raw: (
        int(raw.decode().split('"id": "chatcmpl-')[1].split('"', 1)[0]),
        {"prompt_tokens": 2, "completion_tokens": 2}, "stop",
    ))
    client._tokens_for_uid = lambda path, uid, *_: [json.loads(line) for line in Path(path).read_text().splitlines() if json.loads(line)["uid"] == uid]
    client._input_for_uid = lambda path, uid, *_: next(json.loads(line) for line in Path(path).read_text().splitlines() if json.loads(line)["uid"] == uid)

    def request(_base, input_path, output, **_kwargs):
        if input_path == inputs[1]:
            output.with_suffix(".sse").write_text('data: {"error":{"message":"CUDA out of memory"}}\n')
            (run / "fault_receipt.json").write_text(json.dumps({
                "schema": "ft_dev_oom_receipt/v1", "uid": 1, "epoch": 0,
                "point": "before_forward", "count": 1, "pid": 20,
                "wall_time_ns": 1, "monotonic_ns": 1,
            }))
            fault.set()
            raise RuntimeError("injected OOM")
        if input_path == inputs[2]:
            # The regression assertion: this request must never start during
            # stale serving health; it begins only after health.prequeue exists.
            assert prequeue_observed.is_set(), "queued request started before restarting observation"
            queued_started.set()
            assert restart_waiter_observed.wait(2), "queued request never became a restart waiter"
            value = write_output(input_path, output, 2, 21)
            lifecycle.live = {10, 21, 31, 41}
            queued_finished.set()
            return value
        return write_output(input_path, output, 0, 20)

    stale_once = [True]

    def health(_base):
        if queued_finished.is_set():
            return {"maintenance": "serving", "backend_epoch": 1, "restart_attempts": 1, "restart_waiters": 0}
        if fault.is_set() and not queued_started.is_set():
            if stale_once[0]:
                stale_once[0] = False
                events.append("stale-serving")
                return {"maintenance": "serving", "backend_epoch": 0, "restart_attempts": 0, "restart_waiters": 0}
            events.append("prequeue-restarting")
            prequeue_observed.set()
            return {"maintenance": "restarting", "backend_epoch": 0, "restart_attempts": 1, "restart_waiters": 0}
        if queued_started.is_set():
            events.append("queued-restart-waiter")
            restart_waiter_observed.set()
            return {"maintenance": "restarting", "backend_epoch": 0, "restart_attempts": 1, "restart_waiters": 1}
        return {"maintenance": "serving", "backend_epoch": 0, "restart_attempts": 0, "restart_waiters": 0}

    client.ordinary_request = request
    monkeypatch.setattr(module, "ordinary_client", lambda: client)
    monkeypatch.setattr(module, "_health", health)
    monkeypatch.setattr(module, "_epoch_observer", lambda root, _epoch, uid: Path(root) / "workers" / ("20" if uid == 0 else "21"))

    result = module.run_fault_protocol(1, "4c878f6b3251cca273d8548e7f5cf58a56711d3a", tmp_path / "candidate", *inputs, backend)
    assert events[:3] == ["stale-serving", "prequeue-restarting", "queued-restart-waiter"]
    assert result["prequeue_observation"]["maintenance"] == "restarting"
    assert result["queue_observation"]["restart_waiters"] >= 1
    assert result["health_ready"]["backend_epoch"] == 1
    assert result["cold_token_ids_equal"] and result["cold_full_text_equal"]
    assert (run / "health.prequeue.json").is_file()


def test_prequeue_wait_rejects_failed_maintenance(monkeypatch):
    module = load()
    monkeypatch.setattr(module, "_health", lambda _: {"maintenance": "failed", "backend_epoch": 0, "restart_attempts": 1, "restart_waiters": 0})
    with pytest.raises(RuntimeError, match="failed maintenance"):
        module._wait_for_restart_state("http://fixture/v1", module.time.monotonic() + 1)


def test_prequeue_wait_times_out_without_restarting(monkeypatch):
    module = load()
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: 1, sleep=lambda _: None))
    with pytest.raises(TimeoutError, match="never observed restarting"):
        module._wait_for_restart_state("http://fixture/v1", 0)
