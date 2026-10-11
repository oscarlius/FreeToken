"""Preflight and atomically launch only a reviewed, frozen T17 continuation stage."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = Path("/data2/FreeToken")
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
PY = str(ROOT / "venv/bin/python")
HELPER = ROOT / "runs/plan_batches/e2_launch.py"
# The protocol owns the authoritative hash; keeping the pin there prevents a
# second, independently drifting copy in this launcher.
CANDIDATE = "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
REQUIRED_FILES = {
    "t17_continuation_runner.py", "t17_d14_runner.py", "t17_d14_gpu.py", "t17_d14_artifacts.py",
    "t17_d14_observe.py", "t16_full_tail_base_runner.py", "t17_operator_observe.py", "t17_operator_startup.py",
    "t17_d14_startup.py", "t17_d14_exact_ids.py", "t17_continuation_launch.py",
    "t17_owned_launch_protocol.py", "batchNN_T17.sh", "tests/test_t17_continuation_runner.py",
    "tests/test_t17_operator_observe.py", "tests/test_t17_operator_startup.py",
    "tests/test_t17_continuation_launch.py",
}
REQUIRED_STEPS = {"regression", "base_spawn", "operator_spawn", "preflight", "batch_syntax", "historical_replay"}
SUPPLEMENT_RID = "E2-R034a"
SUPPLEMENT_PARENT = "E2-R034"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(path: Path, digest: str, *, owner: int | None = None) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise ValueError("read-only regular stage evidence required: " + str(path))
    if owner is not None and path.stat().st_uid != owner:
        raise ValueError("stage evidence owner differs: " + str(path))
    if not isinstance(digest, str) or sha(path) != digest:
        raise ValueError("stage evidence SHA differs: " + str(path))


def load_module(protocol, path: Path, digest: str, name: str):
    return protocol.verified_module(path, digest, name)


def load_protocol():
    path = HERE / "t17_owned_launch_protocol.py"
    spec = importlib.util.spec_from_file_location("ft_t17_owned_launch", path)
    if spec is None or spec.loader is None:
        raise ValueError("owned launch protocol is not importable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_stage(stage: Path) -> tuple[dict, str]:
    report_path = stage / "cpu_validation.json"
    if sys.platform != "linux" or stage.is_symlink() or not stage.is_dir() or stage.stat().st_mode & 0o222:
        raise ValueError("Linux owned read-only continuation stage required")
    owner = os.geteuid()
    if stage.stat().st_uid != owner:
        raise ValueError("continuation stage owner differs")
    checked(report_path, sha(report_path), owner=owner)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if (report.get("schema") != "ft_t17_continuation_cpu/v1" or report.get("verdict") != "PASS"
            or report.get("gpu_started") is not False or report.get("requests_sent") is not False):
        raise ValueError("complete CPU-only continuation stage report required")
    files = report.get("files")
    if not isinstance(files, dict) or not REQUIRED_FILES <= set(files):
        raise ValueError("continuation stage source binding incomplete")
    for name, digest in files.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("stage report contains unsafe path")
        checked(stage / relative, digest, owner=owner)
    steps = report.get("steps")
    if not isinstance(steps, dict) or not REQUIRED_STEPS <= set(steps):
        raise ValueError("continuation stage logs missing")
    for name, step in steps.items():
        if not isinstance(step, dict) or step.get("returncode") != 0:
            raise ValueError("continuation CPU step failed: " + str(name))
        checked(stage / (str(name) + ".log"), step.get("log_sha256"), owner=owner)
    regression = (stage / "regression.log").read_text(encoding="utf-8", errors="replace")
    import re
    match = re.search(r"(?m)^(\d+) passed(?: in |$)", regression)
    if (match is None or report.get("passed") != int(match.group(1))
            or re.search(r"\b(failed|skipped|error)\b", regression, re.IGNORECASE)):
        raise ValueError("complete successful regression evidence required")
    base = report.get("spawn_proof", {}); operator = report.get("operator_spawn_proof", {})
    base_worker = base.get("worker", {}); operator_worker = operator.get("worker", {})
    if (base.get("gpu_started") is not False or base_worker.get("cuda_initialized") is not False
            or base_worker.get("scheduler_wrapper") != "restore_observed"
            or base_worker.get("engine_wrapper") != "build_chunks_observed"
            or base_worker.get("input_wrapper") != "process_observed"
            or base_worker.get("reply_wrapper") != "reply_observed"
            or operator.get("gpu_started") is not False or operator_worker.get("cuda_initialized") is not False
            or operator_worker.get("operator_engine_init") != "init_operator"
            or operator_worker.get("operator_process") != "process_operator"
            or operator_worker.get("operator_reply") != "reply_operator"):
        raise ValueError("actual CPU spawn wrapper proof incomplete")
    candidate = report.get("candidate_commit") or report.get("preflight", {}).get("prerequisite", {}).get("candidate_commit")
    if candidate != CANDIDATE:
        raise ValueError("continuation stage candidate differs")
    preflight = report.get("preflight", {})
    if preflight.get("gpu_started") is not False or preflight.get("cases") != 28:
        raise ValueError("complete 28-case R032 continuation preflight required")
    return report, sha(report_path)


def read_review(review: Path, report_sha: str) -> dict:
    checked(review, sha(review), owner=os.geteuid())
    value = json.loads(review.read_text(encoding="utf-8"))
    if (value.get("verdict") != "PASS" or value.get("stage_report_sha256") != report_sha
            or not isinstance(value.get("reviewer"), str) or not value["reviewer"].strip()
            or not isinstance(value.get("batch_template_sha256"), str)):
        raise ValueError("independent PASS review does not bind this stage report")
    return value


def batch_template() -> Path:
    value = os.environ.get("FT_T17_BATCH_TEMPLATE")
    if not value:
        raise ValueError("FT_T17_BATCH_TEMPLATE must name the reviewed template")
    path = Path(value)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise ValueError("read-only batch template required")
    return path


def sealed_failed_harness_parent() -> Path:
    """Verify the closed R034 parent before allocating its lettered supplement."""
    directory = ROUNDS / SUPPLEMENT_PARENT
    required = (directory / "round.json", directory / "MANIFEST.sha256", directory / "round_history",
                directory / "round_history" / "SHA256SUMS")
    if directory.is_symlink() or not directory.is_dir() or any(path.is_symlink() for path in required):
        raise ValueError("sealed R034 parent evidence is missing or symlinked")
    document = json.loads((directory / "round.json").read_text(encoding="utf-8"))
    if document.get("verdict") != "failed_harness":
        raise ValueError("R034 parent must be D04-sealed failed_harness")
    versions = sorted((path for path in (directory / "round_history").iterdir()
                       if re.fullmatch(r"round\.v\d+\.json", path.name)),
                      key=lambda path: int(re.fullmatch(r"round\.v(\d+)\.json", path.name).group(1)))
    if not versions or versions[-1].read_bytes() != (directory / "round.json").read_bytes():
        raise ValueError("R034 parent round history does not bind current round")
    expected_sums = "".join(sha(path) + "  " + path.name + "\n" for path in versions).encode("ascii")
    if (directory / "round_history" / "SHA256SUMS").read_bytes() != expected_sums:
        raise ValueError("R034 parent history sums differ")
    lines = (directory / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("R034 parent manifest is empty")
    for line in lines:
        digest, marker, name = line.partition("  ./")
        path = directory / name
        if not marker or not re.fullmatch(r"[0-9a-f]{64}", digest) or path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise ValueError("R034 parent manifest differs")
    return directory


def allocate(protocol, atomic, requested: str | None) -> tuple[str, int, int]:
    number, batch = protocol.next_round(ROUNDS), atomic.next_batch(ROUNDS)
    if requested is None:
        if number not in (33, 34):
            raise ValueError("reserved round range is E2-R033/E2-R034")
        return f"E2-R{number:03d}", batch, number
    if requested != SUPPLEMENT_RID:
        raise ValueError("only allocated supplementary RID E2-R034a is accepted")
    if number != 35:
        raise ValueError("supplement requires numeric round maximum 34")
    if batch != 63:
        raise ValueError("supplement requires next batch 63")
    parent = sealed_failed_harness_parent()
    if (ROUNDS / requested).exists() or (ROOT / "runs/dev_D16" / ("launch_" + requested + ".json")).exists():
        raise FileExistsError("supplementary round or launch receipt already exists")
    subprocess.run([PY, str(ROOT / "scripts" / "round_json_append.py"), str(parent), "check"], check=True, timeout=60)
    return requested, batch, number


def preflight(stage: Path, review: Path, *, rid: str | None = None):
    report, report_sha = read_stage(stage)
    review_doc = read_review(review, report_sha)
    if review_doc["batch_template_sha256"] != report["files"]["batchNN_T17.sh"]:
        raise ValueError("review template SHA differs from staged template")
    protocol = load_protocol()
    atomic = protocol.verified_module(HELPER, protocol.HELPER_SHA, "ft_t17_continuation_atomic")
    rid, batch, number = allocate(protocol, atomic, rid)
    receipt_path = ROOT / "runs/dev_D16" / ("launch_" + rid + ".json")
    if receipt_path.exists():
        raise FileExistsError("continuation launch receipt already reserves this RID")
    template = batch_template()
    # ``read_stage`` already rejects non-Linux execution; the fallback keeps
    # fake-helper unit tests portable without weakening the Linux launch path.
    checked(template, report["files"]["batchNN_T17.sh"], owner=getattr(os, "geteuid", lambda: None)())
    argv = [PY, "-u", str(stage / "t17_continuation_runner.py"), "--rid", rid, "--batch", str(batch),
            "--inputs", os.environ["FT_T17_INPUTS"], "--closure-binding", os.environ["FT_T17_CLOSURE_BINDING"],
            "--directory", str(ROUNDS / rid), "--resource-preflight"]
    subprocess.run(argv, check=True, timeout=180)
    if (protocol.next_round(ROUNDS) != number or atomic.next_batch(ROUNDS) != batch
            or (ROUNDS / rid).exists()):
        raise ValueError("round/batch ledger changed during continuation preflight")
    return report, report_sha, review_doc, protocol, atomic, argv, rid, batch, template


def freeze(stage: Path, report: dict, template: Path) -> Path:
    parent = Path("/tmp")
    mode = parent.stat().st_mode
    if parent.is_symlink() or not stat.S_ISDIR(mode) or mode & 0o022 and not mode & stat.S_ISVTX:
        raise ValueError("unsafe execution copy parent")
    execution = Path(tempfile.mkdtemp(prefix="ft-t17-continuation-", dir=parent))
    for name, digest in report["files"].items():
        source, target = stage / name, execution / name
        checked(source, digest, owner=os.geteuid()); target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream: stream.write(source.read_bytes())
        target.chmod(0o444)
    report_source, report_target = stage / "cpu_validation.json", execution / "cpu_validation.json"
    with report_target.open("xb") as stream: stream.write(report_source.read_bytes())
    report_target.chmod(0o444)
    target = execution / "batch_template.sh"
    with target.open("xb") as stream: stream.write(template.read_bytes())
    target.chmod(0o444)
    for directory in sorted((p for p in execution.rglob("*") if p.is_dir()), reverse=True): directory.chmod(0o555)
    execution.chmod(0o555)
    return execution


def launch(stage: Path, review: Path, *, rid: str | None = None):
    report, report_sha, review_doc, protocol, atomic, argv, rid, batch, template = preflight(stage, review, rid=rid)
    execution = freeze(stage, report, template)
    frozen_template = execution / "batch_template.sh"
    command = ["env", "FT_T17_STAGE=" + str(execution), "FT_T17_BATCH=" + str(batch),
               "FT_T17_BATCH_TEMPLATE=" + str(frozen_template), "FT_T17_INPUTS=" + os.environ["FT_T17_INPUTS"],
               "FT_T17_CLOSURE_BINDING=" + os.environ["FT_T17_CLOSURE_BINDING"], "bash", str(frozen_template), rid]
    receipt_path = ROOT / "runs/dev_D16" / ("launch_" + rid + ".json")
    reserved = {"schema":"ft_t17_continuation_launch/v1","state":"reserved","rid":rid,"batch":batch,
                "candidate_commit":CANDIDATE,"source_stage":str(stage),"stage_report_sha256":report_sha,
                "independent_review_sha256":sha(review),"batch_template_sha256":sha(template),
                "frozen_runner":str(execution / "t17_continuation_runner.py"),"source_files":report["files"]}
    return protocol.reserve_process(atomic, batch, rid, command, receipt_path, reserved)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True); parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--rid")
    parser.add_argument("--launch", action="store_true"); args = parser.parse_args(argv)
    if args.launch: print(json.dumps(launch(args.stage, args.review, rid=args.rid), sort_keys=True))
    else:
        _, report_sha, _, _, _, command, rid, batch, template = preflight(args.stage, args.review, rid=args.rid)
        print(json.dumps({"state":"preflight_only","rid":rid,"batch":batch,"argv":command,
                          "stage_report_sha256":report_sha,"batch_template_sha256":sha(template)}, sort_keys=True))


if __name__ == "__main__": main()
