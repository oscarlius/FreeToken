import json
import hashlib
import os
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import r067d_retry2_owned as owned
from r067d_retry2_actual import Effects, UnsafeCleanupError, prefix_tail, run_child


def test_cpu_fake_uses_controller_receipt_and_full_lifecycle(tmp_path):
    receipt = owned.fake_positive(tmp_path)
    terminal = receipt["terminal"]
    assert receipt["real_plan_admission"] is False
    assert receipt["controller"]["published"]["child"] == receipt["controller"]["birth"]
    assert set(receipt["controller"]["birth"]) == {"pid", "start_ticks", "execution_id"}
    assert terminal["actual_services"] == 10 and terminal["actual_generation_calls"] == 14
    assert len([event for event in receipt["events"] if event.startswith("materialize:")]) == 10
    assert len([event for event in receipt["events"] if event.startswith("start:")]) == 10
    assert len([event for event in receipt["events"] if event.startswith("request:")]) == 14
    assert len([event for event in receipt["events"] if event.startswith("cleanup:")]) == 10
    assert receipt["gpu_lock_events"] == ["take", "idle", "idle", "release"]
    assert receipt["gpu_started"] is receipt["http_generation"] is receipt["service_started"] is False


def test_product_not_met_stops_before_the_next_tail(tmp_path):
    class DivergentEffects(owned.FakeEffects):
        def request(self, service, item, ids, arm, request_label):
            raw, window, evidence = super().request(service, item, ids, arm, request_label)
            if service["name"] in {"cold_A_p8192_t1", "cold_B_p8192_t1"}:
                evidence["sampled_token_ids"] = [8] * item["max_tokens"]
                evidence["raw_text"] = "different"
            return raw, window, evidence

    effects = DivergentEffects(tmp_path)
    with pytest.raises(RuntimeError, match="not_met"):
        run_child(owned.fake_plan(tmp_path), batch=1, effects=effects, run_dir=effects.run_dir)
    terminal = json.loads((effects.run_dir / "terminal.json").read_text())
    assert terminal["verdict"] == "not_met"
    assert terminal["actual_generation_calls"] == 5
    assert "materialize:cold_A_p8192_t64" not in effects.events


