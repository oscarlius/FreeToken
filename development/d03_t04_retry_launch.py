#!/usr/bin/env python3
"""Inert-until-frozen launcher for the root-assigned T04 R015 retry."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from types import ModuleType


ROOT = Path("/data2/FreeToken")
DEV = ROOT / "runs/dev_D03"
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
RETRY_RID = "E2-R015"
CANDIDATE = "c30ae0d7003c3bbbf56867ce74da797332fa7ed5"
INHERITED_LAUNCHER = Path(__file__).with_name("d03_phase2_launch.py")
INHERITED_LAUNCHER_SHA256 = (
    "6c403cc8ea2c8719c22c8a6be86de23ad266d138d31e5af63fcb02dcb2a588fe"
)
ATOMIC_LAUNCHER_SHA256 = (
    "a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf"
)
RETRY_RUNNER = Path(__file__).with_name("t04_logits_retry.py")
CONTROLLED_CLIENT = Path(__file__).with_name("t04_capture_controlled.py")

# Root freezes the two payload tools externally.  The launcher never hashes
# itself: its deployed bytes are the external launch-review subject.
FROZEN_RETRY_BUNDLE: dict[str, str] | None = {
    "t04_logits_retry.py": "1f8dcac3f75bcd98b38b496068e727d13435cdf60117f0d99c27b95370445458",
    "t04_capture_controlled.py": "14b1eb09a9a49ba4c46176ca3edc5d52b927a07f4c476ae55c1d144c979c50fb",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pinned(path: Path, name: str, expected_sha256: str) -> ModuleType:
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != expected_sha256:
        raise ValueError(f"reviewed source changed: {path.name}")
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def verify_reviewed_sources() -> None:
    if sha256(INHERITED_LAUNCHER) != INHERITED_LAUNCHER_SHA256:
        raise ValueError("frozen D03 phase-two launcher changed")
    if FROZEN_RETRY_BUNDLE is None:
        raise RuntimeError("TODO: root must freeze FROZEN_RETRY_BUNDLE before --run")
    expected_names = {
        "t04_logits_retry.py": RETRY_RUNNER,
        "t04_capture_controlled.py": CONTROLLED_CLIENT,
    }
    if set(FROZEN_RETRY_BUNDLE) != set(expected_names):
        raise ValueError("frozen retry bundle has an incomplete tool set")
    for name, path in expected_names.items():
        expected = FROZEN_RETRY_BUNDLE[name]
        if not path.is_file():
            raise ValueError(f"reviewed retry tool is absent: {name}")
        if not isinstance(expected, str) or len(expected) != 64 or sha256(path) != expected:
            raise ValueError(f"reviewed retry tool changed: {name}")


def arguments(batch: int) -> list[str]:
    check = DEV / "gpu_selfcheck_c30ae0d_urlfix"
    report = json.loads((check / "selfcheck.json").read_text(encoding="utf-8"))
    return [
        "--rid",
        RETRY_RID,
        "--batch",
        str(batch),
        "--candidate-commit",
        CANDIDATE,
        "--g4-token-file",
        report["g4_terminal_binding"]["path"],
        "--raw-binding-manifest",
        str(DEV / "historical_raw_ids_c30ae0d.json"),
        "--trace",
        "/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json",
        "--k",
        "32",
    ]


def require_read_only_sources() -> None:
    """The reviewed retry payload must be sealed before a GPU process starts."""
    paths = (RETRY_RUNNER, CONTROLLED_CLIENT, RETRY_RUNNER.parent)
    for path in paths:
        if not path.exists() or path.is_symlink() or path.stat().st_mode & 0o222:
            raise ValueError(f"reviewed retry source is not read-only: {path}")


def reserve_receipt(batch: int) -> tuple[Path, int]:
    """Claim the R015 launch receipt before the atomic helper can start a process."""
    path = DEV / f"launch_{RETRY_RID}.json"
    data = {
        "state": "reserved",
        "rid": RETRY_RID,
        "card": "T04",
        "batch": batch,
        "candidate_commit": CANDIDATE,
    }
    with path.open("x", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    return path, path.stat().st_ino


def publish_receipt(path: Path, reserved_inode: int, data: dict) -> None:
    """Replace a still-owned reservation atomically, after binding its inode."""
    if path.stat().st_ino != reserved_inode:
        raise RuntimeError("launch receipt reservation inode changed")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        if path.stat().st_ino != reserved_inode:
            raise RuntimeError("launch receipt reservation inode changed")
        os.replace(temp_path, path)
        if os.name == "posix":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def preflight(module: ModuleType, batch: int):
    """Run all source, selfcheck, raw binding, and gate checks before reserve."""
    extra = arguments(batch)
    token_path = Path(extra[extra.index("--g4-token-file") + 1])
    binding_path = Path(extra[extra.index("--raw-binding-manifest") + 1])
    trace = Path(extra[extra.index("--trace") + 1])
    runner = module.RetryPhase2(
        argparse.Namespace(
            rid=RETRY_RID,
            batch=batch,
            candidate_commit=CANDIDATE,
            g4_token_file=token_path,
            raw_binding_manifest=binding_path,
            trace=trace,
            k=32,
        )
    )
    inherited = runner.inherited
    token = inherited.read_token_record(token_path, max_k=32)
    inherited.verify_g4_source(runner.phase.sc, token_path, binding_path, trace, CANDIDATE)
    binding = inherited.read_binding(binding_path, token)
    document, historical, messages = runner.phase.sc.trace_record(trace)
    legacy = json.loads(runner.phase.sc.LEGACY_REPLAY.read_text(encoding="utf-8"))
    payload = runner.phase.sc.historical_payload(document, messages, legacy)
    if (
        binding["trace_sha256"] != inherited.sha256(trace)
        or binding["messages_sha"] != historical["messages_sha"]
        or binding["request_sha256"] != runner.phase.sc.request_sha(payload)
    ):
        raise ValueError("raw binding does not bind the admitted historical G4 request")
    runner.gate()
    return extra


def launch() -> dict:
    if sys.platform != "linux":
        raise RuntimeError("R015 launch requires Linux")
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "0":
        raise RuntimeError("R015 launch requires CUDA_VISIBLE_DEVICES=0")
    verify_reviewed_sources()
    require_read_only_sources()
    inherited = load_pinned(
        INHERITED_LAUNCHER, "t04_r014_launcher", INHERITED_LAUNCHER_SHA256
    )
    gate_dir = inherited.prerequisite()
    atomic_path = ROOT / "runs/plan_batches/e2_launch.py"
    if sha256(atomic_path) != ATOMIC_LAUNCHER_SHA256:
        raise ValueError("atomic e2_launch helper changed")
    atomic = load_pinned(atomic_path, "t04_retry_e2_launch", ATOMIC_LAUNCHER_SHA256)
    batch = atomic.next_batch(ROUNDS)
    if (ROUNDS / RETRY_RID).exists() or (DEV / f"launch_{RETRY_RID}.json").exists():
        raise FileExistsError("R015 evidence or launch receipt already exists")
    module = load_pinned(RETRY_RUNNER, "t04_r015_retry", FROZEN_RETRY_BUNDLE["t04_logits_retry.py"])
    subprocess_args = [sys.executable, str(RETRY_RUNNER), "--self-test"]
    import subprocess

    subprocess.run(subprocess_args, check=True)
    extra = preflight(module, batch)
    if atomic.next_batch(ROUNDS) != batch:
        raise ValueError("batch ledger changed during retry preflight")
    receipt_path, receipt_inode = reserve_receipt(batch)
    argv = [sys.executable, "-u", str(RETRY_RUNNER), *extra]
    process, wrapper, log = atomic.reserve_and_launch(batch, RETRY_RID, argv)
    receipt = {
        "rid": RETRY_RID,
        "card": "T04",
        "batch": batch,
        "batch_pid": process.pid,
        "pgid": process.pid,
        "candidate_commit": CANDIDATE,
        "runner_sha256": sha256(RETRY_RUNNER),
        "controlled_client_sha256": sha256(CONTROLLED_CLIENT),
        "launcher_sha256": sha256(Path(__file__)),
        "wrapper": str(wrapper),
        "wrapper_sha256": sha256(wrapper),
        "batch_log": str(log),
        "prerequisite_round": str(gate_dir),
        "prerequisite_round_sha256": sha256(gate_dir / "round.json"),
    }
    publish_receipt(receipt_path, receipt_inode, receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        assert RETRY_RID == "E2-R015"
        assert sha256(INHERITED_LAUNCHER) == INHERITED_LAUNCHER_SHA256
        print("T04 R015 launch self-test PASS: frozen prerequisite and inert bundle gate")
        return
    if not args.run or sys.platform != "linux":
        parser.error("--run and the Linux test host are required")
    receipt = launch()
    print("T04_RETRY_LAUNCHED", json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
