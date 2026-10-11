"""AST-level regression contract for the shared phase3 benchmark client."""
import ast
import hashlib
import importlib
import json
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get("FT_QUALITY_BENCHMARK_SOURCE", ROOT.parent / "_shared" / "benchmark_client.py"))
EVALUATOR_SHA = "39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330"


def extracted(*names):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in selected} == set(names)
    namespace = {
        "__file__": str(SOURCE), "hashlib": hashlib, "importlib": importlib,
        "json": json, "os": os, "Path": Path,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


def test_standard_grader_uses_content_once_and_preserves_bool_detail_api():
    namespace = extracted("grade_response")
    seen = []
    namespace["grade_standard_response"] = lambda q, content, finish_reason: seen.append((content, finish_reason)) or ("PASS", "standard")
    assert namespace["grade_response"]({"category": "x"}, "visible answer", thinking="private wrong thought", finish_reason="stop") == (True, "standard")
    assert seen == [("visible answer", "stop")]


def test_wrong_standard_evaluator_is_refused(tmp_path):
    namespace = extracted("load_standard_grader")
    fake_client = tmp_path / "benchmark_client.py"
    fake_client.write_text("# fixture\n", encoding="utf-8")
    (tmp_path / "evaluator.py").write_text("def grade_question(*args, **kwargs): return ('PASS', 'wrong')\n", encoding="utf-8")
    namespace["__file__"] = str(fake_client)
    namespace["STANDARD_EVALUATOR_SHA256"] = EVALUATOR_SHA
    with pytest.raises(RuntimeError, match="unexpected standard evaluator sha256"):
        namespace["load_standard_grader"]()


def test_standard_evaluator_error_is_not_converted_to_a_model_failure():
    namespace = extracted("grade_standard_response")
    namespace["_STANDARD_VALID_STATUSES"] = {"PASS", "ANSWER_FAIL", "TRUNCATED", "EVALUATOR_ERROR", "RUNTIME_ERROR"}
    namespace["_STANDARD_FAILURE_STATUSES"] = {"EVALUATOR_ERROR", "RUNTIME_ERROR"}
    namespace["load_standard_grader"] = lambda: lambda *_args, **_kwargs: ("EVALUATOR_ERROR", "bad fixture")
    with pytest.raises(RuntimeError, match="standard grader failure"):
        namespace["grade_standard_response"]({"category": "x"}, "answer")


def test_phase3_keeps_the_fixed_generation_budget():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    phase3 = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_phase3_quality")
    assignments = [node for node in ast.walk(phase3) if isinstance(node, ast.Assign)]
    assert any(any(isinstance(target, ast.Name) and target.id == "max_tok" for target in node.targets) and isinstance(node.value, ast.Constant) and node.value.value == 768 for node in assignments)


def test_phase3_records_single_grade_and_provenance_without_changing_stats(tmp_path):
    namespace = extracted("run_phase3_quality")
    prompt_file = tmp_path / "corpus.json"
    prompts = [{"id": "q1", "category": "structured_tool", "prompt": "one"}, {"id": "q2", "category": "structured_tool", "prompt": "two"}]
    prompt_file.write_text(json.dumps(prompts), encoding="utf-8")
    namespace.update({
        "RUN_DIR": str(tmp_path), "STANDARD_EVALUATOR_SHA256": EVALUATOR_SHA,
        "log_msg": lambda _message: None,
        "load_standard_grader": lambda: None,
        "call_chat_stream": lambda _messages, max_tokens: ("answer", "hidden", 1.1, 0.8, 2.0, 7, 3, 4, "stop", None),
    })
    calls = []
    namespace["grade_standard_response"] = lambda q, content, finish_reason: calls.append((q["id"], content, finish_reason)) or ("PASS", "standard")
    result = namespace["run_phase3_quality"]("fixture", str(prompt_file))
    records = [json.loads(line) for line in (tmp_path / "quality_results_fixture.jsonl").read_text(encoding="utf-8").splitlines()]
    expected_client_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    expected_corpus_sha = hashlib.sha256(prompt_file.read_bytes()).hexdigest()
    assert calls == [("q1", "answer", "stop"), ("q2", "answer", "stop")]
    assert result["passed_cnt"] == 2 and result["total_cnt"] == 2 and result["accuracy"] == 1.0
    assert result["category_stats"] == {"structured_tool": {"passed": 2, "total": 2}}
    assert result["evaluator_sha256"] == EVALUATOR_SHA
    assert result["benchmark_client_sha256"] == expected_client_sha
    assert result["corpus_sha256"] == expected_corpus_sha
    assert result["graded_status_counts"] == {"PASS": 2}
    for record in records:
        assert record["graded_status"] == "PASS"
        assert record["evaluator_sha256"] == EVALUATOR_SHA
        assert record["benchmark_client_sha256"] == expected_client_sha
        assert record["corpus_sha256"] == expected_corpus_sha
        assert {"in_tokens", "content_tokens", "thinking_tokens", "ttft_thought_s", "ttft_content_s", "latency_s", "finish_reason", "response", "thinking"} <= record.keys()
