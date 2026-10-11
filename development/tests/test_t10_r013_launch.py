from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


DEV = Path(__file__).parents[1]
PATH = DEV / "d03_t10_r013_launch.py"
SPEC = importlib.util.spec_from_file_location("r013_launch", PATH)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def test_unfrozen_bundle_rejects_before_any_preflight_or_receipt(monkeypatch):
    monkeypatch.setattr(launcher, "FROZEN_BUNDLE", None)
    with pytest.raises(RuntimeError, match="TODO: root must freeze"):
        launcher.verify_sources()


def _frozen_bundle(monkeypatch, tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    runner_path = bundle / "t10_r013_from_r017.py"
    preparer_path = bundle / "d03_phase2_prepare_r017.py"
    probe_path = bundle / "logits_probe.py"
    lifecycle_path = bundle / "d03_phase2_launch.py"
    atomic_path = bundle / "e2_launch.py"
    for path, source in (
        (runner_path, "value = 'runner'\n"),
        (preparer_path, "value = 'preparer'\n"),
        (probe_path, "value = 'probe'\n"),
        (lifecycle_path, "def prerequisite():\n    return None\n"),
        (atomic_path, "value = 'atomic'\n"),
    ):
        path.write_text(source, encoding="utf-8")
        path.chmod(0o444)
    bundle.chmod(0o555)
    monkeypatch.setattr(launcher, "RUNNER", runner_path)
    monkeypatch.setattr(launcher, "PREPARER", preparer_path)
    monkeypatch.setattr(launcher, "PROBE", probe_path)
    monkeypatch.setattr(launcher, "LIFECYCLE", lifecycle_path)
    monkeypatch.setattr(launcher, "ATOMIC", atomic_path)
    monkeypatch.setattr(launcher, "LIFECYCLE_SHA", launcher.sha(lifecycle_path))
    monkeypatch.setattr(launcher, "ATOMIC_SHA", launcher.sha(atomic_path))
    monkeypatch.setattr(
        launcher,
        "FROZEN_BUNDLE",
        {
            runner_path.name: launcher.sha(runner_path),
            preparer_path.name: launcher.sha(preparer_path),
            probe_path.name: launcher.sha(probe_path),
        },
    )
    return bundle, probe_path


def test_probe_is_sibling_frozen_source_and_changed_or_symlink_probe_rejects(monkeypatch, tmp_path):
    bundle, probe_path = _frozen_bundle(monkeypatch, tmp_path)
    assert launcher.PROBE == launcher.RUNNER.with_name("logits_probe.py")
    launcher.verify_sources()

    probe_path.chmod(0o644)
    probe_path.write_text("changed = True\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen R013 source changed: logits_probe.py"):
        launcher.verify_sources()

    probe_path.write_text("value = 'probe'\n", encoding="utf-8")
    probe_path.chmod(0o444)
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == probe_path or original_is_symlink(path),
    )
    with pytest.raises(ValueError, match="runner bundle must be frozen read-only"):
        launcher.verify_sources()


def test_preflight_uses_r017_canonical_parent_and_runs_no_gpu_service(monkeypatch, tmp_path):
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setattr(launcher, "ROUNDS", tmp_path)
    monkeypatch.setattr(launcher, "FROZEN_BUNDLE", {"t10_r013_from_r017.py": "a", "d03_phase2_prepare_r017.py": "b", "logits_probe.py": "c"})
    monkeypatch.setattr(launcher, "arguments", lambda batch: ["--batch", str(batch), "--candidate-commit", launcher.CANDIDATE, "--phase1-manifest", str(tmp_path / "phase1_manifest.json"), "--phase1-round-json", str(tmp_path / "round.json")])
    calls = []

    class Run:
        def __init__(self, args):
            assert args.phase1_manifest.name == "phase1_manifest.json"
            assert args.phase1_round_json.name == "round.json"

        def sealed_phase1(self):
            calls.append("sealed")
            return (tmp_path / "E2-R017", {"rid": "E2-R017"}, {})

        def recompute_forks(self, root, manifest):
            calls.append("forks")
            return []

        def gate(self):
            raise AssertionError("gate must not run when no actual fork exists")

    module = SimpleNamespace(Run=Run, self_test=lambda: calls.append("selftest"))
    monkeypatch.setattr(launcher, "load_pinned", lambda *args: module)
    _module, forks = launcher.preflight(55)
    assert forks == []
    assert calls == ["sealed", "forks", "selftest"]


