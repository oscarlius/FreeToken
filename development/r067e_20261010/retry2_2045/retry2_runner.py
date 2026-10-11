"""Sealed controller/child wrapper for the inert R067e retry2 packet."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import stat
import sys
from pathlib import Path
from typing import Any

from retry2_execution import HERE, PARENT, RID, filedry, sha
from retry2_effects import Retry2Effects

ROOT = PARENT.parents[1]
T17_RID = "E2-D09-T17-reapply-bd57-20261010"
T17_BATCH = 164


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _owned():
    return _load_module(PARENT / "r067e_owned.py", "r067e_owned_retry2_runner")


def _actual():
    module = _load_module(PARENT / "r067e_actual.py", "r067e_actual_retry2_runner")
    module.RID = RID
    return module


def _sealed_json(path: Path) -> dict[str, Any]:
    """Read a root-sealed JSON file only when its immutable sidecar matches."""
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError("sealed admission/packet absent") from exc
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o222:
        raise RuntimeError("sealed admission/packet is not a read-only regular file")
    sidecar = path.with_name(path.name + ".sha256")
    try:
        side_info = sidecar.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError("sealed admission/packet hash sidecar absent") from exc
    if sidecar.is_symlink() or not stat.S_ISREG(side_info.st_mode) or stat.S_IMODE(side_info.st_mode) & 0o222:
        raise RuntimeError("sealed admission/packet hash sidecar is not a read-only regular file")
    recorded = sidecar.read_text(encoding="ascii").strip()
    actual = sha(path)
    if recorded != actual:
        raise RuntimeError("sealed admission/packet hash differs")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError("sealed admission/packet is not an object")
    return value


def _equal_current(plan: dict[str, Any]) -> None:
    current = filedry()
    if plan.get("source_manifest") != current.get("source_manifest") or plan.get("donor_at_p") != current.get("donor_at_p"):
        raise RuntimeError("retry2 plan/source/donor binding differs from current CPU filedry")


def _load_bound_plan(doc: dict[str, Any]) -> dict[str, Any]:
    packet_path = Path(str(doc.get("execution_packet_path", "")))
    if not packet_path.is_absolute():
        raise RuntimeError("sealed admission lacks absolute execution packet path")
    packet = _sealed_json(packet_path)
    if doc.get("execution_packet_sha256") != sha(packet_path):
        raise RuntimeError("sealed admission execution packet binding differs")
    return packet


def _bound_readonly_file(path: Path, digest: str, label: str) -> bytes:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"T17 {label} absent") from exc
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o222:
        raise RuntimeError(f"T17 {label} is not a read-only regular file")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise RuntimeError(f"T17 {label} SHA differs")
    return data


def _validate_predecessor(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("retry2 admission lacks sealed predecessor_t17")
    required = {"rid": T17_RID, "batch": T17_BATCH}
    if any(value.get(key) != expected for key, expected in required.items()):
        raise RuntimeError("retry2 predecessor T17 RID/batch differs")
    paths = {key: Path(str(value.get(key + "_path", ""))) for key in ("round", "manifest", "terminal")}
    if any(not path.is_absolute() for path in paths.values()) or paths["round"].parent != paths["manifest"].parent:
        raise RuntimeError("retry2 predecessor T17 ancestry differs")
    round_doc = json.loads(_bound_readonly_file(paths["round"], str(value.get("round_sha256", "")), "formal round"))
    _bound_readonly_file(paths["manifest"], str(value.get("manifest_sha256", "")), "formal manifest")
    terminal_doc = json.loads(_bound_readonly_file(paths["terminal"], str(value.get("terminal_sha256", "")), "raw terminal"))
    if round_doc.get("round_id", round_doc.get("rid")) != T17_RID or round_doc.get("batch") != T17_BATCH:
        raise RuntimeError("retry2 predecessor formal round identity differs")
    closed = value.get("closed_verdict")
    if not isinstance(closed, str) or closed == "kept" or round_doc.get("verdict") != closed:
        raise RuntimeError("retry2 predecessor formal closure verdict differs")
    if terminal_doc.get("rid") != T17_RID or terminal_doc.get("proposed_verdict") != "failed_harness":
        raise RuntimeError("retry2 predecessor raw terminal differs")
    return value


def validate_sealed_admission(path: Path, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate root approval, exact retry2 packet, and the terminal T17 gate."""
    doc = _sealed_json(path)
    packet = _load_bound_plan(doc)
    if plan is not None and packet != plan:
        raise RuntimeError("caller plan differs from root-sealed execution packet")
    expected = {
        "schema": "ft_r067e_retry2_admission/v1", "admit": True, "rid": RID,
        "source_manifest": packet.get("source_manifest"), "parent_packet": packet.get("parent_packet"),
        "native_proof": packet.get("native_proof"), "input_binding": packet.get("input_binding"),
        "worktree_commit": packet.get("commit"), "engine_sha256": packet.get("engine_sha256"),
        "budget": packet.get("budget"),
    }
    if any(doc.get(key) != value for key, value in expected.items()):
        raise RuntimeError("retry2 sealed admission differs")
    _validate_predecessor(doc.get("predecessor_t17"))
    if not isinstance(doc.get("batch"), int) or doc["batch"] < 1 or not isinstance(doc.get("receipt_path"), str):
        raise RuntimeError("retry2 sealed admission lacks child binding")
    return doc


