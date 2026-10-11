"""CPU-only prediction gate for the R015 controlled T04 boundary capture.

This is deliberately not a model or GPU proof.  It calls the runtime scheduler's
``PrefillAdder._add_one_req`` and the runtime linear metadata builder on CPU, using
the frozen R015 token source and the actual branch recipe.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

EXPECTED_INPUT_SHA256 = "69e77aafa80b49a0f6a6e4898a2ce1e7265a58e4066860df71901762da93474d"
EXPECTED_GEOMETRY_SHA256 = "dddee68b5b3a8e308ac7f2446cce71f381b14a21d1ea83366b033578a2a27549"
PARENT_COMMIT = "c30ae0d7003c3bbbf56867ce74da797332fa7ed5"
PREFILL_SHA256 = "71f93be121edd17235654cfb2cc731c81ac8600396283fee892eb6345d6f12ce"
LINEAR_SHA256 = "34a4ad296724659825fb31afa6ea857034d3fb24127e82dd653896e638d9c4a1"
PAGE_SIZE = 64
MAX_EXTEND = 4096
RESTORE_LEN = 12672
ANCHORS = frozenset((248069, 248046, 248058))
EXPECTED = {
    "Y96": {"length": 12768, "chunks": [0, 512, 4608, 8704, 12480, 12768], "archives": [448, 4544, 8640, 12416]},
    "Y122": {"length": 12794, "chunks": [0, 512, 4608, 8704, 12672, 12794], "archives": [448, 4544, 8640, 12608]},
    "Y129": {"length": 12801, "chunks": [0, 512, 4608, 8704, 12736, 12801], "archives": [448, 4544, 8640, 12672]},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_frozen(inputs_path: Path, geometry_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if sha256(inputs_path) != EXPECTED_INPUT_SHA256:
        raise ValueError(f"unexpected R015 input SHA256: {inputs_path}")
    if sha256(geometry_path) != EXPECTED_GEOMETRY_SHA256:
        raise ValueError(f"unexpected R015 geometry SHA256: {geometry_path}")
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    if inputs.get("marker_ids") != {"</think>": [248069], "<|im_end|>": [248046], "<tool_call>": [248058]}:
        raise ValueError("R015 anchor source changed")
    fields = inputs.get("parsed_configuration")
    if fields != {"page_size": "1", "prefill_anchor_cut": "True", "prefill_layer_major": "False", "special_token_ckpt": "True", "max_extend_tokens": "4096"}:
        raise ValueError("R015 parsed configuration changed")
    lines = geometry.get("geometry_lines")
    if not isinstance(lines, list) or not any("Page size is overridden to 64" in line for line in lines):
        raise ValueError("geometry lacks qsa_sparse page-size override evidence")
    return inputs, geometry


def branch_variants(inputs: dict[str, Any]) -> dict[str, list[int]]:
    prefix = inputs.get("prefix_ids")
    branch = inputs.get("branch")
    if not isinstance(prefix, list) or len(prefix) != 21976 or not isinstance(branch, dict):
        raise ValueError("invalid frozen prefix/branch")
    seeded = branch.get("branch_ids")
    if not isinstance(seeded, list) or len(seeded) != 12768 or seeded[:RESTORE_LEN] != prefix[:RESTORE_LEN]:
        raise ValueError("branch does not retain the controlled 12672-token prefix")
    if seeded[RESTORE_LEN] != 74 or prefix[RESTORE_LEN] != 17:
        raise ValueError("frozen branch divergence is not the recorded 74-vs-17 token")
    # Exact controlled-client branch recipe: P[:12672] + the first 96 seeded branch
    # tokens.  Longer diagnostics extend the same recorded source token sequence.
    tail = seeded[RESTORE_LEN:]
    out = {"Y96": seeded}
    for name, suffix_len in (("Y122", 122), ("Y129", 129)):
        out[name] = [*prefix[:RESTORE_LEN], *tail, *prefix[RESTORE_LEN + len(tail): RESTORE_LEN + suffix_len]]
    for name, expected in EXPECTED.items():
        if len(out[name]) != expected["length"]:
            raise AssertionError(f"{name} branch recipe length drift")
    return out


@dataclass
class _CpuCache:
    page_size: int = PAGE_SIZE
    swa_paged: bool = False
    # R015 uses a hybrid cache with 32 host slots.  The state contents are not
    # evaluated here, but the scheduler's chunk-alignment capability is real.
    mamba_host_enabled: bool = True

    @property
    def prefill_chunk_align(self) -> int:
        return self.page_size


@dataclass
class _CpuTable:
    token_pool: Any


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def runtime_sources(runtime_root: Path) -> dict[str, Path]:
    runtime_python = runtime_root / "python"
    sources = {
        "prefill": runtime_python / "freetoken" / "scheduler" / "prefill.py",
        "linear": runtime_python / "freetoken" / "attention" / "linear.py",
    }
    if not all(path.is_file() for path in sources.values()):
        raise ValueError(f"runtime root has no freetoken scheduler: {runtime_root}")
    return sources


def validate_runtime_sources(runtime_root: Path) -> dict[str, Path]:
    sources = runtime_sources(runtime_root)
    expected = {"prefill": PREFILL_SHA256, "linear": LINEAR_SHA256}
    for name, path in sources.items():
        if sha256(path) != expected[name]:
            raise ValueError(f"unexpected runtime {name} SHA256: {path}")
    return sources


def assert_loaded_runtime_root(runtime_root: Path) -> None:
    """Reject any cached FreeToken package/module outside this exact worktree."""
    runtime_python = (runtime_root / "python").resolve()
    for name, cached in tuple(sys.modules.items()):
        if name != "freetoken" and not name.startswith("freetoken."):
            continue
        cached_file = getattr(cached, "__file__", None)
        if cached_file and not _inside(Path(cached_file), runtime_python):
            raise ValueError(f"cached module outside requested runtime root: {name}")
        cached_path = getattr(cached, "__path__", None)
        if cached_path is not None:
            for package_dir in cached_path:
                if not _inside(Path(package_dir), runtime_python):
                    raise ValueError(f"cached package outside requested runtime root: {name}")


def _runtime_modules(runtime_root: Path):
    sources = validate_runtime_sources(runtime_root)
    runtime_python = runtime_root / "python"
    # Python's module cache otherwise allows an unrelated worktree to silently
    # satisfy imports, including transitive scheduler and FLA dependencies.
    assert_loaded_runtime_root(runtime_root)
    sys.path.insert(0, str(runtime_python))
    try:
        modules = (
            importlib.import_module("torch"),
            importlib.import_module("freetoken.core"),
            importlib.import_module("freetoken.scheduler.prefill"),
            importlib.import_module("freetoken.scheduler.utils"),
            importlib.import_module("freetoken.attention.linear"),
        )
    finally:
        sys.path.pop(0)
    assert_loaded_runtime_root(runtime_root)
    for module, source in ((modules[2], sources["prefill"]), (modules[4], sources["linear"])):
        if Path(module.__file__).resolve() != source.resolve():
            raise ValueError(f"imported runtime module differs from requested root: {module.__name__}")
    return modules, sources


def _make_segment(prefill: Any, pending: Any, table: _CpuTable, cached_len: int, ping_pong: tuple[int, int], next_track: int):
    # This intentionally invokes the actual runtime admission implementation; only cache/table
    # allocation is replaced by CPU buffers because no model/KV cache is needed for a cut decision.
    adder = prefill.PrefillAdder(
        token_budget=MAX_EXTEND,
        reserved_size=0,
        cache_manager=_CpuCache(),
        table_manager=table,
        layer_major=False,
        anchor_ids=ANCHORS,
        prefill_anchor_cut=True,
    )
    req = adder._add_one_req(
        pending_req=pending,
        cache_handle=object(),
        table_idx=0,
        cached_len=cached_len,
        ping_pong=ping_pong,
        next_track_idx=next_track,
    )
    if req is None:
        raise RuntimeError("real PrefillAdder rejected the CPU segment")
    return req


def classify_tracks(segments: list[dict[str, int | None]]) -> tuple[list[int], int | None]:
    """Archive only tracks made by explicitly non-final scheduler segments."""
    archives = [int(item["track"]) for item in segments if not item["final"] and item["track"] is not None]
    finals = [item["track"] for item in segments if item["final"]]
    if len(finals) != 1:
        raise ValueError("expected exactly one final segment")
    return archives, None if finals[0] is None else int(finals[0])


def _track(linear: Any, core: Any, torch: Any, req: Any) -> int | None:
    runtime_root = Path(linear.__file__).resolve().parents[3]
    assert_loaded_runtime_root(runtime_root)
    old_ctx = core._GLOBAL_CTX
    try:
        # _build_track_metadata only needs the true runtime context's conv-history width.
        # R015's GDN convolution has km1=3.  This supplies metadata shape only;
        # the CPU gate never evaluates state tensors or model values.
        core._GLOBAL_CTX = SimpleNamespace(linear_state_pool=SimpleNamespace(conv_states=torch.zeros((1, 1, 3))))
        metadata = linear._build_track_metadata([req], torch.tensor([0, req.extend_len], dtype=torch.int32), torch.device("cpu"), {})
    finally:
        core._GLOBAL_CTX = old_ctx
    assert_loaded_runtime_root(runtime_root)
    row = metadata["track_boundary_row"]
    return None if row is None else int(row.tolist()[0]) + req.cached_len - 0  # row is local forward offset


def predict(runtime_root: Path, inputs_path: Path, geometry_path: Path) -> dict[str, Any]:
    inputs, geometry = read_frozen(inputs_path, geometry_path)
    variants = branch_variants(inputs)
    (torch, core, prefill, utils, linear), source_files = _runtime_modules(runtime_root)
    output: dict[str, Any] = {
        "scope": "CPU prediction using runtime PrefillAdder._add_one_req and attention.linear._build_track_metadata; not GPU/model measurement proof.",
        "input_sha256": sha256(inputs_path),
        "geometry_sha256": sha256(geometry_path),
        "runtime_root": str(runtime_root),
        "runtime_sha256": {name: sha256(path) for name, path in source_files.items()},
        "runtime_provenance": {"parent_commit": PARENT_COMMIT, "diagnostic_delta_prefill_sha256": PREFILL_SHA256, "linear_sha256": LINEAR_SHA256},
        "configuration": {"page_size": PAGE_SIZE, "max_extend_tokens": MAX_EXTEND, "anchor_mode": "last", "prefill_layer_major": False, "track_chunk": 64, "anchors": sorted(ANCHORS), "restore_length": RESTORE_LEN, "hybrid_host_slots": 32, "cpu_stub_conv_history": 3, "state_tensor_values_evaluated": False},
        "geometry_evidence": geometry["geometry_lines"],
        "scenarios": {},
    }
    for name, ids in variants.items():
        pending = utils.PendingReq(0, torch.tensor(ids, dtype=torch.int32), core.SamplingParams(max_tokens=1))
        table = _CpuTable(torch.empty((1, len(ids) + 1), dtype=torch.int32))
        cached_len, next_track = 0, 0
        chunks, tracks, segments = [0], [], []
        while cached_len < len(ids):
            req = _make_segment(prefill, pending, table, cached_len, (10, 11), next_track)
            boundary = _track(linear, core, torch, req)
            if boundary is not None:
                tracks.append(boundary)
            cached_len = req.device_len
            next_track = req.mamba_next_track_idx
            chunks.append(cached_len)
            segments.append({"end": cached_len, "track": boundary, "final": cached_len == len(ids)})
        archive_tracks, final_track = classify_tracks(segments)
        expected = EXPECTED[name]
        if chunks != expected["chunks"] or archive_tracks != expected["archives"]:
            raise AssertionError(f"{name} runtime prediction changed: chunks={chunks}, archives={archive_tracks}")
        output["scenarios"][name] = {"length": len(ids), "scheduler_chunk_ends": chunks, "all_internal_tracks": tracks, "segments": segments, "archive_tracks_nonfinal_only": archive_tracks, "final_segment_track_not_archive": final_track}
    return output


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=here / "e2d03-continuation")
    parser.add_argument("--inputs", type=Path, default=here / "t04_r015_boundary_inputs.json")
    parser.add_argument("--geometry", type=Path, default=here / "t04_r015_geometry.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = predict(args.runtime_root.resolve(), args.inputs.resolve(), args.geometry.resolve())
    # No evidence replacement: all validation succeeds before this exclusive write.
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
