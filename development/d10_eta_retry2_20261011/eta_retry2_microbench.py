"""Default-inert D10 eta retry2 microbenchmark; graph/cache route proof, no services."""
from __future__ import annotations
import argparse
import hashlib
import json
import stat
import statistics
import subprocess
import sys
from contextlib import AbstractContextManager
from pathlib import Path

EXPECTED_COMMIT = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"
EXPECTED_INPUT_SHA = "f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162"
ETA_RELATIVE_PATH = "development/d10_eta_retry2_20261011/eta_retry2_microbench.py"
ADMISSION_SCHEMA = "ft_d08_d10_eta_retry2_admission/v1"
CPU_REVIEW_SCHEMA = "eta_retry2_independent_cpu_review/v1"
COPIES = 367
LAYERS = 48
REPETITIONS = 50
MIN_FREE_COPY_SLOTS = 2200
BYTES_PER_EXPERT = 2_772_480
MAX_WARMUP_REPLAYS = 32


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split_server_argv(argv: list[str]) -> list[str]:
    try:
        return argv[argv.index("serve") + 1:]
    except ValueError as exc:
        raise ValueError("baseline argv has no ft serve segment") from exc


def final_engine_argv(baseline: list[str]) -> list[str]:
    """Exact Engine parser argv: frozen offload baseline, with no η-only CLI flags."""
    argv = split_server_argv(baseline)
    if "--moe-collect-stats" in argv:
        raise RuntimeError("retry2 forbids --moe-collect-stats")
    return argv


def copy_budget(num_layers: int) -> list[int]:
    if num_layers != LAYERS:
        raise RuntimeError(f"expected {LAYERS} MoE layers, got {num_layers}")
    base, remainder = divmod(COPIES, num_layers)
    budget = [base + (1 if layer < remainder else 0) for layer in range(num_layers)]
    if set(budget) - {7, 8} or sum(budget) != COPIES:
        raise RuntimeError("copy budget must be 48 layers of 7/8 rows totaling 367")
    return budget


def choose_copy_slots(cache_size: int, occupied: list[int]) -> list[int]:
    free = [slot for slot in range(cache_size) if slot not in set(occupied)]
    if len(free) < MIN_FREE_COPY_SLOTS or len(free) < COPIES:
        raise RuntimeError("insufficient graph-disjoint cache slots")
    return free[-COPIES:]


def graph_slots(cache) -> list[int]:
    return [slot for slot, expert_id in enumerate(cache.id_of_slot.detach().cpu().tolist()) if int(expert_id) >= 0]


def copy_bytes(cache) -> int:
    actual = sum(int(value) for value in cache._copy_feat_bytes_host)
    if actual != BYTES_PER_EXPERT:
        raise RuntimeError(f"copy row bytes {actual} != {BYTES_PER_EXPERT}")
    return actual * COPIES


def map_snapshot(cache):
    return cache.slot_for_id.clone(), cache.id_of_slot.clone()


def maps_equal(torch, before, after) -> bool:
    return torch.equal(before[0], after[0]) and torch.equal(before[1], after[1])


