import importlib.util
import io
import json
import os
import sys
import types
import urllib.error
from pathlib import Path

import numpy as np
import pytest


DEV = Path(__file__).parents[1]


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, DEV / file); module = importlib.util.module_from_spec(spec)
    assert spec.loader; spec.loader.exec_module(module); return module


def route(root, seq, phase, uid, count):
    ids = np.tile(np.arange(10, dtype=np.int16), (1, count, 1)); np.savez_compressed(root / f"route-{seq:08d}.npz", expert_ids=ids)
    (root / f"route-{seq:08d}.json").write_text(json.dumps({"seq": seq, "phase": phase, "t": count, "layer_count": 1,
        "layer_ids": [0], "reqs": [{"rid": uid, "n_tokens": count}], "file": f"route-{seq:08d}.npz"}))


def setup_binding(tmp_path, uid=42, completion=3):
    tool = load("t06_v2", "r046c_t06_ordinary_client_v2.py")
    input_path = tmp_path / "input.json"; input_path.write_text(json.dumps({"stream": True, "stream_options": {"include_usage": True}}))
    raw = b'data: {"id":"chatcmpl-42","choices":[{"finish_reason":null}]}\n\ndata: {"id":"chatcmpl-42","choices":[{"finish_reason":"stop"}]}\n\ndata: {"id":"chatcmpl-42","choices":[],"usage":{"prompt_tokens":10,"completion_tokens":3,"prompt_tokens_details":{"cached_tokens":3}}}\n\ndata: [DONE]\n'
    raw_path = tmp_path / "api.sse"; raw_path.write_bytes(raw)
    api = tmp_path / "api.json"; tool.write_new(api, {"schema": tool.API_SCHEMA, "mode": "ordinary_sse", "pause_enabled": False,
        "input_sha256": tool.sha256(input_path), "sse": str(raw_path), "sse_sha256": tool.sha256(raw_path), "id": "chatcmpl-42", "uid": uid,
        "usage": {"prompt_tokens": 10, "completion_tokens": completion, "prompt_tokens_details": {"cached_tokens": 3}}, "finish_reason": "stop"})
    d0 = tmp_path / "d0.jsonl"; d0.write_text(json.dumps({"reqs": [{"rid": uid, "new_tokens": 7, "cached_tokens": 3}]}) + "\n")
    routes = tmp_path / "route"; routes.mkdir(); route(routes, 0, "prefill", uid, 7); route(routes, 1, "decode", uid, 1); route(routes, 2, "decode", uid, 1)
    sidecar = tmp_path / "tokens.jsonl"; service = {"pid": 1}; worker = {"pid": 2}
    sidecar.write_text("".join(json.dumps({"schema": tool.TOKEN_SCHEMA, "uid": uid, "request_seq": n, "next_token": 100+n,
        "completion_tokens_delta": 1, "completion_tokens_cumulative": n, "finished": n == 3, "finish_reason": "stop" if n == 3 else None,
        "service_birth": service, "worker_birth": worker}) + "\n" for n in range(1, 4)))
    return tool, input_path, api, d0, routes, sidecar


def test_bind_replays_raw_sse_and_binds_real_token_sequence_and_route_npz(tmp_path):
    tool, input_path, api, d0, routes, sidecar = setup_binding(tmp_path)
    result = tool.bind(input_path, api, d0, routes, sidecar, tmp_path / "out.json")
    assert result["verdict"] == "uid_and_token_index_bound"
    assert result["route"]["decode_tokens"] == 2
    assert all(len(row["npz_sha256"]) == 64 for row in result["route"]["records"])


@pytest.mark.parametrize("mutate, error", [("duplicate", "sequence"), ("after_terminal", "after terminal"), ("uid", "lacks API UID")])
def test_sidecar_rejects_duplicate_sequence_terminal_tail_and_uid_mismatch(tmp_path, mutate, error):
    tool, input_path, api, d0, routes, sidecar = setup_binding(tmp_path)
    rows = [json.loads(line) for line in sidecar.read_text().splitlines()]
    if mutate == "duplicate": rows[1]["request_seq"] = 1
    elif mutate == "after_terminal": rows[1]["finished"] = True
    else: rows = [{**row, "uid": 99} for row in rows]
    sidecar.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError, match=error): tool.bind(input_path, api, d0, routes, sidecar, tmp_path / "bad.json")


