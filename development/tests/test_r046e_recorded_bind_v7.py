"""Read-only replay of the R046e/b96 length and EOS ordinary evidence."""
from __future__ import annotations

import importlib.util
import json
import os
import socket
from pathlib import Path

import pytest


SOURCE = Path(__file__).parents[1] / "r046e_t06_ordinary_client_v7.py"
RECORDED_ROOT = os.environ.get("FT_RECORDED_R046E_ROOT")
GENERATION_CONFIG = Path(os.environ.get("FT_RECORDED_GENERATION_CONFIG", "/data2/model/Qwen3.8-Flash-Next-NVFP4/generation_config.json"))
GENERATION_CONFIG_SHA = "e70c136c1b78ddc1fb0905bac8e733a4dc448d4f852a5dd75143fffc70be550e"
EOS_TOKEN_IDS = [248046, 248044]


def load():
    spec = importlib.util.spec_from_file_location("r046e_recorded_bind_v7", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _birth(pid: int) -> dict:
    return {"pid": pid, "start_ticks": 10, "execution_id": f"{pid}:10", "pgid": pid, "session": pid}


def _tokens() -> list[dict]:
    service, worker = _birth(71), _birth(72)
    return [{"schema": "ft_t06_ordinary_token/v3", "uid": 7, "request_seq": index,
             "completion_tokens_delta": 1, "completion_tokens_cumulative": index,
             "next_token": index, "finished": index == 2,
             "finish_reason": "stop" if index == 2 else None, "time_ns": index,
             "service_birth": service, "worker_birth": worker} for index in (1, 2)]


@pytest.mark.skipif(not RECORDED_ROOT, reason="set FT_RECORDED_R046E_ROOT to a frozen E2-R046e round")
def test_recorded_b96_tool_calls_binds_all_actual_evidence_read_only(tmp_path, monkeypatch):
    """No raw artifact is copied: v7 reads frozen evidence and writes tmp output."""
    root = Path(RECORDED_ROOT).resolve()
    arm = root / "G_seed12k"
    required = (arm / "round-00.payload.json", arm / "round-00.api.json", arm / "round-00.api.sse", arm / "serve_args_actual.json",
                arm / "d0_prefill.jsonl", arm / "route", arm / "ordinary_observer/inputs.jsonl",
                arm / "ordinary_observer/tokens.jsonl")
    assert root.name == "E2-R046e" and GENERATION_CONFIG.is_file() and all(path.is_file() or path.is_dir() for path in required)
    assert not any(path.is_symlink() for path in required)
    tool = load()
    monkeypatch.setattr(socket, "socket", lambda *_a, **_kw: pytest.fail("recorded bind opened a socket"))
    out = tmp_path / "binding.json"
    value = tool.bind(arm / "round-00.payload.json", arm / "round-00.api.json", arm / "d0_prefill.jsonl",
                      arm / "route", arm / "ordinary_observer/inputs.jsonl", arm / "ordinary_observer/tokens.jsonl", out,
                      generation_config=GENERATION_CONFIG, serve_args=arm / "serve_args_actual.json")
    assert out.is_file() and value["api"]["uid"] == 0
    assert value["api"]["usage"]["completion_tokens"] == 140
    assert value["api"]["finish_reason"] == "tool_calls"
    assert len(value["token_sidecar"]["events"]) == 140
    assert value["token_sidecar"]["events"][-1]["completion_tokens_cumulative"] == 140
    assert value["token_sidecar"]["terminal_binding"]["worker_finish_reason"] == "stop"
    assert value["route"]["records"] and value["d0"]["schedule"]
    assert value["route"]["accounting"]["unstreamed_overlap_forward_tokens"] == 1
    assert value["route"]["accounting"]["terminal_is_eos"] is True
    assert value["route"]["accounting"]["generation_config"]["sha256"] == GENERATION_CONFIG_SHA
    assert value["route"]["accounting"]["generation_config"]["eos_token_ids"] == EOS_TOKEN_IDS


@pytest.mark.skipif(not RECORDED_ROOT, reason="set FT_RECORDED_R046E_ROOT to a frozen E2-R046e round")
def test_recorded_b96_g3_on_length_has_prefill_first_token_and_no_unstreamed_overlap(tmp_path, monkeypatch):
    root = Path(RECORDED_ROOT).resolve(); arm = root / "g3g4" / "g3_on"
    required = (arm / "cold.json", arm / "route", arm / "ordinary_observer/tokens.jsonl", arm / "serve_args_actual.json")
    assert root.name == "E2-R046e" and GENERATION_CONFIG.is_file() and all(path.is_file() or path.is_dir() for path in required)
    tool = load()
    monkeypatch.setattr(socket, "socket", lambda *_a, **_kw: pytest.fail("recorded accounting opened a socket"))
    cold = json.loads((arm / "cold.json").read_text(encoding="utf-8"))
    record = cold["record"] if isinstance(cold, dict) and "record" in cold else cold
    completion = record["completion_tokens"]
    assert record["prompt_tokens"] == 32064 and completion == 128 and record["finish_reason"] == "length"
    rows = [json.loads(line) for line in (arm / "ordinary_observer/tokens.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    uid = rows[0]["uid"]; tokens = [row for row in rows if row.get("uid") == uid]
    v2 = tool._v2(); prefill, decode, _routes = v2.routes_for_uid(arm / "route", uid, v2.ROUTE_ANALYZER)
    accounting = tool._route_accounting(prefill=prefill, decode=decode, completion=completion, max_tokens=128,
                                        tokens=tokens, api_finish="length", worker_finish=tokens[-1]["finish_reason"],
                                        eos=tool._eos_provenance(GENERATION_CONFIG), serve=tool._serve_overlap_provenance(arm / "serve_args_actual.json"))
    assert accounting["prefill_tokens"] == 32064 and accounting["route_decode_tokens"] == 127
    assert accounting["streamed_completion_tokens"] == 128 and accounting["unstreamed_overlap_forward_tokens"] == 0
    assert accounting["generation_config"]["sha256"] == GENERATION_CONFIG_SHA
    assert accounting["generation_config"]["eos_token_ids"] == EOS_TOKEN_IDS


@pytest.mark.parametrize("change, match", [
    (lambda rows: [dict(row, uid=8) for row in rows], "lacks API UID"),
    (lambda rows: [dict(row, completion_tokens_cumulative=1) if row["request_seq"] == 2 else row for row in rows], "sequence differs"),
    (lambda rows: [dict(row, finish_reason="length") if row["finished"] else row for row in rows], "incompatible"),
])
def test_small_local_token_fixtures_reject_uid_count_and_finish(tmp_path, change, match):
    tool = load(); tokens = tmp_path / "tokens.jsonl"
    tokens.write_text("".join(json.dumps(row) + "\n" for row in change(_tokens())), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        tool._tokens_for_uid(tokens, 7, 2, "tool_calls")


def test_small_local_sse_fixture_rejects_invalid_finish_reason():
    tool = load()
    raw = (b'data: {"id":"chatcmpl-7","choices":[{"finish_reason":"wrong"}]}'
           b'\n\ndata: {"id":"chatcmpl-7","choices":[],"usage":{"prompt_tokens":2,"completion_tokens":1}}'
           b'\n\ndata: [DONE]\n')
    with pytest.raises(ValueError, match="lacks id, usage, finish, or DONE"):
        tool._v2().parse_sse(raw)



