"""Read-only independent audit for a measured T17 continuation round."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

CANDIDATE = "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
EXPECTED_CASES = 28
INPUT_SHA = "90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular evidence file required: " + str(path))


def load_json(path: Path) -> dict:
    regular(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON object required: " + str(path))
    return value


def no_symlinks(directory: Path) -> None:
    if directory.is_symlink() or not directory.is_dir() or any(path.is_symlink() for path in directory.rglob("*")):
        raise ValueError("symlink evidence path")


def archived_source(directory: Path, name: str) -> Path:
    for root in (directory / "source_tools", directory / "source_tools" / "runtime_source",
                 directory / "source_tools" / "cpu_source"):
        path = root / name
        if path.is_file() and not path.is_symlink():
            return path
    raise ValueError("archived frozen source missing: " + name)


def verify_launch(directory: Path, receipt_path: Path) -> dict:
    receipt = load_json(receipt_path)
    if receipt.get("candidate_commit") != CANDIDATE or receipt.get("rid") != directory.name:
        raise ValueError("launch receipt candidate or RID differs")
    files = receipt.get("source_files")
    if not isinstance(files, dict) or "t17_continuation_runner.py" not in files:
        raise ValueError("launch receipt frozen source map missing")
    for name, digest in files.items():
        source = archived_source(directory, name)
        if not isinstance(digest, str) or sha(source) != digest:
            raise ValueError("archived frozen source SHA differs: " + name)
    archived_receipt = directory / "source_tools" / "launch_receipt.json"
    if archived_receipt.is_file() and sha(archived_receipt) != sha(receipt_path):
        raise ValueError("round launch receipt archive differs")
    return receipt


def verify_round_bindings(directory: Path, receipt: dict, status: dict) -> None:
    inputs = directory / "real_inputs.json"
    if sha(inputs) != INPUT_SHA:
        raise ValueError("round frozen input bytes differ")
    stage_report = archived_source(directory, "cpu_validation.json")
    if receipt.get("stage_report_sha256") != sha(stage_report):
        raise ValueError("archived CPU stage report differs from launch receipt")
    batch = directory / "batch.sh"; regular(batch)
    if receipt.get("batch_template_sha256") != sha(batch):
        raise ValueError("archived batch template differs from launch receipt")
    if status.get("batch_pid") != receipt.get("batch_pid"):
        raise ValueError("actual status batch PID differs from launch receipt")


def load_readers(directory: Path):
    """Load only the round's archived equivalence reader sources."""
    root = archived_source(directory, "equiv_suite/__init__.py").parent
    name = "t17_review_equiv"
    spec = importlib.util.spec_from_file_location(name, root / "__init__.py", submodule_search_locations=[str(root)])
    if spec is None or spec.loader is None:
        raise ValueError("archived equiv suite is not importable")
    package = importlib.util.module_from_spec(spec); sys.modules[name] = package; spec.loader.exec_module(package)
    legacy_spec = importlib.util.spec_from_file_location("t17_review_artifacts", archived_source(directory, "t17_d14_artifacts.py"))
    if legacy_spec is None or legacy_spec.loader is None: raise ValueError("archived state reader is not importable")
    legacy = importlib.util.module_from_spec(legacy_spec); legacy_spec.loader.exec_module(legacy)
    return SimpleNamespace(raw=importlib.import_module(name + ".raw"), schedule=importlib.import_module(name + ".schedule"),
                           gate=importlib.import_module(name + ".gate"), operators=_load_operator(directory), legacy=legacy)


def _load_operator(directory: Path):
    spec = importlib.util.spec_from_file_location("t17_review_operator", archived_source(directory, "t17_operator_observe.py"))
    if spec is None or spec.loader is None: raise ValueError("archived operator reader is not importable")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


def arm(directory: Path, name: str) -> Path:
    path = directory / name.replace("-", "_")
    if path.is_symlink() or not path.is_dir(): raise ValueError("missing actual service arm: " + name)
    return path


def identity(path: Path, value: dict) -> dict:
    if not {"pid", "start_ticks", "execution_id"} <= set(value): raise ValueError("service identity missing")
    args = load_json(path / "serve_args.txt")
    import re
    if re.findall(r"\.pid=(\d+)", str(args.get("_unique_suffix"))) != [str(value["pid"])]:
        raise ValueError("declared reference PID differs from actual serve arguments")
    env, log = path / "ENV.txt", path / "serve.log"
    regular(env); regular(log)
    if CANDIDATE not in env.read_text(encoding="utf-8", errors="replace"):
        raise ValueError("reference environment candidate differs")
    return value