class CapturedGraphRoutes(AbstractContextManager):
    """Retain the actual ``topk_ids`` tensors allocated during the final bs=1 capture.

    ``ensure_experts`` is executed by Python while a graph is captured, then its input
    tensor becomes a static graph allocation.  A later replay overwrites that same
    tensor with the slot ids it actually consumes.  This records that allocation;
    it does not enable decode statistics or D0 instrumentation.
    """

    def __init__(self, torch):
        self.torch = torch
        self._original = None
        self._current: dict[int, object] = {}
        self.last_complete: dict[int, object] = {}
        self.capture_cycles = 0

    def __enter__(self):
        from freetoken.moe.offload_cache import OffloadMoeCache

        self._original = OffloadMoeCache.ensure_experts

        def traced(cache, layer_id, expert_ids):
            result = self._original(cache, layer_id, expert_ids)
            if self.torch.cuda.is_current_stream_capturing():
                # Captures are complete ordered sweeps of the 48 MoE layers.  GraphRunner
                # captures bs in descending order, so the final complete sweep is bs=1.
                if layer_id in self._current:
                    self._finish_cycle()
                self._current[layer_id] = expert_ids
            return result

        OffloadMoeCache.ensure_experts = traced
        return self

    def _finish_cycle(self):
        if set(self._current) == set(range(LAYERS)):
            self.last_complete = dict(self._current)
            self.capture_cycles += 1
        self._current = {}

    def finish(self) -> dict[int, object]:
        self._finish_cycle()
        if set(self.last_complete) != set(range(LAYERS)):
            raise RuntimeError("did not retain a complete bs=1 CUDA-graph route-buffer sweep")
        if any(len(getattr(tensor, "shape", ())) != 2 or int(tensor.shape[0]) != 1
               for tensor in self.last_complete.values()):
            raise RuntimeError("final graph route-buffer sweep is not bs=1")
        return self.last_complete

    def __exit__(self, exc_type, exc, traceback):
        from freetoken.moe.offload_cache import OffloadMoeCache

        OffloadMoeCache.ensure_experts = self._original
        return False


def _flat_values(tensor) -> list[int]:
    return [int(value) for value in tensor.detach().reshape(-1).cpu().tolist()]


def prove_graph_route_residency(route_buffers: dict[int, object], cache) -> tuple[set[int], list[dict]]:
    """Prove live bs=1 graph route slots resolve through this cache's resident map.

    The graph writes slot ids in-place after each layer's router selects raw expert ids.
    ``id_of_slot`` recovers that actual raw id and ``slot_for_id`` must map it back to
    the same live slot.  A static occupancy scan alone is deliberately insufficient.
    """
    if set(route_buffers) != set(range(LAYERS)):
        raise RuntimeError("route buffers do not cover all 48 graph MoE layers")
    for layer_id, tensor in route_buffers.items():
        device = getattr(tensor, "device", None)
        if device is None or getattr(device, "type", None) != "cuda":
            raise RuntimeError(f"layer {layer_id} route buffer is not a captured CUDA tensor")
    all_slots: set[int] = set()
    evidence: list[dict] = []
    cache_size, num_experts = int(cache.cache_size), int(cache.num_experts)
    data_ptrs: set[int] = set()
    for layer_id in range(LAYERS):
        tensor = route_buffers[layer_id]
        slots = _flat_values(tensor)
        if not slots:
            raise RuntimeError(f"layer {layer_id} captured route buffer is empty")
        data_ptr = int(tensor.data_ptr())
        if data_ptr in data_ptrs:
            raise RuntimeError(f"layer {layer_id} route buffer aliases another layer buffer")
        data_ptrs.add(data_ptr)
        raw_ids: list[int] = []
        for slot in slots:
            if slot < 0 or slot >= cache_size:
                raise RuntimeError(f"layer {layer_id} graph route has invalid/nonresident slot {slot}")
            global_id = int(cache.id_of_slot[slot].item())
            if global_id < 0 or global_id // num_experts != layer_id:
                raise RuntimeError(f"layer {layer_id} graph route slot {slot} has wrong resident expert")
            raw_id = global_id % num_experts
            if int(cache.slot_for_id[layer_id, raw_id].item()) != slot:
                raise RuntimeError(f"layer {layer_id} route id {raw_id} no longer resolves to slot {slot}")
            raw_ids.append(raw_id)
            all_slots.add(slot)
        evidence.append({
            "layer_id": layer_id,
            "buffer_data_ptr": data_ptr,
            "buffer_shape": list(tensor.shape),
            "route_slots": sorted(set(slots)),
            "routed_expert_ids": sorted(set(raw_ids)),
        })
    return all_slots, evidence


def validate_copy_targets(cache, destinations: list[int], graph_route_slots: set[int]) -> None:
    if set(destinations) & graph_route_slots:
        raise RuntimeError("copy targets overlap graph-routed resident slots")
    if any(int(cache.id_of_slot[slot].item()) >= 0 for slot in destinations):
        raise RuntimeError("copy targets are not physically free cache slots")


