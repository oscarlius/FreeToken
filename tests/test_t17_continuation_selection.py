import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

SOURCE_ROOT = Path(__file__).parents[1]
if (SOURCE_ROOT / "development").is_dir():
    SOURCE_ROOT = SOURCE_ROOT / "development"
MODULE = SOURCE_ROOT / "t17_continuation_selection.py"
spec = importlib.util.spec_from_file_location("selection", MODULE); selection = importlib.util.module_from_spec(spec); spec.loader.exec_module(selection)
def inputs():
    rows = []
    for length in selection.BOUNDARIES:
        donor = [length] * (length + 1)
        for tail in selection.TAILS:
            query = donor + [tail] * (tail - 1)
            rows.append({"name": f"prefix-{length}-tail-{tail}", "length": length, "tail": tail,
                         "donor": donor, "query": query,
                         "donor_input_ids_sha256": selection._token_sha(donor), "input_ids_sha256": selection._token_sha(query)})
    return {"schema": "ft_t17_continuation_inputs/v1", "cases": rows}


def git(command, root):
    subprocess.run(["git", "-C", str(root), *command], check=True, capture_output=True)


def repo(tmp_path, change=False):
    root = tmp_path / "repo"; root.mkdir(parents=True); git(["init"], root); git(["config", "user.email", "t@example.test"], root); git(["config", "user.name", "T"], root)
    target = root / "python" / "freetoken" / "engine"; target.mkdir(parents=True); (target / "x.py").write_text("one\n"); git(["add", "."], root); git(["commit", "-m", "base"], root)
    base = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if change: (root / "python" / "freetoken" / "engine" / "x.py").write_text("two\n")
    git(["add", "."], root); git(["commit", "--allow-empty", "-m", "candidate"], root)
    candidate = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    return root, base, candidate


def test_t17_always_uses_real_28_and_only_sample4_cold_envelope():
    result = selection.select(inputs(), run_kind="t17", cases="all", envelope_cases="sample4", assigned_rid="E2-R035")
    assert len(result["measurement_cases"]) == 28
    assert result["ordinary_cold_envelope_cases"] == list(selection.SAMPLE4)
    assert result["admitted"] is False and result["requests_sent"] is False
    with pytest.raises(ValueError, match="all 28"): selection.select(inputs(), run_kind="t17", cases="t20-sample4", envelope_cases="none")


def test_realinput28_and_assigned_rid_fail_closed_on_tamper():
    value = inputs(); value["cases"][0]["input_ids_sha256"] = "bad"
    with pytest.raises(ValueError, match="byte-bound"): selection.select(value, run_kind="t17", cases="all", envelope_cases="none")
    with pytest.raises(ValueError, match="M-assigned"): selection.validate_assigned_rid("E2-R041")
    value = inputs(); value["cases"].pop()
    with pytest.raises(ValueError, match="28"): selection.select(value, run_kind="t17", cases="all", envelope_cases="none")
    receipt = SOURCE_ROOT / "t17_continuation_inputs_cpu_fd6362813705.json"
    with pytest.raises(ValueError, match="raw document SHA"): selection.load_realinput28(receipt)


def retained_review(tmp_path, document=None, *, reuse_permitted=True):
    document = document or inputs()
    source = tmp_path / "E2-R036"; (source / "cases").mkdir(parents=True)
    computed = []
    rows = {row["name"]: row for row in document["cases"]}
    retained_names = [f"prefix-{length}-tail-{tail}" for length in selection.BOUNDARIES[:2] for tail in selection.TAILS]
    for position, name in enumerate(retained_names, start=1):
        row = rows[name]
        case_path = source / "cases" / (name + ".json")
        schedule_path = source / "schedules" / name / "schedule.json"
        schedule_path.parent.mkdir(parents=True)
        case_path.write_text(json.dumps({"case": name, "result": {"verdict": selection.RETAINED_CASE_VERDICT}}))
        schedule_path.write_text(json.dumps({"case": name, "schedule": "actual"}))
        computed.append({"position": position, "case": name,
                         "input_ids_sha256": row["input_ids_sha256"],
                         "verdict": selection.RETAINED_CASE_VERDICT,
                         "case_doc_sha256": selection._sha(case_path.read_bytes()),
                         "schedule_sha256": selection._sha(schedule_path.read_bytes())})
    value = {"schema": "ft_t17_retained_cases_review/v1", "source_rid": "E2-R036",
             "source_candidate": selection.RETAINED_SOURCE_CANDIDATE,
             "target_candidate": selection.RETAINED_TARGET_CANDIDATE,
             "source_round": str(source.resolve()), "admitted": False, "model_accepted": False,
             "reuse_permitted": reuse_permitted, "computed_cases": computed}
    review = tmp_path / "retained-review.json"; review.write_text(json.dumps(value, sort_keys=True))
    return review, selection._sha(review.read_bytes()), source, value


