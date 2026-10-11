"""Exercise the actual shared question loop with SDK transport, without a model."""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from phase3_sdk import run_phase3_sdk
from phase3_sdk import main


def load_benchmark(monkeypatch, output):
    source = Path(os.environ.get("FT_QUALITY_BENCHMARK_SOURCE",
                  Path(__file__).resolve().parents[3] / "_shared" / "benchmark_client.py"))
    monkeypatch.setenv("FT_RUN_DIR", str(output))
    spec = importlib.util.spec_from_file_location("quality60_phase3_test", source)
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    benchmark.MODEL_NAME = "fixture"
    return benchmark


def sse(answer="  北京\n", finish="stop", malformed=False, thinking="private", identity="fixture"):
    base = {"id": identity, "object": "chat.completion.chunk", "created": 0, "model": "fixture"}
    rows = [{**base, "choices": [{"index": 0, "delta": delta, "finish_reason": ending}]}
            for delta, ending in [({"reasoning_content": thinking}, None),
                                  ({"content": answer}, None), ({}, finish)]]
    rows.append({**base, "choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}})
    body = "".join("data: " + json.dumps(row, ensure_ascii=False) + "\n\n" for row in rows)
    return body + ("data: {broken\n\n" if malformed else "") + "data: [DONE]\n\n"


def test_existing_phase3_records_success_truncation_and_failed_capture(tmp_path, monkeypatch):
    benchmark = load_benchmark(monkeypatch, tmp_path)
    prompts = [{"id": f"q{i}", "category": "chinese_extraction", "prompt": str(i), "expected": ["北京"]}
               for i in range(4)]
    corpus = tmp_path / "prompts.json"
    corpus.write_text(json.dumps(prompts), encoding="utf-8")
    bodies = [sse(), sse(answer="", finish="length"), sse(finish=None), sse(malformed=True)]
    seen = []

    def respond(request):
        payload = json.loads(request.content)
        seen.append(payload)
        assert payload["max_tokens"] == 768 and payload["temperature"] == 0
        assert payload["model"] == "fixture" and payload["stream_options"] == {"include_usage": True}
        return httpx.Response(200, headers={"content-type": "text/event-stream", "x-request-id": "req"},
                              content=bodies[len(seen) - 1])

    with httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as transport:
        with OpenAI(base_url="http://fixture.invalid/v1", api_key="fixture", max_retries=0,
                    timeout=5, http_client=transport) as client:
            summary = run_phase3_sdk(benchmark, client, "fixture", corpus)
            output = tmp_path / "quality_results_fixture.jsonl"
            original = output.read_bytes()
            with pytest.raises(FileExistsError):
                run_phase3_sdk(benchmark, client, "fixture", corpus)
            assert output.read_bytes() == original
    assert len(seen) == 4  # Includes failures: no hidden retry and no overwrite request.
    assert summary["graded_status_counts"] == {"PASS": 1, "TRUNCATED": 1, "RUNTIME_ERROR": 2}
    records = [json.loads(line) for line in original.splitlines()]
    assert records[0]["response"] == "  北京\n" and records[0]["thinking"] == "private"
    assert records[0]["capture"]["usage"]["completion_tokens"] == 2
    assert records[0]["capture"]["request_id"] == "req"
    for i, record in enumerate(records):
        assert record["question_id"] == f"q{i}"
        assert all(record[key] is None for key in ("latency_s", "ttft_content_s", "ttft_thought_s", "content_tokens", "thinking_tokens"))
        path = Path(record["capture"]["chunk_log"])
        assert record["capture"]["chunk_log_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        events = [json.loads(line) for line in path.read_bytes().splitlines()]
        assert events[-1]["kind"] == ("complete" if i < 2 else "error")
    assert all(record["finish_reason"] == "error" and record["response"] == "" for record in records[2:])


def test_cli_keeps_requested_model_identity(tmp_path, monkeypatch, capsys):
    corpus = tmp_path / "prompts.json"
    corpus.write_text(json.dumps([{"id": "cli", "category": "chinese_extraction",
                                  "prompt": "city", "expected": ["北京"]}]), encoding="utf-8")
    seen = []

    def respond(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse())

    class MockClient(httpx.Client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "Client", MockClient)
    monkeypatch.setattr(sys, "argv", ["phase3_sdk.py", "--api-base", "http://fixture.invalid/v1",
        "--model", "requested-model", "--prompts", str(corpus), "--run-dir", str(tmp_path / "cli")])
    # main configures its own environment; restore those variables after this test.
    for key in ("FT_API_BASE", "FT_MODEL_NAME", "FT_RUN_DIR"):
        monkeypatch.setenv(key, "prior-fixture")
    main()
    record = json.loads((tmp_path / "cli" / "quality_results_requested-model.jsonl").read_text(encoding="utf-8"))
    assert len(seen) == 1 and seen[0]["model"] == "requested-model"
    assert record["model_id"] == record["capture"]["model"] == "requested-model"
    assert record["graded_status"] == "PASS"
    assert '"passed_cnt": 1' in capsys.readouterr().out
