import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


SOURCE = Path(__file__).parents[1] / "r046c_t06_ordinary_client_v1.py"


def load():
    spec = importlib.util.spec_from_file_location("t06_ordinary", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def write_route(root: Path, uid: int, tokens: int) -> None:
    ids = np.tile(np.arange(10, dtype=np.int16), (1, tokens, 1))
    np.savez_compressed(root / "route-00000000.npz", expert_ids=ids)
    (root / "route-00000000.json").write_text(json.dumps({"seq": 0, "phase": "prefill", "t": tokens,
        "layer_count": 1, "layer_ids": [0], "reqs": [{"rid": uid, "n_tokens": tokens}],
        "file": "route-00000000.npz"}))


def artifacts(tmp_path: Path, uid: int = 42):
    payload = tmp_path / "input.json"
    payload.write_text(json.dumps({"model": "m", "messages": [{"role": "user", "content": "x"}], "stream": True,
                                   "stream_options": {"include_usage": True}}))
    d0 = tmp_path / "d0.jsonl"
    d0.write_text(json.dumps({"chunk": 0, "reqs": [{"rid": uid, "new_tokens": 7, "cached_tokens": 3}]}) + "\n")
    route = tmp_path / "route"
    route.mkdir()
    write_route(route, uid, 7)
    return payload, d0, route


def test_bind_strictly_connects_input_api_d0_and_route_hashes(tmp_path):
    tool = load()
    payload, d0, route = artifacts(tmp_path)
    api = tmp_path / "api.json"
    tool.write_new(api, {"schema": tool.SCHEMA, "mode": "ordinary_sse", "pause_enabled": False,
                         "input_sha256": tool.sha256(payload), "id": "chatcmpl-42", "uid": 42,
                         "usage": {"prompt_tokens": 10, "completion_tokens": 2,
                                   "prompt_tokens_details": {"cached_tokens": 3}}, "finish_reason": "stop"})
    output = tmp_path / "binding.json"
    value = tool.bind_evidence(payload, api, d0, route, output)
    assert value["verdict"] == "uid_bound_not_token_index_bound"
    assert value["d0"]["new_tokens"] == value["route"]["new_tokens"] == 7
    assert len(value["schedule"]["sha256"]) == 64
    assert value["token_index_binding"]["proven"] is False
    assert value["backend_minimum_field_requirement"]["required"] == ["uid", "request_seq", "completion_tokens_delta", "completion_tokens_cumulative"]


def test_bind_rejects_uid_or_usage_total_mismatch(tmp_path):
    tool = load()
    payload, d0, route = artifacts(tmp_path)
    api = tmp_path / "api.json"
    tool.write_new(api, {"schema": tool.SCHEMA, "mode": "ordinary_sse", "pause_enabled": False,
                         "input_sha256": tool.sha256(payload), "id": "chatcmpl-42", "uid": 42,
                         "usage": {"prompt_tokens": 9, "completion_tokens": 2,
                                   "prompt_tokens_details": {"cached_tokens": 3}}, "finish_reason": "stop"})
    with pytest.raises(ValueError, match="schedule totals"):
        tool.bind_evidence(payload, api, d0, route, tmp_path / "bad.json")
    api.unlink()
    tool.write_new(api, {"schema": tool.SCHEMA, "mode": "ordinary_sse", "pause_enabled": False,
                         "input_sha256": tool.sha256(payload), "id": "chatcmpl-99", "uid": 99,
                         "usage": {"prompt_tokens": 10, "completion_tokens": 2,
                                   "prompt_tokens_details": {"cached_tokens": 3}}, "finish_reason": "stop"})
    with pytest.raises(ValueError, match="D0 has no"):
        tool.bind_evidence(payload, api, d0, route, tmp_path / "bad_uid.json")


def test_plain_sse_requires_usage_and_rejects_dev_ack():
    tool = load()
    raw = b'data: {"id":"chatcmpl-7","choices":[{"finish_reason":null}]}\n\ndata: {"id":"chatcmpl-7","choices":[{"finish_reason":"stop"}]}\n\ndata: {"id":"chatcmpl-7","choices":[],"usage":{"prompt_tokens":2,"completion_tokens":1}}\n\ndata: [DONE]\n'
    assert tool.parse_sse(raw) == (7, {"prompt_tokens": 2, "completion_tokens": 1}, "stop")
    with pytest.raises(ValueError, match="development ACK"):
        tool.parse_sse(b'data: {"id":"chatcmpl-7","ft_dev":{}}\n')


def test_dynamic_socket_guard_never_uses_service_port():
    tool = load()
    port = tool.dynamic_private_port()
    assert 1024 <= port <= 65535 and port != 8095
