"""CPU replay of frozen answer fields through the real SDK and canonical grader.

Synthetic SSE envelopes test the adapter, not historical wire bytes or live
generation. Usage is fixture-only; no target-model token counts are inferred.
"""
import hashlib
import importlib.util
import json
import os
from collections import Counter
from pathlib import Path

import httpx
import pytest
from openai import OpenAI

from sdk_capture import capture_chat_stream
from phase3_sdk import run_phase3_sdk
from test_phase3_sdk import load_benchmark, sse


def test_frozen_e0_all_60_statuses_and_fields_match(tmp_path, monkeypatch):
    location = os.environ.get("FT_QUALITY60_FROZEN_ROUNDS")
    if not location:
        pytest.skip("requires read-only frozen target-host corpus and answers")
    root = Path(location)
    sources = {
        "grader": ("E2-R009-regrade/source/evaluator.py", "39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330"),
        "corpus": ("E2-R009-regrade/source/test_prompts_60.json", "bde77ab02bb11539f6ee69861dc441ea3670ed6796d4d27226af1f89f74f9cad"),
        "answers": ("_e0/paper_headroom_20261003/quality60/quality_results_Qwen3.8-Flash-Next-NVFP4.jsonl", "355398ab3f88e261afb0ad8b728b9fcd9851b41468b5a48cea8b8f73124f8233"),
        "expected": ("E2-R009-regrade/E0-R000.regraded.jsonl", "55524848ad13d8e7b0ebc55393e1f937ec292ea7f9ae03ef959ad752ec2c55a5"),
    }
    data = {}
    for key, (relative, expected_hash) in sources.items():
        data[key] = (root / relative).read_bytes()
        assert hashlib.sha256(data[key]).hexdigest() == expected_hash, key
    spec = importlib.util.spec_from_file_location("quality60_frozen_grader", root / sources["grader"][0])
    grader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(grader)
    questions = {row["id"]: row for row in json.loads(data["corpus"])}
    answers = [json.loads(line) for line in data["answers"].splitlines()]
    expected = {row["question_id"]: row for row in map(json.loads, data["expected"].splitlines())}
    assert len(questions) == len(answers) == len(expected) == 60
    assert {row["question_id"] for row in answers} == set(questions) == set(expected)
    statuses = Counter()
    seen = []
    for answer in answers:
        qid = answer["question_id"]
        question = questions[qid]

        def respond(request):
            payload = json.loads(request.content)
            assert payload["messages"] == [{"role": "user", "content": question["prompt"]}]
            seen.append(qid)
            base = {"id": qid, "object": "chat.completion.chunk", "created": 0, "model": "archive-fixture"}
            rows = [{**base, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
                    for delta, finish in [({"reasoning_content": answer["thinking"]}, None),
                                          ({"content": answer["response"]}, None),
                                          ({}, answer["finish_reason"])]]
            rows.append({**base, "choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
            body = "".join("data: " + json.dumps(row, ensure_ascii=False) + "\n\n" for row in rows)
            return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body + "data: [DONE]\n\n")

        with httpx.Client(transport=httpx.MockTransport(respond), trust_env=False) as transport:
            with OpenAI(base_url="http://archive-fixture.invalid/v1", api_key="fixture", max_retries=0,
                        timeout=5.0, http_client=transport) as client:
                result = capture_chat_stream(client, {"model": "archive-fixture",
                    "messages": [{"role": "user", "content": question["prompt"]}], "max_tokens": 768,
                    "temperature": 0, "stream": True, "stream_options": {"include_usage": True}},
                    tmp_path / (qid + ".sdk.jsonl"))
        for key in ("response", "thinking", "finish_reason"):
            assert result[key] == answer[key], (qid, key)
        status, detail = grader.grade_question(question, result["response"], finish_reason=result["finish_reason"])
        assert status == expected[qid]["status"], (qid, status, detail)
        statuses[status] += 1
    assert len(seen) == len(set(seen)) == 60
    assert statuses == {"PASS": 47, "TRUNCATED": 11, "ANSWER_FAIL": 2}

    # Now exercise the actual existing question loop, grading and output schema.
    benchmark = load_benchmark(monkeypatch, tmp_path / "phase3")
    ordered_questions = json.loads(data["corpus"])
    answers_by_id = {answer["question_id"]: answer for answer in answers}
    phase3_seen = []

    def respond_phase3(request):
        question = ordered_questions[len(phase3_seen)]
        payload = json.loads(request.content)
        assert payload["messages"] == [{"role": "user", "content": question["prompt"]}]
        assert payload["max_tokens"] == 768 and payload["temperature"] == 0
        phase3_seen.append(question["id"])
        answer = answers_by_id[question["id"]]
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse(
            answer=answer["response"], thinking=answer["thinking"], finish=answer["finish_reason"],
            identity=question["id"]))

    with httpx.Client(transport=httpx.MockTransport(respond_phase3), trust_env=False) as transport:
        with OpenAI(base_url="http://archive-fixture.invalid/v1", api_key="fixture", max_retries=0,
                    timeout=5, http_client=transport) as client:
            summary = run_phase3_sdk(benchmark, client, "fixture", root / sources["corpus"][0])
    assert summary["graded_status_counts"] == statuses
    assert len(phase3_seen) == len(set(phase3_seen)) == 60
    records = [json.loads(line) for line in (tmp_path / "phase3" / "quality_results_fixture.jsonl").read_bytes().splitlines()]
    assert len(records) == 60
    for record in records:
        qid = record["question_id"]
        for key in ("response", "thinking", "finish_reason"):
            assert record[key] == answers_by_id[qid][key], (qid, key)
        assert record["graded_status"] == expected[qid]["status"]
        log = Path(record["capture"]["chunk_log"])
        assert hashlib.sha256(log.read_bytes()).hexdigest() == record["capture"]["chunk_log_sha256"]
    for relative, expected_hash in sources.values():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected_hash