def test_effects_constructs_and_reads_real_exact_id_bytes(tmp_path):
    source = Path(__file__).resolve().parents[2] / "r067_d20_short_tail_v1" / "R067_V2_exact_inputs.json"
    binding = {"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    case = next(row for row in json.loads(source.read_text())["cases"] if (row["prefix"], row["tail"]) == (8192, 1))
    donor_sha = hashlib.sha256(struct.pack("<%di" % len(case["donor_ids"]), *case["donor_ids"])).hexdigest()
    query_sha = hashlib.sha256(struct.pack("<%di" % len(case["input_ids"]), *case["input_ids"])).hexdigest()
    service = {"name": "hot_p8192", "kind": "hot", "requests": [
        {"role": "seed", "tail": 1, "max_tokens": 2, "input_ids_sha256": donor_sha},
        {"role": "query", "tail": 1, "max_tokens": 2, "input_ids_sha256": query_sha},
    ]}
    effects = Effects(d07=owned.FakeD07(), owned=None, plan={"input_binding": binding, "services": [service]}, t17=object(), artifacts=object(), opener=object(), run_dir=tmp_path / "unique")
    assert effects.ids(service, service["requests"][0], 8192, 1) == case["donor_ids"]
    assert effects.ids(service, service["requests"][1], 8192, 1) == case["input_ids"]


def test_unsafe_cleanup_preserves_child_lock(tmp_path):
    class BrokenCleanup(owned.FakeEffects):
        def cleanup(self, service, process, arm):
            raise RuntimeError("cannot prove process cleanup")

    admission, receipt = tmp_path / "admission.json", tmp_path / "receipt.json"
    plan = owned.fake_plan(tmp_path)
    owned.put_new(admission, {"schema": "ft_r067d_retry2_admission/v1", "admit": True, "rid": owned.RID, "worktree_commit": plan["commit"], "engine_sha256": plan["engine_sha256"], "source_sha256": owned.source_manifest(), "services_max": 10, "generation_calls_max": 14, "batch": 1, "receipt_path": str(receipt)})
    d07 = owned.FakeD07()
    owned.controller(admission, popen=lambda argv, **kwargs: type("P", (), {"pid": 7})(), d07=d07, plan=plan, materialize=False)
    effects = BrokenCleanup(tmp_path)
    with pytest.raises(RuntimeError, match="unsafe cleanup preserves lock"):
        owned.child(admission, 1, receipt, d07=d07, plan=plan, effects=effects)
    assert d07.gpu_events == ["take", "idle"]
    assert (effects.run_dir / "unsafe_cleanup.json").is_file()


def test_readiness_failure_still_cleans_the_started_service(tmp_path):
    class FailingReady(owned.FakeEffects):
        def ready(self, service, process, arm):
            super().ready(service, process, arm)
            raise RuntimeError("health failed")

    effects = FailingReady(tmp_path)
    with pytest.raises(RuntimeError, match="health failed"):
        run_child(owned.fake_plan(tmp_path), batch=1, effects=effects, run_dir=effects.run_dir)
    assert effects.events[:4] == ["materialize:hot_p8192", "start:hot_p8192", "ready:hot_p8192", "cleanup:hot_p8192"]
    terminal = json.loads((effects.run_dir / "terminal.json").read_text())
    assert terminal["verdict"] == "failed_harness" and terminal["actual_generation_calls"] == 0


def test_target_ftvenv_real_plan_materializes_all_services_and_real_ids(tmp_path):
    """Target-only file-dry: all real sources, no Popen, HTTP, GPU, or lock."""
    target = Path("/data2/FreeToken")
    if not (target / "venv/bin/python").is_file():
        pytest.skip("requires target Linux FT venv and pinned source paths")

    import r067d_retry2_runner as runner

    class ControlledD07:
        @staticmethod
        def clean_environment(worktree):
            assert worktree == runner.WORKTREE
            return {"VIRTUAL_ENV": str(target / "venv"), "PYTHONPATH": "discarded-by-service-env", "PATH": os.environ["PATH"]}

        @staticmethod
        def argv_sha256(argv):
            return hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()

    plan = runner.filedry()
    run_dir = tmp_path / "receipt_bound_unique_output"
    effects = Effects(d07=ControlledD07(), owned=None, plan=plan, opener=object(), t17=object(), artifacts=object(), run_dir=run_dir)
    ids_bound = 0
    cold_schedules = 0
    arms = []
    for service in plan["services"]:
        original_plan_arm = Path(service["service_dir"])
        arm, env = effects.materialize(service)
        arms.append(arm)
        assert arm.parent == run_dir / "services" and arm.name == service["name"]
        assert arm != original_plan_arm and not str(arm).startswith(str(target / "runs/dev_R067"))
        assert Path(service["service_dir"]) == Path(service["cwd"]) == arm
        assert Path(service["argv"][5]) == arm / "r067d_retry2_startup.py"
        assert hashlib.sha256((arm / "r067d_retry2_startup.py").read_bytes()).hexdigest() == service["env"]["FT_DEV_R067D_STARTUP_SHA256"]
        assert env["VIRTUAL_ENV"] == str(target / "venv")
        assert env["PYTHONPATH"].startswith(str(arm) + ":")
        if service["kind"] == "cold":
            schedule = arm / "prefill_schedule.json"
            assert schedule.is_file() and hashlib.sha256(schedule.read_bytes()).hexdigest() == service["schedule"]["sha256"]
            assert env["FT_DEV_PREFILL_SCHEDULE"] == str(schedule)
            cold_schedules += 1
        else:
            assert "FT_DEV_PREFILL_SCHEDULE" not in env
        for item in service.get("requests") or [service["request"]]:
            prefix, tail = prefix_tail(service, item)
            ids = effects.ids(service, item, prefix, tail)
            digest = hashlib.sha256(struct.pack("<%di" % len(ids), *ids)).hexdigest()
            assert digest == item["input_ids_sha256"]
            ids_bound += 1
    assert len(arms) == len(set(arms)) == 10
    assert cold_schedules == 8 and ids_bound == 14
    assert not (run_dir / "terminal.json").exists()
