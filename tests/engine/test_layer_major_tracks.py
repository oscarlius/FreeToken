"""CPU contracts for layer-major hybrid-radix checkpoint projection."""

from types import SimpleNamespace
from contextlib import nullcontext

import torch
import pytest

from freetoken.attention.linear import build_fla_metadata
from freetoken.core import Batch, Context, Req, SamplingParams, set_global_ctx
from freetoken.engine.engine import Engine


class _Pool:
    conv_states = torch.zeros(1, 8, 1, 3)


class _AttnBackend:
    def prepare_metadata(self, batch):
        batch.attn_metadata = object()


@pytest.fixture(autouse=True)
def _restore_global_context():
    import freetoken.core as core

    previous = core._GLOBAL_CTX
    try:
        yield
    finally:
        core._GLOBAL_CTX = previous


def _ctx():
    import freetoken.core as core

    core._GLOBAL_CTX = None
    set_global_ctx(Context(page_size=64, linear_state_pool=_Pool()))


def _batch(*, cached_len=0, extend_len=8193, ping_pong=(5, 6), next_track=0):
    req = SimpleNamespace(
        table_idx=1,
        uid=1,
        linear_slot_idx=2,
        cached_len=cached_len,
        device_len=cached_len + extend_len,
        extend_len=extend_len,
        max_device_len=cached_len + extend_len,
        mamba_ping_pong=ping_pong,
        mamba_next_track_idx=next_track,
        mamba_last_track_seqlen=None,
        mamba_restore_src=None,
        swa_evicted_seqlen=0,
        sampling_params=None,
        mrope_delta=0,
        mm_items=None,
        mrope_positions_full=None,
    )
    ids = torch.arange(extend_len, dtype=torch.int32)
    return SimpleNamespace(
        reqs=[req],
        padded_reqs=[req],
        input_ids=ids,
        positions=torch.arange(cached_len, cached_len + extend_len),
        out_loc=torch.arange(extend_len),
        mrope_positions=None,
        linear_table_idx=torch.tensor([2], dtype=torch.int32),
        fla_metadata=None,
        is_decode=False,
    )


def _engine(chunk):
    engine = object.__new__(Engine)
    engine.config = SimpleNamespace(max_extend_tokens=chunk)
    engine.device = torch.device("cpu")
    engine.attn_backend = _AttnBackend()
    return engine


def test_skip_track_metadata_is_side_effect_free():
    _ctx()
    batch = _batch(extend_len=129)

    meta = build_fla_metadata(batch, torch.device("cpu"), include_track=False)

    assert meta.track_dst is None
    assert batch.reqs[0].mamba_next_track_idx == 0
    assert batch.reqs[0].mamba_last_track_seqlen is None


@pytest.mark.parametrize("cached_len", [0, 17, 64])
def test_layer_major_children_keep_absolute_lengths_and_one_frozen_track(monkeypatch, cached_len):
    _ctx()
    batch = _batch(cached_len=cached_len, extend_len=8193)
    batch.fla_metadata = build_fla_metadata(batch, torch.device("cpu"))
    monkeypatch.setenv("FT_LM_CHUNK", "4096")

    chunks = _engine(4096)._build_layer_major_chunks(batch)

    assert [(c.reqs[0].cached_len, c.reqs[0].device_len) for c in chunks] == [
        (cached_len, cached_len+4096), (cached_len+4096, cached_len+8192),
        (cached_len+8192, cached_len+8193)
    ]
    assert batch.reqs[0].mamba_next_track_idx == 1
    assert [c.fla_metadata.track_dst is not None for c in chunks] == [False, False, False]
    assert chunks[0].fla_metadata.has_initial_state.tolist() == [cached_len > 0]
    if cached_len:
        assert chunks[0].fla_metadata.fresh_state_indices is None
    else:
        assert chunks[0].fla_metadata.fresh_state_indices.tolist() == [2]
    assert chunks[-1].track_initial_src == 2
    assert chunks[-1].track_initial_dst == 5


