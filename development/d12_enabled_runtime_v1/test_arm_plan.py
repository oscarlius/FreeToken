"""Actual candidate argument/meta/worker setup; no service or model process."""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

if not os.environ.get("FT_D12_NATIVE_SOURCE"):
    pytest.skip("requires the pinned Linux candidate/config/dependency packages", allow_module_level=True)

import arm_plan


def options(tmp_path):
    return dict(candidate=Path(os.environ["FT_D12_NATIVE_SOURCE"]), runtime=Path(__file__).resolve().parent,
                d16=Path(os.environ["FT_D12_D16_RUNTIME"]), d03=Path(os.environ["FT_D12_D03_ROOT"]),
                inputs=Path(os.environ["FT_D12_TEST_INPUT_BUNDLE"]), service_root=tmp_path / "prospective-services",
                execution_prefix="d12-file-dry-proposal", ports=[18100, 18102, 18104, 18106])


def test_four_arm_native_file_dry_and_no_runtime_side_effects(tmp_path, monkeypatch):
    monkeypatch.setenv("FT_DEV_ROUTE_TRACE", "/untrusted/inherited")
    monkeypatch.setenv("FT_DEV_PREFILL_SCHEDULE", "/untrusted/schedule")
    monkeypatch.setenv("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", "/untrusted/fixed-generations")
    monkeypatch.setenv("FREETOKEN_MAMBA_SSM_DTYPE", "bfloat16")
    monkeypatch.setenv("FREETOKEN_DISABLE_OVERLAP_SCHEDULING", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "CPU-FIXTURE-DO-NOT-PROPAGATE")
    plan = arm_plan.build_plan(**options(tmp_path))
    assert not Path(plan["service_root"]).exists()
    assert plan["planned_services"] == 4 and plan["planned_requests"] == 12 and plan["approved_new_services"] == 0
    result = arm_plan.file_dry(plan, tmp_path / "file-dry")
    assert set(result["native_probes"]) == {name for name, _, _ in arm_plan.ARMS}
    reference = None
    for name, layer_major, threshold in arm_plan.ARMS:
        arm = plan["arms"][name]
        env = arm["environment"]
        assert env["FREETOKEN_MAMBA_SSM_DTYPE"] == "float32"
        assert env["FREETOKEN_DISABLE_OVERLAP_SCHEDULING"] == "0"
        assert not {"FT_DEV_ROUTE_TRACE", "FT_DEV_PREFILL_SCHEDULE", "FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", "OPENAI_API_KEY"} & env.keys()
        assert "CPU-FIXTURE-DO-NOT-PROPAGATE" not in json.dumps(plan)
        row = result["native_probes"][name]
        raw = Path(row["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == row["sha256"]
        probe = json.loads(raw)
        assert probe["cuda_initialized"] is False and probe["model_service_started"] is False
        assert probe["parsed"]["prefill_layer_major"] is layer_major
        assert probe["parsed"]["moe_prefill_routed_only_max_tokens"] == threshold
        assert probe["parsed"]["moe_prefill_overlap"] is False
        shared = {key: probe[key] for key in ("target_geometry", "natural_policy", "tail_policy")}
        if reference is None:
            reference = shared
        assert reference == shared
    assert not Path(plan["service_root"]).exists()
    assert result["host_proc_observer_ready"] is False and result["formal_launch_authorized"] is False
    before = (tmp_path / "file-dry/file-dry.json").read_bytes()
    with pytest.raises(FileExistsError):
        arm_plan.file_dry(plan, tmp_path / "file-dry")
    assert (tmp_path / "file-dry/file-dry.json").read_bytes() == before


@pytest.mark.parametrize("fault", ["overlapping_ports", "shared_endpoint", "ephemeral_port", "bool_port", "execution_id", "occupied_output"])
def test_invalid_launch_identity_rejected_before_file_dry(tmp_path, fault):
    kwargs = options(tmp_path)
    if fault == "overlapping_ports": kwargs["ports"][1] = kwargs["ports"][0] + 1
    elif fault == "shared_endpoint": kwargs["ports"][0] = 8095
    elif fault == "ephemeral_port": kwargs["ports"][0] = 40000
    elif fault == "bool_port": kwargs["ports"][0] = True
    elif fault == "execution_id": kwargs["execution_prefix"] = "E2-R062-gate-D12"
    elif fault == "occupied_output": kwargs["service_root"].mkdir()
    with pytest.raises(ValueError):
        arm_plan.build_plan(**kwargs)


@pytest.mark.parametrize("fault", ["threshold", "layer_major", "argv", "env_route_trace", "env_ssm", "source_hash", "authorization", "roles"])
def test_modified_plan_rejected_before_any_subprocess(tmp_path, monkeypatch, fault):
    plan = arm_plan.build_plan(**options(tmp_path))
    plan = copy.deepcopy(plan)
    enabled = plan["arms"]["enabled"]
    if fault == "threshold": enabled["threshold"] = 512
    elif fault == "layer_major": enabled["layer_major"] = False
    elif fault == "argv": enabled["argv"].append("--shell-mode")
    elif fault == "env_route_trace": enabled["environment"]["FT_DEV_ROUTE_TRACE"] = "/tmp/trace"
    elif fault == "env_ssm": enabled["environment"]["FREETOKEN_MAMBA_SSM_DTYPE"] = "bfloat16"
    elif fault == "source_hash": plan["source_sha256"][str(Path(__file__).with_name("worker_capture.py"))] = "0" * 64
    elif fault == "authorization": plan["formal_launch_authorized"] = True
    elif fault == "roles": plan["comparisons"]["feature"] = ["ordinary_reference", "enabled"]
    original = arm_plan.subprocess.Popen

    def forbid_probe(argv, *args, **kwargs):
        if argv[0] != "git":
            pytest.fail("modified plan reached a subprocess")
        return original(argv, *args, **kwargs)

    monkeypatch.setattr(arm_plan.subprocess, "Popen", forbid_probe)
    with pytest.raises(ValueError, match="plan changed"):
        arm_plan.file_dry(plan, tmp_path / "rejected-file-dry")
    assert not (tmp_path / "rejected-file-dry").exists()
