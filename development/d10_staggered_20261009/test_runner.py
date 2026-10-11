import json
import shutil
from pathlib import Path

import pytest

import runner


def fixture_dir(tmp_path: Path) -> Path:
    shutil.copy2(runner.R045 / "inputs.jsonl", tmp_path / "inputs.jsonl")
    shutil.copy2(runner.ROOT / "inputs_ignore_eos256.jsonl", tmp_path / "inputs_ignore_eos256.jsonl")
    return tmp_path


def test_plan_validates_seal_and_frozen_inputs():
    result = runner.plan()
    assert result["prediction_seal_sha256"] == "3216e1551fba79e09a3cd6b0d24f2ac63e991cdab0bed5ea7c60c7c9179ab7b1"
    assert result["aiperf"]["input_validation"]["prompt_identity"] is True
    assert len(result["aiperf"]["original_waves"]) == 2


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(text="altered"),
    lambda x: x["extra"].update(temperature=0.1),
    lambda x: x["extra"].update(top_p=0.9),
    lambda x: x["extra"].update(ignore_eos=False),
])
def test_variant_rejects_non_variant_delta(tmp_path, mutation):
    base = fixture_dir(tmp_path)
    rows = [json.loads(line) for line in (base / "inputs_ignore_eos256.jsonl").read_text().splitlines()]
    mutation(rows[0])
    (base / "inputs_ignore_eos256.jsonl").write_text("\n".join(json.dumps(x) for x in rows) + "\n")
    with pytest.raises((AssertionError, ValueError)):
        runner.validate_inputs(base)


def test_variant_rejects_byte_mutation(tmp_path):
    base = fixture_dir(tmp_path)
    p = base / "inputs_ignore_eos256.jsonl"
    p.write_bytes(p.read_bytes() + b"\n")
    with pytest.raises((AssertionError, ValueError)):
        runner.validate_inputs(base)


def test_prediction_seal_rejects_tamper(tmp_path):
    manifest = runner.ROOT / "prediction_manifest.json"
    seal = runner.ROOT / "PREDICTION_SEAL.json"
    copied = tmp_path / "prediction_manifest.json"
    copied.write_bytes(manifest.read_bytes() + b" ")
    expected = json.loads(seal.read_text())["sha256"]
    assert runner.hashlib.sha256(copied.read_bytes()).hexdigest() != expected
