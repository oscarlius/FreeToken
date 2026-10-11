import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


STAGE_PATH = Path(__file__).resolve().parents[1] / "d16_path_readers_stage.py"
SPEC = importlib.util.spec_from_file_location("d16_path_readers_stage_test", STAGE_PATH)
stage_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(stage_module)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frozen_stage(tmp_path):
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "source.py").write_text("source\n")
    (stage / "candidate_binding.log").write_text('{"cuda_initialized": false}\n')
    (stage / "regression.log").write_text("35 passed in 0.10s\n")
    sources = {"source.py": digest(stage / "source.py")}
    files = {path.relative_to(stage).as_posix(): digest(path) for path in stage.iterdir() if path.is_file()}
    candidate_tree = str(tmp_path / "candidate")
    report = {
        "schema": stage_module.SCHEMA,
        "verdict": "PASS",
        "gpu_started": False,
        "requests_sent": False,
        "sources": sources,
        "files": files,
        "candidate": {"commit": "commit", "clean": True,
                      "freetoken": str(Path(candidate_tree) / "python/freetoken/__init__.py"),
                      "cuda_initialized": False},
        "steps": {name: {"returncode": 0, "log_sha256": files[f"{name}.log"]}
                  for name in ("candidate_binding", "regression")},
        "passed": 35,
    }
    (stage / "cpu_validation.json").write_text(json.dumps(report))
    return stage, sources, candidate_tree


def test_existing_stage_replays_declared_logs_before_reuse(tmp_path):
    stage, sources, candidate_tree = frozen_stage(tmp_path)
    report = stage_module.validate_existing_stage(
        stage, sources, candidate_tree=candidate_tree, candidate_commit="commit", require_immutable=False)
    assert report["passed"] == 35

    (stage / "regression.log").write_text("35 passed in 0.10s\n1 failed\n")
    with pytest.raises(ValueError, match="declared files differ"):
        stage_module.validate_existing_stage(
            stage, sources, candidate_tree=candidate_tree, candidate_commit="commit", require_immutable=False)


def test_existing_stage_refuses_nonpass_receipt(tmp_path):
    stage, sources, candidate_tree = frozen_stage(tmp_path)
    report_path = stage / "cpu_validation.json"
    report = json.loads(report_path.read_text())
    report["verdict"] = "FAIL"
    report_path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="passed matching CPU receipt"):
        stage_module.validate_existing_stage(
            stage, sources, candidate_tree=candidate_tree, candidate_commit="commit", require_immutable=False)


def test_freeze_excludes_unreviewed_sampler_and_shared_readme():
    files = stage_module.source_files()
    assert "scripts/equiv_suite/retained_d03.py" in files
    assert "tests/scripts/test_equiv_retained_d03.py" in files
    assert "scripts/equiv_suite/sampler_capture.py" not in files
    assert "scripts/equiv_suite/README.md" not in files
    assert "tests/scripts/test_equiv_sampler_capture.py" not in files