def test_missing_api_cached_usage_is_explicit_and_never_falls_back_to_zero(tmp_path):
    tool, input_path, api, d0, routes, sidecar = setup_binding(tmp_path)
    raw_path = tmp_path / "api.sse"; raw_path.write_bytes(b'data: {"id":"chatcmpl-42","choices":[{"finish_reason":"stop"}]}\n\ndata: {"id":"chatcmpl-42","choices":[],"usage":{"prompt_tokens":10,"completion_tokens":3}}\n\ndata: [DONE]\n')
    api.unlink(); tool.write_new(api, {"schema": tool.API_SCHEMA, "mode": "ordinary_sse", "pause_enabled": False,
        "input_sha256": tool.sha256(input_path), "sse": str(raw_path), "sse_sha256": tool.sha256(raw_path), "id": "chatcmpl-42", "uid": 42,
        "usage": {"prompt_tokens": 10, "completion_tokens": 3}, "finish_reason": "stop"})
    value = tool.bind(input_path, api, d0, routes, sidecar, tmp_path / "missing.json")
    assert value["api"]["cached_tokens"] == {"state": "missing", "value": None, "independently_verified": False}
    assert value["d0"]["cached_tokens"] == 3
    raw_path.write_bytes(b'data: {"id":"chatcmpl-42","choices":[{"finish_reason":"stop"}]}\n\ndata: {"id":"chatcmpl-42","choices":[],"usage":{"prompt_tokens":10,"completion_tokens":3,"prompt_tokens_details":{"cached_tokens":"bad"}}}\n\ndata: [DONE]\n')
    api.unlink(); tool.write_new(api, {"schema": tool.API_SCHEMA, "mode": "ordinary_sse", "pause_enabled": False,
        "input_sha256": tool.sha256(input_path), "sse": str(raw_path), "sse_sha256": tool.sha256(raw_path), "id": "chatcmpl-42", "uid": 42,
        "usage": {"prompt_tokens": 10, "completion_tokens": 3, "prompt_tokens_details": {"cached_tokens": "bad"}}, "finish_reason": "stop"})
    with pytest.raises(ValueError, match="cached_tokens invalid"):
        tool.bind(input_path, api, d0, routes, sidecar, tmp_path / "bad_cached.json")


def test_partial_http_error_preserves_raw_and_refuses_8095(monkeypatch, tmp_path):
    tool = load("t06_v2_http", "r046c_t06_ordinary_client_v2.py")
    input_path = tmp_path / "input.json"; input_path.write_text(json.dumps({"stream": True, "stream_options": {"include_usage": True}}))
    error = urllib.error.HTTPError("http://127.0.0.1:4567", 500, "x", {}, io.BytesIO(b"partial failure"))
    monkeypatch.setattr(tool.urllib.request, "urlopen", lambda *_a, **_k: (_ for _ in ()).throw(error))
    with pytest.raises(RuntimeError, match="raw response preserved"): tool.ordinary_request("http://127.0.0.1:4567/v1", input_path, tmp_path / "api.json")
    assert (tmp_path / "api.sse").read_bytes() == b"partial failure"
    with pytest.raises(RuntimeError, match="8095"): tool.ordinary_request("http://127.0.0.1:8095/v1", input_path, tmp_path / "blocked.json")


def test_observer_only_activates_in_engine_worker_and_records_mixed_uids(monkeypatch, tmp_path):
    observer = load("t06_startup", "r046c_t06_ordinary_startup_v2.py")
    class Engine:
        def __init__(self): pass
    class SchedulerIO:
        calls = []
        def _reply_tokenizer_rank0(self, replies): self.calls.extend(replies)
    engine_mod, io_mod = types.ModuleType("freetoken.engine.engine"), types.ModuleType("freetoken.scheduler.io")
    engine_mod.Engine, io_mod.SchedulerIOMixin = Engine, SchedulerIO
    sys.modules.update({"freetoken": types.ModuleType("freetoken"), "freetoken.engine": types.ModuleType("freetoken.engine"),
                        "freetoken.engine.engine": engine_mod, "freetoken.scheduler": types.ModuleType("freetoken.scheduler"), "freetoken.scheduler.io": io_mod})
    monkeypatch.setattr(observer, "birth", lambda: {"pid": 2}); monkeypatch.setenv("R046C_T06_SERVICE_BIRTH", json.dumps({"pid": 1}))
    original = SchedulerIO._reply_tokenizer_rank0; observer.install(tmp_path / "observer")
    assert SchedulerIO._reply_tokenizer_rank0 is original and not (tmp_path / "observer").exists()
    Engine(); scheduler = SchedulerIO()
    DetokenizeMsg = type("DetokenizeMsg", (), {})
    def token(uid, next_token, finished, finish_reason):
        value = DetokenizeMsg(); value.uid, value.next_token, value.finished, value.finish_reason = uid, next_token, finished, finish_reason
        return value
    scheduler._reply_tokenizer_rank0([token(8, 18, False, None), token(9, 19, False, None)])
    scheduler._reply_tokenizer_rank0([token(8, 20, True, "stop"), token(9, 21, True, "length")])
    rows = [json.loads(line) for line in (tmp_path / "observer" / "tokens.jsonl").read_text().splitlines()]
    assert [(row["uid"], row["request_seq"], row["completion_tokens_cumulative"]) for row in rows] == [(8, 1, 1), (9, 1, 1), (8, 2, 2), (9, 2, 2)]
    with pytest.raises(RuntimeError, match="after terminal"):
        scheduler._reply_tokenizer_rank0([token(8, 22, False, None)])
