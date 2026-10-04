"""The frozen companion remains runnable without network or dev instrumentation."""
import json
import subprocess
import sys
import importlib.util

import pytest


def test_default_generate_preserves_agent_trace_schema(tmp_path):
    out = tmp_path / "trace.json"
    result = subprocess.run(
        [sys.executable, "scripts/agent_trace.py", "generate", "--dry-run", "--rounds", "2", "--out", str(out)],
        check=True, capture_output=True, text=True,
    )
    assert result.returncode == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["meta"]["kind"] == "agent_trace"
    assert len(doc["rounds"]) == 2
    assert doc["rounds"][0]["record"]["tool_calls"]
    assert doc["rounds"][0]["record"]["finish_reason"] == "tool_calls"


def load_wrapper(monkeypatch):
    monkeypatch.delenv("FT_DEV_ROUTE_TRACE", raising=False)
    spec = importlib.util.spec_from_file_location("d07_agent_trace", "scripts/agent_trace.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def events(uid=11, *, schema="ft_dev_stream/v1", seq2=2, cumulative2=1, finish="length"):
    return iter([
        {"ft_dev": {"schema": schema, "uid": uid, "request_seq": 1, "completion_tokens_delta": 0, "completion_tokens_cumulative": 0}, "choices": [{"delta": {"content": "x"}, "finish_reason": None}]},
        {"ft_dev": {"schema": schema, "uid": uid, "request_seq": seq2, "completion_tokens_delta": 1, "completion_tokens_cumulative": cumulative2}, "choices": [{"delta": {"content": "y"}, "finish_reason": finish}]},
    ])


def test_dev_generate_writes_nested_ack_evidence(monkeypatch, tmp_path):
    module = load_wrapper(monkeypatch)
    uids = iter([11, 12, 13])
    module._ns["post_events"] = lambda *args: events(next(uids))
    out = tmp_path / "dev.json"
    monkeypatch.setattr(sys, "argv", ["agent_trace.py", "generate", "--route-evidence", "--rounds", "2", "--out", str(out)])
    assert module.main() == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    records = [row["record"] for row in doc["rounds"]]
    assert [r["uid"] for r in records] == [11, 12]
    assert all(r["ack_schema"] == "ft_route_ack/v1" and r["max_tokens"] == 128 and r["token_events"][0]["completion_tokens_delta"] == 0 for r in records)

    replay = tmp_path / "replay.json"
    monkeypatch.setattr(sys, "argv", ["agent_trace.py", "replay", "--route-evidence", "--trace", str(out), "--rounds", "0", "--out", str(replay)])
    assert module.main() == 0
    row = json.loads(replay.read_text(encoding="utf-8"))["rounds"][0]
    assert "record" not in row and row["uid"] == 13 and row["finish_reason"] == "length"


@pytest.mark.parametrize("bad", [
    lambda: events(schema="wrong"),
    lambda: iter([{"ft_dev": {"schema":"ft_dev_stream/v1","uid":1,"request_seq":1,"completion_tokens_delta":0,"completion_tokens_cumulative":0},"choices":[]},{"ft_dev":{"schema":"ft_dev_stream/v1","uid":2,"request_seq":2,"completion_tokens_delta":1,"completion_tokens_cumulative":1},"choices":[{"delta":{},"finish_reason":"stop"}]}]),
    lambda: events(seq2=3), lambda: events(cumulative2=2), lambda: iter([{"choices":[{"delta":{},"finish_reason":"stop"}]}]),
])
def test_dev_rejects_bad_ack_evidence(monkeypatch, bad):
    module = load_wrapper(monkeypatch)
    with pytest.raises(RuntimeError):
        module.consume_stream(bad(), 0.0)


def test_route_evidence_budget_accepts_2048_and_rejects_2049(monkeypatch):
    module = load_wrapper(monkeypatch)
    def stream(n):
        for seq in range(1, n + 1):
            yield {"ft_dev": {"schema": "ft_dev_stream/v1", "uid": 4, "request_seq": seq, "completion_tokens_delta": 1, "completion_tokens_cumulative": seq}, "choices": [{"delta": {}, "finish_reason": "length" if seq == n else None}]}
    module._budgets.append(2048)
    assert module.consume_stream(stream(2048), 0.0)["finish_reason"] == "length"
    module._budgets.append(2048)
    with pytest.raises(RuntimeError, match="exceeds"):
        module.consume_stream(stream(2049), 0.0)
