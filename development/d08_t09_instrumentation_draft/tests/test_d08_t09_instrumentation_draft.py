from pathlib import Path

DRAFT = Path(__file__).parents[1] / "0001-d08-t09-completion-observation.patch"
README = Path(__file__).parents[1] / "README.md"

def test_patch_is_scoped_to_required_candidate_files_and_default_off_gate():
    text = DRAFT.read_text(encoding="utf-8")
    assert set(line.split(" b/", 1)[1] for line in text.splitlines() if line.startswith("diff --git")) == {
        "python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp",
        "python/freetoken/moe/cpu_executor.py",
        "python/freetoken/layers/moe.py",
    }
    assert "std::atomic<bool> trace_enabled{false}" in text
    assert "if not self._hyb_trace_enabled:\n+            return None" in text
    assert "torch.cuda.current_stream().synchronize()" in text

def test_patch_distinguishes_actual_event_completion_from_host_enqueue():
    text = DRAFT.read_text(encoding="utf-8")
    for field in ("trace_start_ns", "trace_end_ns", "trace_barrier_wait_ns", "event_elapsed_ms", "completion_observed_host_ns"):
        assert field in text
    readme = README.read_text(encoding="utf-8")
    assert "diagnostic perturbation" in readme
    assert "external bootstrap cannot" in readme

def test_const_worker_path_uses_mutable_observational_atomics():
    text = DRAFT.read_text(encoding="utf-8")
    assert "mutable std::atomic<int64_t> trace_start_ns" in text
    assert "mutable std::atomic<uint64_t> trace_barrier_wait_ns" in text
    assert "compare_exchange_strong" in text
    source = Path(__file__).parents[2] / "e2d08/python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp"
    assert "submit(t);\n            sync();" in source.read_text(encoding="utf-8")
