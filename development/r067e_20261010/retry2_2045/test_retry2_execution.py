import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("retry2_execution", HERE / "retry2_execution.py")
packet = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(packet)
runner_spec = importlib.util.spec_from_file_location("retry2_runner", HERE / "retry2_runner.py")
runner = importlib.util.module_from_spec(runner_spec); assert runner_spec.loader; runner_spec.loader.exec_module(runner)


def _seal(path: Path, value: dict):
    path.write_text(json.dumps(value, sort_keys=True))
    (path.with_name(path.name + ".sha256")).write_text(packet.sha(path))
    os.chmod(path, 0o444)
    os.chmod(path.with_name(path.name + ".sha256"), 0o444)


def _sealed_admission(tmp_path: Path, monkeypatch):
    formal = tmp_path / "formal"; formal.mkdir()
    round_path = formal / "round.json"; round_path.write_text(json.dumps({"rid": runner.T17_RID, "batch": runner.T17_BATCH, "verdict": "failed_harness"}))
    manifest = formal / "MANIFEST.sha256"; manifest.write_text("formal manifest\n")
    terminal = tmp_path / "terminal.json"; terminal.write_text(json.dumps({"rid": runner.T17_RID, "proposed_verdict": "failed_harness"}))
    for path in (round_path, manifest, terminal): os.chmod(path, 0o444)
    predecessor = {"rid": runner.T17_RID, "batch": runner.T17_BATCH, "closed_verdict": "failed_harness",
                   "round_path": str(round_path), "round_sha256": packet.sha(round_path), "manifest_path": str(manifest),
                   "manifest_sha256": packet.sha(manifest), "terminal_path": str(terminal), "terminal_sha256": packet.sha(terminal)}
    plan = {"schema": "ft_r067e_retry2_execution_packet/v1", "rid": packet.RID,
            "source_manifest": {"task": "x"}, "parent_packet": {"path": "/p", "sha256": "x"},
            "native_proof": {"path": "/n", "sha256": "x"}, "input_binding": {"path": "/i", "sha256": "x"},
            "commit": "fake-commit", "engine_sha256": "engine", "budget": {"services": 10, "generation_calls": 14, "harness_attempts_remaining": 1},
            "donor_at_p": {"8192": "a", "8256": "b"}, "worktree": str(tmp_path), "services": []}
    execution = tmp_path / "execution.json"; _seal(execution, plan)
    admission = {"schema": "ft_r067e_retry2_admission/v1", "admit": True, "rid": packet.RID,
                 "source_manifest": plan["source_manifest"], "parent_packet": plan["parent_packet"], "native_proof": plan["native_proof"],
                 "input_binding": plan["input_binding"], "worktree_commit": plan["commit"], "engine_sha256": plan["engine_sha256"],
                 "budget": plan["budget"], "predecessor_t17": predecessor, "execution_packet_path": str(execution),
                 "execution_packet_sha256": packet.sha(execution), "batch": 7, "receipt_path": str(tmp_path / "receipt.json")}
    approval = tmp_path / "admission.json"; _seal(approval, admission)
    return approval, plan


def _dump(path: Path):
    torch = pytest.importorskip("torch")
    for index, name in enumerate(packet.STATE_FILES):
        torch.save(torch.full((2, 3), index, dtype=torch.int32), path / f"donate_0001_dev_{name}.pt")


def test_engine_hash_includes_engine_slot_labels_and_all_components(tmp_path):
    _dump(tmp_path)
    before = packet.engine_donor_hash(tmp_path)
    torch = pytest.importorskip("torch")
    value = torch.load(tmp_path / "donate_0001_dev_ple_ngram_ctx.pt", weights_only=False)
    value[0, 0] += 1
    torch.save(value, tmp_path / "donate_0001_dev_ple_ngram_ctx.pt")
    assert packet.engine_donor_hash(tmp_path) != before
    assert packet.ENGINE_LABELS[2:] == ("slot_states/ple_conv", "slot_states/ple_ngram_ctx")


def test_plan_preserves_scope_input_and_binds_preguard(tmp_path, monkeypatch):
    inputs = tmp_path / "inputs.json"; inputs.write_text("{}")
    parent = {"budget": {"services": 10, "generation_calls": 14}, "commit": "c", "engine_sha256": "e", "input_binding": {"path": str(inputs), "sha256": packet.sha(inputs)},
              "services": [{"name": "hot_p8192", "kind": "hot", "service_dir": "/x/hot", "worktree": "/x/wt", "env": {}}, {"name": "hot_p8256", "kind": "hot", "service_dir": "/x/hot2", "worktree": "/x/wt", "env": {}},
                           *[{"name": f"cold_A_p{p}_t{t}", "kind": "cold", "service_dir": f"/x/cold-{p}-{t}", "worktree": "/x/wt", "env": {}} for p in (8192, 8256) for t in (1, 64)],
                           *[{"name": f"cold_B_p{p}_t{t}", "kind": "cold", "service_dir": f"/x/cold-b-{p}-{t}", "worktree": "/x/wt", "env": {}} for p in (8192, 8256) for t in (1, 64)]]}
    source = tmp_path / "parent.json"; source.write_text(json.dumps(parent))
    hot = tmp_path / "hot"
    for p in (8192, 8256):
        d = hot / f"hot_p{p}" / "state_dump"; d.mkdir(parents=True); _dump(d)
    result = packet.build_plan(source, hot)
    assert result["budget"] == {"services": 10, "generation_calls": 14, "harness_attempts_remaining": 1}
    assert result["input_binding"] == parent["input_binding"]
    cold = [x for x in result["services"] if x["kind"] == "cold"]
    assert len(cold) == 8
    assert all(x["env"]["FT_DEV_COLD_DONOR_HASH_DOMAIN"].startswith("engine-v1/") for x in cold)
    assert all(x["env"]["FT_DEV_COLD_DONOR_PRE_GUARD_RECEIPT"].endswith("cold_preguard_engine_hash.json") for x in cold)