def test_no_fork_proof_does_not_reserve_batch_or_create_formal_r013(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "DEV", tmp_path)
    monkeypatch.setattr(launcher, "ROUNDS", tmp_path / "rounds")
    launcher.ROUNDS.mkdir()
    monkeypatch.setattr(launcher.sys, "platform", "linux")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    reserved = []

    class Atomic:
        def next_batch(self, root):
            return 60

        def reserve_and_launch(self, *args):
            reserved.append(args)
            raise AssertionError("no-fork path must not reserve")

    monkeypatch.setattr(launcher, "verify_sources", lambda: (SimpleNamespace(prerequisite=lambda: tmp_path), Atomic()))
    monkeypatch.setattr(launcher, "preflight", lambda batch: (SimpleNamespace(), []))
    monkeypatch.setattr(launcher, "sha", lambda path: "a" * 64)
    proof = launcher.launch()
    assert proof["state"] == "not_applicable_no_actual_fork"
    assert reserved == []
    assert not (launcher.ROUNDS / launcher.RID).exists()
    assert json.loads((tmp_path / "t10_r013_no_fork.json").read_text())["gpu_started"] is False


def test_missing_cuda_zero_rejects_before_source_or_batch_work(monkeypatch):
    monkeypatch.setattr(launcher.sys, "platform", "linux")
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    with pytest.raises(ValueError, match="CUDA_VISIBLE_DEVICES"):
        launcher.launch()


