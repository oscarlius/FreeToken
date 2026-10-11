"""Default-inert D10 eta GPU microbenchmark; no service or eager fallback."""
from __future__ import annotations
import argparse, hashlib, json, os, stat, statistics, sys
from dataclasses import dataclass
from pathlib import Path

EXPECTED_COMMIT = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"
COPIES = 367
REPETITIONS = 50
PROTECTED_GRAPH_SLOTS = 480
EXPECTED_INPUT_SHA = "f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162"
MIN_FREE_COPY_SLOTS = 2200
BYTES_PER_EXPERT = 2_772_480
EXPECTED_COPY_BYTES = COPIES * BYTES_PER_EXPERT
MAX_WARMUP_REPLAYS = 32
ADMISSION_SCHEMA = "ft_d08_d10_window_admission/v1"
CPU_REVIEW_SCHEMA = "eta_independent_cpu_review/v1"
ETA_RELATIVE_PATH = "development/d10_eta_20261010/eta_microbench.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_input_sha(path: Path) -> str:
    digest = sha256(path)
    if digest != EXPECTED_INPUT_SHA:
        raise RuntimeError(f"frozen X input SHA differs: {digest}")
    return digest


def split_server_argv(argv: list[str]) -> list[str]:
    """Return only arguments accepted by freetoken.server.args.parse_args."""
    try:
        return argv[argv.index("serve") + 1 :]
    except ValueError as exc:
        raise ValueError("baseline argv has no ft serve segment") from exc


def serve_index(argv: list[str]) -> int:
    try:
        index = argv.index("serve")
    except ValueError as exc:
        raise ValueError("baseline argv has no ft serve segment") from exc
    if index == 0 or argv[index - 1].startswith("-"):
        raise ValueError("baseline serve command lacks its executable")
    return index


def hybrid_argv(baseline: list[str]) -> list[str]:
    """The directive's two allowed change areas: CPU binding prefix and strategy."""
    server = split_server_argv(baseline)
    if server.count("--moe-strategy") != 1:
        raise ValueError("baseline must have exactly one --moe-strategy")
    value = server.index("--moe-strategy") + 1
    if server[value] != "offload":
        raise ValueError("baseline strategy is not offload")
    server[value] = "hybrid"
    # Replace only the old launcher prefix.  Keep both the actual ft executable and
    # the `serve` verb, so the draft is directly usable by Popen.
    return ["numactl", "--interleave=all", "taskset", "-c", "1,3-23,25,27-47", *baseline[serve_index(baseline) - 1 : serve_index(baseline) + 1], *server]


def allowed_hybrid_diff(baseline: list[str], candidate: list[str]) -> bool:
    expected = hybrid_argv(baseline)
    return candidate == expected


def choose_copy_slots(cache_size: int, occupied: list[int], copies: int = COPIES) -> list[int]:
    if cache_size <= 0 or copies <= 0:
        raise ValueError("invalid cache/copy geometry")
    used = set(occupied)
    slots = [slot for slot in range(cache_size) if slot not in used]
    if len(slots) < copies:
        raise RuntimeError("not enough graph-disjoint cache slots")
    return slots[-copies:]


def classify_eta(t_comp_ms: float, t_copy_ms: float, t_both_ms: float) -> dict:
    if min(t_comp_ms, t_copy_ms, t_both_ms) <= 0:
        raise ValueError("timings must be positive")
    copy_expected = 41.9
    comp_expected = 26.2
    deviations = {"t_comp": abs(t_comp_ms / comp_expected - 1), "t_copy": abs(t_copy_ms / copy_expected - 1)}
    if any(v > .20 for v in deviations.values()):
        return {"status": "REPORT_DEVIATION_BEFORE_ETA", "deviation": deviations}
    eta = (t_comp_ms + t_copy_ms - t_both_ms) / min(t_comp_ms, t_copy_ms)
    verdict = "CANDIDATE" if eta >= .8 else "CLOSE_D10" if eta < .5 else "INCONCLUSIVE"
    return {"status": "ETA_VALID", "eta": eta, "verdict": verdict, "deviation": deviations}


def _event_ms(torch, stream, fn):
    start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
    with torch.cuda.stream(stream):
        start.record(stream); fn(); end.record(stream)
    end.synchronize()
    return start.elapsed_time(end)


def _graph_slots(cache) -> list[int]:
    # id_of_slot is the engine's authoritative device-side slot map; one bounded host read
    # occurs only after graph warmup, never inside graph capture/replay timing.
    return [slot for slot, expert_id in enumerate(cache.id_of_slot.detach().cpu().tolist()) if int(expert_id) >= 0]


