from contextlib import nullcontext
from types import SimpleNamespace

import pytest
import torch


@pytest.mark.parametrize("cut", [True, False])
def test_prefill_switch_preserves_decode_anchor_ids(monkeypatch, cut):
    import freetoken.engine as engine_module
    import freetoken.scheduler.scheduler as module

    cache = SimpleNamespace(is_hybrid=True, is_swa=False,
                            prefill_chunk_budget=None, anchor_snapshots_taken=0)
    moe = SimpleNamespace(_d0_on=True)
    engine = SimpleNamespace(
        device=torch.device("cpu"), stream=object(), page_table=None,
        num_pages=8, linear_state_pool=None, kv_cache=None, encoder_cache=None,
        tp_cpu_group=None, moe_offload_cache=moe,
    )
    model_config = SimpleNamespace(
        kv_cache_group_specs=lambda: [], attention_groups=[], model_is_mrope=False,
    )
    config = SimpleNamespace(
        max_running_req=4, page_size=1, cache_type="hybrid_radix",
        model_config=model_config, model_path="unused", prefill_layer_major=False,
        special_token_ckpt=True, prefill_anchor_cut=cut, max_extend_tokens=8192,
        decode_log_interval=40,
    )
    monkeypatch.setattr(engine_module, "Engine", lambda config: engine)
    monkeypatch.setattr(torch.cuda, "Stream", lambda **kw: object())
    monkeypatch.setattr(torch.cuda, "stream", lambda stream: nullcontext())
    monkeypatch.setattr(torch.cuda, "set_stream", lambda stream: None)
    monkeypatch.setattr(module, "CacheManager", lambda *args, **kw: cache)
    monkeypatch.setattr(module, "TableManager",
                        lambda *args: SimpleNamespace(token_pool=None))
    monkeypatch.setattr(module, "load_tokenizer", lambda path: SimpleNamespace(
        encode=lambda text, **kw: [20 if text == "</think>" else 21]))
    monkeypatch.setattr(module, "load_eos_token_ids", lambda *args: [])
    monkeypatch.setattr(module, "load_toolcall_anchor_id", lambda *args: 11)
    monkeypatch.setattr(module.SchedulerIOMixin, "__init__", lambda *args: None)

    sched = module.Scheduler(config)
    assert sched.prefill_manager.prefill_anchor_cut is cut
    assert sched.toolcall_anchor_id == 11
    assert sched.d3_extra_anchor_ids == {20, 21}
    assert sched.prefill_manager.anchor_ids == frozenset({11, 20, 21})
    assert moe.anchor_snapshot_source is cache


def test_scheduler_shutdown_reports_decode_counter_before_engine_exit(monkeypatch):
    from freetoken.scheduler.scheduler import Scheduler

    events = []
    sched = Scheduler.__new__(Scheduler)
    sched.device = torch.device("cpu")
    sched.sync_all_ranks = lambda: events.append("ranks")
    sched.engine = SimpleNamespace(
        moe_offload_cache=SimpleNamespace(
            _d0_on=True, _d0_finish_decode=lambda: events.append("counter")),
        shutdown=lambda: events.append("engine"),
    )
    monkeypatch.setattr(torch.cuda, "synchronize", lambda device: events.append("gpu"))
    sched.shutdown()
    assert events == ["gpu", "ranks", "counter", "engine"]