def test_non_aligned_layer_major_chunk_splits_at_track_boundary(monkeypatch):
    _ctx()
    batch = _batch(extend_len=130)
    batch.fla_metadata = build_fla_metadata(batch, torch.device("cpu"))
    monkeypatch.setenv("FT_LM_CHUNK", "100")

    chunks = _engine(100)._build_layer_major_chunks(batch)

    assert [c.reqs[0].extend_len for c in chunks] == [100, 28, 2]
    assert chunks[2].track_initial_src == 2
    assert chunks[2].track_initial_dst == 5


@pytest.mark.parametrize("cached_len", [0, 64])
def test_layer_major_projects_an_interior_track_without_flipping_ping_pong(monkeypatch, cached_len):
    _ctx()
    batch = _batch(cached_len=cached_len, extend_len=7000)
    batch.fla_metadata = build_fla_metadata(batch, torch.device("cpu"))
    monkeypatch.setenv("FT_LM_CHUNK", "4096")

    chunks = _engine(9000)._build_layer_major_chunks(batch)

    assert len(chunks) == 2
    fla = chunks[1].fla_metadata
    assert fla.track_dst.tolist() == [5]
    assert fla.track_h_row.tolist() == [45]
    assert fla.track_boundary_row.tolist() == [2880]
    assert fla.track_conv_src.tolist() == [[2877, 2878, 2879]]
    assert batch.reqs[0].mamba_next_track_idx == 1


def test_layer_major_without_ping_pong_has_no_track(monkeypatch):
    _ctx()
    batch = _batch(extend_len=8193, ping_pong=None)
    batch.fla_metadata = build_fla_metadata(batch, torch.device("cpu"))
    monkeypatch.setenv("FT_LM_CHUNK", "4096")

    chunks = _engine(4096)._build_layer_major_chunks(batch)

    assert all(chunk.fla_metadata.track_dst is None for chunk in chunks)
    assert all(chunk.track_initial_src is None for chunk in chunks)


def test_explicit_schedule_grid_preserves_short_donor_tail_and_track_target():
    _ctx()
    batch = _batch(cached_len=512, extend_len=7681)
    batch.fla_metadata = build_fla_metadata(batch, torch.device("cpu"))
    batch.dev_layer_major_subchunks = (4096, 3585)

    chunks = _engine(8192)._build_layer_major_chunks(batch)

    assert [(child.reqs[0].cached_len, child.reqs[0].device_len) for child in chunks] == [
        (512, 4608), (4608, 8193)]
    assert [child.reqs[0].extend_len for child in chunks] == [4096, 3585]
    assert batch.fla_metadata.track_dst.tolist() == [5]
    assert batch.reqs[0].mamba_last_track_seqlen == 8192