def audit_case(directory: Path, case: dict, saved: dict, readers) -> dict:
    name = case["name"]
    case = {**case, "context": case.get("context", case.get("expected_ngram"))}
    if not isinstance(case["context"], list): raise ValueError("frozen case boundary context missing")
    warm_arm = arm(directory, name + "-warm")
    schedule_path = directory / "schedules" / name / "schedule.json"; regular(schedule_path)
    schedule, schedule_sha = readers.schedule.read_schedule(schedule_path)
    warm = readers.raw.read_warm(readers.legacy, warm_arm, case, query="hit")
    if warm.get("warm", {}).get("input_ids_sha256") != case.get("input_ids_sha256"):
        raise ValueError("actual warm tokenizer input SHA differs from frozen case")
    rows, d0_sha = readers.schedule.read_jsonl(warm_arm / "d0_prefill.jsonl")
    hit = str(warm["hit_uid"])
    child = readers.schedule.request_segments(rows, hit)[0]
    donor = readers.schedule.request_segments(rows, str(warm["donor_uid"]))[0]
    donor_end = donor["start"] + donor["subchunks"][0]
    compiled = readers.schedule.compile_schedule(rows, donor_uid=str(warm["donor_uid"]), hit_uid=hit,
                                                 cached_tokens=warm["actual_cached_tokens"],
                                                 prompt_tokens=case["length"] + case["tail"])
    if compiled != schedule: raise ValueError("warm D0 cannot reproduce frozen schedule")
    evidence = {**warm, "compiled_schedule_sha256": schedule_sha, "warm_d0_sha256": d0_sha,
                "expected_first_child_end": child["start"] + child["subchunks"][0], "donor_first_segment_end":donor_end,
                "requested_input_ids_sha256": case["input_ids_sha256"], "references": []}
    refs = []
    saved_refs = saved.get("evidence", {}).get("references", [])
    if not isinstance(saved_refs, list) or len(saved_refs) != 2: raise ValueError("saved reference identities missing")
    for number in (1, 2):
        ref_arm = arm(directory, f"{name}-reference-{number}")
        refs.append(readers.raw.read_reference(readers.legacy, ref_arm, schedule_path=schedule_path,
                                                identity=identity(ref_arm, saved_refs[number - 1].get("process_identity", {}))))
    evidence["references"] = refs
    repeat = readers.operators.compare(arm(directory, f"{name}-reference-1") / "operators",
                                       arm(directory, f"{name}-reference-2") / "operators")
    if repeat.get("equal") is not True: raise ValueError("reference operator evidence is unstable")
    operator = readers.operators.compare(warm_arm / "operators", arm(directory, f"{name}-reference-1") / "operators")
    evidence["first_layer_operator_difference"] = operator.get("first_layer_operator_difference")
    result = readers.gate.evaluate(evidence)
    if result["verdict"] == "not_met" and not isinstance(result.get("first_layer_operator_difference"), dict):
        raise ValueError("not_met lacks first operator difference")
    stored = saved.get("result", {})
    if stored.get("verdict") != result["verdict"]: raise ValueError("saved case verdict differs from raw recomputation")
    return {"case": name, "verdict": result["verdict"], "gate": result,
            "schedule_sha256": schedule_sha, "warm_d0_sha256": d0_sha, "operator": operator}


def classify(cases: list[dict], actual_status: dict) -> str:
    verdicts = [row["verdict"] for row in cases]
    if "failed_harness" in verdicts: return "failed_harness"
    if "not_met" in verdicts: return "not_met"
    if len(cases) != EXPECTED_CASES: raise ValueError("kept requires all 28 cases")
    if any(value != "measurements_pass_pending_independent_review" for value in verdicts):
        raise ValueError("incomplete or indeterminate case verdict")
    if actual_status.get("state") != "complete_measurements_pending_independent_review":
        raise ValueError("kept requires completed measurement terminal status")
    return "kept_pending_independent_review"


def audit(directory: Path, receipt_path: Path, actual_status: Path, *, readers=None) -> dict:
    directory = Path(directory); no_symlinks(directory)
    receipt = verify_launch(directory, Path(receipt_path))
    status = load_json(actual_status)
    if status.get("rid") != directory.name or status.get("batch") != receipt.get("batch"):
        raise ValueError("actual terminal status identity differs")
    verify_round_bindings(directory, receipt, status)
    inputs = load_json(directory / "real_inputs.json")
    if inputs.get("candidate_commit") != CANDIDATE or not isinstance(inputs.get("cases"), list):
        raise ValueError("frozen inputs candidate binding differs")
    result_path = directory / "result.json"
    if not result_path.is_file():
        failed = load_json(directory / "failed_harness.json")
        if status.get("state") != "failed": raise ValueError("missing result requires failed terminal status")
        return {"schema":"ft_t17_continuation_independent_audit/v1", "rid":directory.name, "batch":receipt["batch"],
                "candidate_commit":CANDIDATE, "launch_receipt_sha256":sha(Path(receipt_path)),
                "actual_status_sha256":sha(Path(actual_status)), "verdict":"failed_harness", "cases":[],
                "failure":failed.get("error", "runner failed before a measurable case")}
    result = load_json(result_path); case_docs = result.get("cases", {})
    if not isinstance(case_docs, dict): raise ValueError("round case map missing")
    readers = readers or load_readers(directory)
    measured = [case for case in inputs["cases"] if case.get("name") in case_docs]
    expected_prefix = [case.get("name") for case in inputs["cases"][:len(measured)]]
    if not measured or list(case_docs) != expected_prefix:
        raise ValueError("measured cases are not one ordered frozen-matrix prefix")
    audited = []
    for case in measured:
        name = case.get("name")
        if not isinstance(name, str): raise ValueError("input case name missing")
        audited.append(audit_case(directory, case, load_json(directory / "cases" / (name + ".json")), readers))
    verdict = classify(audited, status)
    if result.get("verdict") not in {verdict, "measurements_pass_pending_independent_review"}:
        raise ValueError("round result verdict differs from independent recomputation")
    return {"schema":"ft_t17_continuation_independent_audit/v1", "rid":directory.name, "batch":receipt["batch"],
            "candidate_commit":CANDIDATE, "launch_receipt_sha256":sha(Path(receipt_path)),
            "actual_status_sha256":sha(Path(actual_status)), "verdict":verdict, "cases":audited}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--round", type=Path, required=True); parser.add_argument("--launch-receipt", type=Path, required=True)
    parser.add_argument("--actual-status", type=Path, required=True); args = parser.parse_args(argv)
    print(json.dumps(audit(args.round, args.launch_receipt, args.actual_status), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__": main()
