"""任务 B：--prefill-anchor-cut-min-tokens（默认 0）。

N = 0 时与 release-e2 逐位相同；N > 0 时只在本段待预填 token 数（remain_len）严格大于 N 时才按锚点切段。
仅 CPU 运行（不占 GPU）。
"""
from __future__ import annotations

from types import SimpleNamespace
from contextlib import nullcontext

import pytest
import torch

from freetoken.core import Context, SamplingParams, get_global_ctx, set_global_ctx
from freetoken.scheduler.cache import CacheManager
from freetoken.scheduler.decode import DecodeManager
from freetoken.scheduler.prefill import PrefillManager
from freetoken.scheduler.prefill_trace import SEG_REASON_ANCHOR_CAP, SEG_REASON_OTHER
from freetoken.scheduler.table import TableManager
from freetoken.scheduler.utils import PendingReq

ANCHOR = 99


def _manager(length, *, min_tokens=None, anchor_cut=True):
    try:
        get_global_ctx()
    except AssertionError:
        set_global_ctx(Context(page_size=1))
    table = torch.zeros((8, length + 1), dtype=torch.int32)
    cache = CacheManager(num_pages=length + 1, page_size=1, page_table=table, type="radix")
    kwargs = {"anchor_ids": frozenset({ANCHOR}), "prefill_anchor_cut": anchor_cut}
    if min_tokens is not None:
        kwargs["prefill_anchor_cut_min_tokens"] = min_tokens
    return PrefillManager(cache, TableManager(max_running_reqs=7, page_table=table),
                          DecodeManager(page_size=1), **kwargs)


def _anchored(length, anchor_at):
    ids = list(range(length))
    ids[anchor_at] = ANCHOR
    return ids


def _batch(manager, ids):
    manager.pending_list = [PendingReq(1, torch.tensor(ids, dtype=torch.int32), SamplingParams(max_tokens=1))]
    return manager.schedule_next_batch(len(ids))


def test_default_is_zero_and_matches_explicit_zero_on_anchored_prompt():
    ids = _anchored(12, 5)
    default = _batch(_manager(12), ids)
    explicit = _batch(_manager(12, min_tokens=0), ids)
    assert default.reqs[0].extend_len == explicit.reqs[0].extend_len == 5
    assert default.seg_reason == explicit.seg_reason == SEG_REASON_ANCHOR_CAP


def test_zero_keeps_the_anchor_switch_off_behaviour():
    batch = _batch(_manager(12, min_tokens=0, anchor_cut=False), _anchored(12, 5))
    assert batch.reqs[0].extend_len == 12
    assert batch.seg_reason == SEG_REASON_OTHER


def test_cut_needs_remain_strictly_above_threshold():
    ids = _anchored(12, 5)
    assert _batch(_manager(12, min_tokens=12), ids).reqs[0].extend_len == 12  # remain == N：不切
    cut = _batch(_manager(12, min_tokens=11), ids)                             # remain > N：切
    assert cut.reqs[0].extend_len == 5
    assert cut.seg_reason == SEG_REASON_ANCHOR_CAP


def test_threshold_32768_keeps_a_12k_prompt_whole():
    batch = _batch(_manager(12000, min_tokens=32768), _anchored(12000, 5000))
    assert batch.reqs[0].extend_len == 12000
    assert batch.seg_reason == SEG_REASON_OTHER


def test_threshold_32768_cuts_only_above_32768_and_matches_release():
    at_threshold = _batch(_manager(32768, min_tokens=32768), _anchored(32768, 5000))
    assert at_threshold.reqs[0].extend_len == 32768  # remain == 32768：不切
    over = _anchored(32769, 5000)
    candidate = _batch(_manager(32769, min_tokens=32768), over)
    release = _batch(_manager(32769), over)  # release-e2 行为（N = 0）
    assert candidate.reqs[0].extend_len == release.reqs[0].extend_len == 5000
    assert candidate.seg_reason == release.seg_reason == SEG_REASON_ANCHOR_CAP


def test_parse_args_default_zero_and_explicit_value():
    from freetoken.server.args import ServerArgs, parse_args

    args = ["--model", "/models/anon", "--dtype", "bfloat16"]
    assert ServerArgs.prefill_anchor_cut_min_tokens == 0
    assert parse_args(args)[0].prefill_anchor_cut_min_tokens == 0
    assert parse_args([*args, "--prefill-anchor-cut-min-tokens", "32768"])[0].prefill_anchor_cut_min_tokens == 32768


@pytest.mark.parametrize("min_tokens", [0, 32768])
def test_min_tokens_reaches_scheduler_and_both_prefill_classes(monkeypatch, min_tokens):
    import freetoken.engine as engine_module
    import freetoken.scheduler.scheduler as module

    cache = SimpleNamespace(is_hybrid=True, is_swa=False, prefill_chunk_budget=None, anchor_snapshots_taken=0)
    moe = SimpleNamespace(_d0_on=True)
    engine = SimpleNamespace(
        device=torch.device("cpu"), stream=object(), page_table=None, num_pages=8, linear_state_pool=None,
        kv_cache=None, encoder_cache=None, tp_cpu_group=None, moe_offload_cache=moe,
    )
    model_config = SimpleNamespace(kv_cache_group_specs=lambda: [], attention_groups=[], model_is_mrope=False)
    config = SimpleNamespace(
        max_running_req=4, page_size=1, cache_type="hybrid_radix", model_config=model_config,
        model_path="unused", prefill_layer_major=False, special_token_ckpt=True, prefill_anchor_cut=True,
        prefill_anchor_cut_min_tokens=min_tokens, max_extend_tokens=8192, decode_log_interval=40,
    )
    monkeypatch.setattr(engine_module, "Engine", lambda config: engine)
    monkeypatch.setattr(torch.cuda, "Stream", lambda **kw: object())
    monkeypatch.setattr(torch.cuda, "stream", lambda stream: nullcontext())
    monkeypatch.setattr(torch.cuda, "set_stream", lambda stream: None)
    monkeypatch.setattr(module, "CacheManager", lambda *args, **kw: cache)
    monkeypatch.setattr(module, "TableManager", lambda *args: SimpleNamespace(token_pool=None))
    monkeypatch.setattr(module, "load_tokenizer", lambda path: SimpleNamespace(
        encode=lambda text, **kw: [20 if text == "</think>" else 21]))
    monkeypatch.setattr(module, "load_eos_token_ids", lambda *args: [])
    monkeypatch.setattr(module, "load_toolcall_anchor_id", lambda *args: 11)
    monkeypatch.setattr(module.SchedulerIOMixin, "__init__", lambda *args: None)

    sched = module.Scheduler(config)
    assert sched.prefill_manager.prefill_anchor_cut_min_tokens == min_tokens
    assert sched.prefill_manager.prefill_anchor_cut is True
