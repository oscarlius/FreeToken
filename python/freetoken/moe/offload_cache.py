from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import ClassVar, Iterator

import torch
from flashlib.kernels.slot_cache import N_STATS, Stat
from freetoken.moe.expert_profile import ExpertProfile, read_profile

# Fuse the per-bank expert copies into a single multi-bank launch (one per copy_missing
# instead of one per bank). Set FREETOKEN_FUSED_COPY=0 to force the legacy per-bank path
# (kept for A/B profiling). Falls back to per-bank automatically if a bank's row bytes or
# base address are not 16-byte aligned.
_FUSED_COPY = os.getenv("FREETOKEN_FUSED_COPY", "1").strip().lower() not in {"0", "false", "no", "off"}

# cudaMemcpyBatchAsync silently degrades to a SYNCHRONOUS copy when a batch mixes
# large entries with sub-~256KB entries on registered host memory (H100 + CUDA 13.0,
# empirically bisected: a single 5-22KB entry beside one large entry blocks the
# calling thread for the full transfer; >=253KB entries never do). A synchronous
# call still moves bytes at full PCIe rate but stalls the host, which un-hides the
# GEMM under the copy in transition-zone workloads (gpt-oss 2048tok: -22% e2e).
# Banks whose rows are smaller than this ship as ONE whole-layer entry (their
# whole layer is tiny) and are excluded from the hit gather, so every per-run
# entry the batch sees is >= this size.
_SMALL_BANK_FEAT_BYTES = 256 * 1024

from freetoken.utils import init_logger

logger = init_logger(__name__)


def dev_d0_enabled() -> bool:
    """D0 计时/计数埋点开关（DEV_PLAN_FT_QWEN38_20261003）。只加仪表，不改行为。"""
    return os.environ.get("FT_DEV_D0", "").strip().lower() not in {"", "0", "false", "no", "off"}


def _dev_d0_paths() -> tuple[str, str]:
    base = os.environ.get("FT_DEV_D0_PATH", "/tmp/ft_dev_d0")
    return base + "_prefill.jsonl", base + "_decode.json"


def dev_d0_timeline_enabled() -> bool:
    return dev_d0_enabled() and os.environ.get("FT_DEV_D0_TIMELINE", "0") == "1"

# quant_format -> bank names, in registration order: the single place a format's bank
# layout is declared. The cache machinery (copy_missing, the prefill double buffers,
# bank_views) iterates banks in this order, the layers' kernel dispatch unpacks views
# in this order, and set_bank_sources validates against it.
_BANK_SCHEMAS: dict[str, tuple[str, ...]] = {
    # dense bf16 expert weights
    "bf16": ("gate_up", "down"),
    # DeepSeek-V3-style 128x128 block-fp8 experts (Qwen3.5-FP8): fp8-e4m3 weights +
    # bf16 per-block weight_scale_inv. gate_up [L*E, 2I, H] fp8 + gate_up_scale
    # [L*E, 2I//128, H//128] bf16; down [L*E, H, I] fp8 + down_scale [L*E, H//128, I//128].
    # Half the host/cache footprint of bf16; the grouped GEMM (kernel/triton/fp8_blockscale_moe)
    # reads the routed fp8 rows directly and dequantizes in the K-loop (no bf16 materialization).
    "fp8_block": ("gate_up", "gate_up_scale", "down", "down_scale"),
    # native GGUF Q4_0 experts: packed block bytes per output row, dequantized inside
    # the borrowed ggml MoE kernels. gate_up [L*E, 2I, H//32*18], down [L*E, H, I//32*18].
    "q4_0": ("gate_up", "down"),
    # native ModelOpt rows for the Triton inline-dequant kernels: packed e2m1 codes +
    # fp8-e4m3 per-16 block scales + per-output-row fp16 globals (w1/w3 carry distinct
    # globals, and folding them into the e4m3 block scales would underflow)
    "nvfp4": (
        "gate_up_packed",
        "gate_up_scale",
        "gate_up_global",
        "down_packed",
        "down_scale",
        "down_global",
    ),
    # pre-tiled layouts for the borrowed kernels; the globals are folded into the
    # block scales at repack time and collapse to [L*E] GPU-resident alpha vectors
    # (set_alphas), so they are not banks
    "nvfp4_marlin": ("gate_up_packed", "gate_up_scale", "down_packed", "down_scale"),
    "nvfp4_b12x": ("gate_up_packed", "gate_up_scale", "down_packed", "down_scale"),
    # gpt-oss mxfp4, transposed split-K layout (N innermost): per-expert blocks_t
    # [K//2, N] (uint8), scales_t [K//32, N] (uint8 e8m0), bias [N]. No folded alphas
    # (scales are a bank); split-K GEMV decode + transposed _t grouped prefill.
    "mxfp4_triton": (
        "gate_up_blocks",
        "gate_up_scales",
        "gate_up_bias",
        "down_blocks",
        "down_scales",
        "down_bias",
    ),
    # DeepSeek-V4 FP4: packed e2m1 codes + e8m0 per-32 block scales, no global scale
    # (4 banks). Read by DeepSeek-V4's own DS-FP4 grouped GEMV kernels via bank_views().
    "ds_fp4": ("gate_up_packed", "gate_up_scale", "down_packed", "down_scale"),
}

# lives in kernel/aot_models.py: the AOT row table shares it and must stay importable in the torch-only kernel-cache build env, which cannot import freetoken.moe
from freetoken.kernel.aot_models import fp8_block_scale_pad


