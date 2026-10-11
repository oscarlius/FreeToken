"""R048 v7 binds the candidate trace semantics before judging zero timings."""
import importlib.util
from pathlib import Path


SOURCE = Path(__file__).parents[1] / "r048_t09_prepare_v9.py"


def load():
    spec = importlib.util.spec_from_file_location("r048_v7", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_candidate_trace_without_no_submit_record_keeps_all_zero_rejected(tmp_path):
    tool = load()
    root = tmp_path / "wt"
    files = {
        "python/freetoken/layers/moe.py": 'pending = executor.decode_submit\ncpu_task = executor.task_timing(pending)\n{"cpu_task": cpu_task}\n',
        "python/freetoken/moe/cpu_executor.py": "def task_timing():\n return dict(self._ext.task_timing(task))\n",
        "python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp": 'out["start_ns"]\nout["end_ns"]\nout["barrier_wait_ns_total"]\n',
    }
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    value = tool.native_all_zero_timing_semantics(root)
    assert value["all_zero_permitted"] is False
    assert value["explicit_no_submit_markers"] == {}


def test_explicit_marker_is_evidence_but_does_not_change_this_harness_policy(tmp_path):
    tool = load()
    root = tmp_path / "wt"
    files = {
        "python/freetoken/layers/moe.py": 'pending = executor.decode_submit\ncpu_task = executor.task_timing(pending)\n{"cpu_task": cpu_task}\nnot_submitted\n',
        "python/freetoken/moe/cpu_executor.py": "def task_timing():\n return dict(self._ext.task_timing(task))\n",
        "python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp": 'out["start_ns"]\nout["end_ns"]\nout["barrier_wait_ns_total"]\n',
    }
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    value = tool.native_all_zero_timing_semantics(root)
    assert value["explicit_no_submit_markers"] == {"not_submitted": ["hybrid_callsite"]}
    assert value["all_zero_permitted"] is False
