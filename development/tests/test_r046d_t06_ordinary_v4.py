import importlib.util
import json
import sys
import types

import pytest


DEV = __import__("pathlib").Path(__file__).parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, DEV / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def row(schema, uid, service, worker, **extra):
    return {"schema": schema, "uid": uid, "service_birth": service, "worker_birth": worker, **extra}


def birth(pid):
    return {"pid": pid, "start_ticks": pid * 10, "execution_id": f"{pid}:{pid * 10}", "pgid": pid, "session": pid}


def test_worker_observer_binds_real_usermsg_to_mixed_uid_tokens(monkeypatch, tmp_path):
    startup = load("startup_v4", "r046c_t06_ordinary_startup_v4.py")
    class Engine:
        def __init__(self): pass
    class Scheduler:
        def _process_one_msg(self, msg): return msg
    class SchedulerIO:
        def _reply_tokenizer_rank0(self, replies): return replies
    class UserMsg:
        def __init__(self, uid, ids): self.uid, self.input_ids = uid, ids
    engine_mod, backend_mod = types.ModuleType("freetoken.engine.engine"), types.ModuleType("freetoken.message.backend")
    scheduler_mod, io_mod = types.ModuleType("freetoken.scheduler.scheduler"), types.ModuleType("freetoken.scheduler.io")
    engine_mod.Engine, backend_mod.UserMsg, scheduler_mod.Scheduler, io_mod.SchedulerIOMixin = Engine, UserMsg, Scheduler, SchedulerIO
    sys.modules.update({"freetoken": types.ModuleType("freetoken"), "freetoken.engine": types.ModuleType("freetoken.engine"), "freetoken.engine.engine": engine_mod, "freetoken.message": types.ModuleType("freetoken.message"), "freetoken.message.backend": backend_mod, "freetoken.scheduler": types.ModuleType("freetoken.scheduler"), "freetoken.scheduler.scheduler": scheduler_mod, "freetoken.scheduler.io": io_mod})
    monkeypatch.setattr(startup, "birth", lambda: birth(2)); monkeypatch.setenv("R046C_T06_SERVICE_BIRTH", json.dumps(birth(1)))
    startup.install(tmp_path / "observer")
    assert not (tmp_path / "observer").exists()  # parent/tokenizer child only installed the lazy hook
    Engine(); scheduler, io = Scheduler(), SchedulerIO()
    msg7, msg8 = UserMsg(7, [1, 2, 3]), UserMsg(8, [4, 5])
    assert scheduler._process_one_msg(msg7) is msg7; assert scheduler._process_one_msg(msg8) is msg8
    DetokenizeMsg = type("DetokenizeMsg", (), {})
    def token(uid, value, finished=False):
        message = DetokenizeMsg(); message.uid, message.next_token, message.finished, message.finish_reason = uid, value, finished, "stop" if finished else None; return message
    io._reply_tokenizer_rank0([token(7, 9), token(8, 10), token(7, 11, True), token(8, 12, True)])
    inputs = [json.loads(line) for line in (tmp_path / "observer" / "inputs.jsonl").read_text().splitlines()]
    tokens = [json.loads(line) for line in (tmp_path / "observer" / "tokens.jsonl").read_text().splitlines()]
    assert [(x["uid"], x["input_tokens"]) for x in inputs] == [(7, 3), (8, 2)]
    assert [(x["uid"], x["request_seq"]) for x in tokens] == [(7, 1), (8, 1), (7, 2), (8, 2)]
    assert json.loads((tmp_path / "observer" / "input-7.json").read_text()) == [1, 2, 3]
    with pytest.raises(RuntimeError, match="duplicate"):
        scheduler._process_one_msg(UserMsg(7, [1]))


def test_bind_rejects_payload_hash_and_worker_length_mismatch(tmp_path):
    client = load("client_v3", "r046c_t06_ordinary_client_v3.py")
    input_path = tmp_path / "payload.json"; input_path.write_text('{"stream":true}')
    raw = b'data: {"id":"chatcmpl-7","choices":[{"finish_reason":"stop"}]}\n\ndata: {"id":"chatcmpl-7","choices":[],"usage":{"prompt_tokens":3,"completion_tokens":1}}\n\ndata: [DONE]\n'
    raw_path = tmp_path / "api.sse"; raw_path.write_bytes(raw)
    api = tmp_path / "api.json"; client.write_new(api, {"schema": client.API_SCHEMA, "pause_enabled": False, "payload_source": {"path": str(input_path), "sha256": "0" * 64}, "sse": str(raw_path), "sse_sha256": client.sha256(raw_path), "uid": 7, "usage": {"prompt_tokens": 3, "completion_tokens": 1}, "finish_reason": "stop"})
    for path in (tmp_path / "d0.jsonl", tmp_path / "inputs.jsonl", tmp_path / "tokens.jsonl"): path.write_text("")
    with pytest.raises(ValueError, match="payload source"):
        client.bind(input_path, api, tmp_path / "d0.jsonl", tmp_path, tmp_path / "inputs.jsonl", tmp_path / "tokens.jsonl", tmp_path / "out.json")


