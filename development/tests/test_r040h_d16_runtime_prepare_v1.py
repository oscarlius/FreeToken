import importlib.util
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("r040h", ROOT / "r040h_d16_runtime_prepare_v1.py")
r040h = importlib.util.module_from_spec(spec); spec.loader.exec_module(r040h)


def _patched_startup_module(monkeypatch):
    source = r040h.patch_startup_source(r040h.SOURCE_STARTUP.read_text(encoding="utf-8"))
    module = ModuleType("r040h_startup")
    exec(compile(source, str(r040h.SOURCE_STARTUP), "exec"), module.__dict__)
    class Tensor:
        dtype = "int32"
        is_contiguous = True
        def contiguous(self): return self
    class Resident:
        def detach(self): return self
        def cpu(self): return self
        def clone(self): return self
        def __ge__(self, _): return self
        def sum(self): return 2
    seen = []
    def zeros(shape, *, dtype, device):
        value = Tensor(); seen.append((shape, dtype, device, value.is_contiguous)); return value
    fake_torch = SimpleNamespace(int32="int32", int64="int64", zeros=zeros, save=lambda *_: None)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    cache = SimpleNamespace(num_layers=2, cache_size=2, device="cuda:0", id_of_slot=Resident(),
                            is_cpu_layer=lambda _: False, is_unpinned_layer=lambda _: False,
                            reset=lambda: None, copy_missing=lambda: None, reset_stats=lambda: None)
    def ensure(layer, ids):
        assert ids.dtype == "int32" and ids.is_contiguous
    cache.ensure_experts = ensure
    engine = SimpleNamespace(moe_offload_cache=cache, stream=SimpleNamespace(synchronize=lambda: None),
                             forward_batch=lambda *_: None)
    scheduler = SimpleNamespace(engine=engine, engine_stream_ctx=nullcontext(), shutdown=lambda: None)
    return module, scheduler, seen


def test_configure_expert_cache_executes_actual_warm_branch_with_int32_contiguous_ids(monkeypatch, tmp_path):
    module, scheduler, seen = _patched_startup_module(monkeypatch)
    monkeypatch.setenv("FT_D16_CACHE_INIT", "warm")
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_DIR", str(tmp_path))
    monkeypatch.setenv("FT_D16_EXECUTION_ID", "cpu-warm")
    module.configure_expert_cache(scheduler)
    assert seen == [((1, 1), "int32", "cuda:0", True), ((1, 1), "int32", "cuda:0", True)]
    assert (tmp_path / "expert_cache" / "initialization.json").is_file()


def test_r040h_scope_is_only_the_eight_services_and_ten_calls_left_after_r040g():
    plan = r040h.source_plan()
    assert (plan["replay_services"], plan["replay_calls"]) == (8, 10)
    assert plan["replay_scope"]["completed_source_bindings"]["E2-R040g"] == {
        "services": 6, "calls": 6, "role": "partial parking and cache-cold evidence"}
    assert plan["source_change"]["new"].endswith("dtype=torch.int32, device=cache.device).contiguous()")


def test_missing_retained_proof_fails_closed_before_prepare(tmp_path):
    import pytest
    with pytest.raises(RuntimeError, match="retained-proof"):
        r040h.retained_proof(tmp_path / "missing.json")


def test_warm_selector_skips_completed_cold_arms_and_keeps_only_warm(monkeypatch):
    collector = ModuleType("collector")
    def _collect_state_processes(owner, ids, *, kind, wrapper, source_review, source_review_sha256, base_url):
        values = []
        for park in (False, True):
            values.append("warm" if park else "cold")
        return {"arms": values}
    collector._collect_state_processes = _collect_state_processes
    warm_only = r040h._warm_only_state_collector(collector)
    result = warm_only(None, [], kind="cache", wrapper=None, source_review=None, source_review_sha256=None, base_url="private")
    assert result["arms"] == ["warm"]


def test_remaining_body_runs_only_warm2_and_interleave6(monkeypatch):
    collector = ModuleType("collector")
    def _collect_state_processes(owner, ids, *, kind, wrapper, source_review, source_review_sha256, base_url):
        arms = []
        for park in (False, True):
            for repeat in (0, 1):
                arms.append(("warm_" + str(repeat)) if park else ("cold_" + str(repeat)))
        return {"arms": arms}
    def collect_native_processes(*_args, **kwargs):
        assert kwargs["slots"] == 2 and kwargs["interleave"] is True
        return {"runs": [{"service": index} for index in range(6)]}
    collector._collect_state_processes = _collect_state_processes
    collector.collect_native_processes = collect_native_processes
    monkeypatch.setattr(r040h, "load", lambda *_: collector)
    owner = SimpleNamespace(base_url="http://127.0.0.1:12345")
    result = r040h.run_remaining_body(owner, [1] * 512, [2] * 5000, wrapper=Path("wrapper"),
                                      source_review=Path("review"), source_review_sha256="x")
    assert result["services"] == 8 and result["calls"] == 10
    assert result["d16"]["cache_warm"]["arms"] == ["warm_0", "warm_1"]
