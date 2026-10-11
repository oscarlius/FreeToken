"""Read-only staging primitives for the isolated R041 CPU fixture.

This module deliberately does not create an admission result.  It copies the
exact frozen R035 input document into a caller-owned dev_D16 directory, verifies
its fixed digest, and writes an explicit fixture-only marker.  A caller must
still construct raw T17/R041 evidence and run the real closure verifier.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

INPUT_SHA256 = "90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0"
R035_INPUT = "/data2/_shared/runs/ft_rounds/E2-R035/real_inputs.json"
MARKER_SCHEMA = "ft_r041_closed_fixture/v1"


class FixtureError(ValueError):
    pass


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _write_once(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def freeze(path: Path) -> None:
    for item in sorted(path.rglob("*"), key=lambda value: len(value.parts), reverse=True):
        item.chmod(0o555 if item.is_dir() else 0o444)
    path.chmod(0o555)


def copy_r035_inputs(destination: Path | str, *, remote: str = "9", source: str = R035_INPUT) -> Path:
    """Copy only the immutable R035 input bytes to an empty caller-owned fixture.

    The SSH operation is read-only at the source.  No model, CUDA, service, or
    GPU lock is touched.  The output name avoids pretending this is a new
    tokenizer run.
    """
    destination = Path(destination)
    if destination.exists():
        raise FixtureError("fixture destination must not already exist")
    raw = subprocess.check_output(["ssh", "-o", "BatchMode=yes", remote, "cat", source])
    if sha256(raw) != INPUT_SHA256:
        raise FixtureError("R035 frozen real_inputs SHA differs")
    _write_once(destination / "realinput_28.json", raw)
    marker = {
        "schema": MARKER_SCHEMA,
        "fixture_only": True,
        "model_admitted": False,
        "admitted": False,
        "gpu_started": False,
        "requests_sent": False,
        "source": source,
        "source_sha256": INPUT_SHA256,
        "fixture_input": "realinput_28.json",
    }
    _write_once(destination / "fixture_only.json", (json.dumps(marker, sort_keys=True, indent=2) + "\n").encode())
    freeze(destination)
    return destination


def assert_fixture_only(directory: Path | str) -> dict:
    directory = Path(directory)
    marker = directory / "fixture_only.json"
    if marker.is_symlink() or not marker.is_file():
        raise FixtureError("fixture-only marker required")
    value = json.loads(marker.read_text(encoding="utf-8"))
    if (value.get("schema") != MARKER_SCHEMA or value.get("fixture_only") is not True
            or any(value.get(key) is not False for key in ("model_admitted", "admitted", "gpu_started", "requests_sent"))):
        raise FixtureError("fixture must never claim model/GPU admission")
    inputs = directory / value.get("fixture_input", "")
    if inputs.is_symlink() or not inputs.is_file() or sha256(inputs.read_bytes()) != INPUT_SHA256:
        raise FixtureError("fixture does not retain the exact R035 input bytes")
    return value


def _json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def _sha_path(path: Path) -> str:
    return sha256(path.read_bytes())


def _receipt_arm(arm: Path, *, case: dict, request: str, uid: str, cached: int, maximum: int,
                 tokens: list[int], text: str) -> None:
    """Write one retained endpoint receipt in the real artifacts-reader format."""
    ids = case["donor"] if request == "donor" else case["query"]
    input_sha = hashlib.sha256(__import__("struct").pack("<%di" % len(ids), *ids)).hexdigest()
    observations = [
        {"kind": "input", "uid": uid, "input_ids": ids, "input_length": len(ids),
         "ids_int32le_sha256": input_sha, "sampling": {"temperature": 0.0, "max_tokens": maximum}},
        {"kind": "admitted", "uid": uid, "prompt_tokens": len(ids), "cached_tokens": cached},
        {"kind": "prefill", "uid": uid, "cached_tokens": cached},
    ] + [{"kind": "token", "uid": uid, "token": token, "finished": i == len(tokens) - 1,
          "finish_reason": "length" if i == len(tokens) - 1 else None} for i, token in enumerate(tokens)]
    if request in {"hit", "query"}:
        observations.insert(3, {"kind": "restore-device", "uid": uid, "cached_tokens": case["length"], "src": 1, "dst": 2})
    if request == "hit":
        observations.insert(4, {"kind": "layer-children", "uid": uid, "outer_cached_tokens": case["length"],
                                "children": [{"cached_tokens": case["length"], "device_tokens": len(case["query"]),
                                              "has_initial_state": True, "fresh_state_indices": []}]})
    observed = arm / "observations.jsonl"
    existing = [json.loads(line) for line in observed.read_text(encoding="utf-8").splitlines() if line] if observed.exists() else []
    start = len(existing)
    response = {"uid": uid, "text": text, "finished": True, "finish_reason": "length",
                "usage": {"prompt_tokens": len(ids), "cached_tokens": cached, "completion_tokens": len(tokens)},
                "input_ids_sha256": input_sha}
    raw = arm / (request + ".raw.json")
    _json(raw, response)
    _json(arm / (request + ".json"), {"payload": {"input_ids": ids, "max_tokens": maximum}, "response": response,
          "status": 200, "response_sha256": _sha_path(raw), "expected_input_ids_sha256": input_sha,
          "observation_range": {"start": start, "end": start + len(observations)}, "raw_response_file": raw.name})
    observed.write_text("".join(json.dumps(row) + "\n" for row in [*existing, *observations]), encoding="utf-8")


def _operators(directory: Path, *, case: dict, torch) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    snapshot = directory / "op_hit_0_output.pt"
    tensor = torch.tensor([[1.0]], dtype=torch.float32)
    torch.save(tensor, snapshot)
    raw = tensor.contiguous().view(torch.uint8).numpy().tobytes()
    digest = sha256(raw)
    receipt = {"schema": "t17_operator_observe/v2", "boundary": case["length"], "query_tokens": len(case["query"]),
               "target_input_sha": case["input_ids_sha256"], "uid": "hit", "slot": 2,
               "records": [{"event": 0, "path": "model.0", "layer_idx": 0, "operator": {"method": "forward"},
                            "phase": "output", "occurrence": 1, "uid": "hit", "slot": 2,
                            "cached_tokens": case["length"], "device_tokens": len(case["query"]),
                            "extend_tokens": case["tail"], "absolute_positions": [case["length"]],
                            "shape": [1, 1], "dtype": str(tensor.dtype), "row_sha256": [digest],
                            "byte_sha256": digest, "snapshot_rows": 1, "file": snapshot.name,
                            "file_sha256": _sha_path(snapshot)}]}
    _json(directory / "op_hit_receipt.json", receipt)


def build_first_case(directory: Path | str, case: dict, *, source_root: Path | str) -> dict:
    """Build prefix-8192-tail-65 raw fixture data for the unmodified T17 auditor.

    Inputs are real frozen IDs supplied by the caller.  Output/tensor values are
    intentionally synthetic and are marked fixture-only by the caller.
    """
    try:
        import torch
    except ImportError as error:
        raise FixtureError("torch CPU is required for retained state fixtures") from error
    directory, source_root = Path(directory), Path(source_root)
    if directory.exists():
        raise FixtureError("case fixture directory must not already exist")
    if not isinstance(case.get("name"), str) or case.get("length") not in (8192, 12416, 12736, 18944):
        raise FixtureError("canonical T17 continuation case required")
    directory.mkdir(parents=True)
    # Use the exact archived reader source layout that audit_case loads.
    import shutil
    tools = directory / "source_tools" / "equiv_suite"; tools.mkdir(parents=True)
    for name in ("__init__.py", "raw.py", "schedule.py", "gate.py"):
        shutil.copyfile(source_root / "equiv_suite" / name, tools / name)
    for name in ("t17_d14_artifacts.py", "t17_operator_observe.py"):
        shutil.copyfile(source_root / name, directory / "source_tools" / name)
    schedule = [{"start": 0, "end": case["length"], "mode": "ordinary", "subchunks": [case["length"]]},
                {"start": case["length"], "end": len(case["query"]), "mode": "layer_major", "subchunks": [case["tail"]]}]
    _json(directory / "schedules" / case["name"] / "schedule.json", schedule)
    text, tokens = "fixture completion", list(range(128))
    # pathlib '+' is unavailable; retain the round's canonical arm spelling.
    warm = directory / (case["name"].replace("-", "_") + "_warm")
    warm.mkdir()
    _receipt_arm(warm, case=case, request="donor", uid="donor", cached=0, maximum=2, tokens=[1, 2], text=text)
    _receipt_arm(warm, case=case, request="hit", uid="hit", cached=case["length"], maximum=128, tokens=tokens, text=text)
    donor_files, resume_files = {}, {}
    dump = warm / "dump"; dump.mkdir()
    for role in ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx"):
        before = torch.tensor(case["query"][case["length"]-2:case["length"]], dtype=torch.int64).reshape(2, 1) if role.endswith("ngram_ctx") else torch.tensor([[1.0]])
        after = torch.cat((before, before), dim=1)
        left, right = "donor_" + role.replace(":", "_") + ".pt", "resume_" + role.replace(":", "_") + ".pt"
        torch.save(before, dump / left); torch.save(after, dump / right); donor_files[role], resume_files[role] = left, right
    (dump / "index.jsonl").write_text("\n".join(json.dumps(row) for row in (
        {"kind": "donate", "uid": "donor", "length": case["length"], "dev_slots": [1], "seq": 1, "files": donor_files},
        {"kind": "resume-device", "uid": "hit", "length": case["length"], "dev_slots": [1, 2], "seq": 2,
         "note": json.dumps({"src": 1, "dst": 2}), "files": resume_files},
    )) + "\n", encoding="utf-8")
    d0 = [{"start": 0, "end": case["length"], "mode": "ordinary", "subchunks": [case["length"]], "reqs": [{"rid": "donor", "cached_tokens": 0, "new_tokens": case["length"]}]},
          {"start": case["length"], "end": len(case["query"]), "mode": "layer_major", "subchunks": [case["tail"]], "reqs": [{"rid": "hit", "cached_tokens": case["length"], "new_tokens": case["tail"]}]}]
    (warm / "d0_prefill.jsonl").write_text("".join(json.dumps(row)+"\n" for row in d0), encoding="utf-8")
    _operators(warm / "operators", case=case, torch=torch)
    refs=[]
    for number in (1,2):
        arm=directory/(case["name"].replace("-", "_")+f"_reference_{number}"); arm.mkdir()
        _receipt_arm(arm, case=case, request="query", uid="hit", cached=0, maximum=128, tokens=tokens, text=text)
        ref_d0=[{**row,"reqs":[{"rid":"hit","cached_tokens":row["start"],"new_tokens":row["end"]-row["start"]}]} for row in schedule]
        (arm/"d0_prefill.jsonl").write_text("".join(json.dumps(row)+"\n" for row in ref_d0),encoding="utf-8")
        _json(arm/"serve_args.txt", {"_unique_suffix": f"'.pid={100+number}'"}); (arm/"ENV.txt").write_text("e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7\n"); (arm/"serve.log").write_text("fixture\n")
        _operators(arm/"operators",case=case,torch=torch); refs.append({"process_identity":{"pid":100+number,"start_ticks":200+number,"execution_id":f"{100+number}:{200+number}"}})
    return {"case": case, "saved": {"evidence": {"references": refs}, "result": {"verdict": "measurements_pass_pending_independent_review"}}, "warm": warm}


def build_all28_raw(directory: Path | str, inputs: dict, *, source_root: Path | str) -> list[dict]:
    """Generate every raw arm triple from immutable input IDs; fixture-only data."""
    rows = inputs.get("cases") if isinstance(inputs, dict) else None
    if not isinstance(rows, list) or len(rows) != 28:
        raise FixtureError("exact 28 frozen input cases required")
    root = Path(directory)
    if root.exists():
        raise FixtureError("all28 fixture root must not already exist")
    root.mkdir()
    built = []
    import shutil
    for row in rows:
        temp = root.parent / (root.name + "." + row["name"])
        item = build_first_case(temp, row, source_root=source_root)
        for path in temp.rglob("*"):
            if not path.is_file():
                continue
            target = root / path.relative_to(temp)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.read_bytes() != path.read_bytes():
                    raise FixtureError("shared archived fixture source differs")
            else:
                shutil.move(str(path), target)
        shutil.rmtree(temp)
        built.append({"case": row, "saved": item["saved"]})
    return built


def audit_all28_fixture(directory: Path | str, inputs: dict, built: list[dict], *, source_root: Path | str, frozen_inputs_path: Path | str | None = None) -> dict:
    """Create the minimum retained T17 envelope and run the real raw auditor."""
    directory, source_root = Path(directory), Path(source_root)
    if len(built) != 28 or len(inputs.get("cases", [])) != 28:
        raise FixtureError("all28 raw evidence is required before auditing")
    import importlib.util, shutil
    review_path = source_root / "t17_continuation_review.py"
    if not review_path.is_file(): raise FixtureError("actual auditor source required")
    source = directory / "source_tools"; source.mkdir(exist_ok=True)
    for name in ("t17_continuation_runner.py", "t17_d14_artifacts.py", "t17_operator_observe.py"):
        origin = source_root / name
        if not origin.is_file(): raise FixtureError("archived source missing: " + name)
        target = source / name
        if not target.exists(): shutil.copyfile(origin, target)
    cpu = source / "cpu_validation.json"; _json(cpu, {"schema":"fixture", "fixture_only":True})
    batch = directory / "batch.sh"; batch.write_text("#!/bin/sh\n# fixture_only\n", encoding="utf-8")
    if frozen_inputs_path is None:
        raise FixtureError("exact frozen input byte path required for all28 audit")
    raw_inputs = Path(frozen_inputs_path)
    if sha256(raw_inputs.read_bytes()) != INPUT_SHA256:
        raise FixtureError("all28 auditor requires exact R035 input bytes")
    shutil.copyfile(raw_inputs, directory / "real_inputs.json")
    files = {"t17_continuation_runner.py": _sha_path(source / "t17_continuation_runner.py")}
    receipt = {"rid": directory.name, "batch": 1, "candidate_commit": "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7",
               "source_files": files, "stage_report_sha256": _sha_path(cpu), "batch_template_sha256": _sha_path(batch), "batch_pid": 1,
               "fixture_only": True}
    _json(directory / "launch_receipt.json", receipt)
    _json(directory / "status_batch1.json", {"rid": directory.name, "batch": 1, "batch_pid": 1,
          "state": "complete_measurements_pending_independent_review", "fixture_only": True})
    spec=importlib.util.spec_from_file_location("r041_fixture_auditor", review_path); review=importlib.util.module_from_spec(spec); spec.loader.exec_module(review)
    readers=review.load_readers(directory); cases={}
    for item in built:
        row=item["case"]; checked=review.audit_case(directory,row,item["saved"],readers)
        # audit_case has recomputed the exact result; save it in runner-compatible form.
        _json(directory / "cases" / (row["name"]+".json"), item["saved"])
        cases[row["name"]] = {"result": item["saved"]["result"]}
    (directory / "result.json").write_text(json.dumps({"schema":"ft_t17_continuation/v1", "rid":directory.name,"batch":1,
          "candidate_commit":"e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7","cases":cases,
          "verdict":"measurements_pass_pending_independent_review","fixture_only":True}) + "\n", encoding="utf-8")
    return review.audit(directory, directory / "launch_receipt.json", directory / "status_batch1.json")