def _child_argv(admission_path: Path, batch: int, receipt: Path) -> list[str]:
    return [str(ROOT / "venv/bin/python"), str(HERE / "retry2_runner.py"), "--owned-child", "--admission", str(admission_path), "--batch", str(batch), "--receipt", str(receipt)]


def _configured_parent(plan: dict[str, Any]):
    if str(PARENT) not in sys.path:
        sys.path.insert(0, str(PARENT))
    parent = _owned(); parent.RID = RID
    parent.source_manifest = lambda: plan["source_manifest"]
    parent.admission = lambda path, resolved: validate_sealed_admission(path, resolved)
    parent.child_argv = _child_argv
    return parent


def controller(admission_path: Path, *, popen=None, d07=None, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the parent controller; it alone reserves and birth-binds the child."""
    doc = validate_sealed_admission(admission_path, plan)
    sealed_plan = _load_bound_plan(doc)
    _equal_current(sealed_plan)
    return _configured_parent(sealed_plan).controller(admission_path, popen=popen, d07=d07, plan=sealed_plan, materialize=False)


def prepare_effects(plan: dict[str, Any], **kwargs: Any) -> Retry2Effects:
    return Retry2Effects(plan=plan, **kwargs)


def configured_d07(plan: dict[str, Any], parent=None):
    """Set the task identity before the D07 receipt validator reads defaults."""
    parent = _configured_parent(plan) if parent is None else parent
    d07 = parent.d07_module()
    d07.RID = RID
    d07.CANDIDATE = plan["commit"]
    return d07


def owned_child(admission_path: Path, batch: int, receipt_path: Path) -> dict[str, Any]:
    """Child entrypoint reached only through the controller-issued argv."""
    doc = validate_sealed_admission(admission_path)
    if batch != doc["batch"] or receipt_path != Path(doc["receipt_path"]):
        raise RuntimeError("controller-child admission binding differs")
    plan = _load_bound_plan(doc)
    _equal_current(plan)
    parent = _configured_parent(plan)
    d07 = configured_d07(plan, parent)
    receipt = d07.require_child_receipt(receipt_path, batch, Path(plan["worktree"]), ROOT / "runs/dev_R067", rid=RID, expected_argv=_child_argv(admission_path, batch, receipt_path), schema="ft_r067e_owned_launch/v1")
    actual = _actual()
    child = receipt["child"]
    run_dir = actual.RUN.parent / f"{RID}_batch{batch}_{child['pid']}_{child['start_ticks']}"
    effects = prepare_effects(plan, d07=d07, owned=d07.load_owned_lifecycle(), run_dir=run_dir)
    return parent.child(admission_path, batch, receipt_path, d07=d07, plan=plan, effects=effects)


def execute(admission_path: Path, plan: dict[str, Any], **_unused: Any) -> dict[str, Any]:
    """Compatibility surface: execution starts with the real owned controller."""
    return controller(admission_path, plan=plan)


def parse_cli(argv: list[str] | None = None):
    """Parse both direct CLI and e2_launch's mandatory trailing ``--run``."""
    parser = argparse.ArgumentParser()
    # e2_launch.reserve_and_launch executes ``[*child_argv, '--run']``.
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--controller", action="store_true")
    parser.add_argument("--owned-child", action="store_true")
    parser.add_argument("--admission", required=True, type=Path)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--receipt", type=Path)
    return parser.parse_args(argv)


def e2_launch_wrapped_child_args(argv: list[str]) -> argparse.Namespace:
    """CPU check of the exact e2_launch wrapper injection, without spawning."""
    if len(argv) < 3 or Path(argv[1]) != HERE / "retry2_runner.py":
        raise RuntimeError("retry2 child argv lacks its task-owned executable")
    args = parse_cli([*argv[2:], "--run"])
    if not args.run or not args.owned_child or args.controller or args.batch is None or args.receipt is None:
        raise RuntimeError("e2_launch wrapper argv is not a retry2 owned-child invocation")
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_cli(argv)
    if args.controller and not args.owned_child:
        print(json.dumps(controller(args.admission), sort_keys=True))
    elif args.owned_child and args.batch is not None and args.receipt is not None:
        print(json.dumps(owned_child(args.admission, args.batch, args.receipt), sort_keys=True))
    else:
        raise RuntimeError("use --controller or --owned-child with --batch and --receipt")


if __name__ == "__main__":
    main()