def _copy_bytes(cache) -> int:
    actual = sum(int(value) for value in cache._copy_feat_bytes_host)
    if actual != BYTES_PER_EXPERT:
        raise RuntimeError(f"copy bytes per expert {actual} != expected {BYTES_PER_EXPERT}")
    return actual * COPIES


def _set_fixed_bs1_graph_input(graph_runner, fixed_token: int) -> dict:
    """Write the bs=1 captured input buffer after Engine capture reset its cache.

    Direct `CUDAGraph.replay()` consumes these persistent buffers.  Set every bs=1
    input explicitly so a preceding bs=2 capture cannot leak its table/token state.
    """
    buffer = graph_runner.buffer
    if buffer is None or buffer.input_ids.numel() < 1 or buffer.table_idx.numel() < 1:
        raise RuntimeError("bs=1 graph capture buffer is unavailable")
    slot = graph_runner.dummy_req.linear_slot_idx
    if slot is None:
        raise RuntimeError("captured bs=1 graph has no linear-state table slot")
    buffer.input_ids[0].fill_(fixed_token)
    buffer.out_loc[0].zero_()
    buffer.positions[0].zero_()
    buffer.table_idx[0].fill_(slot)
    return {"graph_bs": 1, "fixed_token": fixed_token, "fixed_table_slot": int(slot)}


def _stats_snapshot(cache) -> list[dict]:
    rows = cache.decode_miss_stats_per_layer()["per_layer"]
    return [
        {"layer": int(row["layer"]), "steps": int(row["steps"]),
         "active": int(round(row["active_per_step"] * row["steps"])),
         "missing": int(round(row["missing_per_step"] * row["steps"]))}
        for row in rows
    ]


def _warm_graph_until_all_hit(torch, graph, cache) -> dict:
    """Warm the actual captured bs=1 graph and require zero new misses per layer."""
    if not cache.collect_stats:
        raise RuntimeError("--moe-collect-stats must be enabled before CUDA graph capture")
    cache.reset_stats()
    for replay in range(1, MAX_WARMUP_REPLAYS + 1):
        before = _stats_snapshot(cache)
        graph.replay()
        torch.cuda.synchronize()
        after = _stats_snapshot(cache)
        delta = [
            {"layer": next_row["layer"], "steps": next_row["steps"] - prior["steps"],
             "active": next_row["active"] - prior["active"],
             "missing": next_row["missing"] - prior["missing"]}
            for prior, next_row in zip(before, after, strict=True)
        ]
        if delta and all(row["steps"] > 0 and row["active"] >= 1 and row["missing"] == 0 for row in delta):
            return {"warmup_replays": replay, "all_layers_no_miss": True, "last_replay_per_layer": delta}
    raise RuntimeError("captured bs=1 graph did not reach all-layer no-miss state")


def _load_readonly_receipt(path: Path, label: str) -> tuple[dict, str]:
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o444:
        raise RuntimeError(f"{label} must be a regular receipt file")
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict) or not payload:
        raise RuntimeError(f"{label} is empty")
    return payload, sha256(path)


def _source_binding(payload: dict, label: str) -> None:
    script_sha = sha256(Path(__file__).resolve())
    source = payload.get("source_pins")
    measure = payload.get("measure")
    paths = payload.get("paths_hashes")
    if not isinstance(source, dict) or not isinstance(measure, dict) or not isinstance(paths, dict):
        raise RuntimeError(f"{label} lacks source_pins, measure, or paths_hashes")
    if source.get("candidate_commit") != EXPECTED_COMMIT or source.get("eta_sha256") != script_sha:
        raise RuntimeError(f"{label} source binding differs")
    if measure.get("eta_path") != ETA_RELATIVE_PATH or measure.get("input_x_sha256") != EXPECTED_INPUT_SHA:
        raise RuntimeError(f"{label} measure binding differs")
    if paths.get("eta_microbench.py") != script_sha or paths.get("inputs_X.jsonl") != EXPECTED_INPUT_SHA:
        raise RuntimeError(f"{label} paths_hashes binding differs")


def validate_admission(path: Path) -> str:
    payload, digest = _load_readonly_receipt(path, "sealed admission")
    if payload.get("schema") != ADMISSION_SCHEMA or payload.get("admit") is not True:
        raise RuntimeError("sealed admission schema or admit flag differs")
    _source_binding(payload, "sealed admission")
    return digest


