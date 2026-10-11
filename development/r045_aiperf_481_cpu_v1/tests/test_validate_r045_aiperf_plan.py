import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("r045_aiperf_plan", ROOT / "validate_r045_aiperf_plan.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def packet():
    return MODULE.load_json(ROOT / "r045_aiperf_plan.json")


def records():
    return MODULE.load_jsonl(ROOT / "inputs.jsonl")


def test_frozen_cpu_plan_validates_without_execution():
    result = MODULE.validate(packet(), records())
    assert result["status"] == "CPU_PLAN_VALID_NO_EXECUTION"
    assert result["records"] == 2


def test_validator_rejects_legacy_prerequisite():
    plan = packet()
    plan["legacy_dependency_policy"]["prerequisites"] = ["E2-R040g"]
    try:
        MODULE.validate(plan, records())
    except ValueError as error:
        assert "legacy prerequisites" in str(error)
    else:
        raise AssertionError("legacy prerequisite unexpectedly accepted")


def test_validator_rejects_execution_state_and_scope_change():
    plan = packet()
    plan["state"] = "admitted"
    try:
        MODULE.validate(plan, records())
    except ValueError as error:
        assert "planning_only" in str(error)
    else:
        raise AssertionError("execution state unexpectedly accepted")
    plan = packet()
    plan["execution_proposal"]["total_generation_calls"] = 5
    try:
        MODULE.validate(plan, records())
    except ValueError as error:
        assert "four-generation-call" in str(error)
    else:
        raise AssertionError("changed request ceiling unexpectedly accepted")


def test_validator_has_no_network_or_process_modules():
    source = (ROOT / "validate_r045_aiperf_plan.py").read_text(encoding="utf-8")
    for forbidden in ("subprocess", "socket", "requests", "httpx", "urllib"):
        assert forbidden not in source