@pytest.mark.parametrize("geometry,expected_calls", [
    ([(0, 512, "ordinary", (512,)),
      (512, 8193, "layer_major", (4096, 3585)),
      (8192, 8257, "ordinary", (65,))],
     ["ordinary", [4096, 3585], "ordinary"]),
    ([(0, 12480, "layer_major", (4096, 4096, 4096, 192)),
      (12480, 12737, "ordinary", (257,)),
      (12736, 12801, "ordinary", (65,))],
     [[4096, 4096, 4096, 192], "ordinary", "ordinary"]),
])
def test_scheduled_prefill_uses_private_track_and_one_final_sample(monkeypatch, geometry, expected_calls):
    """CPU contract for the Engine-owned three logical-call schedule."""
    _ctx()
    prompt_len = geometry[-1][1]
    real = Req(torch.arange(prompt_len, dtype=torch.int32), table_idx=1, cached_len=0,
               output_len=128, uid=1, sampling_params=SamplingParams(), cache_handle=None)
    real.linear_slot_idx, real.mamba_ping_pong, real.mamba_next_track_idx = 2, (5, 6), 0
    outer = Batch(reqs=[real], phase="prefill")
    outer.padded_reqs = [real]
    outer.input_ids = torch.arange(prompt_len, dtype=torch.int32)
    outer.positions = torch.arange(prompt_len, dtype=torch.int32)
    outer.out_loc = torch.arange(prompt_len, dtype=torch.int64)
    outer.mrope_positions = None
    outer.fla_metadata = None
    outer.seg_reason = "other"
    outer.dev_prefill_schedule = tuple(
        SimpleNamespace(start=start, end=end, mode=mode, subchunks=chunks)
        for start, end, mode, chunks in geometry
    )
    calls, samples, copies, segments = [], [], [], []
    class Pool:
        def copy_from(self, src, dst): copies.append((src, dst, "conv,recurrent,ple_conv,ple_ngram_ctx"))
    class Model:
        def forward_host_ctx(self, batch, graph):
            segments.append((batch.seg_start, batch.seg_end, batch.seg_mode, batch.seg_subchunks,
                             batch.seg_reqs, batch.fla_metadata.has_initial_state.tolist(),
                             batch.fla_metadata.fresh_state_indices, int(batch.out_loc[0]),
                             batch.fla_metadata.track_dst.tolist(),
                             batch.reqs[0].mamba_last_track_seqlen))
            if batch.seg_start == geometry[-1][0]:
                assert copies == [(6, 2, "conv,recurrent,ple_conv,ple_ngram_ctx")]
            return nullcontext()
        def forward(self): calls.append("ordinary"); return torch.zeros(1, 3)
        def forward_layer_major(self, chunks): calls.append([c.reqs[0].extend_len for c in chunks]); return torch.zeros(1, 3)
    engine = _engine(8192)
    engine.ctx = SimpleNamespace(forward_batch=lambda batch: nullcontext())
    engine.model = Model(); engine.linear_state_pool = Pool(); engine.moe_offload_cache = None; engine.cpu_moe_executor = SimpleNamespace(raise_if_unhealthy=lambda: calls.append("watchdog"))
    engine.sampler = SimpleNamespace(sample=lambda logits, args: samples.append((tuple(logits.shape), real.mamba_last_track_seqlen)) or torch.tensor([7]))
    engine.stream = torch.device("cpu")
    monkeypatch.setattr(torch.cuda, "Event", lambda: SimpleNamespace(record=lambda stream: None))

    Engine._forward_dev_prefill_schedule(engine, outer, object())

    assert calls[:3] == expected_calls
    assert copies == [(6, 2, "conv,recurrent,ple_conv,ple_ngram_ctx")]
    assert segments[1][8:] == ([6], geometry[-1][0])
    assert samples == [((1, 3), prompt_len - 1)] and real.device_len == prompt_len + 1
    assert real.mamba_last_track_seqlen == prompt_len - 1
    assert [(row[0], row[1], row[2], row[3]) for row in segments] == [
        (start, end, mode, list(chunks)) for start, end, mode, chunks in geometry]
    assert [row[4] for row in segments] == [
        [{"rid": 1, "new_tokens": end - start, "cached_tokens": start}]
        for start, end, mode, chunks in geometry]
    assert segments[2][5] == [True] and segments[2][6] is None and segments[2][7] == geometry[-1][0]


def test_layer_major_rejects_an_outer_boundary_that_disagrees_with_request(monkeypatch):
    _ctx()
    batch = _batch(extend_len=129)
    batch.fla_metadata = build_fla_metadata(batch, torch.device("cpu"))
    batch.reqs[0].mamba_last_track_seqlen += 1
    monkeypatch.setenv("FT_LM_CHUNK", "64")

    with pytest.raises(AssertionError):
        _engine(64)._build_layer_major_chunks(batch)


