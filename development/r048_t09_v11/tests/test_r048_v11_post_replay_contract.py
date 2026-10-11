"""Actual candidate observer -> JSON writer -> formal T09 consumer, CPU only."""
import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import time
from types import SimpleNamespace

import pytest


HERE = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("r048_v11_contract", HERE / "r048_t09_prepare_v11.py")
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
CANDIDATE = Path(os.environ.get("FT_CPU_CANDIDATE_SOURCE", str(HERE.parent / "e2d08-capture-trace")))


def actual_method(name):
    path = CANDIDATE / "python/freetoken/moe/cpu_executor.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "CpuMoeExecutor")
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = {"Path": Path, "os": os, "json": json, "time": time, "math": math}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(path), "exec"), namespace)
    return namespace[name]


@pytest.fixture
def actual_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("FT_DEV_D0_PATH", str(tmp_path / "d0"))
    executor = SimpleNamespace(
        _hyb_trace_enabled=True, _trace_expected_layers=frozenset(range(48)),
        _trace_contexts={1: {}}, _trace_last_observed={}, _trace_observation_sequence=0,
        worker_pool_diagnostics=lambda: {"worker_service_counts": [1]},
    )
    state = {"step": 1}
    executor._ext = SimpleNamespace(task_timing=lambda layer: {
        "start_ns": state["step"] * 1000 + layer * 5,
        "end_ns": state["step"] * 1000 + layer * 5 + 3,
        "barrier_wait_ns_total": 1,
    })
    for layer in range(48):
        executor._trace_contexts[1][layer] = {
            "task": layer, "copy_event_begin": SimpleNamespace(elapsed_time=lambda end: 0.25),
            "copy_event_end": object(), "overlap": True,
            "cpu_submit_enqueue_ns": 1, "pcie_copy_enqueue_ns": 2, "cpu_sync_enqueue_ns": 3,
        }
    observe, append = actual_method("observe_trace_completion"), actual_method("append_trace_records")
    append(observe(executor, 1, replayed=True))
    state["step"] = 2
    append(observe(executor, 1, replayed=True))
    return tmp_path / "d0_hyb_trace.jsonl"


def test_actual_candidate_producer_and_consumer_accept_complete_fresh_replays(actual_trace):
    evidence = tool.trace_evidence(actual_trace)
    assert evidence["rows"] == 96
    assert evidence["graph_replay_observations"] == 2
    assert evidence["expected_hybrid_layers"] == list(range(48))
    assert evidence["fresh_native_completion"] is True


@pytest.mark.parametrize("fault, match", [
    ("missing_first_layer", "missing decode sequences or hybrid layers"),
    ("missing_last_layer", "missing decode sequences or hybrid layers"),
    ("duplicate", "duplicates or mixes"),
    ("stale", "stale native completion"),
    ("sequence_gap", "missing decode sequences"),
    ("missing_sequence", "sequence/layer evidence"),
    ("nan", "PCIe completion event"),
    ("all_eager", "two actual graph replays"),
    ("capture_enqueue", "unobserved Python enqueue"),
])
def test_actual_candidate_trace_mutations_fail_closed(actual_trace, fault, match):
    rows = [json.loads(line) for line in actual_trace.read_text().splitlines()]
    if fault == "missing_first_layer": rows.pop(0)
    elif fault == "missing_last_layer": rows.pop()
    elif fault == "duplicate": rows.insert(1, rows[0])
    elif fault == "stale": rows[48]["cpu_task"] = rows[0]["cpu_task"]
    elif fault == "sequence_gap":
        for row in rows[48:]: row["decode_observation_sequence"] = 3
    elif fault == "missing_sequence": rows[0].pop("decode_observation_sequence")
    elif fault == "nan": rows[0]["pcie_copy"]["event_elapsed_ms"] = float("nan")
    elif fault == "all_eager":
        for row in rows: row["replayed"] = False
    elif fault == "capture_enqueue": rows[0]["cpu_submit_enqueue_ns"] = 12
    actual_trace.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(RuntimeError, match=match): tool.trace_evidence(actual_trace)


def test_source_semantics_bind_actual_post_replay_candidate():
    value = tool.native_all_zero_timing_semantics(CANDIDATE)
    assert value["candidate_commit"] == tool.CANDIDATE
    assert value["all_zero_permitted"] is False
    assert "engine" in value["sources"]
    path = CANDIDATE / "python/freetoken/engine/engine.py"
    assert value["sources"]["engine"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_new_t16_metadata_must_bind_current_commit_and_parent(tmp_path):
    gate = tmp_path / "round.json"
    record = {"experimental": {"candidate_commit": tool.CANDIDATE}, "base": {"commit": tool.BASE}}
    gate.write_text(json.dumps(record))
    assert tool.require_candidate_gate(gate)["candidate_commit"] == tool.CANDIDATE
    record["experimental"]["candidate_commit"] = "8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8"
    gate.write_text(json.dumps(record))
    with pytest.raises(RuntimeError, match="exact candidate"): tool.require_candidate_gate(gate)


def test_actual_service_argv_preserves_graphs_and_hybrid_measurement_configuration():
    lifecycle = tool.load_d07()
    for arm in tool.ARM_PREFIXES:
        argv = tool.service_argv(lifecycle, 18813, arm)
        for key, value in (("--moe-strategy", "hybrid"), ("--cuda-graph-max-bs", "2"),
                           ("--kv-reserve-tokens", "98304"), ("--max-seq-len-override", "98304"),
                           ("--memory-ratio", "0.88"), ("--max-prefill-length", "4096")):
            assert argv[argv.index(key) + 1] == value
        assert "--moe-cpu-layers" not in argv and "--prefill-layer-major" not in argv