def validate_cpu_review(path: Path) -> str:
    payload, digest = _load_readonly_receipt(path, "controller CPU review")
    if payload.get("schema") != CPU_REVIEW_SCHEMA or payload.get("status") != "PASS":
        raise RuntimeError("controller CPU review schema or status differs")
    _source_binding(payload, "controller CPU review")
    return digest


def _require_independent_worktree(worktree: Path) -> None:
    # A linked worktree has a .git file; the release checkout's .git directory is
    # deliberately refused, even when it happens to be at the right commit.
    if not (worktree / ".git").is_file():
        raise RuntimeError("worktree must be an independent linked git worktree, not the release tree")


def _assert_map_unchanged(before, cache) -> None:
    import torch
    if not torch.equal(before[0], cache.slot_for_id) or not torch.equal(before[1], cache.id_of_slot):
        raise RuntimeError("copy altered cache mapping tables")


def run_gpu(worktree: Path, baseline: list[str], fixed_token: int, admission_sha: str, controller_review_sha: str) -> dict:
    """Load exactly one real 481 Engine; benchmark only captured bs=1 graph replays."""
    _require_independent_worktree(worktree)
    import subprocess
    commit = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip()
    if commit != EXPECTED_COMMIT:
        raise RuntimeError(f"worktree commit differs: {commit}")
    sys.path.insert(0, str(worktree / "python"))
    import torch
    from freetoken.engine import Engine
    from freetoken.kernel.fast_index_copy import fast_index_copy_multi_jit
    from freetoken.server.args import parse_args
    engine_argv = split_server_argv(baseline)
    if "--moe-collect-stats" not in engine_argv:
        engine_argv.append("--moe-collect-stats")
    config, _ = parse_args(engine_argv)
    if config.moe_strategy != "offload":
        raise RuntimeError("eta engine must use offload baseline")
    engine = Engine(config)
    graph = engine.graph_runner.graph_map.get(1)
    cache = engine.moe_offload_cache
    if graph is None or cache is None or not cache._copy_fused_ok or not cache._copy_src_ptrs:
        raise RuntimeError("actual bs=1 CUDA graph or fused pinned-bank copy unavailable")
    fixed_graph_input = _set_fixed_bs1_graph_input(engine.graph_runner, fixed_token)
    # GraphRunner resets the offload cache after capture.  Only the fixed bs=1
    # captured graph may warm it; do not substitute eager forwards or route tracing.
    with torch.cuda.stream(engine.stream):
        warmup = _warm_graph_until_all_hit(torch, graph, cache)
    torch.cuda.synchronize(engine.device)
    occupied = _graph_slots(cache)
    free_slots = cache.cache_size - len(occupied)
    if free_slots < MIN_FREE_COPY_SLOTS:
        raise RuntimeError(f"free copy slots {free_slots} < required {MIN_FREE_COPY_SLOTS}")
    dst_slots = choose_copy_slots(cache.cache_size, occupied)
    if set(dst_slots) & set(occupied):
        raise RuntimeError("copy destination overlaps graph-used slot")
    dst = torch.tensor(dst_slots, device=engine.device, dtype=torch.int32)
    src = torch.arange(COPIES, device=engine.device, dtype=torch.int32) % cache.num_experts
    count = torch.tensor([COPIES], device=engine.device, dtype=torch.int64)
    copy_stream = torch.cuda.Stream(device=engine.device)
    copy_total_bytes = _copy_bytes(cache)
    def replay_twice(): graph.replay(); graph.replay()
    def copy_rows(): fast_index_copy_multi_jit(cache._copy_dst_ptrs, cache._copy_src_ptrs[0], cache._copy_feat_bytes, dst, src, count)
    maps = (cache.slot_for_id.clone(), cache.id_of_slot.clone())
    comp = [_event_ms(torch, engine.stream, replay_twice) for _ in range(REPETITIONS)]
    copied = [_event_ms(torch, copy_stream, copy_rows) for _ in range(REPETITIONS)]
    _assert_map_unchanged(maps, cache)
    both, comp_in_both = [], []
    for _ in range(REPETITIONS):
        join = torch.cuda.current_stream(engine.device)
        common, c0, c1, x0, x1, done = (torch.cuda.Event(enable_timing=True) for _ in range(6))
        common.record(join)
        with torch.cuda.stream(engine.stream):
            engine.stream.wait_event(common); c0.record(engine.stream); replay_twice(); c1.record(engine.stream)
        with torch.cuda.stream(copy_stream):
            copy_stream.wait_event(common); x0.record(copy_stream); copy_rows(); x1.record(copy_stream)
        join.wait_event(c1); join.wait_event(x1); done.record(join); done.synchronize()
        both.append(common.elapsed_time(done)); comp_in_both.append(c0.elapsed_time(c1))
    _assert_map_unchanged(maps, cache)
    t_comp, t_copy, t_both = map(statistics.median, (comp, copied, both))
    result = {"engine_commit": commit, "repetitions": REPETITIONS, "copies": COPIES, "graph_bs": 1,
              "fixed_graph_input": fixed_graph_input, "all_hit_warmup": warmup,
              "sealed_admission_sha256": admission_sha, "controller_cpu_review_sha256": controller_review_sha,
              "copy_slots": dst_slots, "graph_occupied_slots": occupied, "free_copy_slots": free_slots,
              "copy_bytes_per_expert": copy_total_bytes // COPIES, "copy_bytes_total": copy_total_bytes,
              "t_comp_ms_median": t_comp,
              "t_copy_ms_median": t_copy, "t_both_ms_median": t_both,
              "t_comp_in_both_ms_median": statistics.median(comp_in_both),
              "compute_slowdown_percent": (statistics.median(comp_in_both) / t_comp - 1.0) * 100.0,
              "maps_unchanged": True}
    result.update(classify_eta(t_comp, t_copy, t_both))
    return result


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--baseline-owner", type=Path)
    p.add_argument("--write-hybrid-draft", type=Path)
    p.add_argument("--parser-check", action="store_true")
    p.add_argument("--input-x", type=Path)
    p.add_argument("--write-preflight", type=Path)
    p.add_argument("--worktree", type=Path)
    p.add_argument("--fixed-token", type=int)
    p.add_argument("--sealed-admission", type=Path)
    p.add_argument("--controller-cpu-review", type=Path)
    p.add_argument("--run-gpu", action="store_true")
    p.add_argument("--out", type=Path)
    a = p.parse_args(argv)
    if not a.baseline_owner:
        p.error("--baseline-owner is required")
    owner = json.loads(a.baseline_owner.read_text())
    baseline = owner["argv"]
    hybrid = hybrid_argv(baseline)
    if a.write_hybrid_draft:
        a.write_hybrid_draft.write_text(json.dumps({"baseline_owner_sha256": sha256(a.baseline_owner), "baseline_argv": baseline, "hybrid_argv": hybrid,
          "allowed_change_areas": ["binding prefix", "--moe-strategy offload -> hybrid"],
          "input_sha256": "f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162"}, indent=2)+"\n")
    cfg = None
    input_sha = validate_input_sha(a.input_x) if a.input_x else None
    if a.parser_check:
        if not a.worktree: p.error("--parser-check requires --worktree")
        sys.path.insert(0, str(a.worktree / "python"))
        from freetoken.server.args import parse_args
        cfg, _ = parse_args(split_server_argv(hybrid))
        if cfg.moe_strategy != "hybrid": raise RuntimeError("hybrid parser parity failed")
    if a.write_preflight:
        if cfg is None or input_sha is None or not a.worktree:
            p.error("--write-preflight requires --parser-check, --input-x, and --worktree")
        engine_source = a.worktree / "python/freetoken/engine/engine.py"
        args_source = a.worktree / "python/freetoken/server/args.py"
        text = engine_source.read_text(encoding="utf8")
        if "hybrid_max_fetch" not in text or "rest on the CPU" not in text:
            raise RuntimeError("release source lacks hybrid max-fetch semantics")
        a.write_preflight.write_text(json.dumps({"source_commit": EXPECTED_COMMIT, "input_x_sha256": input_sha,
          "parser_moe_strategy": cfg.moe_strategy, "parser_moe_hybrid_max_fetch": cfg.moe_hybrid_max_fetch,
          "engine_source_sha256": sha256(engine_source), "args_source_sha256": sha256(args_source),
          "max_fetch_semantics": "per layer/decode step PCIe cap; remaining misses compute on CPU; -1 auto resolves bandwidth fraction or falls back to one"}, indent=2)+"\n")
    if a.run_gpu:
        if not a.worktree or not a.out or a.input_x is None or a.fixed_token is None:
            p.error("--run-gpu requires --worktree, --out, --input-x, and --fixed-token")
        if a.sealed_admission is None or a.controller_cpu_review is None:
            p.error("--run-gpu requires --sealed-admission and --controller-cpu-review")
        admission_sha = validate_admission(a.sealed_admission)
        controller_review_sha = validate_cpu_review(a.controller_cpu_review)
        validate_input_sha(a.input_x)
        a.out.write_text(json.dumps(run_gpu(a.worktree, baseline, a.fixed_token, admission_sha, controller_review_sha), indent=2)+"\n")

if __name__ == "__main__": main()