@pytest.mark.parametrize("boundary", [129, 193])
def test_layer_major_rejects_track_at_or_beyond_full_end(monkeypatch, boundary):
    _ctx()
    batch = _batch(extend_len=129)
    batch.fla_metadata = build_fla_metadata(batch, torch.device("cpu"))
    batch.fla_metadata.track_boundary_row[0] = boundary
    batch.reqs[0].mamba_last_track_seqlen = boundary
    monkeypatch.setenv("FT_LM_CHUNK", "64")

    with pytest.raises(AssertionError):
        _engine(64)._build_layer_major_chunks(batch)


def test_layer_local_track_copy_does_not_overwrite_other_linear_layers():
    from freetoken.models.qwen4_exp.model import _copy_layer_major_track_state

    pool = SimpleNamespace(
        recurrent_states=torch.tensor([[[1.], [100.]], [[9.], [200.]]]),
        conv_states=torch.tensor([[[[2.]], [[20.]]], [[[8.]], [[80.]]]]),
        slot_states={
            "ple_conv": torch.tensor([[[[3.]], [[30.]]]]),
            "ple_ngram_ctx": torch.tensor([[4, 5], [7, 8]]),
        },
    )
    pool.local_index = lambda layer_id: layer_id
    pool.slot_state = lambda name, layer_id=None: (
        pool.slot_states[name][0] if layer_id is not None else pool.slot_states[name]
    )
    layer = SimpleNamespace(
        _is_linear=True,
        linear_attn=SimpleNamespace(layer_id=1),
        ple=None,
    )
    batch = SimpleNamespace(
        track_initial_src=0,
        track_initial_dst=1,
        ple_meta=None,
    )

    _copy_layer_major_track_state(pool, layer, batch)

    assert pool.recurrent_states[:, 1].tolist() == [[100.0], [9.0]]
    assert pool.conv_states[:, 1].tolist() == [[[20.0]], [[8.0]]]


def test_ple_track_copy_uses_incoming_context_before_commit():
    from freetoken.models.qwen4_exp.model import _copy_layer_major_track_state
    from freetoken.models.qwen4_exp.ple import build_ple_metadata, commit_ngram_context

    pool = SimpleNamespace(
        recurrent_states=torch.zeros(1, 2, 1),
        conv_states=torch.zeros(1, 2, 1, 1),
        slot_states={
            "ple_conv": torch.tensor([[[[3.]], [[30.]]]]),
            "ple_ngram_ctx": torch.tensor([[1469, 17], [0, 0]]),
        },
    )
    pool.local_index = lambda layer_id: layer_id
    pool.slot_state = lambda name, layer_id=None: (
        pool.slot_states[name][0] if layer_id is not None else pool.slot_states[name]
    )
    req = SimpleNamespace(extend_len=1, cached_len=8, table_idx=0, linear_slot_idx=0)
    batch = SimpleNamespace(
        padded_reqs=[req],
        input_ids=torch.tensor([23]),
        is_decode=False,
        fla_metadata=SimpleNamespace(
            has_initial_state=torch.tensor([True]),
            cu_seqlens=torch.tensor([0, 1]),
            cache_indices=torch.tensor([0]),
        ),
        track_initial_src=0,
        track_initial_dst=1,
    )
    args = SimpleNamespace(ngram_size=3, ngram_boundary_token_id=0, image_token_id=None)
    batch.ple_meta = build_ple_metadata(
        batch, args, torch.device("cpu"), context_pool=pool.slot_states["ple_ngram_ctx"]
    )
    layer = SimpleNamespace(_is_linear=False, ple=SimpleNamespace(layer_id=0))

    _copy_layer_major_track_state(pool, layer, batch)
    commit_ngram_context(batch.ple_meta, None, context_pool=pool.slot_states["ple_ngram_ctx"])

    assert pool.slot_states["ple_ngram_ctx"].tolist() == [[17, 23], [1469, 17]]