def set_fixed_bs1_graph_input(graph_runner, fixed_token: int) -> dict:
    buffer = graph_runner.buffer
    if buffer is None or buffer.input_ids.numel() < 1 or buffer.table_idx.numel() < 1:
        raise RuntimeError("bs=1 graph capture buffer unavailable")
    slot = graph_runner.dummy_req.linear_slot_idx
    if slot is None:
        raise RuntimeError("bs=1 graph has no live linear-state slot")
    buffer.input_ids[0].fill_(fixed_token)
    buffer.out_loc[0].zero_()
    buffer.positions[0].zero_()
    buffer.table_idx[0].fill_(slot)
    return {"graph_bs": 1, "fixed_token": fixed_token, "fixed_table_slot": int(slot)}


def warm_until_stable_cache(torch, graph, cache) -> dict:
    """Use the existing LRU map state as the no-miss proof; no stats/D0 instrumentation."""
    for replay in range(1, MAX_WARMUP_REPLAYS + 1):
        before = map_snapshot(cache)
        graph.replay()
        torch.cuda.synchronize()
        after = map_snapshot(cache)
        if maps_equal(torch, before, after):
            return {"warmup_replays": replay, "route": "actual_bs1_cuda_graph", "map_state_unchanged": True,
                    "occupied_slots": len(graph_slots(cache))}
    raise RuntimeError("actual bs=1 graph never reached stable cache-map state")


def classify_eta(t_comp_ms: float, t_copy_ms: float, t_both_ms: float) -> dict:
    if min(t_comp_ms, t_copy_ms, t_both_ms) <= 0:
        raise ValueError("timings must be positive")
    eta = (t_comp_ms + t_copy_ms - t_both_ms) / min(t_comp_ms, t_copy_ms)
    deviation = {"t_comp": abs(t_comp_ms / 26.2 - 1.0), "t_copy": abs(t_copy_ms / 41.9 - 1.0)}
    verdict = "CANDIDATE" if eta >= .8 else "CLOSE_D10" if eta < .5 else "INCONCLUSIVE"
    denominator_ms = t_copy_ms + t_comp_ms - eta * min(t_copy_ms, t_comp_ms)
    if denominator_ms <= 0:
        raise RuntimeError("measured bound denominator is not positive")
    return {"eta": eta, "verdict": verdict, "deviation": deviation,
            "deviation_exceeded": any(value > .20 for value in deviation.values()),
            "measured_bound_tok_s": 1000.0 / denominator_ms}


def event_ms(torch, stream, fn) -> float:
    start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    with torch.cuda.stream(stream):
        start.record(stream); fn(); end.record(stream)
    end.synchronize()
    return start.elapsed_time(end)


def require_independent_worktree(worktree: Path) -> None:
    if not (worktree / ".git").is_file():
        raise RuntimeError("worktree must be an independent linked worktree")


def parse_final_engine_argv(worktree: Path, baseline: list[str]) -> dict:
    require_independent_worktree(worktree)
    commit = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip()
    if commit != EXPECTED_COMMIT:
        raise RuntimeError(f"worktree commit differs: {commit}")
    sys.path.insert(0, str(worktree / "python"))
    from freetoken.server.args import parse_args
    config, _ = parse_args(final_engine_argv(baseline))
    if config.moe_strategy != "offload":
        raise RuntimeError("eta must parse the frozen offload baseline")
    return {"commit": commit, "argv": final_engine_argv(baseline), "moe_strategy": config.moe_strategy}


def load_readonly_receipt(path: Path, label: str) -> tuple[dict, str]:
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o444:
        raise RuntimeError(f"{label} must be a regular mode-0444 receipt")
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label} must be an object")
    return payload, sha256(path)


def validate_binding(payload: dict, label: str) -> None:
    script_sha = sha256(Path(__file__).resolve())
    source, measure, paths = payload.get("source_pins"), payload.get("measure"), payload.get("paths_hashes")
    if not all(isinstance(value, dict) for value in (source, measure, paths)):
        raise RuntimeError(f"{label} lacks binding objects")
    if source.get("candidate_commit") != EXPECTED_COMMIT or source.get("eta_sha256") != script_sha:
        raise RuntimeError(f"{label} source binding differs")
    if measure.get("eta_path") != ETA_RELATIVE_PATH or measure.get("input_x_sha256") != EXPECTED_INPUT_SHA:
        raise RuntimeError(f"{label} measure binding differs")
    if paths.get("eta_retry2_microbench.py") != script_sha or paths.get("inputs_X.jsonl") != EXPECTED_INPUT_SHA:
        raise RuntimeError(f"{label} paths binding differs")