def test_remaining_requires_reviewed_exact_r036_prefix_and_selects_only_the_last14(tmp_path):
    document = inputs(); document["cases"] = document["cases"][7:] + document["cases"][:7]
    review, digest, _, _ = retained_review(tmp_path, document)
    result = selection.select(document, run_kind="t17", cases="remaining", envelope_cases="sample4",
                              assigned_rid="E2-R038", resume_review=review,
                              resume_review_sha256=digest,
                              target_candidate=selection.RETAINED_TARGET_CANDIDATE)
    assert result["measurement_cases"] == [f"prefix-{length}-tail-{tail}" for length in selection.BOUNDARIES[2:] for tail in selection.TAILS]
    assert result["ordinary_cold_envelope_cases"] == list(selection.SAMPLE4[2:])
    assert result["retained_review"]["retained_cases"] == [f"prefix-{length}-tail-{tail}" for length in selection.BOUNDARIES[:2] for tail in selection.TAILS]
    assert result["admitted"] is False and result["requests_sent"] is False


def test_remaining_rejects_unpermitted_tampered_gapped_or_different_target_review(tmp_path):
    document = inputs()
    review, digest, source, receipt = retained_review(tmp_path, document, reuse_permitted=False)
    with pytest.raises(ValueError, match="explicitly permit"):
        selection.select(document, run_kind="t17", cases="remaining", envelope_cases="none",
                         assigned_rid="E2-R038", resume_review=review, resume_review_sha256=digest,
                         target_candidate=selection.RETAINED_TARGET_CANDIDATE)

    review, digest, source, receipt = retained_review(tmp_path / "tamper", document)
    (source / "schedules" / document["cases"][0]["name"] / "schedule.json").write_text("tampered")
    with pytest.raises(ValueError, match="bytes differ"):
        selection.select(document, run_kind="t17", cases="remaining", envelope_cases="none",
                         assigned_rid="E2-R038", resume_review=review, resume_review_sha256=digest,
                         target_candidate=selection.RETAINED_TARGET_CANDIDATE)

    review, digest, _, receipt = retained_review(tmp_path / "gap", document)
    receipt["computed_cases"][5]["position"] = 7
    review.write_text(json.dumps(receipt, sort_keys=True)); digest = selection._sha(review.read_bytes())
    with pytest.raises(ValueError, match="continuous canonical"):
        selection.select(document, run_kind="t17", cases="remaining", envelope_cases="none",
                         assigned_rid="E2-R038", resume_review=review, resume_review_sha256=digest,
                         target_candidate=selection.RETAINED_TARGET_CANDIDATE)

    review, digest, _, _ = retained_review(tmp_path / "target", document)
    with pytest.raises(ValueError, match="explicit a9"):
        selection.select(document, run_kind="t17", cases="remaining", envelope_cases="none",
                         assigned_rid="E2-R038", resume_review=review, resume_review_sha256=digest,
                         target_candidate="0" * 40)
    with pytest.raises(ValueError, match="only valid"):
        selection.select(document, run_kind="t17", cases="all", envelope_cases="none",
                         assigned_rid="E2-R038", resume_review=review, resume_review_sha256=digest)


def r041_proof(tmp_path, **overrides):
    values = {
        "r041_round": tmp_path / "r041",
        "r041_independent_review": tmp_path / "review.json",
        "caller_ir_sha256": "1" * 64,
        "accepted_t17_path": tmp_path / "accepted-t17",
        "accepted_t17_review": tmp_path / "accepted-review.json",
        "expected_tag": "E2-base.1@2396728",
        "expected_d17_commit": "2" * 40,
        "expected_d17_worktree": "/data2/FreeToken/wt/e2d17",
        "expected_gate_case_sha256": "3" * 64,
        "expected_artifacts_sha256": "4" * 64,
        "expected_t16_runner_sha256": "5" * 64,
        "expected_parser_sha256": "6" * 64,
        "expected_d04_checker_sha256": "7" * 64,
        "expected_verifier_sha256": "8" * 64,
    }
    values.update(overrides)
    return values


