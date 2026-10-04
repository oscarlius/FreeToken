from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "multisession_probe.py"
SPEC = importlib.util.spec_from_file_location("multisession_probe", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def _record(first, last, events):
    return {
        "t_first_s": first,
        "t_last_s": last,
        "completion_tokens": sum(event["completion_tokens_delta"] for event in events),
        "token_events": events,
    }


def _event(t_s, delta, cumulative):
    return {
        "t_s": t_s,
        "completion_tokens_delta": delta,
        "completion_tokens_cumulative": cumulative,
        "uid": 4,
        "request_seq": cumulative,
    }


def test_common_window_uses_real_events_not_sum_of_per_way_averages():
    left = _record(0.0, 10.0, [_event(1.0, 5, 5), _event(4.0, 5, 10), _event(9.0, 5, 15)])
    right = _record(2.0, 8.0, [_event(3.0, 3, 3), _event(7.0, 3, 6)])

    seconds, tokens, tps = probe.common_window([left, right])

    assert seconds == 6.0
    assert tokens == 11
    assert tps == pytest.approx(11 / 6)
    assert tps != pytest.approx(probe.decode_tps(left) + probe.decode_tps(right))


def test_ack_rejects_duplicate_zero_and_jump_counters():
    event = {"ft_dev": {"schema": probe.DEV_SCHEMA, "uid": 9, "request_seq": 1, "completion_tokens_delta": 1, "completion_tokens_cumulative": 1}}
    uid, sequence, delta, cumulative, duplicate = probe._ack(event, None)
    assert (uid, sequence, delta, cumulative, duplicate) == (9, 1, 1, 1, False)
    with pytest.raises(probe.ProbeError, match="uid/request_seq"):
        probe._ack(event, (uid, sequence, cumulative, delta))

    jumped = {"ft_dev": {"schema": probe.DEV_SCHEMA, "uid": 9, "request_seq": 2, "completion_tokens_delta": 1, "completion_tokens_cumulative": 5}}
    with pytest.raises(probe.ProbeError, match="non-contiguous"):
        probe._ack(jumped, (uid, sequence, cumulative, delta))
    zero = {"ft_dev": {"schema": probe.DEV_SCHEMA, "uid": 9, "request_seq": 2, "completion_tokens_delta": 0, "completion_tokens_cumulative": 1}}
    with pytest.raises(probe.ProbeError, match="delta must equal"):
        probe._ack(zero, (uid, sequence, cumulative, delta))


class _Response:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.lines)


def _line(value):
    return ("data: " + json.dumps(value) + "\n\n").encode()


def test_stream_uses_ack_counters_and_done_not_sse_frame_count(monkeypatch):
    first = {"id": "ignore", "choices": [{"delta": {"role": "assistant", "content": ""}}]}
    ack = {"ft_dev": {"schema": probe.DEV_SCHEMA, "uid": 7, "request_seq": 1, "completion_tokens_delta": 1, "completion_tokens_cumulative": 1}, "choices": [{"delta": {"content": "hello"}}]}
    usage = {"usage": {"completion_tokens": 1}, "choices": []}
    monkeypatch.setattr(probe, "_open_response", lambda *_args, **_kwargs: _Response([_line(first), _line(ack), _line(usage), b"data: [DONE]\n\n"]))

    record = probe.stream_request(base_url="http://unit/v1", model="m", timeout=1, messages=[{"role": "user", "content": "x"}], max_tokens=4)

    assert record["completion_tokens"] == 1
    assert len(record["token_events"]) == 1
    assert record["token_events"][0]["completion_tokens_delta"] == 1


def test_separate_ack_and_content_chunks_bind_count_without_counting_text(monkeypatch):
    ack = {"ft_dev": {"schema": probe.DEV_SCHEMA, "uid": 7, "request_seq": 1, "completion_tokens_delta": 1, "completion_tokens_cumulative": 1}, "choices": []}
    content = {"choices": [{"delta": {"content": "token"}}]}
    monkeypatch.setattr(probe, "_open_response", lambda *_args, **_kwargs: _Response([_line(ack), _line(content), b"data: [DONE]\n\n"]))

    record = probe.stream_request(base_url="http://unit/v1", model="m", timeout=1, messages=[{"role": "user", "content": "x"}], max_tokens=4)

    assert record["completion_tokens"] == 1
    assert len(record["token_events"]) == 1
    assert record["ttft_s"] >= 0


