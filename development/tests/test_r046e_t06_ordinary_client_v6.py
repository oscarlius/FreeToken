"""CPU contract regression for b96's API tool_calls terminal semantics."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).parents[1] / "r046e_t06_ordinary_client_v6.py"


def load():
    spec = importlib.util.spec_from_file_location("r046e_t06_ordinary_client_v6", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_v6_binds_v2_route_reader_to_the_sealed_ordinary_analyzer():
    tool = load()
    assert tool.ROUTE_ANALYZER.name == "r046c_route_analyze_ordinary_v2.py"
    assert tool._v2().ROUTE_ANALYZER == tool.ROUTE_ANALYZER


def _analyzer():
    path = Path(__file__).parents[1] / "r046c_route_analyze_ordinary_v2.py"
    spec = importlib.util.spec_from_file_location("r046e_ordinary_analyzer_v2", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _route(path: Path, ranges):
    import numpy as np
    record = {"seq": 0, "phase": "prefill", "t": 4, "layer_count": 1, "layer_ids": [0],
              "reqs": [{"rid": 7, "n_tokens": 4}], "file": "route-00000000.npz",
              "layer_major_chunk_ranges": ranges}
    (path / "route-00000000.json").write_text(json.dumps(record), encoding="utf-8")
    np.savez(path / "route-00000000.npz", expert_ids=np.asarray([[
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
        [20, 21, 22, 23, 24, 25, 26, 27, 28, 29], [30, 31, 32, 33, 34, 35, 36, 37, 38, 39]]], dtype=np.int16))


def test_v2_route_loader_accepts_complete_prefill_layer_major_npz(tmp_path):
    route = tmp_path / "route"; route.mkdir()
    _route(route, [{"start": 0, "end": 2}, {"start": 2, "end": 4}])
    record, ids = _analyzer().load_route(route / "route-00000000.json")
    assert record["layer_major_chunk_ranges"][-1]["end"] == record["t"] == ids.shape[1]


def test_v2_route_loader_rejects_noncontiguous_layer_major_ranges(tmp_path):
    route = tmp_path / "route"; route.mkdir()
    _route(route, [{"start": 0, "end": 2}, {"start": 3, "end": 4}])
    with pytest.raises(ValueError, match="layer-major chunk ranges"):
        _analyzer().load_route(route / "route-00000000.json")


def test_v2_analyzer_accepts_v6_tool_call_binding_with_worker_stop(tmp_path):
    binding = {"schema": "ft_t06_ordinary_binding/v6", "verdict": "worker_input_uid_token_bound",
               "worker_input": {"input_ids_sha256": "a" * 64, "input_tokens": 2},
               "api": {"uid": 7, "usage": {"completion_tokens": 2}, "finish_reason": "tool_calls"},
               "token_sidecar": {"terminal_binding": {"api_finish_reason": "tool_calls", "worker_finish_reason": "stop",
                                                         "normalized": "tool_calls_api_terminal_to_worker_decode_stop"},
                                 "events": [{"schema": "ft_t06_ordinary_token/v3", "uid": 7, "request_seq": 1,
                                             "completion_tokens_delta": 1, "completion_tokens_cumulative": 1, "next_token": 1,
                                             "finished": False, "finish_reason": None, "time_ns": 1},
                                            {"schema": "ft_t06_ordinary_token/v3", "uid": 7, "request_seq": 2,
                                             "completion_tokens_delta": 1, "completion_tokens_cumulative": 2, "next_token": 2,
                                             "finished": True, "finish_reason": "stop", "time_ns": 2}]}}
    trace = tmp_path / "trace.json"
    trace.write_text(json.dumps({"schema": "ft_r046c_ordinary_seed_trace/v1", "rounds": [{"record": {
        "api_uid": 7, "completion_tokens": 2, "finish_reason": "tool_calls", "actual_input_binding": binding}}]}), encoding="utf-8")
    result = _analyzer().load_ordinary_trace(trace)
    assert result[7]["finish_reason"] == "tool_calls"


def _b96_sse() -> bytes:
    # b96 G_seed12k terminal shape: API tool call at completion token 140.
    chunks = [
        {"id": "chatcmpl-0", "choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "."}}]}, "finish_reason": None}]},
        {"id": "chatcmpl-0", "choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        {"id": "chatcmpl-0", "choices": [], "usage": {"prompt_tokens": 12660, "completion_tokens": 140, "total_tokens": 12800}},
    ]
    return b"\n\n".join(b"data: " + json.dumps(value, separators=(",", ":")).encode() for value in chunks) + b"\n\ndata: [DONE]\n"


def _birth(pid: int) -> dict:
    return {"pid": pid, "start_ticks": 123, "execution_id": f"{pid}:123", "pgid": pid, "session": pid}


def _tokens(uid: int = 0) -> list[dict]:
    service, worker = _birth(4100), _birth(4200)
    return [{"schema": "ft_t06_ordinary_token/v3", "uid": uid, "request_seq": index,
             "completion_tokens_delta": 1, "completion_tokens_cumulative": index,
             "next_token": index, "finished": index == 140,
             "finish_reason": "stop" if index == 140 else None,
             "time_ns": 100 + index, "service_birth": service, "worker_birth": worker}
            for index in range(1, 141)]


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")


def b96_fixture(tmp_path: Path, monkeypatch):
    tool = load()
    raw = tmp_path / "round-00.api.sse"; raw.write_bytes(_b96_sse())
    payload = tmp_path / "round-00.payload.json"; _write(payload, {"stream": True, "stream_options": {"include_usage": True}})
    api = tmp_path / "round-00.api.json"
    _write(api, {"schema": tool.API_SCHEMA, "mode": "ordinary_sse", "pause_enabled": False,
                 "payload_source": {"path": str(payload), "sha256": tool.sha256(payload)},
                 "sse": str(raw), "sse_sha256": tool.sha256(raw), "id": "chatcmpl-0", "uid": 0,
                 "usage": {"prompt_tokens": 12660, "completion_tokens": 140, "total_tokens": 12800},
                 "finish_reason": "tool_calls"})
    ids = tmp_path / "input_ids.json"; ids.write_bytes(json.dumps([0] * 12660, separators=(",", ":")).encode("ascii"))
    service, worker = _birth(4100), _birth(4200)
    inputs = tmp_path / "inputs.jsonl"
    _write(inputs, {"schema": tool.INPUT_SCHEMA, "uid": 0, "service_birth": service, "worker_birth": worker,
                    "canonical_encoding": "utf8-json-int-array-separators=,:", "input_tokens": 12660,
                    "input_ids_sha256": hashlib.sha256(ids.read_bytes()).hexdigest(), "input_ids_file_sha256": hashlib.sha256(ids.read_bytes()).hexdigest(),
                    "input_ids_path": str(ids), "source": "Scheduler._process_one_msg(UserMsg)", "time_ns": 1})
    tokens = tmp_path / "tokens.jsonl"; tokens.write_text("".join(json.dumps(row) + "\n" for row in _tokens()), encoding="utf-8")
    (tmp_path / "d0.jsonl").write_text("fixture\n", encoding="utf-8")
    (tmp_path / "route").mkdir()
    real_v2 = tool._v2()
    monkeypatch.setattr(tool, "_v2", lambda: SimpleNamespace(
        parse_sse=real_v2.parse_sse,
        d0_for_uid=lambda *_: (12660, 0, [{"actual": "fixture"}]),
        routes_for_uid=lambda *_: (12660, 139, [{"actual": "fixture"}]),
        ROUTE_ANALYZER=object()))
    return tool, payload, api, inputs, tokens


def test_b96_tool_calls_api_terminal_normalizes_only_to_worker_decode_stop(tmp_path, monkeypatch):
    tool, payload, api, inputs, tokens = b96_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(socket, "socket", lambda *_a, **_kw: pytest.fail("CPU bind opened a socket"))
    value = tool.bind(payload, api, tmp_path / "d0.jsonl", tmp_path / "route", inputs, tokens, tmp_path / "binding.json")
    assert value["schema"] == tool.BINDING_SCHEMA
    assert value["api"]["finish_reason"] == "tool_calls"
    assert value["api"]["usage"]["completion_tokens"] == 140
    assert value["token_sidecar"]["events"][-1]["completion_tokens_cumulative"] == 140
    assert value["token_sidecar"]["terminal_binding"] == {
        "api_finish_reason": "tool_calls", "worker_finish_reason": "stop",
        "normalized": "tool_calls_api_terminal_to_worker_decode_stop"}


@pytest.mark.parametrize("change, match", [
    (lambda rows: [dict(row, uid=1) for row in rows], "lacks API UID"),
    (lambda rows: [dict(row, completion_tokens_cumulative=8) if row["request_seq"] == 9 else row for row in rows], "sequence differs"),
    (lambda rows: [dict(row, finish_reason="length") if row["finished"] else row for row in rows], "incompatible"),
    (lambda rows: rows + [dict(rows[-1], request_seq=141, completion_tokens_cumulative=141, time_ns=999)], "terminal position differs"),
])
def test_b96_terminal_contract_rejects_wrong_uid_count_or_finish(tmp_path, change, match):
    tool = load()
    path = tmp_path / "tokens.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in change(_tokens())), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        tool._tokens_for_uid(path, 0, 140, "tool_calls")