def test_sealed_admission_rejects_writable_or_hash_changed_packet(tmp_path, monkeypatch):
    second = tmp_path / "bad-pid"; second.mkdir()
    admission, plan = _sealed_admission(second, monkeypatch)
    assert runner.validate_sealed_admission(admission, plan)["batch"] == 7
    packet_path = Path(json.loads(admission.read_text())["execution_packet_path"])
    os.chmod(packet_path, 0o644)
    with pytest.raises(RuntimeError, match="read-only regular"):
        runner.validate_sealed_admission(admission, plan)


def test_sealed_admission_rejects_writable_or_misbinding_predecessor(tmp_path, monkeypatch):
    admission, plan = _sealed_admission(tmp_path, monkeypatch)
    document = json.loads(admission.read_text())
    predecessor = document["predecessor_t17"]
    raw = Path(predecessor["terminal_path"])
    os.chmod(raw, 0o644)
    with pytest.raises(RuntimeError, match="raw terminal is not a read-only"):
        runner.validate_sealed_admission(admission, plan)
    os.chmod(raw, 0o444)
    predecessor["manifest_sha256"] = "0" * 64
    os.chmod(admission, 0o644); os.chmod(admission.with_name(admission.name + ".sha256"), 0o644); _seal(admission, document)
    with pytest.raises(RuntimeError, match="formal manifest SHA differs"):
        runner.validate_sealed_admission(admission, plan)


def test_sealed_admission_rejects_formal_kept_verdict(tmp_path, monkeypatch):
    admission, plan = _sealed_admission(tmp_path, monkeypatch)
    document = json.loads(admission.read_text())
    round_path = Path(document["predecessor_t17"]["round_path"])
    os.chmod(round_path, 0o644)
    round_path.write_text(json.dumps({"rid": runner.T17_RID, "batch": runner.T17_BATCH, "verdict": "kept"}))
    os.chmod(round_path, 0o444)
    document["predecessor_t17"]["round_sha256"] = packet.sha(round_path)
    os.chmod(admission, 0o644); os.chmod(admission.with_name(admission.name + ".sha256"), 0o644); _seal(admission, document)
    with pytest.raises(RuntimeError, match="formal closure verdict differs"):
        runner.validate_sealed_admission(admission, plan)


def test_controller_uses_parent_transport_and_publishes_child_binding(tmp_path, monkeypatch):
    admission, plan = _sealed_admission(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "filedry", lambda: plan)
    parent = runner._owned()
    d07 = parent.FakeD07()
    result = runner.controller(admission, plan=plan, d07=d07, popen=lambda argv, **kwargs: SimpleNamespace(pid=73))
    receipt = json.loads(Path(result["receipt"]).read_text())
    assert result["argv"] == runner._child_argv(admission, 7, Path(receipt["receipt_path"]) if "receipt_path" in receipt else Path(result["receipt"]))
    assert receipt["child"] == {"pid": 73, "start_ticks": 173, "execution_id": "73:173"}


def test_controller_rejects_missing_receipt_or_bad_pid_before_child(tmp_path, monkeypatch):
    admission, plan = _sealed_admission(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "filedry", lambda: plan)
    doc = json.loads(admission.read_text()); doc.pop("receipt_path")
    os.chmod(admission, 0o644); os.chmod(admission.with_name(admission.name + ".sha256"), 0o644); _seal(admission, doc)
    with pytest.raises(RuntimeError, match="lacks child binding"):
        runner.controller(admission, plan=plan)
    # Restore a sealed document and prove the parent controller rejects a PID
    # identity that cannot be bound to its spawned transport process.
    second = tmp_path / "bad-pid"; second.mkdir()
    admission, plan = _sealed_admission(second, monkeypatch)
    parent = runner._owned(); d07 = parent.FakeD07()
    d07.process_identity = lambda pid: {"pid": pid + 1, "start_ticks": 1}
    with pytest.raises(RuntimeError, match="cannot bind child PID birth"):
        runner.controller(admission, plan=plan, d07=d07, popen=lambda argv, **kwargs: SimpleNamespace(pid=74))