def test_stream_rejects_zero_or_duplicate_acknowledgements(monkeypatch):
    prompt_ack = {"ft_dev": {"schema": probe.DEV_SCHEMA, "uid": 7, "request_seq": 1, "completion_tokens_delta": 0, "completion_tokens_cumulative": 0}, "choices": []}
    monkeypatch.setattr(probe, "_open_response", lambda *_args, **_kwargs: _Response([_line(prompt_ack), b"data: [DONE]\n\n"]))

    with pytest.raises(probe.ProbeError, match="delta must equal"):
        probe.stream_request(base_url="http://unit/v1", model="m", timeout=1, messages=[{"role": "user", "content": "x"}], max_tokens=4)


def test_prompt_new_tokens_requires_real_usage_evidence():
    assert probe.prompt_new_tokens({"usage": {"prompt_tokens": 10, "prompt_tokens_details": {"cached_tokens": 3}}}) == 7
    assert probe.prompt_new_tokens({"usage": {"prompt_tokens": 10}}) is None
    assert probe.prompt_new_tokens({"usage": {"prompt_tokens": 2, "prompt_tokens_details": {"cached_tokens": 3}}}) is None


@pytest.mark.parametrize("lines, match", [
    ([b"data: {bad}\n\n"], "invalid SSE JSON"),
    ([_line({"choices": [{"delta": {"content": "x"}}]}), b"data: [DONE]\n\n"], "before a validated"),
])
def test_stream_rejects_invalid_or_unacknowledged_trace(monkeypatch, lines, match):
    monkeypatch.setattr(probe, "_open_response", lambda *_args, **_kwargs: _Response(lines))
    with pytest.raises(probe.ProbeError, match=match):
        probe.stream_request(base_url="http://unit/v1", model="m", timeout=1, messages=[{"role": "user", "content": "x"}], max_tokens=4)


def test_timeout_fails_closed_and_parallel_calls_share_one_clock_origin(monkeypatch):
    monkeypatch.setattr(probe, "_open_response", lambda *_args, **_kwargs: (_ for _ in ()).throw(probe.ProbeError("stream request failed: late")))
    with pytest.raises(probe.ProbeError, match="stream request failed"):
        probe.stream_request(base_url="http://unit/v1", model="m", timeout=1, messages=[{"role": "user", "content": "x"}], max_tokens=4)

    calls = []

    def fake_stream(**kwargs):
        calls.append(kwargs)
        return {"way": len(calls)}

    monkeypatch.setattr(probe, "stream_request", fake_stream)
    assert probe._run_parallel([{"base_url": "x", "model": "m", "timeout": 1, "messages": [], "max_tokens": 1}] * 2)
    assert len(calls) == 2
    assert calls[0]["clock_origin"] == calls[1]["clock_origin"]
    assert calls[0]["wall_anchor"] == calls[1]["wall_anchor"]


def test_different_prompt_frontends_have_evidence_and_overlap():
    class Tokenizer:
        chat_template = "fixture"
        def encode(self, text, add_special_tokens=False):
            return [ord(char) for char in text]

        def apply_chat_template(self, messages, tokenize=True, add_generation_prompt=True, **kwargs):
            assert tokenize is False and kwargs == {"enable_thinking": False}
            return "<u>" + messages[0]["content"] + "<a>"

    left, left_ids = probe.make_messages(Tokenizer(), 100, "left")
    right, right_ids = probe.make_messages(Tokenizer(), 100, "right")
    assert left != right
    assert len(left_ids) == len(right_ids) == 100
    assert probe.prompt_sha256(left_ids) != probe.prompt_sha256(right_ids)
    assert 0 < probe.common_prefix_tokens(left_ids, right_ids) < len(left_ids)


def test_invalid_trace_and_h1_evidence_gap_are_explicit(tmp_path, monkeypatch):
    bad_trace = tmp_path / "bad.json"
    bad_trace.write_text("{}", encoding="utf-8")
    with pytest.raises(probe.ProbeError, match="trace round"):
        probe._trace_messages(bad_trace, 0)

    monkeypatch.setenv("FT_DEV_D0_PATH", str(tmp_path / "missing"))
    result = probe.h_steps(7, 1.0, [1, 8, 32])
    assert "missing" in result["nullreason"]