def validate_admission(path: Path) -> str:
    payload, digest = load_readonly_receipt(path, "sealed admission")
    if payload.get("schema") != ADMISSION_SCHEMA or payload.get("admit") is not True:
        raise RuntimeError("sealed admission schema/admit differs")
    validate_binding(payload, "sealed admission")
    return digest


def validate_cpu_review(path: Path) -> str:
    payload, digest = load_readonly_receipt(path, "independent CPU review")
    if payload.get("schema") != CPU_REVIEW_SCHEMA or payload.get("status") != "PASS":
        raise RuntimeError("independent CPU review schema/status differs")
    validate_binding(payload, "independent CPU review")
    return digest


def run_gpu(worktree: Path, baseline: list[str], fixed_token: int, admission_sha: str, review_sha: str) -> dict:
    """The sole GPU path. It is never called unless --run-gpu is supplied."""
    parsed = parse_final_engine_argv(worktree, baseline)
    import torch
    from freetoken.engine import Engine
    from freetoken.kernel.fast_index_copy import fast_index_copy_multi_jit
    from freetoken.server.args import parse_args

    config, _ = parse_args(final_engine_argv(baseline))
    # Install only while Engine captures graphs.  The retained tensors are the actual
    # bs=1 graph's per-layer route outputs, not a cache descriptor or D0/stats stream.
    with CapturedGraphRoutes(torch) as captured_routes:
        engine = Engine(config)
        route_buffers = captured_routes.finish()
    graph = engine.graph_runner.graph_map.get(1)
    cache = engine.moe_offload_cache
    if graph is None or cache is None or not cache._copy_fused_ok or not cache._copy_src_ptrs:
        raise RuntimeError("actual bs=1 graph or fused real-host-bank copy is unavailable")
    if len(cache._copy_src_ptrs) != LAYERS:
        raise RuntimeError("actual source-bank layer count differs")
    fixed_graph_input = set_fixed_bs1_graph_input(engine.graph_runner, fixed_token)
    with torch.cuda.stream(engine.stream):
        warmup = warm_until_stable_cache(torch, graph, cache)
    torch.cuda.synchronize(engine.device)
    graph_route_slots, graph_route_evidence = prove_graph_route_residency(route_buffers, cache)
    occupied = graph_slots(cache)
    destinations = choose_copy_slots(cache.cache_size, occupied)
    validate_copy_targets(cache, destinations, graph_route_slots)
    bytes_total = copy_bytes(cache)
    layer_budget = copy_budget(len(cache._copy_src_ptrs))
    copy_stream = torch.cuda.Stream(device=engine.device)
    count_cache: dict[int, object] = {}
    dst_parts, src_parts = [], []
    offset = 0
    for layer_id, rows in enumerate(layer_budget):
        dst_parts.append(torch.tensor(destinations[offset: offset + rows], device=engine.device, dtype=torch.int32))
        # Rows are read from this exact layer's pinned host-bank descriptor.  They
        # are data-only copies; no cache map is ever passed to the copy kernel.
        src_parts.append(torch.arange(rows, device=engine.device, dtype=torch.int32) % cache.num_experts)
        count_cache[rows] = torch.tensor([rows], device=engine.device, dtype=torch.int64)
        offset += rows
    if offset != COPIES:
        raise RuntimeError("copy partition does not total 367 rows")

    def copy_all_layers():
        for layer_id, rows in enumerate(layer_budget):
            fast_index_copy_multi_jit(
                cache._copy_dst_ptrs, cache._copy_src_ptrs[layer_id], cache._copy_feat_bytes,
                dst_parts[layer_id], src_parts[layer_id], count_cache[rows],
            )

    def replay_twice():
        graph.replay(); graph.replay()

    maps_before = map_snapshot(cache)
    comp = [event_ms(torch, engine.stream, replay_twice) for _ in range(REPETITIONS)]
    copied = [event_ms(torch, copy_stream, copy_all_layers) for _ in range(REPETITIONS)]
    if not maps_equal(torch, maps_before, map_snapshot(cache)):
        raise RuntimeError("separate timing altered cache maps")
    both, comp_in_both = [], []
    for _ in range(REPETITIONS):
        join = torch.cuda.current_stream(engine.device)
        common, c0, c1, x1, done = (torch.cuda.Event(enable_timing=True) for _ in range(5))
        common.record(join)
        with torch.cuda.stream(engine.stream):
            engine.stream.wait_event(common); c0.record(engine.stream); replay_twice(); c1.record(engine.stream)
        with torch.cuda.stream(copy_stream):
            copy_stream.wait_event(common); copy_all_layers()
            x1.record(copy_stream)
        join.wait_event(c1); join.wait_event(x1); done.record(join); done.synchronize()
        both.append(common.elapsed_time(done)); comp_in_both.append(c0.elapsed_time(c1))
    if not maps_equal(torch, maps_before, map_snapshot(cache)):
        raise RuntimeError("concurrent timing altered cache maps")
    t_comp, t_copy, t_both = map(statistics.median, (comp, copied, both))
    result = {
        "engine_commit": parsed["commit"], "repetitions": REPETITIONS, "graph_bs": 1,
        "fixed_graph_input": fixed_graph_input, "warmup": warmup,
        "graph_route_proof": {
            "capture_cycles": captured_routes.capture_cycles,
            "route": "actual_bs1_cuda_graph_captured_topk_buffers",
            "all_layers_resident": True,
            "graph_routed_slots": sorted(graph_route_slots),
            "layers": graph_route_evidence,
        },
        "sealed_admission_sha256": admission_sha, "cpu_review_sha256": review_sha,
        "copy_calls": LAYERS, "copy_rows_per_layer": layer_budget, "copy_rows_total": sum(layer_budget),
        "copy_bytes_per_expert": bytes_total // COPIES, "copy_bytes_total": bytes_total,
        "graph_occupied_slots": occupied, "copy_slots": destinations,
        "free_copy_slots": cache.cache_size - len(occupied), "maps_unchanged": True,
        "t_comp_ms_median": t_comp, "t_copy_ms_median": t_copy, "t_both_ms_median": t_both,
        "t_comp_in_both_ms_median": statistics.median(comp_in_both),
        "compute_slowdown_percent": (statistics.median(comp_in_both) / t_comp - 1.0) * 100.0,
    }
    result.update(classify_eta(t_comp, t_copy, t_both))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-owner", type=Path, required=True)
    parser.add_argument("--worktree", type=Path)
    parser.add_argument("--parser-check", action="store_true")
    parser.add_argument("--sealed-admission", type=Path)
    parser.add_argument("--cpu-review", type=Path)
    parser.add_argument("--input-x", type=Path)
    parser.add_argument("--fixed-token", type=int)
    parser.add_argument("--run-gpu", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    baseline = json.loads(args.baseline_owner.read_text(encoding="utf8"))["argv"]
    if args.parser_check:
        if not args.worktree:
            parser.error("--parser-check requires --worktree")
        print(json.dumps(parse_final_engine_argv(args.worktree, baseline), sort_keys=True))
    if args.run_gpu:
        if not all((args.worktree, args.sealed_admission, args.cpu_review, args.input_x, args.out)) or args.fixed_token is None:
            parser.error("--run-gpu requires worktree, receipts, input-x, fixed-token, and out")
        if sha256(args.input_x) != EXPECTED_INPUT_SHA:
            raise RuntimeError("frozen X input SHA differs")
        admission_sha, review_sha = validate_admission(args.sealed_admission), validate_cpu_review(args.cpu_review)
        args.out.write_text(json.dumps(run_gpu(args.worktree, baseline, args.fixed_token, admission_sha, review_sha), indent=2)+"\n")

if __name__ == "__main__":
    main()
