import copy
import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / "p1_snapshot_prepare.py"
SPEC = importlib.util.spec_from_file_location("p1_snapshot_prepare", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SHA = "a" * 64
COMMIT = "b" * 40


def process(index):
    snapshot = {"uid": f"donor-{index}", "slot": index + 10, "device_tokens": 8192,
                "successful_snapshot_count": 1}
    return {
        "process_id": f"p{index}", "commit": COMMIT,
        "source_bindings": {"serve_cmd_sha256": SHA, "startup_sha256": SHA,
                            "runner_sha256": SHA, "compiled_extensions_sha256": SHA,
                            "tokenizer_source_sha256": SHA},
        "decode_snapshot": snapshot,
        "donation": {key: snapshot[key] for key in ("uid", "slot", "device_tokens")},
        "restore": {"uid": f"consumer-{index}", "slot": index + 30,
                    "source_slot": index + 10, "device_tokens": 8192},
        "admission": {"uid": f"consumer-{index}", "cached_tokens": 8192, "prompt_tokens": 8257},
        "consumer": {"uid": f"consumer-{index}", "finished": True, "completion_tokens": 128,
                     "prefix_input_ids_int32le_sha256": SHA, "raw_response_sha256": SHA},
    }


def good():
    return {
        "schema": MODULE.SCHEMA,
        "base": {"commit": COMMIT, "code_version": "E2-base.1@" + COMMIT[:7],
                 "accepted_e2_base1_receipt_sha256": SHA},
        "t16_default_gate": {"verdict": "kept", "commit": COMMIT, "receipt_sha256": SHA},
        "tokenized_input": {"input_ids_int32le_sha256": SHA, "trace_source_sha256": SHA,
                            "tokenizer_source_sha256": SHA, "input_tokens": 8193},
        "processes": [process(1), process(2), process(3)],
    }


def test_accepts_exact_three_real_evidence_shaped_chains():
    result = MODULE.validate(good())
    assert result["positive_decode_snapshot_coverage"] is True
    assert [item["process_id"] for item in result["processes"]] == ["p1", "p2", "p3"]


@pytest.mark.parametrize("mutate, message", [
    (lambda value: value["processes"][0]["decode_snapshot"].update(successful_snapshot_count=0), "positive integer"),
    (lambda value: value["processes"].pop(), "exactly three"),
    (lambda value: value["processes"][0]["donation"].update(slot=99), "donation does not bind"),
    (lambda value: value["processes"][0]["restore"].update(source_slot=99), "restore source slot"),
    (lambda value: value["processes"][0]["restore"].update(uid="donor-1"), "consumer UID"),
    (lambda value: value["processes"][0]["admission"].update(cached_tokens=0), "admission cache length"),
    (lambda value: value["processes"][0]["consumer"].update(prefix_input_ids_int32le_sha256="c" * 64), "prefix IDs"),
    (lambda value: value["processes"][1].update(commit="c" * 40), "commit differs"),
    (lambda value: value["t16_default_gate"].update(verdict="pending_review"), "default T16 gate"),
])
def test_rejects_zero_or_unbound_or_unaccepted_evidence(mutate, message):
    evidence = good()
    mutate(evidence)
    with pytest.raises(ValueError, match=message):
        MODULE.validate(evidence)


def test_does_not_mutate_the_input_evidence():
    evidence = good()
    original = copy.deepcopy(evidence)
    MODULE.validate(evidence)
    assert evidence == original

