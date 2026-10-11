"""Versioned, fail-closed T17/T20 continuation runner.  Dry plans allocate no GPU."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
R041_PROOF_KEYS = (
    "r041_round", "r041_independent_review", "caller_ir_sha256",
    "accepted_t17_path", "accepted_t17_review", "expected_tag",
    "expected_d17_commit", "expected_d17_worktree", "expected_gate_case_sha256",
    "expected_artifacts_sha256", "expected_t16_runner_sha256", "expected_parser_sha256",
    "expected_d04_checker_sha256", "expected_verifier_sha256",
)
class V2Error(ValueError):
    pass


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise V2Error("module unavailable: " + str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _selection():
    return _module("t17_selection_v2", HERE / "t17_continuation_selection.py")


def _runtime():
    return _module("t17_runtime_v2", HERE / "t17_continuation_runtime_v2.py")


def plan(realinput28, *, run_kind, cases, envelope_cases, assigned_rid,
         candidate_worktree, candidate_sha, parent_sha, d17_worktree=None,
         d17_base=None, d17_candidate=None, d14_baseline_receipt=None,
         expected_input_sha256=None, resume_review=None, resume_review_sha256=None,
         t20_full=False, d16_source_review=None, d16_source_review_sha256=None,
         **r041_proof):
    full = None
    if t20_full:
        if run_kind != 't20' or assigned_rid != 'E2-R040':
            raise V2Error('full measurements require assigned E2-R040/T20')
        if not d16_source_review or not re.fullmatch('[0-9a-f]{64}', d16_source_review_sha256 or ''):
            raise V2Error('full T20 requires the D16 source review and caller SHA')
        full = {'d16_source_review': str(Path(d16_source_review).resolve()),
                'd16_source_review_sha256': d16_source_review_sha256}
    elif d16_source_review is not None or d16_source_review_sha256 is not None:
        raise V2Error('D16 source review requires full T20 mode')
    unknown = set(r041_proof) - set(R041_PROOF_KEYS)
    if unknown:
        raise V2Error("unknown R041 proof fields: " + ", ".join(sorted(unknown)))
    s = _selection()
    inputs = s.load_realinput28(
        realinput28, expected_document_sha256=expected_input_sha256 or s.INPUTS_SHA256
    )
    chosen = s.select(
        inputs, run_kind=run_kind, cases=cases, envelope_cases=envelope_cases,
        assigned_rid=assigned_rid, d17_worktree=d17_worktree, d17_base=d17_base,
        d17_candidate=d17_candidate, d14_baseline_receipt=d14_baseline_receipt,
        resume_review=resume_review, resume_review_sha256=resume_review_sha256,
        target_candidate=candidate_sha,
        **r041_proof,
    )
    r = _runtime()
    candidate = r.verify_candidate(candidate_worktree, candidate_sha, parent_sha)
    return {
        "schema": "ft_t17_continuation_runner_v2_plan/v2",
        "admitted": False,
        "requests_sent": False,
        "t20_full": full,
        "inputs": str(Path(realinput28).resolve()),
        "inputs_sha256": _sha(Path(realinput28).read_bytes()),
        "candidate": candidate,
        "selection": chosen,
        "retained_source_commit": (
            chosen["retained_review"]["source_candidate"]
            if chosen.get("retained_review") is not None else None
        ),
        "case_choices": [
            {"name": name, "input_ids_sha256": chosen["case_input_sha256"][name],
             "allow_cold_envelope": name in chosen["ordinary_cold_envelope_cases"]}
            for name in chosen["measurement_cases"]
        ],
    }


def preflight(document, *, cpu_report, source_root, rounds, closure_binding,
              prior_t16_rid, prior_t16_batch, rid, batch, directory,
              source_review=None, source_review_sha256=None):
    r = _runtime()
    candidate = document["candidate"]
    cpu = r.verify_cpu_report(
        cpu_report, source_root, source_review=source_review,
        source_review_sha256=source_review_sha256,
        run_kind=document["selection"]["run_kind"]
    )
    prior = r.verify_t16(
        rounds, closure_binding, rid=prior_t16_rid, batch=prior_t16_batch,
        parent=candidate["parent_commit"], candidate=candidate["candidate_commit"]
    )
    if cpu["candidate_commit"] != candidate["candidate_commit"]:
        raise V2Error("CPU report candidate must match execution candidate")
    if document.get('t20_full') is not None:
        full = document['t20_full']
        for name in ('t20_measurements.py', 't00_runner.py', 't08_runner.py', 't16_runner.py',
                     'd16_native_process_collection.py', 'd16_service_workloads.py',
                     'd16_exact_service_startup.py', 'equiv_suite/native_workloads.py',
                     'batchNN_E2-R040.sh', 'batchNN_E2-R040_continuation_v3.sh'):
            if name not in cpu['files']:
                raise V2Error('full T20 source inventory missing: ' + name)
            r._source_file(Path(source_root), name)
        native = _module('t20_d16_preflight', Path(source_root)/'d16_native_process_collection.py')
        native.verify_source_review(Path(source_root)/'d16_exact_service_startup.py',
            full['d16_source_review'], full['d16_source_review_sha256'])
    r041_proof = document["selection"].get("r041_proof")
    retained_review = document["selection"].get("retained_review")
    remaining_scope = retained_review is not None
    input_provenance = {
        "raw_inputs_sha256": document["inputs_sha256"],
        "origin_candidate": "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7",
        "target_candidate": candidate["candidate_commit"],
    }
    execution_archive = {
        "files": cpu["files"],
        "cpu_report_sha256": cpu["cpu_report_sha256"],
        # Runtime must independently re-check this record before use.
        "r041_proof": r041_proof,
    }
    if remaining_scope:
        input_provenance.update({"retained_source_commit": retained_review["source_candidate"],
                                 "measurement_scope": "remaining_cases_only"})
        execution_archive.update({"retained_review": retained_review,
                                  "measurement_scope": "remaining_cases_only"})
    return {
        **document,
        "admitted": False,
        "execution_ready": True,
        "input_provenance": input_provenance,
        "execution_archive": execution_archive,
        "cpu": cpu,
        "prior_t16": prior,
        "rid": rid,
        "batch": batch,
        "directory": str(directory),
        "preflight_paths": {
            "cpu_report": str(cpu_report),
            "source_root": str(source_root),
            "rounds": str(rounds),
            "closure_binding": str(closure_binding),
            "source_review": str(source_review) if source_review is not None else None,
            "source_review_sha256": source_review_sha256,
            "r041_round": r041_proof["r041_round"] if r041_proof else None,
            "r041_independent_review": r041_proof["independent_review"] if r041_proof else None,
            "r041_verifier_sha256": r041_proof["verifier_sha256"] if r041_proof else None,
        },
    }


def _imports():
    sys.path.insert(0, str(HERE))
    gpu = _module("t17_v2_legacy_gpu", HERE / "t17_d14_gpu.py")
    artifacts = _module("t17_v2_legacy_artifacts", HERE / "t17_d14_artifacts.py")
    init = HERE / "equiv_suite/__init__.py"
    _module("t17_v2_equiv", init)
    continuation = __import__("t17_v2_equiv.continuation", fromlist=["*"])
    return gpu, artifacts, continuation


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--realinput28", required=True)
    p.add_argument("--candidate-worktree", required=True)
    p.add_argument("--candidate-sha", required=True)
    p.add_argument("--parent-sha", required=True)
    p.add_argument("--run-kind", choices=("t17", "t20"), required=True)
    p.add_argument('--t20-full', action='store_true')
    p.add_argument('--d16-source-review')
    p.add_argument('--d16-source-review-sha256')
    p.add_argument("--cases", choices=("all", "remaining", "t20-sample4"), default="all")
    p.add_argument("--envelope-cases", choices=("all", "sample4", "none"), default="sample4")
    p.add_argument("--rid", required=True)
    p.add_argument("--batch", type=int, required=True)
    p.add_argument("--d17-worktree")
    p.add_argument("--d17-base")
    p.add_argument("--d17-candidate")
    p.add_argument("--d14-baseline-receipt")
    p.add_argument("--resume-review")
    p.add_argument("--resume-review-sha256")
    for key in R041_PROOF_KEYS:
        p.add_argument("--" + key.replace("_", "-"), dest=key)
    p.add_argument("--run", action="store_true")
    p.add_argument("--cpu-report")
    p.add_argument("--source-root")
    p.add_argument("--rounds")
    p.add_argument("--closure-binding")
    p.add_argument("--prior-t16-rid")
    p.add_argument("--prior-t16-batch", type=int)
    p.add_argument("--directory")
    p.add_argument("--preflight-artifact")
    p.add_argument("--source-review")
    p.add_argument("--source-review-sha256")
    a = p.parse_args(argv)
    doc = plan(
        a.realinput28, run_kind=a.run_kind, cases=a.cases,
        envelope_cases=a.envelope_cases, assigned_rid=a.rid,
        candidate_worktree=a.candidate_worktree, candidate_sha=a.candidate_sha,
        parent_sha=a.parent_sha, d17_worktree=a.d17_worktree, d17_base=a.d17_base,
        d17_candidate=a.d17_candidate, d14_baseline_receipt=a.d14_baseline_receipt,
        resume_review=a.resume_review, resume_review_sha256=a.resume_review_sha256,
        t20_full=a.t20_full, d16_source_review=a.d16_source_review,
        d16_source_review_sha256=a.d16_source_review_sha256,
        **{key: getattr(a, key) for key in R041_PROOF_KEYS},
    )
    if not a.run:
        print(json.dumps(doc, sort_keys=True))
        return 0
    required = (a.cpu_report, a.source_root, a.rounds, a.closure_binding,
                a.prior_t16_rid, a.prior_t16_batch, a.directory, a.preflight_artifact)
    if any(value is None for value in required):
        p.error("--run requires CPU report/source, rounds/closure, explicit prior T16 rid/batch, and directory")
    checked = preflight(
        doc, cpu_report=Path(a.cpu_report), source_root=Path(a.source_root),
        rounds=Path(a.rounds), closure_binding=Path(a.closure_binding),
        prior_t16_rid=a.prior_t16_rid, prior_t16_batch=a.prior_t16_batch,
        rid=a.rid, batch=a.batch, directory=Path(a.directory),
        source_review=a.source_review, source_review_sha256=a.source_review_sha256,
    )
    receipt = Path(a.preflight_artifact)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.open("x", encoding="utf-8").write(json.dumps(checked, sort_keys=True))
    receipt.chmod(0o444)
    print(json.dumps(_runtime().execute(
        checked,
        cases_by_name={case["name"]: case for case in _selection().load_realinput28(a.realinput28)["cases"]},
        sealed_preflight=receipt, run_kind=a.run_kind,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