def verified_result(document, *, mismatch=None):
    rows = {row["name"]: row for row in document["cases"]}
    result = {
        "permit": True,
        "admitted": False,
        "model_admitted": False,
        "r041_result_sha256": "9" * 64,
        "cases": {name: {"input_ids_sha256": rows[name]["input_ids_sha256"]} for name in selection.SAMPLE4},
    }
    if mismatch:
        result["cases"][mismatch]["input_ids_sha256"] = "0" * 64
    return result


def test_t20_missing_or_unpinned_r041_proof_stays_all28(tmp_path):
    root, base, candidate = repo(tmp_path, change=True)
    missing=selection.select(inputs(), run_kind="t20", cases="t20-sample4", envelope_cases="sample4", d17_worktree=root, d17_base=base, d17_candidate=candidate)
    assert len(missing["measurement_cases"]) == 28 and missing["r041_proof"] is None
    bad=selection.select(inputs(), run_kind="t20", cases="t20-sample4", envelope_cases="sample4", **r041_proof(tmp_path, expected_verifier_sha256="0" * 64))
    assert len(bad["measurement_cases"]) == 28 and bad["r041_proof"] is None


def test_t20_does_not_upgrade_a_bare_permit_json(tmp_path):
    # A JSON object claiming permit is merely an untrusted round path.  The
    # independently pinned closure verifier must still recompute it.
    bare = tmp_path / "permit.json"
    bare.write_text(json.dumps({"permit": True, "cases": list(selection.SAMPLE4)}))
    result=selection.select(inputs(), run_kind="t20", cases="t20-sample4", envelope_cases="sample4", **r041_proof(tmp_path, r041_round=bare, expected_verifier_sha256=selection._sha((SOURCE_ROOT / "t20_r041_sample4_closure.py").read_bytes())))
    assert len(result["measurement_cases"]) == 28 and result["r041_proof"] is None


def test_t20_verified_r041_selects_exact_sample4_even_with_diagnostic_diff(tmp_path, monkeypatch):
    document = inputs()
    root, base, candidate = repo(tmp_path, change=True)

    class VerifiedClosure:
        @staticmethod
        def verify_sealed_startup(**kwargs):
            assert kwargs["r041_round"] == r041_proof(tmp_path)["r041_round"]
            return verified_result(document)

    monkeypatch.setattr(selection, "_closure_module", lambda pin: VerifiedClosure)
    result = selection.select(document, run_kind="t20", cases="t20-sample4", envelope_cases="sample4",
                              d17_worktree=root, d17_base=base, d17_candidate=candidate,
                              **r041_proof(tmp_path))
    assert result["measurement_cases"] == list(selection.SAMPLE4)
    assert result["selection_reason"] == "t20_r041_archived_sample4"
    assert result["d17_tree_proof"]["changed_paths"] == ["python/freetoken/engine/x.py"]
    assert result["r041_proof"]["verifier_sha256"] == "8" * 64
    expected_inputs = r041_proof(tmp_path)
    assert result["r041_proof"]["verification_inputs"] == {
        key: str(value) if isinstance(value, Path) else value
        for key, value in expected_inputs.items()
    }


def test_t20_verified_r041_rejects_different_selector_input_hash(tmp_path, monkeypatch):
    document = inputs()

    class WrongInputsClosure:
        @staticmethod
        def verify_sealed_startup(**kwargs):
            return verified_result(document, mismatch=selection.SAMPLE4[0])

    monkeypatch.setattr(selection, "_closure_module", lambda pin: WrongInputsClosure)
    result=selection.select(document, run_kind="t20", cases="t20-sample4", envelope_cases="sample4", **r041_proof(tmp_path))
    assert len(result["measurement_cases"]) == 28 and result["r041_proof"] is None

@pytest.mark.parametrize("change", [False, True])
def test_plain_baseline_receipt_cannot_replace_r041_bitwise_closure(tmp_path, change):
    root, base, candidate = repo(tmp_path, change=change)
    receipt = tmp_path / "baseline.json"
    receipt.write_text(json.dumps({"candidate_commit": base, "verdict": "PASS"}))
    receipt.chmod(0o444)
    with pytest.raises(ValueError, match="R041 closure verifier"):
        selection.select(inputs(), run_kind="t20", cases="t20-sample4",
                         envelope_cases="sample4", d17_worktree=root,
                         d17_base=base, d17_candidate=candidate,
                         d14_baseline_receipt=receipt)