def test_worker_input_receipt_requires_exactly_one_uid_and_api_length(tmp_path):
    client = load("client_v3_receipt", "r046c_t06_ordinary_client_v3.py")
    service, worker = birth(1), birth(2); sidecar = tmp_path / "inputs.jsonl"; ids = tmp_path / "input-7.json"; ids.write_bytes(b"[1,2,3]")
    digest = client.sha256(ids)
    good = row(client.INPUT_SCHEMA, 7, service, worker, input_tokens=3, canonical_encoding="utf8-json-int-array-separators=,:", input_ids_sha256=digest, input_ids_file_sha256=digest, input_ids_path=str(ids), source="Scheduler._process_one_msg(UserMsg)", time_ns=10)
    sidecar.write_text(json.dumps(good) + "\n" + json.dumps(good) + "\n")
    with pytest.raises(ValueError, match="exactly one"):
        client._input_for_uid(sidecar, 7, service, worker)
    sidecar.write_text(json.dumps(good) + "\n")
    assert client._input_for_uid(sidecar, 7, service, worker)["input_tokens"] == 3
    sidecar.write_text("")
    with pytest.raises(ValueError, match="exactly one"):
        client._input_for_uid(sidecar, 7, service, worker)


def test_canonical_worker_input_sha_is_full_integer_sequence_not_payload_claim():
    startup = load("startup_v4_sha", "r046c_t06_ordinary_startup_v4.py")
    ids, raw, digest = startup.canonical_input_ids([1, 23, 456])
    assert ids == [1, 23, 456] and raw == b"[1,23,456]"
    assert digest == "acc530bc25a03099e58e4192945b5bafebdaff82745082040feef0e286934f7e"
    with pytest.raises(RuntimeError, match="non-canonical"):
        startup.canonical_input_ids([1, True])


def test_input_file_tamper_missing_birth_and_token_before_input_fail(tmp_path):
    client = load("client_v3_tamper", "r046c_t06_ordinary_client_v3.py")
    service, worker = birth(1), birth(2); ids = tmp_path / "input-7.json"; ids.write_bytes(b"[1,2]"); sidecar = tmp_path / "inputs.jsonl"
    receipt = row(client.INPUT_SCHEMA, 7, service, worker, input_tokens=2, canonical_encoding="utf8-json-int-array-separators=,:", input_ids_sha256=client.sha256(ids), input_ids_file_sha256=client.sha256(ids), input_ids_path=str(ids), source="Scheduler._process_one_msg(UserMsg)", time_ns=20)
    sidecar.write_text(json.dumps(receipt) + "\n"); ids.write_bytes(b"[1,3]")
    with pytest.raises(ValueError, match="digest"):
        client._input_for_uid(sidecar, 7, service, worker)
    receipt["service_birth"] = None; ids.write_bytes(b"[1,2]"); receipt["input_ids_sha256"] = receipt["input_ids_file_sha256"] = client.sha256(ids); sidecar.write_text(json.dumps(receipt) + "\n")
    with pytest.raises(ValueError, match="receipt"):
        client._input_for_uid(sidecar, 7, service, worker)
    with pytest.raises(ValueError, match="earlier"):
        client._require_input_before_tokens({"time_ns": 20}, [{"time_ns": 10}])


def test_partial_sse_read_is_preserved(monkeypatch, tmp_path):
    client = load("client_v3_partial", "r046c_t06_ordinary_client_v3.py")
    payload = tmp_path / "payload.json"; payload.write_text('{"stream":true,"stream_options":{"include_usage":true}}')
    class Response:
        def __init__(self): self.calls = 0
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def read(self, _size):
            self.calls += 1
            if self.calls == 1: return b'data: {"id":"chatcmpl-7"}\n\n'
            raise OSError("socket closed")
    monkeypatch.setattr(client.urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(RuntimeError, match="partial raw"):
        client.ordinary_request("http://127.0.0.1:4567/v1", payload, tmp_path / "api.json")
    assert (tmp_path / "api.sse").read_bytes() == b'data: {"id":"chatcmpl-7"}\n\n'
