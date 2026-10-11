"""T17 continuation batch runner using the retained D14 service lifecycle."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = Path("/data2/FreeToken")
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
WT = ROOT / "wt/e2d14-schedule"
TOOLS = HERE / "equiv_suite"
PARENT = "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42"
CANDIDATE = "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
T16_RID, T16_BATCH = "E2-R032-gate-D14", 60
RID_RE = re.compile(r"E2-R03(?:3|4a?)(?:-gate-T17)?\Z")
APPEND_SHA = "67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"regular file required: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def frozen(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise ValueError("outer closure binding must be a frozen regular file")


def sealed_manifest(directory: Path) -> set[str]:
    manifest = directory / "MANIFEST.sha256"
    if directory.is_symlink() or not directory.is_dir() or manifest.is_symlink() or not manifest.is_file():
        raise ValueError("closed T16 directory and manifest required")
    declared = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as error:
            raise ValueError("invalid T16 manifest line") from error
        relative = relative.removeprefix("./")
        candidate = Path(relative)
        raw = directory / candidate
        path = raw.resolve()
        if candidate.is_absolute() or ".." in candidate.parts or raw.is_symlink() or directory.resolve() not in path.parents or not path.is_file() or sha(path) != digest:
            raise ValueError("T16 manifest evidence differs")
        declared.add(relative)
    if any(path.is_symlink() or path.stat().st_mode & 0o222 for path in (directory, *directory.rglob("*"))):
        raise ValueError("T16 evidence is not sealed read-only")
    return declared


def d04_check(directory: Path) -> None:
    writer = ROOT / "scripts/round_json_append.py"
    if writer.is_symlink() or not writer.is_file() or sha(writer) != APPEND_SHA:
        raise ValueError("canonical D04 round_json_append source differs")
    completed = subprocess.run([sys.executable, str(writer), str(directory), "check"], capture_output=True, text=True)
    if completed.returncode:
        raise ValueError("R032 D04 history check failed: " + completed.stderr[-500:])


def verify_prerequisite(rounds: Path, closure_binding: Path) -> dict:
    """Accept only the sealed R032/b60 kept gate bound by an outer closure receipt."""
    directory = rounds / T16_RID
    round_json = load(directory / "round.json")
    gate_path, review_path = directory / f"gate_batch{T16_BATCH}.json", directory / f"review_batch{T16_BATCH}.json"
    gate, review = load(gate_path), load(review_path)
    if (round_json.get("round_id") != T16_RID or round_json.get("card") != "T16"
            or round_json.get("verdict") != "kept" or not round_json.get("closed_at")
            or round_json.get("retractions") != []
            or round_json.get("base", {}).get("commit") != PARENT
            or round_json.get("experimental", {}).get("candidate_commit") != CANDIDATE
            or round_json.get("independent_review_sha256") != sha(review_path)):
        raise ValueError("R032 is not the kept exact-parent T16 closure")
    if (gate.get("proposed_verdict") != "kept" or gate.get("parent_commit") != PARENT
            or gate.get("new_commit") != CANDIDATE or review.get("verdict") != "PASS"
            or review.get("rid") != T16_RID or review.get("batch") != T16_BATCH):
        raise ValueError("R032 gate or independent review is not the required PASS")
    declared = sealed_manifest(directory)
    required = {gate_path.name, review_path.name, "batch.sh"}
    history = directory / "round_history"
    if not required <= declared or history.is_symlink() or not history.is_dir() or not any(history.iterdir()):
        raise ValueError("R032 D04 chain is incomplete")
    d04_check(directory)
    frozen(closure_binding)
    binding = load(closure_binding)
    actual = {"round": T16_RID, "batch": T16_BATCH, "parent_commit": PARENT,
              "candidate_commit": CANDIDATE, "round_sha256": sha(directory / "round.json"),
              "gate_sha256": sha(gate_path), "review_sha256": sha(review_path),
              "manifest_sha256": sha(directory / "MANIFEST.sha256")}
    if any(binding.get(key) != value for key, value in actual.items()):
        raise ValueError("outer closure binding does not match sealed R032 evidence")
    return {"directory": str(directory), **actual, "closure_binding_sha256": sha(closure_binding)}


def _suite_modules(_worktree: Path = WT):
    init = TOOLS / "__init__.py"
    if TOOLS.is_symlink() or not init.is_file() or init.is_symlink():
        raise ValueError("frozen D16 tool stage is unavailable")
    name = "t17_frozen_equiv_suite"
    spec = importlib.util.spec_from_file_location(name, init, submodule_search_locations=[str(TOOLS)])
    if spec is None or spec.loader is None:
        raise ValueError("frozen D16 tool stage is not importable")
    package = importlib.util.module_from_spec(spec); sys.modules[name] = package; spec.loader.exec_module(package)
    cases = importlib.import_module(name + ".cases")
    gate = importlib.import_module(name + ".gate")
    continuation = importlib.import_module(name + ".continuation")
    root = TOOLS.resolve()
    if any(root not in Path(module.__file__).resolve().parents for module in (cases, gate, continuation)):
        raise ValueError("D16 modules did not load from the frozen tool stage")
    return cases, gate, continuation


def load_inputs(path: Path, *, worktree: Path = WT) -> list[dict]:
    """Validate the outer frozen target-tokenizer input matrix before GPU ownership."""
    frozen(path); document = load(path)
    cases, gate, _ = _suite_modules(worktree)
    matrix = cases.continuation_matrix()
    if document.get("candidate_commit") != CANDIDATE or not isinstance(document.get("cases"), list):
        raise ValueError("frozen real inputs do not bind the exact candidate")
    supplied = document["cases"]
    expected = {(row["name"], row["boundary"], row["tail"]) for row in matrix}
    got = {(row.get("name"), row.get("length"), row.get("tail")) for row in supplied if isinstance(row, dict)}
    if got != expected or len(supplied) != len(matrix):
        raise ValueError("frozen real input matrix differs from the required 28 continuation cases")
    checked = []
    for row in supplied:
        donor, query = row.get("donor"), row.get("query")
        length, tail = row.get("length"), row.get("tail")
        context = row.get("expected_ngram", row.get("context"))
        if (not isinstance(donor, list) or not isinstance(query, list) or type(length) is not int or type(tail) is not int
                or len(donor) != length + 1 or len(query) != length + tail or donor != query[:length + 1]
                or any(type(token) is not int for token in donor + query)
                or not isinstance(context, list) or len(context) != 2 or context != query[length - 2:length]
                or any(type(token) is not int for token in context)
                or type(row.get("trace_index")) is not int):
            raise ValueError("frozen real input case lacks exact target-tokenizer IDs")
        digest = gate.token_sha(query)
        if row.get("input_ids_sha256") != digest or row.get("donor_input_ids_sha256") != gate.token_sha(donor):
            raise ValueError("frozen real input token SHA differs")
        checked.append({**row, "context": list(row.get("expected_ngram", row.get("context")))})
    return checked


def verify_input_provenance(path: Path) -> dict:
    expected = "90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0"
    frozen(path)
    if sha(path) != expected:
        raise ValueError("input bytes differ from the target-tokenizer frozen build")
    receipt_path = path.parent / "cpu_validation.json"
    frozen(receipt_path)
    if sha(receipt_path) != "9e5d408c3ddecaaa766631ce98de671d8671f078428f6a6190ef93eeeffd90a8":
        raise ValueError("input generator receipt differs")
    receipt = load(receipt_path)
    document = load(path)
    builder = path.parent / "t17_continuation_inputs.py"
    frozen(builder)
    if (sha(builder) != "552ae66c2511c4998add6a0e16875fa15403b7c0088e722fdf092a3c9e7a85d3"
            or receipt.get("verdict") != "PASS" or receipt.get("inputs_sha256") != expected
            or document.get("trace_sha256") != "097b7a039e730d356985f47bc9fd747c86f4658fc6b89f1dec3243c0771b5e24"):
        raise ValueError("target-tokenizer input provenance differs")
    return {"inputs_sha256": expected, "generator_receipt_sha256": sha(receipt_path),
            "generator_sha256": sha(builder), "trace_sha256": document["trace_sha256"],
            "model": str(ROOT / "models/Qwen3.8-Flash-Next-NVFP4-overlay")}


def verify_execution_archive() -> dict:
    receipt_path = HERE / "cpu_validation.json"
    frozen(receipt_path)
    receipt = load(receipt_path)
    if receipt.get("verdict") != "PASS" or not isinstance(receipt.get("files"), dict):
        raise ValueError("frozen CPU source receipt required")
    for name, digest in receipt["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("invalid frozen source path")
        source = HERE / relative
        frozen(source)
        if sha(source) != digest:
            raise ValueError("frozen source differs: " + name)
    value = os.environ.get("FT_T17_BATCH_TEMPLATE")
    if not value:
        raise ValueError("frozen original T17 batch template required before GPU lock")
    template = Path(value)
    frozen(template)
    if sha(template) != receipt["files"].get("batchNN_T17.sh"):
        raise ValueError("batch template differs from tested frozen source")
    return {"files": receipt["files"], "cpu_receipt_sha256": sha(receipt_path),
            "batch_sha256": sha(template), "template": str(template)}


def bind_gpu_runtime(gpu: Any) -> None:
    """Bind the retained Run implementation to this exact candidate in this process only."""
    gpu.WT = WT
    gpu.helper.PARENT = PARENT
    gpu.helper.CANDIDATE = CANDIDATE
    gpu.helper.T16_RID = T16_RID
    gpu.helper.T16_BATCH = T16_BATCH
    if gpu.WT != WT or gpu.helper.CANDIDATE != CANDIDATE:
        raise ValueError("retained D14 runner did not bind the exact continuation candidate")


def xwrite(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


class Run:
    """Small coordinator; all service startup/stop behavior remains gpu.Run.service."""
    def __init__(self, options: Any, *, gpu: Any, artifacts: Any, continuation: Any):
        bind_gpu_runtime(gpu)
        self.options, self.gpu, self.artifacts, self.continuation = options, gpu, artifacts, continuation
        self.base = gpu.Run(options)
        self.base.directory = Path(options.directory)
        self.base.status = self.base.directory / f"status_batch{options.batch}.json"

    def _diagnostic(self, case: dict, result: dict) -> dict:
        producer = getattr(self.options, "diagnostic_producer", None) or getattr(self.base, "operator_diagnostic", None)
        if not callable(producer):
            return {"verdict": "diagnostic_missing"}
        receipt = producer(case, result)
        if not isinstance(receipt, dict) or not isinstance(receipt.get("first_layer_operator_difference"), dict):
            return {"verdict": "diagnostic_missing"}
        path, digest = receipt.get("receipt_path"), receipt.get("receipt_sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            return {"verdict": "diagnostic_missing"}
        evidence = Path(path)
        if evidence.is_symlink() or not evidence.is_file() or sha(evidence) != digest:
            return {"verdict": "diagnostic_missing"}
        return {"verdict": "recorded", "receipt": receipt}

    def execute(self, inputs: list[dict], prerequisite: dict, *, run: bool) -> dict:
        if not run:
            return {"schema": "ft_t17_continuation_preflight/v1", "gpu_started": False,
                    "prerequisite": prerequisite, "cases": len(inputs)}
        after_cases = getattr(self.options, 'after_cases', None)
        if after_cases is not None and (not callable(after_cases) or self.options.rid != 'E2-R040'
                                       or getattr(self.options, 'gate', None) != 'T20'):
            raise ValueError('additional measurements require the actual T20 batch')
        base = self.base
        if base.directory.exists():
            raise FileExistsError("assigned T17 evidence directory already exists")
        base.lock_take(); lock_owned = True
        owned = False
        try:
            base.directory.mkdir(); owned = True
            base.set_status(state="running")
            xwrite(base.directory / "prerequisite.json", prerequisite)
            # Keep the exact tested startup chain with the measurement evidence.
            archive = getattr(self.options, "execution_archive", None)
            if archive:
                destination = base.directory / "source_tools"
                destination.mkdir()
                for name in [*archive["files"], "cpu_validation.json"]:
                    target = destination / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(HERE / name, target)
            template = os.environ.get("FT_T17_BATCH_TEMPLATE")
            if template:
                source = Path(template)
                if source.is_symlink() or not source.is_file():
                    raise ValueError("regular original T17 batch template required")
                with (base.directory / "batch.sh").open("xb") as stream:
                    stream.write(source.read_bytes())
            if getattr(self.options, "input_provenance", None):
                shutil.copyfile(self.options.inputs, base.directory / "real_inputs.json")
                xwrite(base.directory / "input_provenance.json", self.options.input_provenance)
                xwrite(base.directory / "execution_archive.json", archive)
            else:
                xwrite(base.directory / "real_inputs.json", {"candidate_commit": CANDIDATE, "cases": inputs})
            (base.directory / "schedules").mkdir()
            output = {"schema": "ft_t17_continuation/v1", "rid": self.options.rid, "batch": self.options.batch,
                      "candidate_commit": CANDIDATE, "admitted": False, "cases": {}}
            for case in inputs:
                base.current_case = case
                base.case_arms = {}
                resources = SimpleNamespace(run=base, legacy=self.artifacts,
                                            schedule_dir=base.directory / "schedules" / case["name"],
                                            allow_cold_envelope=True)
                result = self.continuation.run_case(resources, case)
                verify_operators = getattr(base, "verify_operators", None)
                if callable(verify_operators) and result.get("evidence", {}).get("references"):
                    result["operator_evidence"] = verify_operators(case, result)
                xwrite(base.directory / "cases" / (case["name"] + ".json"), result)
                output["cases"][case["name"]] = {"result": result["result"], "stopped": result.get("stopped")}
                if result.get("stopped"):
                    if result["stopped"] == "not_met":
                        diagnostic = self._diagnostic(case, result)
                        xwrite(base.directory / "cases" / (case["name"] + ".diagnostic.json"), diagnostic)
                        output["diagnostic"] = diagnostic
                        if diagnostic["verdict"] != "recorded":
                            output["measurement_verdict"] = "not_met"
                            output["verdict"] = "failed_harness"
                            output["reason"] = "required first-layer/operator diagnostic is missing"
                    output.setdefault("verdict", result["stopped"])
                    xwrite(base.directory / "result.json", output)
                    base.set_status(state="failed", verdict=output["verdict"])
                    return output
            if after_cases is not None:
                # This remains inside the retained try/finally and its original
                # exclusive GPU lock. A later failure stops the owned service
                # before releasing the same token/inode-bound lock.
                output['t20_measurements'] = after_cases(base)
            output["verdict"] = "measurements_pass_pending_independent_review"
            xwrite(base.directory / "result.json", output)
            base.set_status(state="complete_measurements_pending_independent_review")
            return output
        except BaseException as error:
            if owned:
                report = {"schema": "ft_t17_continuation_failure/v1", "error": repr(error), "admitted": False}
                try: xwrite(base.directory / "failed_harness.json", report)
                except FileExistsError: pass
                base.set_status(state="failed", error=repr(error))
            raise
        finally:
            try:
                base.stop()
            finally:
                if lock_owned and base.proc is None:
                    base.lock_release()


def _imports():
    sys.path.insert(0, str(HERE))
    import t17_d14_artifacts as artifacts
    import t17_d14_gpu as gpu
    import t17_operator_observe as operators
    original = gpu.Run

    class ObservedRun(original):
        def environment(self, wt, arm=None, d0=False):
            env = super().environment(wt, arm, d0)
            for key in list(env):
                if key.startswith("FT_T17_OPERATOR"):
                    env.pop(key)
            if arm is not None:
                case = self.current_case
                env.update(FT_T17_OPERATOR=str(arm / "operators"),
                           FT_T17_OPERATOR_QUERY_SHA=case["input_ids_sha256"],
                           FT_T17_OPERATOR_QUERY_TOKENS=str(len(case["query"])),
                           FT_T17_OPERATOR_BOUNDARY=str(case["length"]))
            return env

        def startup_wrapper(self):
            return HERE / "t17_operator_startup.py"

        def service(self, name, operation, **kwargs):
            # Artifact arm names follow the round schema's ASCII contract.
            actual = name.replace("-", "_")
            self.case_arms[name] = self.directory / actual
            return super().service(actual, operation, **kwargs)

        def operator_diagnostic(self, case, result):
            warm = self.case_arms[case["name"] + "-warm"] / "operators"
            ref = self.case_arms[case["name"] + "-reference-1"] / "operators"
            receipt = operators.compare(warm, ref)
            if not isinstance(receipt.get("first_layer_operator_difference"), dict):
                raise ValueError("output differs but observed Python boundaries have no first difference")
            path = self.directory / "cases" / (case["name"] + ".operator_comparison.json")
            xwrite(path, receipt)
            return {**receipt, "receipt_path": str(path), "receipt_sha256": sha(path)}

        def verify_operators(self, case, result):
            name = case["name"]
            ref1 = self.case_arms[name + "-reference-1"] / "operators"
            ref2 = self.case_arms[name + "-reference-2"] / "operators"
            repeat = operators.compare(ref1, ref2)
            if repeat.get("equal") is not True:
                path = self.directory / "cases" / (name + ".unstable_reference_operators.json")
                xwrite(path, repeat)
                raise ValueError("same-structure reference operator bytes differ across processes")
            # Even equal final text cannot establish coverage when an observer
            # silently omitted one side's actual operator rows.
            warm = self.case_arms[name + "-warm"] / "operators"
            comparison = operators.compare(warm, ref1)
            return {"reference_repeat": repeat, "warm_reference": comparison,
                    "scope": "observed Python token-row boundaries; not internal CUDA kernel proof"}

    gpu.Run = ObservedRun
    return gpu, artifacts


def verify_candidate_source() -> None:
    if subprocess.check_output(["git", "-C", str(WT), "rev-parse", "HEAD"], text=True).strip() != CANDIDATE:
        raise ValueError("candidate worktree head differs")
    if subprocess.check_output(["git", "-C", str(WT), "status", "--porcelain", "--untracked-files=no"], text=True):
        raise ValueError("candidate worktree has tracked changes")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rid", required=True)
    parser.add_argument("--batch", required=True, type=int)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--closure-binding", required=True, type=Path)
    parser.add_argument("--directory", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--resource-preflight", action="store_true")
    args = parser.parse_args(argv)
    if not RID_RE.fullmatch(args.rid) or args.batch < 1:
        parser.error("rid must be E2-R033/E2-R034/E2-R034a optionally suffixed -gate-T17; batch must be positive")
    if args.directory != ROUNDS / args.rid:
        parser.error("directory must be the canonical round path")
    args.gate = "T17"
    if sys.platform != "linux":
        parser.error("T17 continuation execution requires the Linux owner host")
    verify_candidate_source()
    args.input_provenance = verify_input_provenance(args.inputs)
    if args.run:
        args.execution_archive = verify_execution_archive()
    prerequisite = verify_prerequisite(ROUNDS, args.closure_binding)
    inputs = load_inputs(args.inputs)
    gpu, artifacts = _imports()
    _, _, continuation = _suite_modules(WT)
    runner = Run(args, gpu=gpu, artifacts=artifacts, continuation=continuation)
    if args.resource_preflight:
        runner.base.gate(WT, CANDIDATE)
        runner.base.compiled_extensions(WT)
    result = runner.execute(inputs, prerequisite, run=args.run)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("verdict") in (None, "measurements_pass_pending_independent_review") else 1


if __name__ == "__main__":
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signal_number, lambda number, frame: (_ for _ in ()).throw(InterruptedError("owned batch signal")))
    raise SystemExit(main())