def test_parent_controller_then_child_runs_full_cpu_fake_effects(tmp_path, monkeypatch):
    """Transport is parent-owned; the child retains parent Effects lifecycle."""
    formal = tmp_path / "formal"; formal.mkdir()
    round_path = formal / "round.json"; round_path.write_text(json.dumps({"rid": runner.T17_RID, "batch": runner.T17_BATCH, "verdict": "failed_harness"}))
    manifest = formal / "MANIFEST.sha256"; manifest.write_text("formal manifest\n")
    terminal = tmp_path / "terminal.json"; terminal.write_text(json.dumps({"rid": runner.T17_RID, "proposed_verdict": "failed_harness"}))
    for path in (round_path, manifest, terminal): os.chmod(path, 0o444)
    predecessor = {"rid": runner.T17_RID, "batch": runner.T17_BATCH, "closed_verdict": "failed_harness", "round_path": str(round_path), "round_sha256": packet.sha(round_path), "manifest_path": str(manifest), "manifest_sha256": packet.sha(manifest), "terminal_path": str(terminal), "terminal_sha256": packet.sha(terminal)}
    parent = runner._owned()
    plan = parent.fake_plan(tmp_path)
    plan.update({"schema": "ft_r067e_retry2_execution_packet/v1", "source_manifest": {"task": "x"},
                 "parent_packet": {"path": "/p", "sha256": "x"}, "native_proof": {"path": "/n", "sha256": "x"},
                 "input_binding": {"path": "/i", "sha256": "x"}, "budget": {"services": 10, "generation_calls": 14, "harness_attempts_remaining": 1},
                 "donor_at_p": {"8192": "a", "8256": "b"}})
    execution = tmp_path / "execution-lifecycle.json"; _seal(execution, plan)
    approval = tmp_path / "admission-lifecycle.json"
    doc = {"schema": "ft_r067e_retry2_admission/v1", "admit": True, "rid": packet.RID,
           "source_manifest": plan["source_manifest"], "parent_packet": plan["parent_packet"], "native_proof": plan["native_proof"],
           "input_binding": plan["input_binding"], "worktree_commit": plan["commit"], "engine_sha256": plan["engine_sha256"], "budget": plan["budget"],
           "predecessor_t17": predecessor, "execution_packet_path": str(execution), "execution_packet_sha256": packet.sha(execution),
           "batch": 8, "receipt_path": str(tmp_path / "receipt-lifecycle.json")}
    _seal(approval, doc)
    monkeypatch.setattr(runner, "filedry", lambda: plan)
    d07 = parent.FakeD07()
    d07.release_d07_gpu_lock = lambda owner: d07.gpu_events.append("release")
    launch = runner.controller(approval, plan=plan, d07=d07, popen=lambda argv, **kwargs: SimpleNamespace(pid=75))
    bound = runner._configured_parent(plan)
    effects = bound.FakeEffects(tmp_path)
    terminal_result = bound.child(approval, 8, Path(launch["receipt"]), d07=d07, plan=plan, effects=effects)
    assert terminal_result["actual_services"] == 10 and terminal_result["actual_generation_calls"] == 14
    assert len([event for event in effects.events if event.startswith("start:")]) == 10
    assert len([event for event in effects.events if event.startswith("request:")]) == 14
    assert len([event for event in effects.events if event.startswith("cleanup:")]) == 10


def test_e2_launch_trailing_run_is_accepted_for_actual_owned_child_argv(tmp_path):
    admission, _plan = _sealed_admission(tmp_path, pytest.MonkeyPatch())
    receipt = tmp_path / "receipt.json"
    child_argv = runner._child_argv(admission, 164, receipt)
    args = runner.e2_launch_wrapped_child_args(child_argv)
    assert args.run and args.owned_child and args.batch == 164 and args.receipt == receipt


@pytest.mark.skipif(sys.platform != "linux", reason="actual D07 receipt replay requires /proc")
def test_configured_d07_replays_real_child_receipt_and_rejects_candidate_mismatch(tmp_path):
    plan = {"commit": "b861-retry2-candidate", "source_manifest": {}}
    d07 = runner.configured_d07(plan)
    assert d07.RID == packet.RID and d07.CANDIDATE == plan["commit"]
    receipt_path = tmp_path / "receipt.json"
    birth = d07.process_birth()
    argv = runner._child_argv(tmp_path / "admission.json", 166, receipt_path)
    receipt = {"schema": "ft_r067e_owned_launch/v1", "state": "launched", "rid": packet.RID, "batch": 166,
               "batch_pid": birth["pid"], "candidate_commit": plan["commit"], "argv_sha256": d07.argv_sha256(argv), "child": birth}
    receipt_path.write_text(json.dumps(receipt))
    assert d07.require_child_receipt(receipt_path, 166, tmp_path, tmp_path, rid=packet.RID, expected_argv=argv, schema="ft_r067e_owned_launch/v1")["child"] == birth
    receipt["candidate_commit"] = "wrong"; receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(RuntimeError, match="binding differs"):
        d07.require_child_receipt(receipt_path, 166, tmp_path, tmp_path, rid=packet.RID, expected_argv=argv, schema="ft_r067e_owned_launch/v1")
