"""Exercise the real D16 sealed source-review verifier against copied CPU bytes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


collector = load("d16_source_review_collector", ROOT / "d16_native_process_collection.py")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def readonly_tree(root):
    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(0o444 if path.is_file() else 0o555)
    root.chmod(0o555)


def materialize(tmp_path):
    """Build a sealed CPU fixture from the verifier's actual import graph."""
    try:
        import t17_d14_gpu as gpu
        import equiv_suite.service_capture as capture
        import equiv_suite.service_capture_startup as startup
        import equiv_suite.sampler_capture as sampler
        import equiv_suite.native_workloads as reader
    except ImportError as error:
        pytest.skip("sealed D16 export dependencies unavailable: " + str(error))
    exact_ids = ROOT / "t17_d14_exact_ids.py"
    wrapper = ROOT / "d16_exact_service_startup.py"
    if not exact_ids.is_file() or not wrapper.is_file():
        pytest.skip("sealed D16 producer has not materialized exact-ID sources")
    actual = {
        "adapter": ROOT / "d16_native_process_collection.py", "startup_wrapper": wrapper,
        "workloads": Path(collector.workloads.__file__), "runner": Path(collector.retained.__file__), "gpu_run": Path(gpu.__file__),
        "observe": ROOT / "t17_d14_observe.py", "artifacts": ROOT / "t17_d14_artifacts.py",
        "exact_ids": exact_ids, "base_lifecycle": ROOT / "t16_full_tail_base_runner.py",
        "launch_protocol": ROOT / collector.retained.T16_LAUNCH_PROTOCOL,
        "capture": Path(capture.__file__), "capture_startup": Path(startup.__file__),
        "sampler_capture": Path(sampler.__file__), "reader": Path(reader.__file__),
    }
    if any(not path.is_file() for path in actual.values()):
        pytest.skip("sealed D16 producer source set is incomplete")
    cpu_root = tmp_path / "cpu_export"; source_root = cpu_root / "sources"; source_root.mkdir(parents=True)
    files, declared = {}, {}
    for name, source in actual.items():
        rel = Path("sources") / (name + ".py")
        target = cpu_root / rel
        target.write_bytes(source.read_bytes())
        digest = sha(source)
        files[rel.as_posix()] = digest
        declared[name] = {"path": str(source.resolve()), "sha256": digest, "cpu_inventory_path": rel.as_posix()}
    report = cpu_root / "cpu_validation.json"
    report.write_text(json.dumps({"schema": "ft_d16_exact_startup_cpu/v1", "verdict": "PASS", "fixture_only": True,
                                  "gpu_started": False, "model_admitted": False, "files": files}, sort_keys=True))
    review_root = tmp_path / "independent_review"; review_root.mkdir()
    review = review_root / "review.json"
    review.write_text(json.dumps({"schema": "ft_d16_collector_source_review/v1", "scope": "owned-gpu-test-startup-only",
        "source_execution_ready": True, "model_admitted": False, "source_files": declared,
        "cpu_report": str(report.resolve()), "cpu_report_sha256": sha(report), "fixture_only": True}, sort_keys=True))
    readonly_tree(cpu_root); readonly_tree(review_root)
    return {"fixture_root": tmp_path, "review": review, "report": report, "cpu_root": cpu_root, "declared": declared}


def thaw_fixture(case, path):
    """Unseal only one known fixture member; never walk ancestors."""
    root = case["fixture_root"].resolve()
    target = Path(path).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise AssertionError("test attempted to thaw outside tmp_path") from error
    if target.is_dir():
        target.chmod(0o755)
    else:
        target.parent.chmod(0o755)
        target.chmod(0o644)


def rewrite_review(case, mutate):
    thaw_fixture(case, case["review"])
    data = json.loads(case["review"].read_text()); mutate(data)
    case["review"].write_text(json.dumps(data, sort_keys=True)); readonly_tree(case["review"].parent)
    return sha(case["review"])


def rewrite_report(case, mutate):
    thaw_fixture(case, case["report"])
    data = json.loads(case["report"].read_text()); mutate(data)
    case["report"].write_text(json.dumps(data, sort_keys=True)); readonly_tree(case["report"].parent)
    return rewrite_review(case, lambda document: document.update(cpu_report_sha256=sha(case["report"])))


def test_sealed_cpu_fixture_calls_real_verifier_and_stays_non_admitting(tmp_path):
    case = materialize(tmp_path)
    result = collector.verify_source_review(ROOT / "d16_exact_service_startup.py", case["review"], sha(case["review"]))
    assert result["model_admitted"] is False
    assert result["cpu_report_sha256"] == sha(case["report"])


@pytest.mark.parametrize("mutation, match", [
    (lambda doc: doc.update(schema="wrong"), "source readiness review"),
    (lambda doc: doc["source_files"]["adapter"].update(path="/wrong/source.py"), "dependency origin"),
    (lambda doc: doc["source_files"]["adapter"].update(sha256="0" * 64), "dependency SHA"),
])
def test_review_document_tampering_is_rejected(tmp_path, mutation, match):
    case = materialize(tmp_path)
    pinned = rewrite_review(case, mutation)
    with pytest.raises(ValueError, match=match):
        collector.verify_source_review(ROOT / "d16_exact_service_startup.py", case["review"], pinned)


def test_wrong_caller_pinned_review_sha_is_rejected(tmp_path):
    case = materialize(tmp_path)
    with pytest.raises(ValueError, match="review SHA"):
        collector.verify_source_review(ROOT / "d16_exact_service_startup.py", case["review"], "0" * 64)


def test_cpu_inventory_digest_and_source_cpu_mismatch_are_rejected(tmp_path):
    case = materialize(tmp_path)
    pinned = rewrite_report(case, lambda report: report["files"].update({"sources/adapter.py": "0" * 64}))
    with pytest.raises(ValueError, match="CPU source inventory"):
        collector.verify_source_review(ROOT / "d16_exact_service_startup.py", case["review"], pinned)


def test_source_vs_cpu_copy_mismatch_rejects_after_report_and_review_repinned(tmp_path):
    case = materialize(tmp_path)
    copied = case["cpu_root"] / "sources" / "adapter.py"
    thaw_fixture(case, copied)
    copied.write_bytes(copied.read_bytes() + b"# fixture CPU-copy mismatch\n")
    readonly_tree(case["cpu_root"])
    pinned = rewrite_report(case, lambda report: report["files"].update({"sources/adapter.py": sha(copied)}))
    with pytest.raises(ValueError, match="source.*CPU|CPU.*source"):
        collector.verify_source_review(ROOT / "d16_exact_service_startup.py", case["review"], pinned)


@pytest.mark.parametrize("target", ["review", "report"])
def test_writable_sealed_parent_is_rejected(tmp_path, target):
    case = materialize(tmp_path)
    target_path = case[target]
    thaw_fixture(case, target_path.parent)
    with pytest.raises(ValueError, match="source review tree must be sealed|CPU source report directory must be sealed"):
        collector.verify_source_review(ROOT / "d16_exact_service_startup.py", case["review"], sha(case["review"]))