def test_h_steps_joins_uid_bound_d02_rows_and_rejects_short_or_wrong_uid(tmp_path, monkeypatch):
    base = tmp_path / "d0"
    steps = [
        {"step": 1, "t": 9.0, "rids": [7], "h2d_bytes": 1, "missing_total": 2},
        {"step": 2, "t": 11.0, "rids": [8], "h2d_bytes": 99, "missing_total": 99},
        {"step": 3, "t": 12.0, "rids": [7], "h2d_bytes": 3, "missing_total": 4},
    ]
    timeline = [
        {"step": 1, "t": 9.0, "rids": [7], "step_ms": 1.0},
        {"step": 3, "t": 12.0, "rids": [7], "step_ms": 3.0},
    ]
    (tmp_path / "d0_decode_steps.jsonl").write_text("\n".join(json.dumps(row) for row in steps) + "\n", encoding="utf-8")
    (tmp_path / "d0_decode_timeline.jsonl").write_text("\n".join(json.dumps(row) for row in timeline) + "\n", encoding="utf-8")
    (tmp_path / "d0_prefill.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setenv("FT_DEV_D0_PATH", str(base))

    result = probe.h_steps(7, 10.0, [1, 8])

    assert result["H"]["1"]["value"] == 3.0
    assert result["H"]["1"]["post_event_h2d_bytes"] == 3
    assert result["H"]["1"]["post_event_miss_total"] == 4
    assert result["H"]["8"]["value"] is None
    assert "insufficient" in result["H"]["8"]["nullreason"]


def test_pair_batch_evidence_requires_actual_prefill_uid_membership(tmp_path, monkeypatch):
    base = tmp_path / "d0"
    rows = [
        {"reqs": [{"rid": 4}, {"rid": 5}], "t_start": 1.0, "t_end": 2.0},
        {"reqs": [{"rid": 6}], "t_start": 3.0, "t_end": 4.0},
    ]
    (tmp_path / "d0_prefill.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    (tmp_path / "d0_decode_steps.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "d0_decode_timeline.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setenv("FT_DEV_D0_PATH", str(base))
    assert probe.pair_batch_evidence(4, 5) == (True, None)
    assert probe.pair_batch_evidence(4, 6) == (False, None)
    assert probe.pair_batch_evidence(4, 9)[0] is None


def test_main_failure_writes_exclusive_error_json(tmp_path):
    out = tmp_path / "result.json"
    rc = probe.main(["two-decode", "--ctx", "10", "--max-tokens", "2", "--same-prompt", "0", "--reps", "1", "--out", str(out), "--tokenizer-path", str(tmp_path / "missing")])
    assert rc == 2
    value = json.loads(out.read_text(encoding="utf-8"))
    assert value["state"] == "error"
    with pytest.raises(FileExistsError):
        probe.write_exclusive(out, value)
    assert probe.main(["two-decode", "--ctx", "10", "--max-tokens", "2", "--same-prompt", "0", "--reps", "1", "--out", str(out)]) == 2
    assert json.loads(out.read_text(encoding="utf-8")) == value

@pytest.mark.parametrize("delta", [True, 1.0])
def test_ack_requires_integer_delta(delta):
    event = {"ft_dev": {"schema": probe.DEV_SCHEMA, "uid": 7, "request_seq": 1,
                        "completion_tokens_delta": delta, "completion_tokens_cumulative": 1}}
    with pytest.raises(probe.ProbeError, match="delta must equal"):
        probe._ack(event, None)


def test_content_before_first_ack_cannot_be_retroactively_confirmed(monkeypatch):
    content = {"choices": [{"delta": {"content": "bogus"}}]}
    ack = {"ft_dev": {"schema": probe.DEV_SCHEMA, "uid": 7, "request_seq": 1,
                      "completion_tokens_delta": 1, "completion_tokens_cumulative": 1}, "choices": []}
    monkeypatch.setattr(probe, "_open_response", lambda *_a, **_kw:
                        _Response([_line(content), _line(ack), b"data: [DONE]\n\n"]))
    with pytest.raises(probe.ProbeError, match="before a validated"):
        probe.stream_request(base_url="http://unit/v1", model="m", timeout=1,
                             messages=[{"role": "user", "content": "x"}], max_tokens=1)


def test_pause_preserves_top_level_server_timestamps_inside_client_evidence(monkeypatch):
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return False
        def read(self, *_args):
            return json.dumps({"status": "accepted", "request_id": "p",
                               "accepted_wallclock_s": 10.0, "pause_started_wallclock_s": 11.0,
                               "deadline_wallclock_s": 12.0}).encode()
    monkeypatch.setattr(probe, "_open_response", lambda *_a, **_kw: Response())
    pause = probe._dev_pause("http://unit/v1", 1.0, 5.0)
    assert pause["response"]["deadline_wallclock_s"] == 12.0
    assert pause["response"]["pause_started_wallclock_s"] == 11.0

def test_pair_short_reports_actual_submit_skew_with_shared_wall_anchor(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(probe, "_trace_messages", lambda *_a: [{"role": "user", "content": "x"}])
    monkeypatch.setattr(probe, "_run_parallel", lambda *_a: [
        {"uid": 4, "ttft_s": 1.0, "t_anchor_unix_s": 100.0, "t_start_s": 2.0},
        {"uid": 5, "ttft_s": 1.0, "t_anchor_unix_s": 100.0, "t_start_s": 2.25},
    ])
    monkeypatch.setattr(probe, "pair_batch_evidence", lambda *_a: (None, "no D0"))
    args = SimpleNamespace(rounds="0,1", trace=Path("unused"), reps=1,
                           base_url="http://unit/v1", model="m", timeout=1.0)
    result = probe.run_pair_short(args)
    assert result["reps"][0]["submit_skew_s"] == pytest.approx(0.25)


def _write_d0(tmp_path, monkeypatch, steps, timeline, prefill=None):
    base = tmp_path / "d0"
    for suffix, rows in [("decode_steps", steps), ("decode_timeline", timeline), ("prefill", prefill or [])]:
        (tmp_path / f"d0_{suffix}.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    monkeypatch.setenv("FT_DEV_D0_PATH", str(base))


def test_h1_event_counters_are_separate_from_post_event_steps(tmp_path, monkeypatch):
    steps = [{"step": i, "t": float(i), "rids": [7], "h2d_bytes": i * 10, "missing_total": i}
             for i in range(1, 6)]
    timeline = [{"step": i, "t": float(i), "rids": [7], "step_ms": float(i)}
                for i in range(1, 6)]
    _write_d0(tmp_path, monkeypatch, steps, timeline)
    result = probe.h_steps(7, 4.0, [1], event_start_wallclock_s=2.0)
    assert result["H"]["1"]["value"] == 4.0
    assert result["event_counters"]["steps"] == [2, 3]
    assert result["event_counters"]["h2d_bytes"] == 50
    assert result["event_counters"]["miss_total"] == 5
    assert result["H"]["1"]["post_event_h2d_bytes"] == 40


def test_missing_d0_counter_is_not_fabricated_zero(tmp_path, monkeypatch):
    steps = [{"step": 1, "t": 1.0, "rids": [7], "missing_total": 1}]
    timeline = [{"step": 1, "t": 1.0, "rids": [7], "step_ms": 1.0}]
    _write_d0(tmp_path, monkeypatch, steps, timeline)
    result = probe.h_steps(7, 1.0, [1], event_start_wallclock_s=0.0)
    assert "h2d_bytes" in result["nullreason"]


def test_chunked_prefill_aggregates_all_uid_bound_intervals():
    rows = [{"reqs": [{"rid": 7}], "t_start": 10.0, "t_end": 12.0},
            {"reqs": [{"rid": 8}], "t_start": 12.0, "t_end": 13.0},
            {"reqs": [{"rid": 7}], "t_start": 13.0, "t_end": 16.0}]
    bound = probe._prefill_for_uid(rows, 7)
    assert (bound["t_start"], bound["t_end"], bound["chunks"]) == (10.0, 16.0, 2)


@pytest.fixture
def http_endpoint():
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    stopped, blocked_started, disconnected = threading.Event(), threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        def log_message(self, *_args):
            pass
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            content = payload.get("messages", [{}])[0].get("content", "")
            try:
                if content == "slow-headers":
                    self.connection.sendall(b"HTTP/1.1 200 OK\r\n")
                    while not stopped.wait(0.01):
                        self.connection.sendall(b"X-Keepalive: yes\r\n")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()
                if content == "bad":
                    assert blocked_started.wait(1.0)
                    self.wfile.write(b"data: {invalid}\n\n")
                    self.wfile.flush()
                    return
                blocked_started.set()
                while not stopped.wait(0.01):
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
            except (OSError, ValueError):
                disconnected.set()
            finally:
                self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", disconnected
    finally:
        stopped.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)


@pytest.mark.parametrize("content", ["heartbeat", "slow-headers"])
def test_total_timeout_interrupts_continuously_active_http(http_endpoint, content):
    import threading
    import time
    base_url, disconnected = http_endpoint
    started = time.perf_counter()
    with pytest.raises(probe.ProbeError, match="total request timeout"):
        probe.stream_request(base_url=base_url, model="m", timeout=0.15,
                             messages=[{"role": "user", "content": content}], max_tokens=4)
    assert time.perf_counter() - started < 1.5
    assert disconnected.wait(1.0)
    assert not any(t.name == "probe-request-deadline" and t.is_alive()
                   for t in threading.enumerate())


def test_parallel_failure_cancels_live_sibling_socket_and_joins(http_endpoint):
    import threading
    import time
    base_url, disconnected = http_endpoint
    calls = [{"base_url": base_url, "model": "m", "timeout": 5.0,
              "messages": [{"role": "user", "content": content}], "max_tokens": 4}
             for content in ("bad", "heartbeat")]
    started = time.perf_counter()
    with pytest.raises(probe.ProbeError, match="invalid SSE JSON"):
        probe._run_parallel(calls)
    assert time.perf_counter() - started < 1.5
    assert disconnected.wait(1.0)
    assert not any(t.name.startswith("probe-way-") and t.is_alive()
                   for t in threading.enumerate())


def test_real_d02_step_zero_is_valid(tmp_path, monkeypatch):
    steps = [{"step": 0, "t": 1.0, "rids": [7], "h2d_bytes": 2, "missing_total": 1}]
    timeline = [{"step": 0, "t": 1.0, "rids": [7], "step_ms": 4.0}]
    _write_d0(tmp_path, monkeypatch, steps, timeline)
    result = probe.h_steps(7, 1.0, [1])
    assert result["H"]["1"]["value"] == 4.0
    assert result["H"]["1"]["steps"] == [0]


def test_h1_run_matches_actual_prefill_duration_and_computes_deltas(monkeypatch):
    from types import SimpleNamespace
    lock = __import__("threading").Lock()
    next_uid = [10]
    prefill_records, pauses, warmed = [], [], []

    class Tokenizer:
        chat_template = "fixture"
        def apply_chat_template(self, messages, **kwargs):
            assert kwargs["enable_thinking"] is False and kwargs["tokenize"] is False
            return "<u>" + messages[0]["content"] + "<a>"
        def encode(self, text, **_kwargs):
            return [ord(char) for char in text]

    monkeypatch.setattr(probe, "load_tokenizer", lambda *_a: Tokenizer())
    def fake_stream(**kwargs):
        with lock:
            uid = next_uid[0]
            next_uid[0] += 1
        callback = kwargs.get("on_first_real")
        if callback:
            callback(uid)
            import threading
            for thread in threading.enumerate():
                if thread.name == "probe-h1-event":
                    thread.join(timeout=1.0)  # simulated decode outlives the event
        else:
            prefill_records.append(uid)
        return {"uid": uid}
    monkeypatch.setattr(probe, "stream_request", fake_stream)
    monkeypatch.setattr(probe, "_wait_decode_steps",
                        lambda uid, count, *_a: warmed.append((uid, count)))
    monkeypatch.setattr(probe, "d0_evidence", lambda: (
        [{"reqs": [{"rid": prefill_records[-1]}], "t_start": 10.0, "t_end": 12.0},
         {"reqs": [{"rid": prefill_records[-1]}], "t_start": 12.0, "t_end": 16.0}],
        [], [], "fixture"))
    def fake_pause(_base, seconds, _timeout, **_kwargs):
        pauses.append(seconds)
        return {"response": {"pause_started_wallclock_s": 20.0,
                             "deadline_wallclock_s": 20.0 + seconds}}
    monkeypatch.setattr(probe, "_dev_pause", fake_pause)
    def fake_h(_uid, end, horizons, **kwargs):
        assert "event_start_wallclock_s" in kwargs
        prefill = end == 16.0
        return {"H": {str(h): {"value": float(h) * (3 if prefill else 2)}
                      for h in horizons},
                "event_counters": {"h2d_bytes": 100 if prefill else 0,
                                   "miss_total": 4 if prefill else 0}}
    monkeypatch.setattr(probe, "h_steps", fake_h)
    args = SimpleNamespace(tokenizer_path="fixture", prefill_target=300, H="1,8,32",
                           base_url="http://fixture/v1", model="m", timeout=1, reps=1)
    result = probe.run_h1(args)
    row = result["reps"][0]
    assert pauses == [6.0]
    assert row["idle"]["event_duration_s"] == row["prefill"]["event_duration_s"] == 6.0
    assert row["delta_H"] == {"1": 1.0, "8": 8.0, "32": 32.0}
    assert row["event_extra_h2d_bytes"] == 100
    assert row["event_extra_miss_total"] == 4
    assert row["execution_order"] == ["prefill", "idle", "none"]
    assert len(warmed) == 3 and all(count == 8 for _uid, count in warmed)


def test_frontend_rejects_nonstandard_encoder_before_request():
    class Tokenizer:
        chat_template = None
        def apply_chat_template(self, *_args, **_kwargs):
            raise AssertionError("DSV4 must not be measured as the standard frontend")
    with pytest.raises(probe.ProbeError, match="DSV4"):
        probe.frontend_ids(Tokenizer(), [{"role": "user", "content": "x"}])


def _stall_args():
    from types import SimpleNamespace
    return SimpleNamespace(tokenizer_path="fixture", decode_ctx=300, decode_max_tokens=50,
                           prefill_kind="cold32k", prefill_target=500, trace=None, round=None,
                           delay=0.0, reps=1, base_url="http://fixture/v1", model="m", timeout=1)


def _stall_tokenizer():
    class Tokenizer:
        chat_template = "fixture"
        def apply_chat_template(self, messages, **kwargs):
            assert kwargs["enable_thinking"] is False
            return "<u>" + messages[0]["content"] + "<a>"
        def encode(self, text, **_kwargs):
            return [ord(char) for char in text]
    return Tokenizer()


def test_stall_counts_only_send_to_first_content_and_returns_longest_gap(monkeypatch):
    import threading
    finished = threading.Event()
    monkeypatch.setattr(probe, "load_tokenizer", lambda *_a: _stall_tokenizer())
    def stream(**kwargs):
        if kwargs.get("on_first_real"):
            kwargs["on_first_real"](7)
            assert finished.wait(1.0)
            return {"uid": 7, "t_first_s": 1.0, "t_last_s": 10.0,
                    "token_events": [_event(float(t), 1, i + 1)
                                     for i, t in enumerate([1, 2, 4, 7, 10])]}
        finished.set()
        return {"uid": 8, "t_start_s": 3.0, "t_first_s": 6.0,
                "t_last_s": 7.0, "ttft_s": 3.0,
                "usage": {"prompt_tokens": 500, "prompt_tokens_details": {"cached_tokens": 0}}}
    monkeypatch.setattr(probe, "stream_request", stream)
    result = probe.run_stall(_stall_args())["reps"][0]
    assert result["interference_tps"] == pytest.approx(1 / 3)
    assert result["max_gap_s"] == 3.0
    assert result["prefill_new_tokens"] == 500
    assert result["frontend_token_counts"] == [300, 500]


def test_stall_prefill_failure_cancels_decode_worker(monkeypatch):
    import threading
    monkeypatch.setattr(probe, "load_tokenizer", lambda *_a: _stall_tokenizer())
    stopped = threading.Event()
    def stream(**kwargs):
        if kwargs.get("on_first_real"):
            kwargs["on_first_real"](7)
            assert kwargs["control"].cancelled.wait(1.0)
            stopped.set()
            kwargs["control"].check()
        raise probe.ProbeError("prefill refused")
    monkeypatch.setattr(probe, "stream_request", stream)
    with pytest.raises(probe.ProbeError, match="prefill refused"):
        probe.run_stall(_stall_args())
    assert stopped.is_set()
    assert not any(t.name == "probe-stall-decode" and t.is_alive()
                   for t in threading.enumerate())