def _install_launch_environment(monkeypatch, tmp_path, *, batch_values=(61, 61), reserve_error=None):
    dev = tmp_path / "dev"
    rounds = tmp_path / "rounds"
    parent = rounds / launcher.PARENT_RID
    dev.mkdir()
    parent.mkdir(parents=True)
    manifest = parent / "phase1_manifest.json"
    phase_round = parent / "round.json"
    manifest.write_text('{"rid":"E2-R017"}', encoding="utf-8")
    phase_round.write_text('{"round_id":"E2-R017"}', encoding="utf-8")
    wrapper = tmp_path / "batch.sh"
    log = tmp_path / "batch.log"
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    log.write_text("launch\n", encoding="utf-8")
    order = []
    reserve_calls = []

    class Lifecycle:
        def prerequisite(self):
            order.append("prerequisite")
            return parent

    class Atomic:
        def next_batch(self, root):
            order.append("ledger")
            return batch_values[len([item for item in order if item == "ledger"]) - 1]

        def reserve_and_launch(self, batch, rid, argv):
            order.append("launch")
            reserve_calls.append((batch, rid, argv))
            receipt = dev / f"launch_{launcher.RID}.json"
            assert receipt.exists()
            reserved = json.loads(receipt.read_text(encoding="utf-8"))
            assert reserved["state"] == "reserved"
            assert reserved["runner"] == str(launcher.RUNNER)
            assert reserved["parent_rid"] == launcher.PARENT_RID
            assert reserved["phase1_manifest"] == str(manifest)
            assert reserved["phase1_round_json"] == str(phase_round)
            if reserve_error is not None:
                raise reserve_error
            return SimpleNamespace(pid=7151), wrapper, log

    def preflight(batch):
        order.append("preflight")
        return SimpleNamespace(), [{"fork": 1}]

    monkeypatch.setattr(launcher, "DEV", dev)
    monkeypatch.setattr(launcher, "ROUNDS", rounds)
    monkeypatch.setattr(launcher, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setattr(launcher, "verify_sources", lambda: (Lifecycle(), Atomic()))
    monkeypatch.setattr(launcher, "preflight", preflight)
    return dev, parent, order, reserve_calls


def test_nonzero_fork_reserves_before_launch_and_publishes_same_inode_receipt(monkeypatch, tmp_path):
    dev, parent, order, reserve_calls = _install_launch_environment(monkeypatch, tmp_path)

    receipt = launcher.launch()

    receipt_path = dev / f"launch_{launcher.RID}.json"
    stored = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert order == ["prerequisite", "ledger", "preflight", "ledger", "launch"]
    assert reserve_calls and reserve_calls[0][1] == launcher.RID
    argv = reserve_calls[0][2]
    assert argv[:4] == [str(launcher.ROOT / "venv/bin/python"), "-u", str(launcher.RUNNER), "--run"]
    assert argv[4:] == [
        "--batch", "61",
        "--candidate-commit", launcher.CANDIDATE,
        "--phase1-manifest", str(parent / "phase1_manifest.json"),
        "--phase1-round-json", str(parent / "round.json"),
    ]
    assert receipt["state"] == stored["state"] == "launched"
    assert receipt["batch_pid"] == 7151
    assert stored["phase1_manifest_sha256"] == launcher.sha(parent / "phase1_manifest.json")
    assert stored["phase1_round_json_sha256"] == launcher.sha(parent / "round.json")


def test_atomic_launch_failure_publishes_failure_without_pid(monkeypatch, tmp_path):
    dev, _parent, _order, reserve_calls = _install_launch_environment(
        monkeypatch, tmp_path, reserve_error=OSError("atomic start failed")
    )

    with pytest.raises(OSError, match="atomic start failed"):
        launcher.launch()

    stored = json.loads((dev / f"launch_{launcher.RID}.json").read_text(encoding="utf-8"))
    assert reserve_calls
    assert stored["state"] == "launch_failed"
    assert "batch_pid" not in stored
    assert "pgid" not in stored


def test_ledger_drift_writes_no_receipt_and_never_launches(monkeypatch, tmp_path):
    dev, _parent, _order, reserve_calls = _install_launch_environment(
        monkeypatch, tmp_path, batch_values=(61, 62)
    )

    with pytest.raises(ValueError, match="batch ledger changed"):
        launcher.launch()

    assert reserve_calls == []
    assert not (dev / f"launch_{launcher.RID}.json").exists()


def test_receipt_identity_or_symlink_replacement_is_rejected(monkeypatch, tmp_path):
    receipt = tmp_path / "receipt.json"
    launcher._write_exclusive(receipt, {"state": "reserved"})
    identity = (receipt.stat().st_dev, receipt.stat().st_ino)
    replacement = tmp_path / "replacement.json"
    launcher._write_exclusive(replacement, {"state": "foreign"})
    replacement.replace(receipt)
    with pytest.raises(ValueError, match="identity changed"):
        launcher.publish_receipt(receipt, identity, {"state": "launched"})

    receipt.unlink()
    launcher._write_exclusive(receipt, {"state": "reserved"})
    identity = (receipt.stat().st_dev, receipt.stat().st_ino)
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == receipt or original_is_symlink(path),
    )
    with pytest.raises(ValueError, match="identity changed"):
        launcher.publish_receipt(receipt, identity, {"state": "launched"})


@pytest.mark.parametrize("failure", [
    ValueError("sealed parent invalid"),
    ValueError("candidate commit invalid"),
    ValueError("validator SHA invalid"),
])
def test_preflight_source_or_parent_failures_cannot_reserve(monkeypatch, tmp_path, failure):
    dev = tmp_path / "dev"
    dev.mkdir()
    calls = []

    class Atomic:
        def next_batch(self, root):
            calls.append("ledger")
            return 61

        def reserve_and_launch(self, *args):
            calls.append("launch")
            raise AssertionError("must not launch")

    monkeypatch.setattr(launcher, "DEV", dev)
    monkeypatch.setattr(launcher, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    monkeypatch.setattr(launcher, "verify_sources", lambda: (SimpleNamespace(prerequisite=lambda: tmp_path), Atomic()))
    monkeypatch.setattr(launcher, "preflight", lambda batch: (_ for _ in ()).throw(failure))

    with pytest.raises(ValueError, match="invalid"):
        launcher.launch()

    assert calls == ["ledger"]
    assert not (dev / f"launch_{launcher.RID}.json").exists()