# bytes per (expert, layer) as f(hidden, moe_intermediate), from the bank shapes above; keep in sync with _BANK_SCHEMAS
# keyed by the config-time format tag (expert_quant / moe_weight_format), not quant_format: "mxfp4" sizes the mxfp4_triton banks, "nvfp4" also covers its repacked variants
_BANK_BYTES_PER_EXPERT = {
    "bf16": lambda H, I: 3 * I * H * 2,
    "fp8_block": lambda H, I: 3 * I * H + (
        (2 * I // 128) * fp8_block_scale_pad(2 * I // 128, H // 128)
        + (H // 128) * fp8_block_scale_pad(H // 128, I // 128)
    ) * 2,
    "q4_0": lambda H, I: 2 * I * (H // 32) * 18 + H * (I // 32) * 18,
    "nvfp4": lambda H, I: 2 * I * (H // 2 + H // 16 + 2) + H * (I // 2 + I // 16 + 2),
    "mxfp4": lambda H, I: 2 * I * (H // 2 + H // 32 + 2) + H * (I // 2 + I // 32 + 2),
    "ds_fp4": lambda H, I: 2 * I * (H // 2 + H // 32) + H * (I // 2 + I // 32),
}

# vLLM's marlin grouped-GEMM hands the full [cache_size] slot cache as its expert
# dimension; moe_align_block_size requires round_up(experts, 32) < 1024, i.e. <= 992.
MARLIN_MAX_CACHE_SIZE = 992


@dataclass
class DecodeBoundary:
    """Result of checking a caller-supplied completion event."""

    status: str
    sequence: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class AdaptationResult:
    status: str
    swaps: int = 0


@dataclass(frozen=True)
class AdaptationPlan:
    """Frozen replacement proposal; maps are not published until apply succeeds."""

    status: str
    replacements: tuple[tuple[int, int, int], ...] = ()  # (slot, layer, expert)
    reason: str | None = None
    mapping_generation: int | None = None
    boundary_seq: int | None = None


@dataclass(frozen=True)
class RuntimeAdaptationProof:
    cache_identity: int
    device: torch.device
    scheduler_identity: str
    launch_generation: int
    mapping_generation: int
    boundary_seq: int
    key: object


@dataclass(frozen=True)
class _LaunchGateReceipt:
    coordinator_identity: int
    launch_generation: int
    nonce: object


class RuntimeAdaptationCoordinator:
    """Scheduler-owned proof issuer; it has no cache mutation capability."""

    def __init__(self, cache, scheduler_identity: str):
        self._cache = cache
        self.scheduler_identity = scheduler_identity
        self._nonce = object()

    def close_launch_gate(self, launch_generation: int) -> _LaunchGateReceipt:
        return _LaunchGateReceipt(id(self), launch_generation, self._nonce)

    def issue_proof(self, gate: _LaunchGateReceipt, completed_events, drained_streams) -> RuntimeAdaptationProof | None:
        """Issue only after the caller stopped launch and drained every real stream.

        Query checks reject stale/incomplete receipts; the scheduler hook, not this
        cache module, establishes the stronger no-inflight fact before calling it.
        """
        cache = self._cache
        if (
            gate.coordinator_identity != id(self)
            or gate.nonce is not self._nonce
            or cache._policy_locked
            or cache.expert_policy != "profile+adapt"
        ):
            return None
        receipts = tuple(completed_events) + tuple(drained_streams)
        if not receipts or any(not callable(getattr(receipt, "query", None)) for receipt in receipts):
            return None
        try:
            if not all(receipt.query() for receipt in receipts):
                return None
        except Exception:
            return None
        try:
            if any(torch.device(getattr(receipt, "device", cache.device)) != cache.device for receipt in receipts):
                return None
        except (TypeError, RuntimeError):
            return None
        cache._decode_boundary_seq += 1
        return RuntimeAdaptationProof(
            id(cache), cache.device, self.scheduler_identity, gate.launch_generation,
            cache._mapping_generation, cache._decode_boundary_seq, cache._proof_key,
        )


@dataclass
class OffloadMoeCache:
    _d0_on: ClassVar[bool] = False
    _d0_prefill_active: ClassVar[bool] = False
    _d0_decode_recorder = None

    num_layers: int
    num_experts: int
    cache_size: int
    device: torch.device
    cache_policy: str = "lru"
    prefill_overlap: bool = False
    # Prefill hit/miss split: experts already resident in the slot cache (slots
    # >= 2 * num_experts) are gathered device-side into the double buffer instead
    # of re-crossing PCIe; only the misses are H2D'd (one cudaMemcpyBatchAsync of
    # coalesced runs). Requires prefill_overlap, cache_size > 2 * num_experts and
    # the fused copy plan; silently falls back to the full-layer copy otherwise.
    prefill_hit_d2d: bool = False
    # "bf16" (default, dense expert weights) or one of the NVFP4 bank layouts:
    # "nvfp4" (native ModelOpt rows, FreeToken Triton kernels), "nvfp4_marlin"
    # (Marlin-tiled, vLLM W4A16 GEMM, sm_80-99) or "nvfp4_b12x" (flashinfer SM12x
    # W4A16); or "mxfp4_triton" (gpt-oss transposed split-K GEMV decode + _t grouped
    # prefill). The format names its bank layout (_BANK_SCHEMAS) and which kernels
    # may read the banks; the cache machinery itself is layout-agnostic.
    quant_format: str = "bf16"
    # Decode mode + bank layout; per-layer CPU routing is cpu_layer_ids. "gpu":
    # GPU-tiled banks, all decode on GPU (stream misses over PCIe into the slot
    # cache, GEMM on GPU). "cpu": native (CPU-readable) banks + a CPU executor;
    # decode computes experts on the CPU (the slot cache only backs the prefill
    # double buffer). "hybrid": native banks + a CPU executor + a full slot cache;
    # each layer fetches a capped subset of its misses over PCIe (``hybrid_max_fetch``
    # / ``hybrid_fetch_fraction`` below; the GPU computes those plus the hits) and the
    # CPU absorbs the overflow misses, then the partials merge. The CPU executor is
    # attached (set_cpu_executor) for cpu/hybrid, set whenever >=1 layer decodes on the CPU.
    decode_target: str = "gpu"
    # hybrid only: max experts fetched over PCIe per (layer, decode step); the rest
    # of that step's misses are computed on the CPU. 0 -> never fetch (CPU does every
    # miss, the GPU cache stays cold); large -> behaves like pure offload.
    hybrid_max_fetch: int = 1
    # hybrid only: when > 0, replaces the fixed cap with a per-step fraction -- fetch
    # ~fraction * misses experts over PCIe (rounded to whichever integer balances the
    # overlap best), the CPU computes the rest. The engine sets it to the benched
    # pcie_bw / cpu_bw ratio so the PCIe fetch and the CPU overflow GEMV take equal
    # time (perfect overlap): fetched : cpu = pcie : cpu - pcie.
    hybrid_fetch_fraction: float = 0.0
    # bank layout from the expert kernel (a BankSpec per role); when given it replaces the _BANK_SCHEMAS lookup and the slot cap comes from max_slots
    layout: dict | None = None
    max_slots: int | None = None
    # The scheduler attaches its CacheManager for D0's successful-anchor counter.
    # Kept optional so the cache remains usable outside the serving scheduler.
    anchor_snapshot_source: object | None = None

    def __post_init__(self) -> None:
        policy_ids = {"lru": 0}
        assert self.cache_policy in policy_ids
        self.expert_policy = os.getenv("FT_DEV_EXPERT_POLICY", "lru").strip().lower()
        if self.expert_policy not in {"lru", "profile", "profile+adapt"}:
            raise ValueError("FT_DEV_EXPERT_POLICY must be lru, profile, or profile+adapt")
        self.expert_profile_path = os.getenv("FT_DEV_EXPERT_PROFILE", "").strip()
        self.expert_adapt_every = int(os.getenv("FT_DEV_EXPERT_ADAPT_EVERY", "0"))
        self.expert_adapt_swaps = int(os.getenv("FT_DEV_EXPERT_ADAPT_SWAPS", "0"))
        if self.expert_policy == "profile+adapt" and (self.expert_adapt_every <= 0 or self.expert_adapt_swaps <= 0):
            raise ValueError("profile+adapt requires positive FT_DEV_EXPERT_ADAPT_EVERY and FT_DEV_EXPERT_ADAPT_SWAPS")
        self._expert_profile: ExpertProfile | None = None
        self._decode_boundary_seq = 0
        self._adapted_boundary_seq = 0
        self._mapping_generation = 0
        self._proof_key = object()
        self._policy_locked = False
        assert self.decode_target in ("gpu", "cpu", "hybrid"), self.decode_target
        if self.layout is None:
            assert self.quant_format in _BANK_SCHEMAS, f"unknown quant_format {self.quant_format!r}"
        # Attached by the engine for decode_target == "cpu" (CpuMoeExecutor); None
        # for the GPU decode path.
        self.cpu_executor = None
        # MoE layer ids whose decode runs on the CPU executor; the rest use the GPU
        # offload/PCIe path. Set by the engine after construction (empty = all-GPU,
        # all layers = the plain --moe-strategy cpu case).
        self.cpu_layer_ids: frozenset = frozenset()
        # num_experts floor + nvfp4_marlin slot cap, shared with the runtime-rebuild path.
        self.validate_rebuild(self.cache_size)
        assert not self.prefill_overlap or self.cache_size >= 2 * self.num_experts, (
            "Prefill overlap borrows two full expert-layer buffers from the unified MoE "
            "cache, so cache_size must be at least 2 * num_experts "
            "(raise moe_cache_size or disable moe_prefill_overlap)"
        )
        self.cache_policy_id = policy_ids[self.cache_policy]
        self.slot_for_id = torch.full(
            (self.num_layers, self.num_experts),
            -1,
            dtype=torch.int32,
            device=self.device,
        )
        # Reverse map, in the flat id space flashlib's slot_cache works in:
        # id == layer_id * num_experts + expert, so one array replaces the (layer,
        # expert) pair and evicting a slot needs no decode.
        self.id_of_slot = torch.full(
            (self.cache_size,),
            -1,
            dtype=torch.int32,
            device=self.device,
        )
        self.usage = torch.zeros((self.cache_size,), dtype=torch.int64, device=self.device)
        self.step = torch.zeros((), dtype=torch.int64, device=self.device)
        self.active_mask = torch.zeros((self.num_experts,), dtype=torch.int32, device=self.device)
        # lru_ensure validates these against plan = min(batch * top_k, cache_size), so num_experts elements would under-size them
        plan_slots = max(self.num_experts, self.cache_size)
        self.evict_slots = torch.empty((plan_slots,), dtype=torch.int32, device=self.device)
        self.src_indices = torch.empty((plan_slots,), dtype=torch.int32, device=self.device)
        self.num_indices = torch.zeros((1,), dtype=torch.int64, device=self.device)
        # hybrid only: full missing count BEFORE the per-step fetch cap (num_indices holds
        # the capped count that copy_missing actually fetches). The difference is what the
        # CPU computes this step. Written by the hybrid ensure kernel.
        self.num_missing_full = torch.zeros((1,), dtype=torch.int64, device=self.device)
        # hybrid only: per-(layer, expert) last-active decode step (LRU on the expert), -1
        # if never active. The hybrid ensure kernel reads it to pick which capped misses to
        # fetch (most-recently active first) and bumps it for every active expert.
        self.expert_recency = torch.full(
            (self.num_layers, self.num_experts), -1, dtype=torch.int64, device=self.device
        )
        # Host source banks (one [num_experts, ...] tensor per layer, so layers can
        # carry independent host attributes -- see layer_residency) and their GPU
        # slot caches, keyed by the format's bank schema (attached by
        # set_bank_sources). The GPU slot cache stays one unified pool per bank.
        if self.layout is not None:
            self.bank_schema = tuple(role for role, spec in self.layout.items() if not spec.resident)
        else:
            self.bank_schema = _BANK_SCHEMAS[self.quant_format]
        self.bank_sources: dict[str, list[torch.Tensor]] = {}
        self.bank_caches: dict[str, torch.Tensor] = {}
        # per-layer host residency: the GPU movement paths require "pinned"; LOCKED/PAGEABLE layers decode on the CPU executor and prefill via copy_missing's pageable branch
        # _unpinned_layers is the derived id set the hot paths test against
        self.layer_residency: list[str] = []
        self._unpinned_layers: frozenset = frozenset()
        # marlin/b12x per-expert global scales ([L*E], GPU resident, see set_alphas).
        self.gate_up_alpha: torch.Tensor | None = None
        self.down_alpha: torch.Tensor | None = None
        # Opt-in decode miss-rate instrumentation. Accumulated on-device (no per-step host
        # sync); read via ``decode_miss_stats``. Graph-safe: the ``+=`` is captured into the
        # decode graph and re-executes with each replay's REAL routing (record_decode_stats
        # must be enabled before capture — see engine graph setup). The only graph artifact
        # is a one-off warm-up increment at capture time (<0.1% over a session).
        self.collect_stats = False
        # [num_layers, N_STATS] -- ensure_experts passes lru_stats[layer_id] straight to
        # the kernel, which accumulates in the same launch. The stat_* tensors below stay
        # for the hybrid path, whose kernel is still ours.
        self.lru_stats = torch.zeros(
            (self.num_layers, N_STATS), dtype=torch.int64, device=self.device
        )
        self.stat_missing = torch.zeros((), dtype=torch.int64, device=self.device)
        self.stat_active = torch.zeros((), dtype=torch.int64, device=self.device)
        self.stat_calls = torch.zeros((), dtype=torch.int64, device=self.device)
        # hybrid only: experts actually fetched over PCIe (<= stat_missing). The CPU
        # computes stat_missing - stat_fetched of them.
        self.stat_fetched = torch.zeros((), dtype=torch.int64, device=self.device)
        # Per-layer counterparts of the scalars above (indexed by MoE-layer id). Same
        # device-side accumulation (graph-safe: layer_id is a static index per graph node),
        # so one req's per-layer miss rate is readable via decode_miss_stats_per_layer().
        self.stat_missing_layer = torch.zeros(self.num_layers, dtype=torch.int64, device=self.device)
        self.stat_active_layer = torch.zeros(self.num_layers, dtype=torch.int64, device=self.device)
        self.stat_fetched_layer = torch.zeros(self.num_layers, dtype=torch.int64, device=self.device)
        self.stat_steps_layer = torch.zeros(self.num_layers, dtype=torch.int64, device=self.device)
        # Opt-in decode routing histogram (per layer, per expert) for cache-skew
        # analysis. Accumulated in ``ensure_experts`` from the raw expert ids before the
        # kernel rewrites them to slots. Only accurate with CUDA graphs disabled (the
        # captured graph would not re-run this host-side scatter on replay).
        self.collect_decode_freq = False
        self.decode_freq = torch.zeros(
            (self.num_layers, self.num_experts), dtype=torch.int64, device=self.device
        )
        # D15 policy counters stay separate from D0's global LRU counters.  They are
        # only read at a safe boundary and therefore never alter the default path.
        self.policy_hits = torch.zeros((), dtype=torch.int64, device=self.device)
        self.policy_misses = torch.zeros((), dtype=torch.int64, device=self.device)
        self.policy_swap_bytes = torch.zeros((), dtype=torch.int64, device=self.device)
        self.policy_recent = torch.zeros((self.num_layers, self.num_experts), dtype=torch.int64, device=self.device)
        # (per-layer sources, cache) per bank, in schema order. Every piece of cache
        # machinery that moves bank bytes (copy_missing, the prefill double buffers,
        # bank_views) iterates this list, so the slot cache is bank-count agnostic.
        self.banks: list[tuple[list[torch.Tensor], torch.Tensor]] = []
        # Fused multi-bank copy descriptor (built by set_bank_sources/_build_copy_plan).
        # Source pointers are per layer (_copy_src_ptrs[layer_id] -> [num_banks] device
        # tensor); dst/feat are layer-invariant.
        self._copy_fused_ok = False
        self._copy_dst_ptrs: torch.Tensor | None = None
        self._copy_src_ptrs: list[torch.Tensor] | None = None
        self._copy_feat_bytes: torch.Tensor | None = None
        # The layer whose misses ensure_experts/materialize_layer staged last; consumed
        # by copy_missing to pick the per-layer source (part of the same pending-copy
        # state as evict_slots/src_indices/num_indices).
        # _pending_whole_layer records WHICH staged it: the pageable branch is only sound after materialize_layer
        self._pending_src_layer: int | None = None
        self._pending_whole_layer = False
        # Per-bank [2, num_experts, ...] double-buffer views over the slot cache's
        # first 2 * num_experts slots (set up when prefill_overlap is enabled).
        self.prefill_bank_buffers: list[torch.Tensor] = []
        self.prefill_copy_stream: torch.cuda.Stream | None = None
        self.prefill_begin_event: torch.cuda.Event | None = None
        self.prefill_ready_events: list[torch.cuda.Event] = []
        self.prefill_release_events: list[torch.cuda.Event] = []
        self._prefill_buffer_layer: list[int | None] = [None, None]
        self._prefill_buffer_released: list[bool] = [True, True]
        self._prefill_buffer_has_release_event: list[bool] = [False, False]
        # hit-D2D split state: pinned begin-of-chunk snapshot of slot_for_id (the
        # classification input; frozen for the chunk -- no decode runs inside one,
        # and buffer invalidation only clears slot < 2E entries, which classify as
        # miss regardless), the lazily resolved batch-memcpy entry point (False =
        # unavailable), and row counters for cache reports.
        self._prefill_slot_snapshot: torch.Tensor | None = None
        self._prefill_snapshot_np = None
        self._prefill_hit_d2d_active = False
        self._hit_d2d_fallback_logged = False
        self._batch_memcpy = None
        self.prefill_hit_rows = 0
        self.prefill_total_rows = 0
        # --- D0 instrumentation (FT_DEV_D0=1): timing/byte counters only, no behavior change.
        self._d0_on = dev_d0_enabled()
        if self._d0_on:
            import threading
            import time as _time

            self._d0_chunk_idx = 0
            self._d0_h2d = 0
            self._d0_d2d = 0
            self._d0_layers: list[dict] = []
            self._d0_t_begin = _time.perf_counter()
            # 双缓冲会复用事件导致 GPU 时间戳被覆盖：每层新建事件，按 buffer 暂存
            self._d0_pending: dict[int, dict] = {}
            self._d0_prefill_path, self._d0_decode_path = _dev_d0_paths()
            from freetoken.moe.d0_decode import D0DecodeRecorder

            timeline = dev_d0_timeline_enabled()
            self._d0_decode_recorder = D0DecodeRecorder(
                os.environ.get("FT_DEV_D0_PATH", "/tmp/ft_dev_d0"), self.device,
                timeline=timeline,
                timeline_steps=int(os.environ.get("FT_DEV_D0_TIMELINE_STEPS", "200")) if timeline else 200,
            )
            self._d0_decode_recorder.compute_scopes = [
                "cpu_stream_wait_and_result" if self.is_cpu_layer(layer) else "gpu_experts"
                for layer in range(self.num_layers)
            ]

            # CUDA graph 捕获期间禁止任何设备同步读取（否则 capture 被作废）
            self._d0_capturing = [0]
            try:
                _orig_genter = torch.cuda.graphs.graph.__enter__
                _orig_gexit = torch.cuda.graphs.graph.__exit__

                def _d0_genter(gself, *a, **k):
                    self._d0_capturing[0] += 1
                    return _orig_genter(gself, *a, **k)

                def _d0_gexit(gself, *a, **k):
                    self._d0_capturing[0] -= 1
                    return _orig_gexit(gself, *a, **k)

                torch.cuda.graphs.graph.__enter__ = _d0_genter
                torch.cuda.graphs.graph.__exit__ = _d0_gexit
            except Exception:
                pass

            self._d0_decode_finished = False
            self._d0_decode_lock = threading.RLock()

            def _d0_dump_decode() -> None:
                while True:
                    _time.sleep(2.0)
                    if self._d0_decode_finished:
                        return
                    if self._d0_capturing[0] > 0:
                        continue
                    try:
                        self._d0_write_decode()
                    except Exception:
                        pass

            threading.Thread(target=_d0_dump_decode, daemon=True).start()
            logger.info("D0 instrumentation enabled (prefill -> %s, decode -> %s)", *(_dev_d0_paths()))

    def _d0_write_decode(self, *, final: bool = False) -> None:
        """Atomically refresh the D0 decode snapshot without changing runtime state."""
        if not getattr(self, "_d0_on", False):
            return
        with self._d0_decode_lock:
            if getattr(self, "_d0_decode_finished", False) and not final:
                return
            import json
            import time as _time

            snap = {"ts": _time.time(), "decode_target": self.decode_target}
            snap.update(self.decode_miss_stats())
            snap["expert_policy"] = self.expert_policy_stats()
            try:
                snap["per_layer"] = self.decode_miss_stats_per_layer()
            except Exception:
                pass
            snap["anchor_snapshots_taken"] = int(
                getattr(getattr(self, "anchor_snapshot_source", None), "anchor_snapshots_taken", 0)
            )
            from freetoken.moe.d0_decode import read_sm_clock_mhz

            snap["sm_clock_mhz"] = read_sm_clock_mhz(self.device)
            tmp = self._d0_decode_path + ".tmp"
            with open(tmp, "w") as f:
                json.dump(snap, f)
            os.replace(tmp, self._d0_decode_path)

    def _d0_finish_decode(self) -> None:
        """Write and report the final D0 decode snapshot once during graceful shutdown."""
        if not getattr(self, "_d0_on", False) or getattr(self, "_d0_decode_finished", False):
            return
        with self._d0_decode_lock:
            if self._d0_decode_finished:
                return
            self._d0_decode_finished = True
            try:
                self._d0_write_decode(final=True)
            except Exception:
                logger.exception("failed to write final D0 decode snapshot")
        logger.info(
            "D0 anchor_snapshots_taken=%d",
            int(getattr(getattr(self, "anchor_snapshot_source", None), "anchor_snapshots_taken", 0)),
        )

    def _d0_set_segment(self, batch) -> None:
        """Copy schedule-frozen metadata before the next scheduler mutation can move it."""
        import copy

        reqs = list(getattr(batch, "reqs", ()))
        start = getattr(batch, "seg_start", None)
        end = getattr(batch, "seg_end", None)
        if start is None and len(reqs) == 1:
            start = reqs[0].cached_len
        if end is None and len(reqs) == 1:
            end = reqs[0].device_len
        mode = getattr(batch, "seg_mode", None)
        if mode is None:
            mode = "layer_major" if getattr(batch, "layer_major", False) else "ordinary"
        subchunks = getattr(batch, "seg_subchunks", None)
        if subchunks is None and start is not None and end is not None:
            subchunks = [end - start]
        self._d0_segment = {
            "seg_reason": getattr(batch, "seg_reason", "other"),
            "reqs": copy.deepcopy(getattr(batch, "seg_reqs", [])),
            "start": start,
            "end": end,
            "mode": mode,
            "subchunks": copy.deepcopy(subchunks),
        }

    def _d0_begin_prefill(self, batch) -> None:
        """Begin only a real scheduled batch; warmup calls bypass forward_batch."""
        if not self._d0_on:
            return
        if self._d0_prefill_active:
            raise RuntimeError("D0 previous prefill segment did not finish")
        import time

        self._d0_set_segment(batch)
        self._d0_segment["t_start"] = time.time()
        self._d0_t_begin = time.perf_counter()
        self._d0_layers = []
        self._d0_pending = {}
        self._d0_h2d = self._d0_d2d = 0
        self._d0_prefill_active = True

    def end_prefill(self) -> None:
        """Synchronously publish this segment before forward_batch returns."""
        if self._d0_on:
            self._d0_flush_chunk()

    def _d0_decode_counts(self) -> tuple[list[int], list[int]]:
        if self.decode_target == "hybrid":
            counts = torch.stack((self.stat_missing_layer, self.stat_fetched_layer))
            missing, fetched = counts.tolist()
            return missing, fetched
        missing = self.lru_stats[:, Stat.MISS].tolist()
        # The GPU-only path fetches every missing expert. Its hybrid fetched
        # accumulator is intentionally unused and would report zero bytes.
        return missing, missing.copy()

    def _d0_begin_decode(self, batch) -> None:
        if self._d0_on:
            self._d0_decode_recorder.begin(batch, *self._d0_decode_counts())

    def _d0_end_decode(self) -> None:
        if self._d0_on:
            if self._d0_decode_recorder.timeline:
                self._d0_decode_recorder.seal_timeline()
            self._d0_decode_recorder.finish(
                *self._d0_decode_counts(),
                expert_row_bytes=sum(cache[0].numel() * cache.element_size() for _, cache in self.banks),
                hybrid=self.decode_target == "hybrid",
            )

    def _d0_decode_mark(self, layer: int, name: str) -> None:
        if self._d0_on and self._d0_decode_recorder._active:
            self._d0_decode_recorder.mark(layer, name)

    def _d0_sync_prefill_mark(self, layer: int, name: str) -> None:
        """D0 events for the non-overlap whole-layer prefill path."""
        if not self._d0_prefill_active:
            return
        event = torch.cuda.Event(enable_timing=True)
        event.record(torch.cuda.current_stream(self.device))
        pending = self._d0_pending.setdefault(layer, {})
        pending[name] = event
        if name == "copy_start":
            self._d0_h2d += sum(bank[0].numel() * bank.element_size() for _, bank in self.banks) * self.num_experts
        if name == "compute_end":
            self._d0_layers.append({"layer": layer, **pending, "d2d_start": None, "d2d_end": None})
            del self._d0_pending[layer]

    def _d0_flush_chunk(self) -> None:
        """Flush the completed segment now, including the process's last one."""
        if not getattr(self, "_d0_on", False):
            return
        if not self._d0_prefill_active:
            return
        import json as _json
        import time as _time

        # 解析 elapsed 前同步：确保所有事件已在 GPU 上完成
        if self.device.type == "cuda":
            torch.cuda.synchronize(self.device)
        t_end = _time.time()

        layers = []
        for ent in self._d0_layers:
            rec = {"layer": ent["layer"]}
            for name, a, b in (
                ("copy_ms", ent["copy_start"], ent["copy_end"]),
                ("compute_ms", ent["compute_start"], ent["compute_end"]),
                ("d2d_ms", ent["d2d_start"], ent["d2d_end"]),
            ):
                try:
                    rec[name] = round(a.elapsed_time(b), 3)
                except Exception:
                    rec[name] = None
            layers.append(rec)

        wall = _time.perf_counter() - self._d0_t_begin
        tot_h2d_gib = round(self._d0_h2d / 2**30, 3)
        tot_d2d_gib = round(self._d0_d2d / 2**30, 3)
        rec = {
            "chunk": self._d0_chunk_idx,
            "wall_s": round(wall, 4),
            "h2d_bytes": self._d0_h2d,
            "d2d_bytes": self._d0_d2d,
            "h2d_gib": tot_h2d_gib,
            "d2d_gib": tot_d2d_gib,
            "layers": layers,
        }
        rec.update(getattr(self, "_d0_segment", {"seg_reason": "other", "reqs": []}))
        rec["t_end"] = t_end
        with open(self._d0_prefill_path, "a", encoding="utf-8", buffering=1) as f:
            f.write(_json.dumps(rec, allow_nan=False) + chr(10))
            f.flush()
        logger.info(
            "D0 prefill chunk %d: wall %.3fs, H2D %.2f GiB, D2D %.3f GiB, layers %d",
            self._d0_chunk_idx, wall, tot_h2d_gib, tot_d2d_gib, len(layers),
        )
        reqs = rec["reqs"]
        req_summary = ",".join(
            f"{req.get('rid')}:{req.get('new_tokens')}/{req.get('cached_tokens')}"
            for req in reqs
        )
        logger.info(
            "D0 seg: idx=%d reason=%s reqs=%s",
            self._d0_chunk_idx, rec["seg_reason"], req_summary,
        )
        self._d0_chunk_idx += 1
        self._d0_h2d = 0
        self._d0_d2d = 0
        self._d0_layers = []
        self._d0_t_begin = _time.perf_counter()
        self._d0_prefill_active = False

    def _d0_layer_bytes(self, hit_rows: int) -> tuple[int, int]:
        """(h2d_bytes, d2d_bytes) for one layer given its hit row count. Small banks
        are copied whole (they also carry the hit rows); large banks split
        hit(D2D) / miss(H2D)."""
        h2d = 0
        d2d = 0
        for feat in self._copy_feat_bytes_host:
            if feat < _SMALL_BANK_FEAT_BYTES:
                h2d += self.num_experts * feat
            else:
                h2d += (self.num_experts - hit_rows) * feat
                d2d += hit_rows * feat
        return h2d, d2d

    def set_bank_sources(
        self,
        sources: dict[str, list[torch.Tensor]],
        layer_residency: list[str] | None = None,
    ) -> None:
        """Attach the host (CPU pinned) expert source banks and allocate a GPU slot
        cache per bank, following the format's bank schema.

        Every bank is a list of ``num_layers`` tensors, one ``[num_experts, ...]``
        per layer (independent allocations, so each layer can carry its own host
        attributes); each slot cache mirrors the bank's row shape and dtype as one
        unified GPU pool. The row layouts are produced by the weight loaders /
        repackers (see ``_BANK_SCHEMAS`` and :mod:`freetoken.layers.quantization.moe.nvfp4`)
        -- the cache machinery is layout-agnostic and just moves rows.

        ``layer_residency`` labels each layer with a ``HostResidency`` value (default: all pinned).
        Non-pinned (LOCKED/PAGEABLE) layers have no device address: they must already be routed to the CPU executor (``cpu_layer_ids``, set BEFORE this call), the copy plan skips their rows, and their only movement is ``copy_missing``'s whole-layer pageable prefill branch -- which is why prefill overlap is incompatible with them.
        """
        from freetoken.moe.legacy_format import canonical_role
        from freetoken.moe.host_banks import HostResidency

        # loaders and FTW files may still name the banks the old way (gate_up_packed, ...)
        by_role = {canonical_role(name): per_layer for name, per_layer in sources.items()}
        if set(by_role) != {canonical_role(n) for n in self.bank_schema}:
            raise AssertionError(
                f"banks {sorted(sources)} do not match the {self.quant_format!r} schema {self.bank_schema}"
            )
        sources = {name: by_role[canonical_role(name)] for name in self.bank_schema}
        residency = layer_residency or [HostResidency.PINNED.value] * self.num_layers
        assert len(residency) == self.num_layers, (len(residency), self.num_layers)
        unpinned = frozenset(
            i for i, r in enumerate(residency) if r != HostResidency.PINNED.value
        )
        if unpinned:
            if not unpinned <= self.cpu_layer_ids:
                raise ValueError(
                    f"non-pinned layers {sorted(unpinned - self.cpu_layer_ids)} are not in "
                    f"cpu_layer_ids: a layer without a device address can only decode on "
                    f"the CPU executor (set cache.cpu_layer_ids before set_bank_sources)"
                )
            if self.prefill_overlap:
                raise ValueError(
                    "prefill overlap DMAs from registered banks; it must be disabled "
                    "when any layer is LOCKED/PAGEABLE (the engine does this)"
                )
        self._unpinned_layers = unpinned
        self.layer_residency = list(residency)
        for name in self.bank_schema:
            per_layer = sources[name]
            assert len(per_layer) == self.num_layers, (name, len(per_layer))
            head = per_layer[0]
            if self.layout is not None:
                spec = self.layout[name]
                if tuple(head.shape[1:]) != tuple(spec.shape) or head.dtype != spec.dtype:
                    raise ValueError(
                        f"bank {name!r} rows are {tuple(head.shape[1:])} {head.dtype} but the expert kernel's layout "
                        f"wants {tuple(spec.shape)} {spec.dtype}; the banks were packed for another kernel"
                    )
            for layer_id, source in enumerate(per_layer):
                assert source.is_contiguous(), f"bank {name!r} layer {layer_id} must be contiguous"
                assert source.size(0) == self.num_experts, (name, layer_id, source.shape)
                assert source.shape == head.shape and source.dtype == head.dtype, (
                    name, layer_id, source.shape, source.dtype,
                )
            self.bank_sources[name] = list(per_layer)
            self.bank_caches[name] = torch.zeros(
                (self.cache_size, *head.shape[1:]),
                dtype=head.dtype,
                device=self.device,
            )
        self.banks = [(self.bank_sources[n], self.bank_caches[n]) for n in self.bank_schema]
        self._build_copy_plan()
        if self.prefill_overlap:
            self._init_prefill_overlap_buffers()
        self._initialize_expert_profile()

    def _initialize_expert_profile(self) -> None:
        """Preload an explicit STRP profile into stable slots (never the first 2E).

        This is startup-only.  Automatic adaptive swaps require an engine decode
        boundary and are intentionally not run from a layer-local copy call.
        """
        if self.expert_policy == "lru":
            return
        if not self.expert_profile_path:
            raise ValueError("profile policies require FT_DEV_EXPERT_PROFILE")
        profile = read_profile(self.expert_profile_path, num_layers=self.num_layers, num_experts=self.num_experts)
        self._expert_profile = profile
        stable_start = 2 * self.num_experts if self.prefill_overlap else 0
        capacity = max(0, self.cache_size - stable_start)
        if not capacity:
            logger.warning("D15 profile requested but cache has no stable slots after the 2E prefill region")
            return
        for slot, (layer, expert) in enumerate(profile.for_capacity(capacity), start=stable_start):
            if layer in self._unpinned_layers:
                continue
            for sources, target in self.banks:
                target[slot].copy_(sources[layer][expert], non_blocking=False)
            flat_id = layer * self.num_experts + expert
            self.slot_for_id[layer, expert] = slot
            self.id_of_slot[slot] = flat_id
        logger.info("D15 %s preloaded %d STRP experts into stable slots [%d, %d)", self.expert_policy, min(capacity, len(profile.ranked)), stable_start, self.cache_size)

    def record_expert_policy_routes(self, layer_id: int, expert_ids: torch.Tensor) -> None:
        """Count raw routes before slot rewriting; default LRU has no added work."""
        if self.expert_policy == "lru":
            return
        ids = expert_ids.reshape(-1).long()
        slots = self.slot_for_id[layer_id].index_select(0, ids)
        self.policy_hits += (slots >= 0).sum()
        self.policy_misses += (slots < 0).sum()
        self.policy_recent[layer_id].scatter_add_(0, ids, torch.ones_like(ids))

    def expert_policy_stats(self) -> dict:
        hits, misses, swap_bytes = (int(value.item()) for value in (self.policy_hits, self.policy_misses, self.policy_swap_bytes))
        state = "disabled-default" if self.expert_policy == "lru" else "profile-preload"
        if self.expert_policy == "profile+adapt":
            state = "adapt-boundary-proven" if self._decode_boundary_seq else "adapt-armed-awaiting-boundary"
        return {"policy": self.expert_policy, "state": state, "hits": hits, "misses": misses, "hit_rate": hits / (hits + misses) if hits + misses else 0.0, "swap_bytes": swap_bytes}

    def runtime_adaptation_coordinator(self, scheduler_identity: str) -> RuntimeAdaptationCoordinator | None:
        """Create the scheduler-side issuer only for an explicit adaptive policy."""
        if self.expert_policy != "profile+adapt" or self._policy_locked:
            return None
        return RuntimeAdaptationCoordinator(self, scheduler_identity)

    def seal_decode_boundary(self, copy_done_event, *, event_device=None) -> DecodeBoundary:
        """Accept only an event that reports completed on this cache's device.

        A recorded event is insufficient: callers must first establish completion
        (normally ``synchronize()``), then call this method.  Missing, incomplete,
        malformed, and foreign-device events return ``indeterminate`` and never
        create a usable adaptation token or mutate cache state.
        """
        if self._d0_prefill_active:
            return DecodeBoundary("indeterminate", reason="prefill_active")
        query = getattr(copy_done_event, "query", None)
        if not callable(query):
            return DecodeBoundary("indeterminate", reason="missing_completion_event")
        try:
            if not query():
                return DecodeBoundary("indeterminate", reason="completion_event_incomplete")
        except Exception:
            return DecodeBoundary("indeterminate", reason="completion_event_unqueryable")
        supplied_device = getattr(copy_done_event, "device", event_device)
        if supplied_device is not None and torch.device(supplied_device) != self.device:
            return DecodeBoundary("indeterminate", reason="completion_event_foreign_device")
        self._decode_boundary_seq += 1
        return DecodeBoundary("verified", sequence=self._decode_boundary_seq)

    def plan_profile_adaptation(self, proof: RuntimeAdaptationProof | None) -> AdaptationPlan:
        """Plan bounded replacements without mutating any cache slot or weight.

        A completed event only proves an earlier batch completed; it cannot prove a
        later overlapping batch is not reading these weights.  Therefore live
        caches always return ``indeterminate`` until D17 provides a real quiescent
        runtime proof.  CPU fixtures can model that proof with the private token.
        """
        if self.expert_policy != "profile+adapt":
            return AdaptationPlan("disabled")
        if self._d0_prefill_active or self._policy_locked:
            return AdaptationPlan("indeterminate", reason="prefill_active")
        if not isinstance(proof, RuntimeAdaptationProof) or (
            proof.cache_identity != id(self) or proof.device != self.device or proof.key is not self._proof_key
            or proof.mapping_generation != self._mapping_generation or proof.boundary_seq != self._decode_boundary_seq
            or proof.boundary_seq <= self._adapted_boundary_seq
        ):
            return AdaptationPlan("indeterminate", reason="no_runtime_quiescent_proof")
        if proof.boundary_seq % self.expert_adapt_every:
            return AdaptationPlan("scheduled")
        stable_start = 2 * self.num_experts if self.prefill_overlap else 0
        if stable_start >= self.cache_size:
            return AdaptationPlan("verified", mapping_generation=self._mapping_generation, boundary_seq=proof.boundary_seq)
        candidates = sorted(
            ((int(self.policy_recent[layer, expert].item()), layer, expert) for layer in range(self.num_layers) for expert in range(self.num_experts)),
            key=lambda row: (-row[0], row[1], row[2]),
        )
        usage = self.usage.tolist()
        planned_slots: set[int] = set()
        replacements = []
        for count, layer, expert in candidates:
            if (
                not count
                or len(replacements) >= self.expert_adapt_swaps
                or len(planned_slots) >= self.cache_size - stable_start
                or int(self.slot_for_id[layer, expert]) >= stable_start
            ):
                continue
            victim = min((slot for slot in range(stable_start, self.cache_size) if slot not in planned_slots), key=lambda slot: (usage[slot], slot))
            planned_slots.add(victim)
            replacements.append((victim, layer, expert))
            usage[victim] = int(self.step.item())
        return AdaptationPlan("verified", tuple(replacements), mapping_generation=self._mapping_generation, boundary_seq=proof.boundary_seq)

    def apply_profile_adaptation(self, plan: AdaptationPlan, proof: RuntimeAdaptationProof | None) -> AdaptationResult:
        """Transactional all-bank copy, rollback fence, then map publication."""
        if self._policy_locked or plan.status != "verified" or not isinstance(proof, RuntimeAdaptationProof):
            return AdaptationResult("indeterminate")
        if (proof.cache_identity != id(self) or proof.key is not self._proof_key or plan.mapping_generation != self._mapping_generation or plan.boundary_seq != proof.boundary_seq or proof.boundary_seq != self._decode_boundary_seq):
            return AdaptationResult("indeterminate")
        stable_start = 2 * self.num_experts if self.prefill_overlap else 0
        if len({slot for slot, _, _ in plan.replacements}) != len(plan.replacements) or any(slot < stable_start or slot >= self.cache_size or not (0 <= layer < self.num_layers and 0 <= expert < self.num_experts) for slot, layer, expert in plan.replacements):
            return AdaptationResult("indeterminate")
        backups = [(target, slot, target[slot].clone()) for slot, _, _ in plan.replacements for _, target in self.banks]
        try:
            for victim, layer, expert in plan.replacements:
                for sources, target in self.banks:
                    target[victim].copy_(sources[layer][expert], non_blocking=False)
            if self.device.type == "cuda":
                torch.cuda.current_stream(self.device).synchronize()
        except Exception:
            try:
                for target, slot, original in backups:
                    target[slot].copy_(original, non_blocking=False)
                if self.device.type == "cuda":
                    torch.cuda.current_stream(self.device).synchronize()
            except Exception:
                self._policy_locked = True
                return AdaptationResult("locked")
            return AdaptationResult("rolled_back")
        for victim, layer, expert in plan.replacements:
            previous = int(self.id_of_slot[victim])
            if previous >= 0:
                self.slot_for_id.view(-1)[previous] = -1
            self.slot_for_id[layer, expert] = victim
            self.id_of_slot[victim] = layer * self.num_experts + expert
            self.usage[victim] = self.step
            self.policy_swap_bytes += sum(target[victim].numel() * target[victim].element_size() for _, target in self.banks)
        self.policy_recent.zero_()
        self._adapted_boundary_seq = self._decode_boundary_seq
        self._mapping_generation += 1
        return AdaptationResult("verified", len(plan.replacements))

    def _build_copy_plan(self) -> None:
        self._build_fused_copy_plan()
        if self._copy_fused_ok or self.device.type != "cuda" or not self.banks:
            return
        for name in self.bank_schema:
            cache = self.bank_caches[name]
            feat = math.prod(cache.shape[1:]) * cache.element_size()
            if feat % 128:
                raise RuntimeError(
                    f"MoE bank {name!r} rows are {feat} bytes (not a multiple of 128): "
                    f"only the fused multi-bank copy can move them, but it is disabled"
                )

    def _build_fused_copy_plan(self) -> None:
        """Precompute the fused multi-bank copy descriptor (base addrs + per-row bytes).

        Built once here (and on :meth:`rebuild`, which reallocates the slot caches);
        the addresses are fixed for the cache's lifetime so the descriptor tensors are
        CUDA-graph safe. Disabled (-> per-bank fallback) if any bank's row bytes or base
        address is not 16-byte aligned, or via FREETOKEN_FUSED_COPY=0.
        """
        self._copy_fused_ok = False
        self._copy_dst_ptrs = None
        self._copy_src_ptrs = None
        self._copy_feat_bytes = None
        self._copy_dst_ptrs_host: list[int] = []
        self._copy_src_ptrs_host: list[list[int]] = []
        self._copy_feat_bytes_host: list[int] = []
        self._gather_bank_ids: list[int] = []
        self._gather_dst_ptrs: torch.Tensor | None = None
        self._gather_feat_bytes: torch.Tensor | None = None
        if not _FUSED_COPY or self.device.type != "cuda" or not self.banks:
            return
        from freetoken.kernel.pinned import device_ptr

        dst_ptrs, feats = [], []
        layer_src_ptrs = [[] for _ in range(self.num_layers)]
        for per_layer, cache in self.banks:
            feat = math.prod(per_layer[0].shape[1:]) * per_layer[0].element_size()
            if feat % 16 != 0 or cache.data_ptr() % 16 != 0:
                return  # leave fused disabled; copy_missing uses the per-bank path
            for layer_id, source in enumerate(per_layer):
                if layer_id in self._unpinned_layers:
                    # unregistered layer: no device alias exists, and the row is never consumed (CPU decode; pageable prefill)
                    # a 0 placeholder keeps the descriptor shape
                    layer_src_ptrs[layer_id].append(0)
                    continue
                # The kernel dereferences these on the GPU, so store each host bank's
                # device alias (== data_ptr() under UVA identity; differs on
                # Windows/WDDM).
                src_dev = device_ptr(source)
                if src_dev % 16 != 0:
                    return
                layer_src_ptrs[layer_id].append(src_dev)
            dst_ptrs.append(cache.data_ptr())
            feats.append(feat)
        self._copy_dst_ptrs = torch.tensor(dst_ptrs, dtype=torch.int64, device=self.device)
        self._copy_src_ptrs = [
            torch.tensor(ptrs, dtype=torch.int64, device=self.device)
            for ptrs in layer_src_ptrs
        ]
        self._copy_feat_bytes = torch.tensor(feats, dtype=torch.int64, device=self.device)
        self._copy_dst_ptrs_host = dst_ptrs
        self._copy_src_ptrs_host = layer_src_ptrs
        self._copy_feat_bytes_host = feats
        # hit-D2D gather serves only the big banks; small banks are whole-layer
        # H2D entries (see _SMALL_BANK_FEAT_BYTES), so their rows never need D2D.
        self._gather_bank_ids = [i for i, f in enumerate(feats) if f >= _SMALL_BANK_FEAT_BYTES]
        if len(self._gather_bank_ids) == len(feats):
            self._gather_dst_ptrs = self._copy_dst_ptrs
            self._gather_feat_bytes = self._copy_feat_bytes
        elif self._gather_bank_ids:
            self._gather_dst_ptrs = self._copy_dst_ptrs[self._gather_bank_ids].contiguous()
            self._gather_feat_bytes = self._copy_feat_bytes[self._gather_bank_ids].contiguous()
        self._copy_fused_ok = True

    def validate_rebuild(self, cache_size: int) -> None:
        """Pure geometry validation of a rebuild target (no GPU side effects).

        Raises ``ValueError`` if ``cache_size`` is below the ``num_experts`` floor or
        above the marlin slot cap. Called by :meth:`rebuild` and by the engine's
        pre-teardown check, so an invalid target rejects with the old cache intact
        (no destructive free first).
        """
        if cache_size < self.num_experts:
            raise ValueError(f"cache_size {cache_size} < num_experts {self.num_experts}")
        if self.max_slots is not None and cache_size > self.max_slots:
            raise ValueError(
                f"moe_cache_size={cache_size} exceeds the expert kernel's slot limit of {self.max_slots}; "
                f"pass --moe-cache-size {self.max_slots} or less, or let the default kernel serve the experts"
            )
        if self.layout is None and self.quant_format == "nvfp4_marlin" and cache_size > MARLIN_MAX_CACHE_SIZE:
            raise ValueError(
                f"moe_cache_size={cache_size} exceeds the marlin backend's slot limit of "
                f"{MARLIN_MAX_CACHE_SIZE} (vLLM moe_align_block_size caps padded experts at "
                "1024); reduce moe_cache_size or force --quant-backend moe.nvfp4=triton"
            )

    def rebuild(self, cache_size: int) -> None:
        """Resize the GPU slot cache + bookkeeping to ``cache_size`` IN PLACE.

        Keeps the CPU/pinned ``bank_sources`` and the GPU-resident alphas; never
        reloads banks. Tears down prefill-overlap buffers first (their views alias
        the old ``bank_caches``), frees the old GPU tensors, then reallocates. Slots
        cold-start after rebuild. Object identity is preserved so attached layers and
        ``ctx.moe_offload_cache`` stay valid.
        """
        assert self.bank_sources, "set_bank_sources must run before rebuild"
        self.validate_rebuild(cache_size)
        # 1. Tear down prefill-overlap (its buffer views alias the old bank_caches).
        self.prefill_bank_buffers = []
        self.prefill_copy_stream = None
        self.prefill_begin_event = None
        self.prefill_ready_events = []
        self.prefill_release_events = []
        self._prefill_buffer_layer = [None, None]
        self._prefill_buffer_released = [True, True]
        self._prefill_buffer_has_release_event = [False, False]
        # 2. Drop old GPU tensors (free-before-alloc).
        self.banks = []
        self.bank_caches = {}
        self.cache_size = cache_size
        if self.device.type == "cuda":
            torch.cuda.synchronize(self.device)
            torch.cuda.empty_cache()
        # 3. Reallocate the slot cache from the retained host sources.
        for name in self.bank_schema:
            head = self.bank_sources[name][0]
            self.bank_caches[name] = torch.zeros(
                (cache_size, *head.shape[1:]), dtype=head.dtype, device=self.device
            )
        self.banks = [(self.bank_sources[n], self.bank_caches[n]) for n in self.bank_schema]
        self._build_copy_plan()  # slot caches were reallocated -> refresh fused-copy addrs
        # 4. Reallocate cache_size-shaped bookkeeping; reset the slot map (cold start).
        self.slot_for_id.fill_(-1)
        self.id_of_slot = torch.full((cache_size,), -1, dtype=torch.int32, device=self.device)
        self.usage = torch.zeros((cache_size,), dtype=torch.int64, device=self.device)
        plan_slots = max(self.num_experts, cache_size)
        self.evict_slots = torch.empty((plan_slots,), dtype=torch.int32, device=self.device)
        self.src_indices = torch.empty((plan_slots,), dtype=torch.int32, device=self.device)
        self.step.zero_()
        self.active_mask.zero_()
        self.num_indices.zero_()
        self.num_missing_full.zero_()
        self.expert_recency.fill_(-1)
        self.stat_missing.zero_()
        self.stat_active.zero_()
        self.stat_calls.zero_()
        self.stat_fetched.zero_()
        self.stat_missing_layer.zero_()
        # a rebuild is a cold start for the cache; carrying pre-rebuild hit/miss counts over would skew every post-rebuild stats report
        self.lru_stats.zero_()
        self.stat_active_layer.zero_()
        self.stat_fetched_layer.zero_()
        self.stat_steps_layer.zero_()
        self.decode_freq.zero_()
        self.prefill_hit_rows = 0
        self.prefill_total_rows = 0
        self._hit_d2d_fallback_logged = False  # geometry changed; re-log if still unusable
        # 5. Re-evaluate prefill overlap against the new size.
        if self.prefill_overlap and cache_size < 2 * self.num_experts:
            logger.warning(
                f"Disabling MoE prefill overlap on rebuild: cache_size {cache_size} "
                f"< 2*num_experts {2 * self.num_experts}."
            )
            self.prefill_overlap = False
        if self.prefill_overlap:
            self._init_prefill_overlap_buffers()

    def set_alphas(
        self, gate_up_alpha: torch.Tensor | None, down_alpha: torch.Tensor | None
    ) -> None:
        """Attach the marlin/b12x per-expert global scales (``[L*E]``, GPU resident).

        These are kernel-preprocessed scalars, far too small to bother offloading;
        the forward path looks them up per slot with :meth:`alphas_for_slots` /
        :meth:`alphas_for_layer` (pure device-side lookups, CUDA-graph safe).
        ``(None, None)`` is a no-op so callers can pass a format's (possibly
        absent) alphas through unconditionally.
        """
        if gate_up_alpha is None and down_alpha is None:
            return
        assert gate_up_alpha is not None and down_alpha is not None
        total = self.num_layers * self.num_experts
        assert gate_up_alpha.shape == down_alpha.shape == (total,)
        self.gate_up_alpha = gate_up_alpha.to(self.device)
        self.down_alpha = down_alpha.to(self.device)

    def set_cpu_executor(self, executor) -> None:
        """Attach the CPU MoE executor (``decode_target`` in {"cpu", "hybrid"}).

        The executor owns the persistent worker pool, the pinned activation/result
        IO buffers, and the ``cudaLaunchHostFunc`` submit/sync plumbing. It reads
        experts straight from this cache's host ``bank_sources`` (no extra copy).
        """
        assert self.decode_target in ("cpu", "hybrid"), (
            "set_cpu_executor requires decode_target in {'cpu','hybrid'}"
        )
        self.cpu_executor = executor

    def is_cpu_layer(self, layer_id: int) -> bool:
        """Whether ``layer_id`` decodes on the CPU executor (vs the GPU offload path)."""
        return layer_id in self.cpu_layer_ids

    def is_unpinned_layer(self, layer_id: int) -> bool:
        """Whether ``layer_id``'s host banks have no device address (LOCKED/PAGEABLE): the GPU slot-gather paths cannot serve it.
        ``copy_missing`` takes the whole-layer pageable branch, which presumes materialize's position == expert id (never ``ensure_experts``'s LRU slot remap)."""
        return layer_id in self._unpinned_layers

    def alphas_for_slots(self, layer_id: int) -> tuple[torch.Tensor, torch.Tensor] | None:
        """Per-slot global scales for a decode call, or ``None`` when the format
        keeps no GPU-resident alphas (bf16 / triton-nvfp4). Slots of other layers
        yield garbage values, but only slots routed to -- and those belong to
        ``layer_id`` -- are ever read by the grouped GEMM."""
        if self.gate_up_alpha is None:
            return None
        idx = layer_id * self.num_experts + (
            self.id_of_slot.clamp(min=0).long() % self.num_experts
        )
        return self.gate_up_alpha[idx], self.down_alpha[idx]

    def alphas_for_layer(self, layer_id: int) -> tuple[torch.Tensor, torch.Tensor] | None:
        """Global scales for a full-layer prefill (overlap or materialize), where
        position == expert id (contiguous slices, no gather); ``None`` when the
        format keeps no GPU-resident alphas."""
        if self.gate_up_alpha is None:
            return None
        lo = layer_id * self.num_experts
        hi = lo + self.num_experts
        return self.gate_up_alpha[lo:hi], self.down_alpha[lo:hi]

    def bank_views(self, n: int | None = None) -> tuple[torch.Tensor, ...]:
        """Per-bank cache views in registration order: the full ``[S]`` slot cache
        (decode), or its first ``n`` slots (materialized layer)."""
        assert self.banks, "set_bank_sources must register the banks first"
        if n is None:
            return tuple(cache for _, cache in self.banks)
        return tuple(cache[:n] for _, cache in self.banks)

    def _init_prefill_overlap_buffers(self) -> None:
        assert self.banks, "set_bank_sources must register the banks first"
        self._prefill_buffer_layer = [None, None]
        self._prefill_buffer_released = [True, True]
        self._prefill_buffer_has_release_event = [False, False]
        # The double buffers borrow the slot cache's first 2 * num_experts slots
        # (one full expert layer per buffer), one view per registered bank.
        self.prefill_bank_buffers = [
            cache[: 2 * self.num_experts].view(2, self.num_experts, *cache.shape[1:])
            for _, cache in self.banks
        ]
        if self.device.type == "cuda":
            self.prefill_copy_stream = torch.cuda.Stream(device=self.device)
            self.prefill_ready_events = [torch.cuda.Event() for _ in range(2)]
            self.prefill_release_events = [torch.cuda.Event() for _ in range(2)]
            self.prefill_begin_event = torch.cuda.Event()
        if self.prefill_hit_d2d and self.device.type == "cuda":
            self._prefill_slot_snapshot = torch.empty(
                (self.num_layers, self.num_experts), dtype=torch.int32, pin_memory=True
            )
            self._prefill_snapshot_np = self._prefill_slot_snapshot.numpy()
            self._prefill_hit_dst = torch.empty(
                (self.num_experts,), dtype=torch.int32, device=self.device
            )
            self._prefill_hit_src = torch.empty(
                (self.num_experts,), dtype=torch.int32, device=self.device
            )
            self._prefill_hit_num = torch.zeros((1,), dtype=torch.int64, device=self.device)

    def _invalidate_prefill_buffer(self, buffer_id: int) -> None:
        slot_start = buffer_id * self.num_experts
        slot_end = slot_start + self.num_experts
        old_ids = self.id_of_slot[slot_start:slot_end]
        self.slot_for_id.view(-1)[old_ids[old_ids >= 0].long()] = -1
        old_ids.fill_(-1)
        # usage=0 makes these slots the oldest, so the argmin(usage) victim selection in
        # ensure_experts evicts them first.
        self.usage[slot_start:slot_end].zero_()

    def begin_prefill(self, batch=None) -> None:
        if not self.prefill_overlap:
            return
        self._prefill_buffer_layer = [None, None]
        self._prefill_buffer_released = [True, True]
        if self.prefill_copy_stream is not None:
            # Fence this prefill's copy-stream work behind everything already enqueued
            # on the compute stream. The release/ready events only order against the
            # *previous prefill*; under overlap scheduling a new prefill can be enqueued
            # while the preceding decode batch is still running, and that decode may
            # have loaded experts into the slots the buffers borrow -- without this
            # fence the first prefetch would stomp bytes a running GEMM is reading.
            self.prefill_begin_event.record(torch.cuda.current_stream(self.device))
            self.prefill_copy_stream.wait_event(self.prefill_begin_event)
        self._prefill_hit_d2d_active = self.prefill_hit_d2d and self._hit_d2d_usable()
        if self._prefill_hit_d2d_active:
            # The copy stream is fenced behind the previous decode, so the snapshot
            # observes its final slot map; one host sync per chunk, then per-layer
            # classification is pure host math.
            with torch.cuda.stream(self.prefill_copy_stream):
                self._prefill_slot_snapshot.copy_(self.slot_for_id, non_blocking=True)
            self.prefill_copy_stream.synchronize()

    def prefetch_prefill_layer(self, layer_id: int) -> None:
        if not self.prefill_overlap or layer_id >= self.num_layers:
            return
        if layer_id < 0:
            raise ValueError(f"Invalid prefill layer id: {layer_id}")

        assert self.banks and self.prefill_bank_buffers

        buffer_id = layer_id % 2
        if self._prefill_buffer_layer[buffer_id] == layer_id:
            return
        if self._prefill_buffer_layer[buffer_id] is not None:
            assert self._prefill_buffer_released[buffer_id], (
                "Prefill overlap buffer is being reused before release"
            )

        def copy() -> None:
            self._invalidate_prefill_buffer(buffer_id)
            for (per_layer, _), buffer in zip(self.banks, self.prefill_bank_buffers):
                buffer[buffer_id].copy_(per_layer[layer_id], non_blocking=True)

        if self._prefill_hit_d2d_active:
            self._prefetch_split(layer_id, buffer_id)
        elif self.prefill_copy_stream is None:
            if self._d0_prefill_active:
                _h2d_b, _ = self._d0_layer_bytes(0)
                self._d0_h2d += _h2d_b
                self._d0_pending[buffer_id] = {
                    "copy_start": torch.cuda.Event(enable_timing=True),
                }
                self._d0_pending[buffer_id]["copy_start"].record(
                    torch.cuda.current_stream(self.device)
                )
            copy()
        else:
            with torch.cuda.stream(self.prefill_copy_stream):
                if self._prefill_buffer_has_release_event[buffer_id]:
                    self.prefill_copy_stream.wait_event(self.prefill_release_events[buffer_id])
                if self._d0_prefill_active:
                    _h2d_b, _ = self._d0_layer_bytes(0)
                    self._d0_h2d += _h2d_b
                    self._d0_pending[buffer_id] = {
                        "copy_start": torch.cuda.Event(enable_timing=True),
                    }
                    self._d0_pending[buffer_id]["copy_start"].record(self.prefill_copy_stream)
                copy()
                self.prefill_ready_events[buffer_id].record(self.prefill_copy_stream)
                if self._d0_prefill_active:
                    self._d0_pending[buffer_id]["copy_end"] = torch.cuda.Event(enable_timing=True)
                    self._d0_pending[buffer_id]["copy_end"].record(self.prefill_copy_stream)

        self._prefill_buffer_layer[buffer_id] = layer_id
        self._prefill_buffer_released[buffer_id] = False

    def _hit_d2d_usable(self) -> bool:
        """Whether the hit-D2D split can serve this prefill; logs the first fallback.

        The flag is an auto-fallback optional: any unusable condition must degrade
        to the legacy full-layer copy AND say so once in the server log, so a
        configuration that silently runs the legacy path is visible.
        """
        from freetoken.kernel.fast_index_copy import _skip_fast_index_copy_enabled

        if self._prefill_slot_snapshot is None or self.prefill_copy_stream is None:
            reason = "prefill overlap buffers are not initialized for this device"
        elif _skip_fast_index_copy_enabled():
            reason = "FREETOKEN_SKIP_FAST_INDEX_COPY is set (the hit gather would be a no-op)"
        elif not self._copy_fused_ok:
            reason = "the fused copy plan is unavailable (bank alignment or FREETOKEN_FUSED_COPY=0)"
        elif self.cache_size <= 2 * self.num_experts:
            reason = (
                f"cache_size {self.cache_size} leaves no hit region "
                f"(needs > {2 * self.num_experts} slots)"
            )
        elif not self._resolve_batch_memcpy():
            reason = "cudaMemcpyBatchAsync is unavailable"  # resolve logged the specifics
        else:
            return True
        if not self._hit_d2d_fallback_logged:
            logger.warning(
                f"MoE prefill hit-D2D requested but unavailable ({reason}); "
                "falling back to full-layer copies"
            )
            self._hit_d2d_fallback_logged = True
        return False

    def _resolve_batch_memcpy(self) -> bool:
        if self._batch_memcpy is None:
            try:
                from freetoken.kernel.batch_memcpy import load_batch_memcpy

                self._batch_memcpy = load_batch_memcpy()
            except Exception as exc:  # noqa: BLE001 -- any build/runtime gap => legacy path
                logger.warning(f"MoE prefill hit-D2D disabled ({exc}); using full-layer copies")
                self._batch_memcpy = False
        return self._batch_memcpy is not False

    def _prefetch_split(self, layer_id: int, buffer_id: int) -> None:
        """Hit/miss-split prefetch of one expert layer into the double buffer.

        Resident experts are gathered cache -> buffer on the CURRENT stream, fully
        device-side: a one-launch compaction reads the LIVE slot_for_id row into
        fixed-shape gather indices (no host round trip), then fast_index_copy_multi
        moves the rows. Serializing the gather before this layer's GEMMs costs its
        plain duration instead of nondeterministic SM contention. Misses cross
        PCIe as ONE cudaMemcpyBatchAsync of coalesced expert-id runs on the copy
        stream, under the existing release/ready event discipline; its host-built
        run list comes from the begin-of-chunk snapshot because the batch API
        takes HOST pointer arrays. Live-vs-snapshot cannot disagree: the only
        chunk-internal writer (buffer invalidation) rewrites slots already below
        the 2E threshold, and slots < 2E (including -1) are misses on both sides
        -- the buffers own those slots, so their bytes are volatile within the
        chunk. Hit and miss row sets are disjoint, so the streams need no
        ordering against each other.
        """
        import numpy as np

        from freetoken.kernel.fast_index_copy import fast_index_copy_multi_jit
        from freetoken.moe.offload_kernels import prefill_hit_compact

        E = self.num_experts
        snap = self._prefill_snapshot_np[layer_id]
        hit_mask = snap >= 2 * E
        self.prefill_hit_rows += int(hit_mask.sum())
        self.prefill_total_rows += E
        if self._d0_prefill_active:
            _h2d_b, _d2d_b = self._d0_layer_bytes(int(hit_mask.sum()))
            self._d0_h2d += _h2d_b
            self._d0_d2d += _d2d_b
            self._d0_pending[buffer_id] = {
                "copy_start": torch.cuda.Event(enable_timing=True),
                "d2d_start": torch.cuda.Event(enable_timing=True),
            }
            self._d0_pending[buffer_id]["d2d_start"].record(
                torch.cuda.current_stream(self.device)
            )
        if self._gather_dst_ptrs is not None:
            prefill_hit_compact(self, layer_id, buffer_id)
            # blocks_per_bank=64 vs the PCIe-tuned default of 8: HBM D2D needs the
            # wider grid (~22 GB/s per 1024-thread block on H100).
            fast_index_copy_multi_jit(
                self._gather_dst_ptrs,
                self._gather_dst_ptrs,
                self._gather_feat_bytes,
                self._prefill_hit_dst,
                self._prefill_hit_src,
                self._prefill_hit_num,
                blocks_per_bank=64,
            )
            if self._d0_prefill_active:
                self._d0_pending[buffer_id]["d2d_end"] = torch.cuda.Event(enable_timing=True)
                self._d0_pending[buffer_id]["d2d_end"].record(
                    torch.cuda.current_stream(self.device)
                )
        miss = np.nonzero(~hit_mask)[0]
        with torch.cuda.stream(self.prefill_copy_stream):
            if self._prefill_buffer_has_release_event[buffer_id]:
                self.prefill_copy_stream.wait_event(self.prefill_release_events[buffer_id])
            if self._d0_prefill_active:
                self._d0_pending[buffer_id]["copy_start"].record(self.prefill_copy_stream)
            self._invalidate_prefill_buffer(buffer_id)
            if miss.size:
                run_starts = np.concatenate(([0], np.nonzero(np.diff(miss) != 1)[0] + 1))
                starts = miss[run_starts]
                lengths = np.diff(np.concatenate((run_starts, [miss.size])))
            dst, src, nbytes = [], [], []
            for b, feat in enumerate(self._copy_feat_bytes_host):
                if feat < _SMALL_BANK_FEAT_BYTES:
                    # Whole layer as one entry, EVEN with zero misses: it keeps every
                    # batch entry above the driver's async floor and covers the hit
                    # rows the gather skips for these banks.
                    dst.append(self._copy_dst_ptrs_host[b] + buffer_id * E * feat)
                    src.append(self._copy_src_ptrs_host[layer_id][b])
                    nbytes.append(E * feat)
                elif miss.size:
                    dst.extend(self._copy_dst_ptrs_host[b] + (buffer_id * E + starts) * feat)
                    src.extend(self._copy_src_ptrs_host[layer_id][b] + starts * feat)
                    nbytes.extend(lengths * feat)
            if dst:
                self._batch_memcpy(
                    torch.tensor(dst, dtype=torch.int64),
                    torch.tensor(src, dtype=torch.int64),
                    torch.tensor(nbytes, dtype=torch.int64),
                    torch.cuda.current_stream(self.device).cuda_stream,
                )
            self.prefill_ready_events[buffer_id].record(self.prefill_copy_stream)
            if self._d0_prefill_active:
                self._d0_pending[buffer_id]["copy_end"] = torch.cuda.Event(enable_timing=True)
                self._d0_pending[buffer_id]["copy_end"].record(self.prefill_copy_stream)

    def wait_prefill_layer(self, layer_id: int) -> tuple[torch.Tensor, ...]:
        """Full-layer ``[num_experts, ...]`` bank views for ``layer_id``, one per
        registered bank in registration order: bf16 ``(gate_up, down)``; nvfp4
        marlin/b12x ``(gate_up_packed, gate_up_scale, down_packed, down_scale)``;
        nvfp4 native adds the two global banks after each scale bank."""
        assert self.prefill_overlap
        assert self.prefill_bank_buffers
        self.prefetch_prefill_layer(layer_id)
        buffer_id = layer_id % 2
        assert self._prefill_buffer_layer[buffer_id] == layer_id
        if self.prefill_ready_events:
            torch.cuda.current_stream(self.device).wait_event(self.prefill_ready_events[buffer_id])
        if self._d0_prefill_active:
            self._d0_pending.setdefault(buffer_id, {})[
                "compute_start"
            ] = torch.cuda.Event(enable_timing=True)
            self._d0_pending[buffer_id]["compute_start"].record(
                torch.cuda.current_stream(self.device)
            )
        return tuple(buffer[buffer_id] for buffer in self.prefill_bank_buffers)

    def release_prefill_layer(self, layer_id: int) -> None:
        if not self.prefill_overlap:
            return
        buffer_id = layer_id % 2
        if self._prefill_buffer_layer[buffer_id] != layer_id:
            return
        if self._d0_prefill_active:
            compute_end = torch.cuda.Event(enable_timing=True)
            compute_end.record(torch.cuda.current_stream(self.device))
            # 事件完成与否取决于 GPU 进度：不在 release 时解析 elapsed（host 可能领先
            # GPU），只存事件对象，在本段 end_prefill 的 flush 统一解析。
            pend = self._d0_pending.pop(buffer_id, {})
            self._d0_layers.append({
                "layer": layer_id,
                "copy_start": pend.get("copy_start"),
                "copy_end": pend.get("copy_end"),
                "compute_start": pend.get("compute_start"),
                "compute_end": compute_end,
                "d2d_start": pend.get("d2d_start"),
                "d2d_end": pend.get("d2d_end"),
            })
        if self.prefill_release_events:
            self.prefill_release_events[buffer_id].record(torch.cuda.current_stream(self.device))
            self._prefill_buffer_has_release_event[buffer_id] = True
        self._prefill_buffer_released[buffer_id] = True

    def ensure_experts(self, layer_id: int, expert_ids: torch.Tensor) -> None:
        from freetoken.moe.offload_kernels import ensure_experts

        self.record_expert_policy_routes(layer_id, expert_ids)
        if self.collect_decode_freq:
            # ``expert_ids`` still holds raw expert ids here (the kernel rewrites them to
            # slot ids in place), so snapshot the routing histogram before that happens.
            ids = expert_ids.reshape(-1).long()
            self.decode_freq[layer_id].scatter_add_(0, ids, torch.ones_like(ids))
        self._pending_src_layer = layer_id
        self._pending_whole_layer = False
        self._mapping_generation += 1
        ensure_experts(self, layer_id, expert_ids)

    def ensure_experts_hybrid(self, layer_id: int, expert_ids: torch.Tensor) -> None:
        """Capped-fetch LRU for the hybrid backend.

        Like :meth:`ensure_experts` but assigns slots to (and schedules copies for) at
        most ``hybrid_max_fetch`` -- or ``~hybrid_fetch_fraction * misses`` when the
        fraction is set -- of this step's missing experts; the overflow misses are
        left non-resident and ``expert_ids`` is rewritten to their cache slot (hit or
        freshly fetched) or ``-1`` (overflow -> compute on the CPU). ``num_indices`` holds
        the capped fetch count (for ``copy_missing``); ``num_missing_full`` the pre-cap
        miss count (for stats). All device-side / fixed-shape, so it is CUDA-graph safe."""
        from freetoken.moe.offload_kernels import ensure_experts_hybrid

        if self.collect_decode_freq:
            ids = expert_ids.reshape(-1).long()
            self.decode_freq[layer_id].scatter_add_(0, ids, torch.ones_like(ids))
        self._pending_src_layer = layer_id
        self._pending_whole_layer = False
        self._mapping_generation += 1
        ensure_experts_hybrid(
            self, layer_id, expert_ids, self.hybrid_max_fetch, self.hybrid_fetch_fraction
        )

    def materialize_layer(self, layer_id: int) -> None:
        from freetoken.moe.offload_kernels import materialize_layer

        self._pending_src_layer = layer_id
        self._pending_whole_layer = True
        self._mapping_generation += 1
        materialize_layer(self, layer_id)

    def reset(self) -> None:
        from freetoken.moe.offload_kernels import reset_cache

        reset_cache(self)
        self._mapping_generation += 1
        # Per-expert recency is not cache_size-shaped, so reset_cache leaves it alone; wipe
        # it here so a new sequence starts with cold hybrid fetch priorities.
        self.expert_recency.fill_(-1)
        # A graph/warm-up reset is a cold cache; reapply only an explicitly enabled
        # startup profile.  The default LRU path remains exactly the reset kernel.
        if self.banks:
            self._initialize_expert_profile()

    def reset_stats(self) -> None:
        self.prefill_hit_rows = 0
        self.prefill_total_rows = 0
        self.lru_stats.zero_()
        self.stat_missing.zero_()
        self.stat_active.zero_()
        self.stat_calls.zero_()
        self.stat_fetched.zero_()
        self.stat_missing_layer.zero_()
        self.stat_active_layer.zero_()
        self.stat_fetched_layer.zero_()
        self.stat_steps_layer.zero_()
        self.policy_hits.zero_()
        self.policy_misses.zero_()
        self.policy_swap_bytes.zero_()
        self.policy_recent.zero_()

    def record_decode_stats(self, layer_id: int) -> None:
        """No-op: ``ensure_experts`` accumulates into ``lru_stats`` inside its own launch.

        Kept so the hybrid and non-hybrid call sites stay symmetric. The previous version
        was eight torch ops per layer per step, all captured into the decode graph.
        """

    def record_decode_stats_hybrid(self, layer_id: int) -> None:
        """Hybrid stats: full miss count (pre-cap), the PCIe-fetched count (capped), and
        the active count. The CPU computes (missing - fetched) experts. Device-side;
        accumulates both the scalar totals and the per-layer breakdown."""
        assert 0 <= layer_id < self.num_layers, f"layer_id {layer_id} out of range [0, {self.num_layers})"
        missing = self.num_missing_full.sum()
        fetched = self.num_indices.sum()
        active = self.active_mask.sum()
        self.stat_missing += missing
        self.stat_fetched += fetched
        self.stat_active += active
        self.stat_calls += 1
        self.stat_missing_layer[layer_id] += missing
        self.stat_fetched_layer[layer_id] += fetched
        self.stat_active_layer[layer_id] += active
        self.stat_steps_layer[layer_id] += 1

    def decode_miss_stats(self) -> dict:
        if self.decode_target == "hybrid":
            active = int(self.stat_active.item())
            missing = int(self.stat_missing.item())
            calls = int(self.stat_calls.item())
        else:
            active, missing, calls = (int(x) for x in self.lru_stats.sum(0))
        fetched = int(self.stat_fetched.item())
        return {
            "layer_calls": calls,
            "active_per_layer": (active / calls) if calls else 0.0,
            "missing_per_layer": (missing / calls) if calls else 0.0,
            "miss_rate": (missing / active) if active else 0.0,
            # hybrid: how the misses split between PCIe fetch (GPU) and CPU compute.
            "fetched_per_layer": (fetched / calls) if calls else 0.0,
            "cpu_per_layer": ((missing - fetched) / calls) if calls else 0.0,
            "fetch_rate": (fetched / missing) if missing else 0.0,
            # prefill hit-D2D split: expert rows served from the cache (D2D) vs all
            # rows prefetched into the double buffer since the last reset.
            "prefill_hit_rows": self.prefill_hit_rows,
            "prefill_rows": self.prefill_total_rows,
        }

    def decode_miss_stats_per_layer(self) -> dict:
        """Per-MoE-layer realized decode stats for one (reset_stats-delimited) window.

        Requires ``collect_stats`` and the call sites passing ``layer_id``. Returns python
        lists indexed by MoE-layer id: missing/active experts per step and the realized
        miss_rate (missing/active) -- i.e. how cacheable each layer's routing actually was
        under the running LRU. Reads device tensors once (no per-step host sync)."""
        if self.decode_target == "hybrid":
            steps = self.stat_steps_layer.tolist()
            missing = self.stat_missing_layer.tolist()
            active = self.stat_active_layer.tolist()
        else:
            cols = self.lru_stats.t().tolist()
            active, missing, steps = cols[Stat.ACTIVE], cols[Stat.MISS], cols[Stat.CALLS]
        fetched = self.stat_fetched_layer.tolist()
        per_layer = []
        for L in range(self.num_layers):
            s, m, a, f = steps[L], missing[L], active[L], fetched[L]
            per_layer.append({
                "layer": L,
                "steps": s,
                "active_per_step": (a / s) if s else 0.0,
                "missing_per_step": (m / s) if s else 0.0,
                "miss_rate": (m / a) if a else 0.0,
                "fetched_per_step": (f / s) if s else 0.0,
            })
        return {"per_layer": per_layer}

    def decode_routing_stats(self) -> dict:
        """Per-layer decode routing concentration, for cache-skew analysis.

        Uses the histogram from ``collect_decode_freq``. The ``oracle_hit`` is the best a
        per-layer LRU holding ``cache_size/num_layers`` slots could achieve on the observed
        (stationary) routing distribution -- i.e. an upper bound on hit rate that depends
        purely on how skewed routing is, independent of any LRU/LFU dynamics.
        """
        freq = self.decode_freq.float()
        total = freq.sum(dim=1)
        valid = total > 0
        if int(valid.sum()) == 0:
            return {}
        slots_per_layer = self.cache_size / self.num_layers
        C = max(1, int(round(slots_per_layer)))
        sorted_f, _ = torch.sort(freq, dim=1, descending=True)
        oracle_hit = (sorted_f[:, :C].sum(dim=1)[valid] / total[valid]).mean().item()
        ws = (freq > 0).sum(dim=1).float()
        cdf = torch.cumsum(sorted_f, dim=1) / total.clamp(min=1).unsqueeze(1)
        cover90 = ((cdf < 0.9).sum(dim=1).float() + 1)[valid]
        p = freq / total.clamp(min=1).unsqueeze(1)
        ent = -(p * p.clamp(min=1e-12).log()).sum(dim=1)[valid]
        norm_ent = (ent / torch.log(torch.tensor(float(self.num_experts)))).mean().item()
        return {
            "slots_per_layer": slots_per_layer,
            "working_set_mean": ws[valid].mean().item(),
            "working_set_max": int(ws[valid].max().item()),
            "experts_for_90pct": cover90.mean().item(),
            "oracle_hit_at_slots": oracle_hit,
            "norm_entropy": norm_ent,
        }

    def copy_missing(self) -> None:
        assert self.banks, "set_bank_sources must register the banks first"
        layer_id = self._pending_src_layer
        assert layer_id is not None, "no staged misses (ensure_experts/materialize_layer first)"
        if layer_id in self._unpinned_layers:
            if not self._pending_whole_layer:
                raise RuntimeError(
                    f"layer {layer_id} is unpinned: its only copy is the whole-layer "
                    f"pageable materialize (position == expert id); ensure_experts's "
                    f"LRU slot remap cannot be honored without a device alias"
                )
            # the only copy a non-pinned layer ever needs is the non-overlap prefill materialize, which schedules the whole layer into slots [0, num_experts) with position == expert id -- a plain synchronous pageable H2D copy
            # never CUDA-graph captured: prefill is not captured, and decode never reaches this branch (it routes to the CPU executor)
            for per_layer, cache in self.banks:
                cache[: self.num_experts].copy_(per_layer[layer_id])
            return
        if self._copy_fused_ok:
            from freetoken.kernel.fast_index_copy import fast_index_copy_multi_jit

            # One launch copies the missing rows for every bank (instead of one launch per
            # bank). evict_slots/src_indices/num_indices are shared across banks;
            # src_indices holds layer-local expert rows, resolved against this layer's
            # source pointers (layer_id is a static int per captured graph node).
            fast_index_copy_multi_jit(
                self._copy_dst_ptrs,
                self._copy_src_ptrs[layer_id],
                self._copy_feat_bytes,
                self.evict_slots,
                self.src_indices,
                self.num_indices,
            )
            return

        from freetoken.kernel import fast_index_copy_jit

        for per_layer, cache in self.banks:
            fast_index_copy_jit(
                cache,
                self.evict_slots,
                per_layer[layer_id],
                self.src_indices,
                self.num_indices,
            )


def iter_offload_moe_layers(model) -> Iterator:
    from freetoken.layers import BaseOP, OffloadMoELayer

    if isinstance(model, OffloadMoELayer):
        yield model

    if not isinstance(model, BaseOP):
        return

    for value in model.__dict__.values():
        if isinstance(value, BaseOP):
            yield from iter_offload_moe_layers(value)
        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from iter_offload_moe_layers(item)


def attach_offload_moe_cache(model, cache: OffloadMoeCache) -> list:
    layers = list(iter_offload_moe_layers(model))
    for layer in layers:
        layer.offload_cache = cache
    return layers
