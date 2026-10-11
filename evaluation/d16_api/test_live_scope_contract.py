from __future__ import annotations

import json
from pathlib import Path

import pytest

import live_scope


def test_scope_binding_has_the_two_expected_prompt_token_counts():
    _, prompts = live_scope.scope_inputs()
    assert sorted(count for _, count in prompts.values()) == [512, 8257]


def test_collect_one_disables_environment_proxy_and_persists_prompt_count(monkeypatch, tmp_path):
    seen = {}
    class Http:
        def __init__(self, **kwargs): seen["http"] = kwargs
    class Client:
        def __init__(self, **kwargs): seen["client"] = kwargs
        def close(self): pass
    monkeypatch.setattr(live_scope.httpx, "Client", Http)
    monkeypatch.setattr(live_scope, "OpenAI", Client)
    monkeypatch.setattr(live_scope, "collect_completion", lambda client, request: {"request": request, "response": {}, "chunks": [], "projection": {"text": "x", "finish_reason": "length", "usage": {"prompt_tokens": 512, "completion_tokens": 128, "total_tokens": 640}}})
    result = live_scope.collect_one("http://127.0.0.1:1", "m", {"service": "interleave_0", "label": "x", "input": "slot_0_short_512"}, "p", 512, tmp_path / "call.json")
    assert seen["http"] == {"trust_env": False} and seen["client"]["max_retries"] == 0
    assert result["projection"]["usage"]["prompt_tokens"] == 512
    assert json.loads((tmp_path / "call.json").read_text())["client"]["service"] == "interleave_0"


def test_collect_one_persists_a_prompt_count_mismatch_before_failing(monkeypatch, tmp_path):
    class Http:
        def __init__(self, **kwargs): pass
    class Client:
        def __init__(self, **kwargs): pass
        def close(self): pass
    monkeypatch.setattr(live_scope.httpx, "Client", Http); monkeypatch.setattr(live_scope, "OpenAI", Client)
    monkeypatch.setattr(live_scope, "collect_completion", lambda *args: {"request": {}, "response": {}, "chunks": [], "projection": {"text": "x", "finish_reason": "length", "usage": {"prompt_tokens": 2, "completion_tokens": 128, "total_tokens": 130}}})
    target = tmp_path / "call.json"
    with pytest.raises(ValueError, match="expected=512"):
        live_scope.collect_one("http://127.0.0.1:1", "m", {"service": "interleave_0", "label": "x", "input": "slot_0_short_512"}, "p", 512, target)
    assert "contract_error" in json.loads(target.read_text())
