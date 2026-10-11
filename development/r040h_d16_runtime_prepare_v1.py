"""CPU-only assembly contract for the R040h D16 remainder retry.

It describes, but never launches, the new source capsule.  The sole runtime
change is the flashlib-required dtype used by the cache warm priming path.
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import shutil
import textwrap
from pathlib import Path


HERE = Path(__file__).resolve().parent
R040G_RUNTIME = HERE / "r040g_d16_v1" / "runtime"
RID = "E2-R040h"
SOURCE_ENTRY = R040G_RUNTIME / "r040g_d16_remaining_prepare_v1.py"
SOURCE_STARTUP = R040G_RUNTIME / "d16_exact_service_startup.py"
HISTORICAL_SLOTS4_RID = "E2-R040e"
PARTIAL_R040G_RID = "E2-R040g"

# The original 14-service / 16-call plan completed parking (4/4) and cache
# cold (2/2).  The retry has only cache warm plus native interleave remaining.
REPLAY_SCOPE = {
    "completed_source_bindings": {
        HISTORICAL_SLOTS4_RID: {"services": 0, "calls": 0, "role": "retained slots4 evidence"},
        PARTIAL_R040G_RID: {"services": 6, "calls": 6, "role": "partial parking and cache-cold evidence"},
    },
    "replay": {
        "cache_warm": {"services": 2, "calls": 2, "arms": ("warm_0", "warm_1")},
        "native_interleave": {"services": 6, "calls": 8,
                              "arms": ("batch_0", "batch_1", "single_0_0", "single_0_1", "single_1_0", "single_1_1")},
    },
}
WARM_DTYPE_OLD = "torch.zeros((1, 1), dtype=torch.int64, device=cache.device)"
WARM_DTYPE_NEW = "torch.zeros((1, 1), dtype=torch.int32, device=cache.device).contiguous()"


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replay_totals() -> tuple[int, int]:
    replay = REPLAY_SCOPE["replay"].values()
    return sum(item["services"] for item in replay), sum(item["calls"] for item in replay)


def patch_startup_source(source: str) -> str:
    """Make the one reviewed warm-path correction, exactly once."""
    if source.count(WARM_DTYPE_OLD) != 1 or WARM_DTYPE_NEW in source:
        raise ValueError("R040h expected exactly one unpatched warm priming expression")
    return source.replace(WARM_DTYPE_OLD, WARM_DTYPE_NEW)


def source_plan() -> dict:
    """Return a reviewable source map; no filesystem mutation or runtime launch."""
    services, calls = replay_totals()
    if (services, calls) != (8, 10):
        raise AssertionError("R040h replay scope no longer matches remaining collector arms")
    return {
        "rid": RID,
        "mode": "prepare_only",
        "base_entry": str(SOURCE_ENTRY),
        "base_entry_sha256": sha256(SOURCE_ENTRY),
        "base_startup": str(SOURCE_STARTUP),
        "base_startup_sha256": sha256(SOURCE_STARTUP),
        "new_startup_name": "d16_exact_service_startup.py",
        "new_startup_sha256": hashlib.sha256(
            patch_startup_source(SOURCE_STARTUP.read_text(encoding="utf-8")).encode()).hexdigest(),
        "source_change": {"old": WARM_DTYPE_OLD, "new": WARM_DTYPE_NEW},
        "replay_scope": REPLAY_SCOPE,
        "replay_services": services,
        "replay_calls": calls,
        "requires": ["fresh CPU capsule test", "fresh source/dry-run review", "explicit GPU approval"],
    }


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def retained_proof(path: Path) -> dict:
    """Require R-supplied immutable source identities before any retry plan runs."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("R040h requires an independent retained-proof file")
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = {HISTORICAL_SLOTS4_RID, PARTIAL_R040G_RID}
    if value.get("schema") != "ft_r040h_retained_sources/v1" or set(value.get("sources", ())) != expected:
        raise RuntimeError("R040h retained-proof identities are incomplete")
    for rid in expected:
        item = value["sources"][rid]
        if not isinstance(item, dict) or not all(isinstance(item.get(key), str) and len(item[key]) == 64
                                                 for key in ("round_sha256", "manifest_sha256", "source_sha256")):
            raise RuntimeError("R040h retained-proof hash is absent: " + rid)
    return value


def assemble_runtime(destination: Path, proof: Path) -> dict:
    """Create a new local runtime capsule with the one reviewed source change."""
    retained = retained_proof(proof)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("R040h runtime destination must be new")
    shutil.copytree(R040G_RUNTIME, destination)
    startup = destination / "d16_exact_service_startup.py"
    startup.write_text(patch_startup_source(startup.read_text(encoding="utf-8")), encoding="utf-8")
    plan = source_plan()
    receipt = {**plan, "retained_proof": str(Path(proof).resolve()),
               "retained_proof_sha256": sha256(proof), "runtime": str(destination.resolve()),
               "runtime_startup_sha256": sha256(startup)}
    (destination / "r040h_prepare_receipt.json").write_text(json.dumps(receipt, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def _warm_only_state_collector(collector):
    """Reuse the actual collector body, changing only its state-arm selector."""
    original = inspect.getsource(collector._collect_state_processes)
    needle = "for park in (False, True):"
    if original.count(needle) != 1:
        raise RuntimeError("R040h collector source no longer has the reviewed cold/warm selector")
    namespace = dict(collector.__dict__)
    patched = textwrap.dedent(original).replace(needle, "for park in (True,):")
    exec(compile(patched, getattr(collector, "__file__", "<r040h-collector>"), "exec"), namespace)
    return namespace["_collect_state_processes"]


def run_remaining_body(owner, short_ids, long_ids, *, wrapper, source_review, source_review_sha256,
                       collector_path=R040G_RUNTIME / "d16_native_process_collection_v6.py"):
    """Actual R040h collector control flow: warm2 then interleave6 only.

    The caller remains responsible for the retained owned lifecycle, dry-run,
    launch receipt, lock, and approval gates supplied by the R040g structure.
    """
    collector = load(Path(collector_path), "r040h_retained_collector")
    if not isinstance(short_ids, list) or not isinstance(long_ids, list) or len(short_ids) >= 4096 or len(long_ids) <= 4096:
        raise ValueError("R040h requires the retained short and long D16 inputs")
    warm = _warm_only_state_collector(collector)(owner, short_ids, kind="cache", wrapper=wrapper,
        source_review=source_review, source_review_sha256=source_review_sha256, base_url=owner.base_url)
    interleave = collector.collect_native_processes(owner, [short_ids, long_ids], slots=2, wrapper=wrapper,
        source_review=source_review, source_review_sha256=source_review_sha256, base_url=owner.base_url, interleave=True)
    if len(warm["arms"]) != 2 or len(interleave.get("runs", ())) != 6:
        raise RuntimeError("R040h actual collector scope differs from warm2 plus interleave6")
    return {"rid": RID, "d16": {"cache_warm": warm, "interleave": interleave},
            "services": 8, "calls": 10, "admitted": False}
