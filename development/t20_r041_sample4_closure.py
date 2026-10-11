"""Fail-closed evidence verifier for PLAN §8.3's T20 four-case exception.

This reader never launches a service and never upgrades a boolean verdict.  It
requires the sealed R041 raw result, the accepted D14 T17 closure, an external
independent-review digest, and a caller-pinned copy of the D17 gate adapter.
It exists solely to decide whether T20 may select the four prescribed rows.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any

HERE = Path(__file__).resolve().parent
SCHEMA = "ft_t20_r041_sample4_closure/v1"
RID = "E2-R041-gate-D17"
CONTROL_COMMIT = "a9dca443cd07e1f60d1533e0a678935a09d21636"
INPUT_ORIGIN_COMMIT = "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
INPUT_SHA256 = "90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0"
SAMPLE4 = (
    "prefix-8192-tail-65",
    "prefix-12416-tail-4097",
    "prefix-12736-tail-8193",
    "prefix-18944-tail-4097",
)
ROLES = ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx")
CANONICAL_ROUNDS = Path("/data2/_shared/runs/ft_rounds")
CANONICAL_ROUNDS_POSIX = PurePosixPath("/data2/_shared/runs/ft_rounds")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_TAG = re.compile(r"E2-base\.1@([0-9a-f]{7,40})\Z")


class ClosureError(ValueError):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ClosureError("sealed regular JSON evidence required: " + str(path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ClosureError("readable JSON evidence required: " + str(path)) from error
    if not isinstance(value, dict):
        raise ClosureError("JSON object required: " + str(path))
    return value


def _inside(root: Path, relative: str, *, directory: bool = False) -> Path:
    item = Path(relative)
    if not relative or item.is_absolute() or ".." in item.parts:
        raise ClosureError("unsafe evidence path")
    path = root / item
    if path.is_symlink() or (not path.is_dir() if directory else not path.is_file()):
        raise ClosureError("evidence path is not a regular sealed member")
    if root.resolve() not in path.resolve().parents:
        raise ClosureError("evidence path escapes sealed round")
    return path


def _sealed_tree(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ClosureError("canonical R041 directory required")
    # A frozen R041 is a POSIX sealed archive. Windows fixtures cannot model
    # this permission invariant, but production validation runs on Linux.
    if os.name != "nt" and root.stat().st_mode & 0o222:
        raise ClosureError("R041 evidence directory remains writable")
    for path in root.rglob("*"):
        if path.is_symlink() or (os.name != "nt" and path.stat().st_mode & 0o222):
            raise ClosureError("R041 evidence tree contains a symlink or writable member")


def _canonical_arm(root: Path, raw_arm: str) -> tuple[Path, str]:
    if not isinstance(raw_arm, str):
        raise ClosureError("raw warm arm path missing")
    # Round evidence is generated on Linux; parse its serialized absolute path
    # as POSIX even when CPU tests run on Windows.
    path, prefix = PurePosixPath(raw_arm), CANONICAL_ROUNDS_POSIX / RID
    if not path.is_absolute():
        raise ClosureError("actual retained warm arm must retain canonical absolute path")
    try:
        relative = path.relative_to(prefix).as_posix()
    except ValueError as error:
        raise ClosureError("actual warm arm origin is not canonical R041") from error
    local = _inside(root, relative, directory=True)
    return local, relative

def _manifest(root: Path) -> dict[str, str]:
    manifest = root / "MANIFEST.sha256"
    if manifest.is_symlink() or not manifest.is_file():
        raise ClosureError("R041 MANIFEST.sha256 required")
    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        try:
            digest, relative = line.split("  ", 1)
        except ValueError as error:
            raise ClosureError("invalid R041 manifest") from error
        relative = relative.removeprefix("./")
        if _SHA.fullmatch(digest) is None or relative in entries:
            raise ClosureError("invalid R041 manifest digest/path")
        path = _inside(root, relative)
        if sha256(path) != digest:
            raise ClosureError("R041 manifest payload SHA differs: " + relative)
        entries[relative] = digest
    return entries


def _exact_inventory(root: Path, entries: dict[str, str]) -> None:
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    # round_close writes the signed D04 journal after MANIFEST creation.
    actual -= {"round.json", "MANIFEST.sha256"}
    actual = {name for name in actual if not name.startswith("round_history/")}
    if any(name.startswith("round_history/") for name in entries) or actual != set(entries):
        raise ClosureError("R041 manifest inventory is partial or has undeclared members")


def _manifest_file(root: Path, entries: dict[str, str], relative: str) -> Path:
    if relative not in entries:
        raise ClosureError("R041 manifest omits required evidence: " + relative)
    path = _inside(root, relative)
    if sha256(path) != entries[relative]:
        raise ClosureError("R041 required evidence digest differs: " + relative)
    return path


def _load_gate(expected_gate_case_sha256: str):
    path = HERE / "d17_gate_case.py"
    if _SHA.fullmatch(expected_gate_case_sha256 or "") is None or sha256(path) != expected_gate_case_sha256:
        raise ClosureError("caller-pinned d17_gate_case source SHA differs")
    spec = importlib.util.spec_from_file_location("t20_pinned_d17_gate_case", path)
    if spec is None or spec.loader is None:
        raise ClosureError("pinned D17 gate adapter is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _verify_tag(tag: str, commit: str, worktree: Path) -> dict[str, str]:
    match = _TAG.fullmatch(tag or "")
    if match is None or match.group(1) != commit[:len(match.group(1))]:
        raise ClosureError("PLAN §6 E2-base.1@<shortcommit> tag binding differs")
    try:
        tagged = subprocess.check_output(
            ["git", "-C", str(worktree), "rev-parse", f"refs/tags/{tag}^{{commit}}"], text=True
        ).strip()
        head = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=no"], text=True
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise ClosureError("exact candidate worktree/tag cannot be verified") from error
    if tagged != commit or head != commit or dirty:
        raise ClosureError("candidate tag, HEAD, or tracked-clean binding differs")
    return {"tag": tag, "commit": commit, "worktree": str(worktree.resolve())}


def _identity(row: dict[str, Any]) -> tuple[int, int, str]:
    identity = row.get("process_identity")
    if not isinstance(identity, dict) or type(identity.get("pid")) is not int or identity["pid"] <= 0:
        raise ClosureError("typed physical process PID required")
    if type(identity.get("start_ticks")) is not int or identity["start_ticks"] <= 0:
        raise ClosureError("typed physical process start_ticks required")
    expected = f"{identity['pid']}:{identity['start_ticks']}"
    if identity.get("execution_id") != expected:
        raise ClosureError("physical process execution_id binding differs")
    return identity["pid"], identity["start_ticks"], expected


def _tensor(path: Path):
    try:
        import torch
    except ImportError as error:
        raise ClosureError("torch CPU reader required for restore uint8 comparison") from error
    value = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(value, torch.Tensor):
        raise ClosureError("restore payload is not a tensor")
    return value


def _same_tensor(left: Path, right: Path) -> bool:
    a, b = _tensor(left), _tensor(right)
    return a.dtype == b.dtype and a.shape == b.shape and _tensor_bytes(a) == _tensor_bytes(b)


def _tensor_bytes(value) -> bytes:
    torch = __import__("torch")
    flat = torch.empty(value.numel(), dtype=value.dtype, device=value.device)
    flat.copy_(value.reshape(-1))
    return flat.view(torch.uint8).numpy().tobytes()


def _role_path(root: Path, manifest: dict[str, str], arm: dict[str, Any], role: str) -> Path:
    local_arm, rel_arm = _canonical_arm(root, arm.get("arm"))
    roles = arm.get("restore_roles")
    if not isinstance(roles, dict) or set(roles) != set(ROLES):
        raise ClosureError("exact four raw restore roles required")
    record = roles[role]
    resume = record.get("resume") if isinstance(record, dict) else None
    if not isinstance(resume, dict) or not isinstance(resume.get("file"), str) or _SHA.fullmatch(resume.get("sha256", "")) is None:
        raise ClosureError("raw restore role resume file/SHA required")
    file = Path(resume["file"])
    if file.is_absolute() or ".." in file.parts:
        raise ClosureError("raw restore role file escapes dump")
    relative = (Path(rel_arm) / "dump" / file).as_posix()
    path = _manifest_file(root, manifest, relative)
    if path != local_arm / "dump" / file or sha256(path) != resume["sha256"]:
        raise ClosureError("raw restore role file SHA differs")
    return path


def _raw_warm(root: Path, manifest: dict[str, str], arm: dict[str, Any], case: dict[str, Any], pins: dict[str, str]) -> dict[str, Any]:
    name = case["name"]
    """Re-read retained donor/hit receipts; never trust `result.json` summaries."""
    local_arm, rel_arm = _canonical_arm(root, arm.get("arm"))
    for required in ("donor.json", "hit.json", "observations.jsonl", "dump/index.jsonl", "serve.log", "owned_process.json"):
        _manifest_file(root, manifest, (Path(rel_arm) / required).as_posix())
    artifacts = _load_artifacts(pins)
    length = int(name.split("-")[1])
    birth = _read_json(_manifest_file(root, manifest, (Path(rel_arm) / "owned_process.json").as_posix()))
    donor = artifacts.request_evidence(local_arm, "donor", 0, 2)
    hit = artifacts.request_evidence(local_arm, "hit", length, 128)
    if len(donor["input_ids"]) != length + 1 or donor["input_ids"] != hit["input_ids"][:length + 1]:
        raise ClosureError("actual donor/hit input IDs do not bind")
    if arm.get("warm") != {"token_ids": hit["tokens"], "text": hit["response"]["text"], "input_ids_sha256": hit["input_sha256"]}:
        raise ClosureError("result warm summary differs from retained raw receipts")
    if arm.get("actual_cached_tokens") != length or hit["actual_cached_tokens"] != length:
        raise ClosureError("actual cached boundary differs")
    try:
        _, _, _, roles = artifacts._validate_states(case, local_arm / "dump", donor, hit,
                                                      read=artifacts.load_tensor, equal=artifacts.bit_equal)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ClosureError("actual donor/resume/restore state binding differs") from error
    if arm.get("restore_roles") != roles:
        raise ClosureError("result restore-role summary differs from recomputed raw states")
    return {"token_ids": hit["tokens"], "text": hit["response"]["text"], "input_ids_sha256": hit["input_sha256"], "uid": hit["uid"], "arm": local_arm, "birth": birth, "roles": roles}


def _load_artifacts(pins: dict[str, str]):
    # This source is part of the frozen verifier package and is never loaded
    # from the R041 directory. Its bytes must be caller-pinned before use.
    path = HERE / "t17_d14_artifacts.py"
    expected = pins["artifacts"]
    if _SHA.fullmatch(expected or "") is None or sha256(path) != expected:
        raise ClosureError("caller-pinned retained raw reader source SHA differs")
    spec = importlib.util.spec_from_file_location("t20_pinned_artifacts", path)
    if spec is None or spec.loader is None:
        raise ClosureError("retained raw reader unavailable")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def _warm_pair(root: Path, manifest: dict[str, str], case: dict[str, Any], control: dict[str, Any], candidate: dict[str, Any], candidate_commit: str, pins: dict[str, str]) -> dict[str, Any]:
    name = case["name"]
    expected_input_sha = case["input_ids_sha256"]
    if control.get("candidate_commit") != CONTROL_COMMIT or candidate.get("candidate_commit") != candidate_commit:
        raise ClosureError("warm candidate binding differs: " + name)
    a, b = _identity(control), _identity(candidate)
    if a == b or a[:2] == b[:2] or a[2] == b[2]:
        raise ClosureError("control/candidate reuse a physical process: " + name)
    length = int(name.split("-")[1])
    if control.get("coordinate") != length or candidate.get("coordinate") != length:
        raise ClosureError("raw warm coordinate differs: " + name)
    left, right = _raw_warm(root, manifest, control, case, pins), _raw_warm(root, manifest, candidate, case, pins)
    if left["birth"] != control["process_identity"] or right["birth"] != candidate["process_identity"]:
        raise ClosureError("retained server birth metadata differs from result identity")
    if (len(left["token_ids"]) != 128 or len(right["token_ids"]) != 128
            or left["token_ids"] != right["token_ids"] or left["text"] != right["text"]
            or left["input_ids_sha256"] != right["input_ids_sha256"] or left["input_ids_sha256"] != expected_input_sha):
        raise ClosureError("actual raw warm IDs/text/input differ: " + name)
    roles = {}
    for role in ROLES:
        if not _same_tensor(_role_path(root, manifest, control, role), _role_path(root, manifest, candidate, role)):
            raise ClosureError("restore dtype/shape/uint8 bytes differ: " + name + "/" + role)
        roles[role] = True
    return {"control_process": a[2], "candidate_process": b[2], "input_ids_sha256": left["input_ids_sha256"], "roles": roles}

def _verify(**kwargs: Any) -> dict[str, Any]:
    r041_round = Path(kwargs["r041_round"])
    review = Path(kwargs["r041_independent_review"])
    accepted = Path(kwargs["accepted_t17_path"])
    accepted_review = Path(kwargs["accepted_t17_review"])
    expected_commit = kwargs["expected_d17_commit"]
    if not isinstance(expected_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ClosureError("full expected D17 commit required")
    gate = _load_gate(kwargs["expected_gate_case_sha256"])
    if expected_commit != gate.CANDIDATE_COMMIT:
        raise ClosureError("expected D17 commit differs from pinned gate adapter")
    tag = _verify_tag(kwargs["expected_tag"], expected_commit, Path(kwargs["expected_d17_worktree"]))
    accepted_evidence = gate.verify_accepted_t17(accepted, accepted_review)
    root = r041_round.resolve()
    if r041_round.is_symlink() or not root.is_dir() or review.parent.resolve() != root:
        raise ClosureError("canonical same-round R041 review directory required")
    pins = {"artifacts": kwargs.get("expected_artifacts_sha256"), "t16": kwargs.get("expected_t16_runner_sha256"),
            "parser": kwargs.get("expected_parser_sha256"), "d04": kwargs.get("expected_d04_checker_sha256")}
    if any(_SHA.fullmatch(value or "") is None for value in pins.values()):
        raise ClosureError("all caller-pinned raw/cold/D04 helper SHAs are required")
    _sealed_tree(root)
    manifest = _manifest(root)
    _exact_inventory(root, manifest)
    _d04_history(root, pins)
    raw_path = _manifest_file(root, manifest, "result.json")
    review_rel = review.relative_to(root).as_posix()
    review_path = _manifest_file(root, manifest, review_rel)
    caller_sha = kwargs["caller_ir_sha256"]
    if _SHA.fullmatch(caller_sha or "") is None or sha256(review_path) != caller_sha:
        raise ClosureError("caller-pinned independent review SHA differs")
    closure = _read_json(root / "round.json")
    raw, ir = _read_json(raw_path), _read_json(review_path)
    if (closure.get("schema") != "ft_round/v2" or closure.get("card") != "T16" or closure.get("round_id") != RID
            or closure.get("verdict") != "kept" or not closure.get("closed_at") or closure.get("retractions") != []):
        raise ClosureError("canonical kept D04 R041 closure required")
    if closure.get("experimental", {}).get("candidate_commit") != expected_commit:
        raise ClosureError("D04 R041 candidate binding differs")
    if closure.get("independent_review_sha256") != caller_sha:
        raise ClosureError("D04 R041 does not bind independent review bytes")
    if (ir.get("schema") != "ft_d17_r041_independent_audit/v1" or ir.get("rid") != RID
            or ir.get("candidate_commit") != expected_commit or ir.get("control_commit") != CONTROL_COMMIT
            or ir.get("verdict") != "kept_pending_independent_review" or ir.get("result_sha256") != sha256(raw_path)):
        raise ClosureError("typed independent R041 raw audit binding required")
    if (raw.get("schema") != "ft_d17_r041/v1" or raw.get("rid") != RID
            or raw.get("candidate_commit") != expected_commit or raw.get("control_commit") != CONTROL_COMMIT
            or raw.get("verdict") != "measurements_pass_pending_independent_review"):
        raise ClosureError("actual D17 R041 raw result binding required")
    _recompute_cold(root, manifest, raw.get("cold"), pins)
    cases = raw.get("cases")
    if not isinstance(cases, dict) or set(cases) != set(SAMPLE4):
        raise ClosureError("exact PLAN §8.3 four raw warm cases required")
    expected_inputs = _accepted_inputs(accepted.parent)
    evidence = {name: _warm_pair(root, manifest, expected_inputs[name], cases[name].get("control", {}), cases[name].get("candidate", {}), expected_commit, pins) for name in SAMPLE4}
    return {"schema": SCHEMA, "permit": True, "admitted": False, "model_admitted": False,
            "rid": RID, "tag": tag, "accepted_t17": accepted_evidence, "r041_result_sha256": sha256(raw_path),
            "independent_review_sha256": caller_sha, "cases": evidence, "reasons": []}


def _accepted_inputs(directory: Path) -> dict[str, dict[str, Any]]:
    entries = _manifest(directory)
    path = _manifest_file(directory, entries, "real_inputs.json")
    if sha256(path) != INPUT_SHA256:
        raise ClosureError("accepted T17 real_inputs frozen SHA differs")
    value = _read_json(path)
    rows = value.get("cases")
    if value.get("candidate_commit") != INPUT_ORIGIN_COMMIT or not isinstance(rows, list):
        raise ClosureError("accepted T17 real_inputs candidate/cases binding differs")
    # verify_accepted_t17 has already authenticated the sealed R038 archive.
    # Keep byte origin distinct from the candidate covered by its reuse permit.
    provenance = _read_json(_manifest_file(directory, entries, "input_provenance.json"))
    if (provenance.get("raw_inputs_sha256") != INPUT_SHA256
            or provenance.get("origin_candidate") != INPUT_ORIGIN_COMMIT
            or provenance.get("retained_source_commit") != INPUT_ORIGIN_COMMIT
            or provenance.get("target_candidate") != CONTROL_COMMIT
            or provenance.get("measurement_scope") != "remaining_cases_only"):
        raise ClosureError("accepted T17 input origin/runtime provenance differs")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("name") not in SAMPLE4:
            continue
        name, query, length = row["name"], row.get("query"), row.get("length")
        if type(length) is not int or not isinstance(query, list) or any(type(token) is not int for token in query):
            raise ClosureError("accepted T17 typed case input is invalid")
        if len(query) != length + int(name.rsplit("-", 1)[1]) or _SHA.fullmatch(row.get("input_ids_sha256", "")) is None:
            raise ClosureError("accepted T17 case input SHA/length differs")
        result[name] = {"name": name, "length": length, "context": query[length-2:length],
                        "input_ids_sha256": row["input_ids_sha256"]}
    if set(result) != set(SAMPLE4) or any(len(row["context"]) != 2 for row in result.values()):
        raise ClosureError("accepted T17 real_inputs lacks exact sample4 cases")
    return result


def verify_sealed_startup(**kwargs: Any) -> dict[str, Any]:
    """T20 preflight consumes registered closure/review metadata, never R041 raw."""
    try:
        path = HERE / "d07_g3g4_prepare.py"
        spec = importlib.util.spec_from_file_location("t20_closed_gate", path)
        gate = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(gate)
        closed = gate.require_closed_round(RID, "kept")
        if Path(kwargs["r041_round"]).resolve() != closed.parent.resolve(): raise ClosureError("registered R041 path differs")
        closure, review = _read_json(closed), _read_json(Path(kwargs["r041_independent_review"]))
        caller = kwargs["caller_ir_sha256"]
        if (sha256(Path(kwargs["r041_independent_review"])) != caller or closure.get("independent_review_sha256") != caller
                or review.get("schema") != "ft_d17_r041_independent_audit/v1" or review.get("rid") != RID
                or review.get("candidate_commit") != kwargs["expected_d17_commit"] or review.get("control_commit") != CONTROL_COMMIT
                or review.get("verdict") != "kept_pending_independent_review"):
            raise ClosureError("sealed R041 review metadata differs")
        accepted = gate.require_closed_round("E2-R038", "kept")
        if Path(kwargs["accepted_t17_path"]).resolve() != accepted.resolve(): raise ClosureError("registered E2-R038 path differs")
        combined_path = Path(kwargs["accepted_t17_review"])
        combined = _read_json(combined_path)
        retained, recomputed, coverage = combined.get("r036_retained_cases"), combined.get("r038_recomputed_cases"), combined.get("canonical_coverage")
        accepted_round = _read_json(accepted)
        if (combined_path.parent.resolve() != accepted.parent.resolve()
                or accepted_round.get("independent_review_sha256") != sha256(combined_path)
                or combined.get("candidate_commit") != CONTROL_COMMIT or combined.get("verdict") != "PASS_ALL_28_PENDING_CANONICAL_D04"
                or not isinstance(retained, list) or not isinstance(recomputed, list) or len(retained) != 14 or len(recomputed) != 14
                or not isinstance(coverage, dict) or coverage.get("exact") is not True
                or coverage.get("actual_positions") != list(range(1,29)) or coverage.get("expected_positions") != list(range(1,29))
                or not isinstance(coverage.get("actual_case_names"), list) or coverage.get("actual_case_names") != coverage.get("expected_case_names") or len(coverage.get("actual_case_names")) != 28):
            raise ClosureError("E2-R038 combined 14+14 canonical coverage differs")
        rows = review.get("cases")
        if not isinstance(rows, dict) or set(rows) != set(SAMPLE4):
            raise ClosureError("R041 archived review lacks exact sample4 metadata")
        def input_sha(row):
            return row.get("input_ids_sha256", row.get("input_sha256")) if isinstance(row, dict) else None
        if any(_SHA.fullmatch(input_sha(rows[name]) or "") is None for name in SAMPLE4):
            raise ClosureError("R041 archived review sample4 input SHA differs")
        for name in SAMPLE4:
            comparison = rows[name].get("comparison")
            roles = comparison.get("four_roles_bitwise_equal") if isinstance(comparison, dict) else None
            if not isinstance(comparison, dict) or not isinstance(roles, dict) or set(roles) != set(ROLES) or not all(value is True for value in roles.values()) or comparison.get("token_ids_equal") is not True or comparison.get("full_text_equal") is not True or comparison.get("token_count") != 128:
                raise ClosureError("R041 archived review comparison metadata differs")
        return {"schema":SCHEMA,"permit":True,"admitted":False,"model_admitted":False,"rid":RID,
                "r041_result_sha256":review.get("result_sha256"),"independent_review_sha256":caller,
                "cases":{name:{"input_ids_sha256":input_sha(rows[name]),"reviewed":True} for name in SAMPLE4},"reasons":[]}
    except (ClosureError, OSError, ValueError, KeyError, TypeError) as error:
        return {"schema":SCHEMA,"permit":False,"admitted":False,"model_admitted":False,"reasons":[str(error)]}

def _recompute_cold(root: Path, manifest: dict[str, str], cold: Any, pins: dict[str, str]) -> None:
    if not isinstance(cold, dict) or cold.get("schema") != "ft_d17_default_cold/v1":
        raise ClosureError("actual default cold evidence required")
    control, candidate = cold.get("control"), cold.get("candidate")
    if not isinstance(control, str) or not isinstance(candidate, str):
        raise ClosureError("default cold arm paths required")
    left, rel_left = _canonical_arm(root, control); right, rel_right = _canonical_arm(root, candidate)
    for arm, rel in ((left, rel_left), (right, rel_right)):
        for name in ("serve.log", "det.json", "prefill_seq.txt"):
            _manifest_file(root, manifest, (Path(rel) / name).as_posix())
    # The retained functions are deliberately recomputed from raw paths.  A
    # result.json `passed` flag cannot grant this gate.
    runner = HERE / "t16_full_tail_base_runner.py"
    if _SHA.fullmatch(pins["t16"] or "") is None or sha256(runner) != pins["t16"]:
        raise ClosureError("caller-pinned T16 cold helper source SHA differs")
    spec = importlib.util.spec_from_file_location("t20_pinned_t16", runner)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    parser_path = HERE / "serve_args_diff.py"
    if _SHA.fullmatch(pins["parser"] or "") is None or sha256(parser_path) != pins["parser"]:
        raise ClosureError("caller-pinned serve-args parser source SHA differs")
    parser = __import__("runpy").run_path(str(parser_path))["parse"]
    module.strict_args(parser(str(left / "serve.log")), parser(str(right / "serve.log")), {})
    module.check_det([left / "det.json", right / "det.json"], 32052, 128)
    if not (left / "prefill_seq.txt").read_bytes() or (left / "prefill_seq.txt").read_bytes() != (right / "prefill_seq.txt").read_bytes():
        raise ClosureError("default cold raw prefill sequence differs")



def _d04_history(root: Path, pins: dict[str, str]) -> None:
    history = root / "round_history"
    if history.is_symlink() or not history.is_dir() or not any(history.iterdir()):
        raise ClosureError("canonical D04 round_history is required")
    checker = HERE / "t17_continuation_runner.py"
    if _SHA.fullmatch(pins["d04"] or "") is None or sha256(checker) != pins["d04"]:
        raise ClosureError("caller-pinned D04 history checker source SHA differs")
    spec = importlib.util.spec_from_file_location("t20_pinned_d04", checker)
    if spec is None or spec.loader is None:
        raise ClosureError("canonical D04 history checker unavailable")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.d04_check(root)

def verify(**kwargs: Any) -> dict[str, Any]:
    """Return a detailed false permit for any absent, mutable, or mismatched proof."""
    try:
        return _verify(**kwargs)
    except (ClosureError, OSError, ValueError, KeyError, TypeError) as error:
        return {"schema": SCHEMA, "permit": False, "admitted": False, "model_admitted": False,
                "reasons": [str(error)]}



