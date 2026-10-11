"""Owned controller/child launch for the two fixed T16 gates."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path("/data2/FreeToken")
DEV = Path(__file__).resolve().parent
PARENT_COMMIT = "effb9969706922ddad9e59b96377e46469ebe97f"
SPECS = {
    "D15": ("E2-R050-gate-D15", "988c9e183c8dca4415fd9b5d02318b26664da619", "t16_r050_d15_candidate.py"),
    "D08": ("E2-R051-gate-D08", "2600ada8faef6490b7a5fbdf6708e12c29d86536", "t16_r051_d08_candidate.py"),
}
RECEIPT_WAIT_SECONDS = 30


def d07():
    path = DEV / "d07_g3g4_prepare.py"
    spec = importlib.util.spec_from_file_location("r050_d07", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def source_hashes(card):
    """The R startup review binds the executable leaf launcher and adapter."""
    _, _, adapter = SPECS[card]
    return {
        name: hashlib.sha256((DEV / name).read_bytes()).hexdigest()
        for name in (Path(__file__).name, adapter, "d07_g3g4_prepare.py", "t16_private_port_base_runner.py")
    }


def review_path(card):
    rid, _, _ = SPECS[card]
    return ROOT / "runs/dev_T16/reviews" / f"{rid}_startup_review_v4.json"


def require_leaf_review(card):
    """Accept only a sealed R review for the exact sources this leaf will run."""
    rid, commit, _ = SPECS[card]
    path = review_path(card)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError("leaf startup review is absent or writable")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("leaf startup review is unreadable") from exc
    expected = {
        "schema": "ft_t16_leaf_startup_review/v1",
        "rid": rid,
        "card": card,
        "candidate_commit": commit,
        "parent_commit": PARENT_COMMIT,
        "verdict": "PASS",
        "approved": True,
        "source_sha256": source_hashes(card),
    }
    if any(value.get(key) != wanted for key, wanted in expected.items()):
        raise RuntimeError("leaf startup review binding differs")
    return path


def require_candidate(card):
    """Small git identity checks only; no payload scans or candidate mutation."""
    _, commit, _ = SPECS[card]
    worktree = ROOT / "wt" / ("e2d15" if card == "D15" else "e2d08")
    if worktree.is_symlink():
        raise RuntimeError("candidate worktree is symlinked")
    try:
        head = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=no"], text=True
        )
        ancestor = subprocess.run(
            ["git", "-C", str(worktree), "merge-base", "--is-ancestor", PARENT_COMMIT, "HEAD"],
            check=False,
        ).returncode
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("candidate worktree is unavailable") from exc
    if head != commit or dirty or ancestor:
        raise RuntimeError("candidate worktree identity, cleanliness, or ancestry differs")
    return worktree


def required_rounds(card):
    # HANDOFF section seven: the measurement-tree gate precedes D15 and R046a.
    if card == "D15":
        return (("E2-R055-gate-D06", "kept"), ("E2-R041-gate-D17", "kept"))
    return (("E2-R049", "measured"), ("E2-R041-gate-D17", "kept"))


def admission(g, card):
    """Metadata-only predecessor, review, candidate and foreign-lock checks."""
    if g.LOCK.exists() or g.LOCK.is_symlink():
        raise RuntimeError("foreign GPU lock exists; T16 gate remains queued")
    for rid, verdict in required_rounds(card):
        g.require_closed_round(rid, verdict)
    require_candidate(card)
    require_leaf_review(card)


def argv(card, batch, receipt):
    return [
        str(ROOT / "venv/bin/python"),
        str(Path(__file__).resolve()),
        "--run", "--card", card, "--owned-child", "--batch", str(batch),
        "--launch-receipt", str(receipt),
    ]


def controller(card):
    if sys.platform != "linux":
        raise RuntimeError("Linux only")
    rid, commit, _ = SPECS[card]
    gate = d07()
    admission(gate, card)
    owned = gate.load_owned_lifecycle()
    helper = owned.verified_module(ROOT / "runs/plan_batches/e2_launch.py", gate.ATOMIC_HELPER_SHA, "r050_atomic")
    batch = helper.next_batch(gate.ROUNDS)
    receipt = ROOT / "runs/dev_T16" / f"launch_{rid}_batch{batch}.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    child_argv = argv(card, batch, receipt)
    reserved = {
        "schema": "ft_t16_owned_launch/v1",
        "state": "reserved",
        "rid": rid,
        "batch": batch,
        "candidate_commit": commit,
        "argv_sha256": gate.argv_sha256(child_argv),
        "controller": gate.process_birth(),
    }
    got = owned.reserve_process(helper, batch, rid, child_argv, receipt, reserved)
    identity = owned.process_identity(got["batch_pid"])
    child_identity = {
        "pid": identity["pid"],
        "start_ticks": identity["start_ticks"],
        "execution_id": f"{identity['pid']}:{identity['start_ticks']}",
    }
    return gate.publish_child_binding(receipt, got, child_identity, lifecycle=owned)


def require_receipt(gate, card, batch, path):
    rid, commit, _ = SPECS[card]
    mine = gate.process_birth()
    expected = gate.argv_sha256(argv(card, batch, path))
    deadline = time.monotonic() + RECEIPT_WAIT_SECONDS
    static = {"schema": "ft_t16_owned_launch/v1", "rid": rid, "batch": batch,
              "candidate_commit": commit, "argv_sha256": expected}
    while time.monotonic() < deadline:
        if path.is_symlink():
            raise RuntimeError("T16 child receipt is symlinked")
        if not path.is_file():
            time.sleep(.05)
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("T16 child receipt is unreadable") from exc
        if any(document.get(key) != value for key, value in static.items()):
            raise RuntimeError("T16 child launch receipt binding differs")
        state = document.get("state")
        if state == "reserved":
            time.sleep(.05)
            continue
        if state != "launched":
            raise RuntimeError("T16 child receipt state is unknown")
        child = document.get("child")
        if child is None:
            time.sleep(.05)
            continue
        if document.get("batch_pid") != mine["pid"] or child != mine:
            raise RuntimeError("T16 child launch receipt binding differs")
        return document
    raise RuntimeError("T16 child launch receipt did not reach launched state")


def adapter_module(name):
    path = DEV / name
    spec = importlib.util.spec_from_file_location("t16_leaf_" + name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def child(card, batch, receipt):
    if sys.platform != "linux":
        raise RuntimeError("Linux only")
    rid, commit, name = SPECS[card]
    gate = d07()
    admission(gate, card)
    require_receipt(gate, card, batch, receipt)
    owner = gate.take_d07_gpu_lock(rid, batch)
    runner, release = None, True
    try:
        module = adapter_module(name)

        class OwnedRunner(module.CandidateRunner):
            def lock_take(self):
                return None

            def lock_release(self):
                return None

            def stop(self):
                try:
                    return super().stop()
                except BaseException:
                    self._owned_cleanup_failed = True
                    raise

        runner = OwnedRunner(SimpleNamespace(
            case=card, rid=rid, batch=batch, candidate_commit=commit, run=True, gate=None
        ))
        # The retained gate verifies this exact child-owned lock on every arm.
        # Only the outer child releases it; the leaf never acquires a second lock.
        runner.token = owner['lock_token']
        runner.lock_inode = owner['lock_inode']
        runner.execute()
        return {"rid": rid, "batch": batch, "candidate_commit": commit,
                "verdict": "pending_review", "proposed_verdict": "kept"}
    finally:
        if runner is not None and getattr(runner, "_owned_cleanup_failed", False):
            release = False
        elif runner is not None and runner.proc is not None and gate.load_owned_lifecycle().owned_group_alive(runner.proc.pid):
            release = False
        if release:
            gate.release_d07_gpu_lock(owner)


def main(argv_in=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--card", choices=SPECS)
    parser.add_argument("--owned-child", action="store_true")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--launch-receipt", type=Path)
    args = parser.parse_args(argv_in)
    if not args.run:
        if args.card or args.owned_child or args.batch or args.launch_receipt:
            parser.error("--run required for launch arguments")
        print(json.dumps({"schema": "ft_t16_gate_prepare/v1", "requests_sent": False,
                          "gpu_lock_taken": False, "gates": SPECS}))
        return 0
    if not args.card:
        parser.error("--card required")
    if args.owned_child:
        if args.batch is None or args.launch_receipt is None:
            parser.error("child requires batch and receipt")
        child(args.card, args.batch, args.launch_receipt)
        return 0
    if args.batch is not None or args.launch_receipt is not None:
        parser.error("controller does not accept child arguments")
    controller(args.card)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
