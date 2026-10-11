import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "t20_r041_sample4_closure", Path(__file__).parents[1] / "t20_r041_sample4_closure.py"
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return path


@pytest.mark.parametrize("changed", [None, "origin_candidate", "target_candidate", "raw_inputs_sha256", "retained_source_commit", "measurement_scope"])
def test_accepted_inputs_preserves_reused_origin_and_runtime_target(monkeypatch, tmp_path, changed):
    rows = []
    for name in m.SAMPLE4:
        length, tail = int(name.split("-")[1]), int(name.rsplit("-", 1)[1])
        rows.append({"name": name, "length": length, "query": [1] * (length + tail), "input_ids_sha256": "a" * 64})
    inputs = put(tmp_path / "real_inputs.json", {"candidate_commit": m.INPUT_ORIGIN_COMMIT, "cases": rows})
    provenance = {"raw_inputs_sha256": m.INPUT_SHA256, "origin_candidate": m.INPUT_ORIGIN_COMMIT,
                  "retained_source_commit": m.INPUT_ORIGIN_COMMIT, "target_candidate": m.CONTROL_COMMIT,
                  "measurement_scope": "remaining_cases_only"}
    if changed:
        provenance[changed] = "wrong"
    put(tmp_path / "input_provenance.json", provenance)
    # Small input fixture stands in for the byte-pinned 28-case file. The
    # manifest/path reader remains real; only its expected input digest differs.
    monkeypatch.setattr(m, "INPUT_SHA256", sha(inputs))
    if changed != "raw_inputs_sha256":
        provenance["raw_inputs_sha256"] = sha(inputs)
        put(tmp_path / "input_provenance.json", provenance)
    (tmp_path / "MANIFEST.sha256").write_text("".join(
        f"{sha(path)}  {path.name}\n" for path in (inputs, tmp_path / "input_provenance.json")))
    if changed:
        with pytest.raises(m.ClosureError, match="provenance"):
            m._accepted_inputs(tmp_path)
    else:
        assert set(m._accepted_inputs(tmp_path)) == set(m.SAMPLE4)
        assert m.CONTROL_COMMIT == "a9dca443cd07e1f60d1533e0a678935a09d21636"
        assert m.INPUT_ORIGIN_COMMIT == "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"



def unseal(root: Path):
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o755 if path.is_dir() else 0o644)
    root.chmod(0o755)


def seal(root: Path):
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        path.chmod(0o555 if path.is_dir() else 0o444)
    root.chmod(0o555)


def fixture(tmp_path):
    root = tmp_path / "r041"; root.mkdir()
    candidate = "2" * 40
    files = []
    cases = {}
    for number, name in enumerate(m.SAMPLE4, 1):
        length = int(name.split("-")[1])
        row = {}
        for side, commit, pid in (("control", m.CONTROL_COMMIT, number * 10), ("candidate", candidate, number * 10 + 1)):
            rel_arm = f"arms/{name}/{side}"; arm = str(m.CANONICAL_ROUNDS_POSIX / m.RID / rel_arm); dump = root / rel_arm / "dump"; dump.mkdir(parents=True)
            roles = {}
            for role in m.ROLES:
                payload = (role + "-same").encode()
                path = dump / (role.replace(":", "_") + ".pt")
                path.write_bytes(payload); files.append(path)
                roles[role] = {"resume": {"file": path.name, "sha256": sha(path)}}
            identity={"pid": pid, "start_ticks": pid + 100, "execution_id": f"{pid}:{pid + 100}"}
            birth=put(dump.parent / "owned_process.json", identity); files.append(birth)
            row[side] = {"candidate_commit": commit, "coordinate": length, "arm": arm,
                         "process_identity": identity,
                         "warm": {"token_ids": list(range(128)), "text": "complete text", "input_ids_sha256": "a" * 64},
                         "actual_raw": {"token_ids": list(range(128)), "text": "complete text", "input_ids_sha256": "a" * 64},
                         "restore_roles": roles}
        cases[name] = row
    raw = {"schema": "ft_d17_r041/v1", "rid": m.RID, "candidate_commit": candidate,
           "control_commit": m.CONTROL_COMMIT, "verdict": "measurements_pass_pending_independent_review",
           "cold": {"schema": "ft_d17_default_cold/v1", "passed": True}, "cases": cases}
    raw_path = put(root / "result.json", raw); files.append(raw_path)
    review = {"schema": "ft_d17_r041_independent_audit/v1", "rid": m.RID, "candidate_commit": candidate,
              "control_commit": m.CONTROL_COMMIT, "verdict": "kept_pending_independent_review", "result_sha256": sha(raw_path)}
    review_path = put(root / "independent_review.json", review); files.append(review_path)
    closure = {"schema": "ft_round/v2", "card": "T16", "round_id": m.RID, "verdict": "kept", "closed_at": "2026-10-05", "retractions": [],
               "experimental": {"candidate_commit": candidate}, "independent_review_sha256": sha(review_path)}
    put(root / "round.json", closure)
    accepted_round=put(root / "accepted-round.json", {}); accepted_review=put(root / "accepted-review.json", {"cases": [{"case": name, "input_ids_sha256": "a" * 64} for name in m.SAMPLE4]}); files.extend((accepted_round, accepted_review))
    history=root / "round_history"; history.mkdir(); history_file=put(history / "001.json", {"event": "close"}); # D04 creates a hash-linked journal after MANIFEST; it is checker-authenticated, not manifest-bound.
    (root / "MANIFEST.sha256").write_text("".join(f"{sha(path)}  {path.relative_to(root).as_posix()}\n" for path in files), encoding="utf-8")
    seal(root)
    return root, candidate, review_path


def args(root, candidate, review):
    return dict(r041_round=root, r041_independent_review=review, caller_ir_sha256=sha(review),
                accepted_t17_path=root / "accepted-round.json", accepted_t17_review=root / "accepted-review.json",
                expected_tag="E2-base.1@" + candidate[:8], expected_d17_commit=candidate,
                expected_d17_worktree=root, expected_gate_case_sha256=sha(Path(m.HERE / "d17_gate_case.py")),
                expected_artifacts_sha256="b" * 64, expected_t16_runner_sha256="c" * 64, expected_parser_sha256="d" * 64, expected_d04_checker_sha256="e" * 64)


def allowed(monkeypatch, candidate):
    gate = SimpleNamespace(CANDIDATE_COMMIT=candidate,
                           verify_accepted_t17=lambda closure, review: {"rid": "E2-R034a", "closure": str(closure)})
    monkeypatch.setattr(m, "_load_gate", lambda digest: gate)
    monkeypatch.setattr(m, "_verify_tag", lambda tag, commit, worktree: {"tag": tag, "commit": commit, "worktree": str(worktree)})
    monkeypatch.setattr(m, "_recompute_cold", lambda *_: None)
    monkeypatch.setattr(m, "_d04_history", lambda *_: None)
    monkeypatch.setattr(m, "_accepted_inputs", lambda *_: {name: {"name": name, "length": int(name.split("-")[1]), "context": [1, 2], "input_ids_sha256": "a" * 64} for name in m.SAMPLE4})
    def reread(_root, _manifest, arm, _name, _pins):
        if arm["warm"] != arm["actual_raw"]:
            raise m.ClosureError("result warm summary differs from retained raw receipts")
        return {**arm["actual_raw"], "birth": arm["process_identity"], "roles": arm["restore_roles"]}
    monkeypatch.setattr(m, "_raw_warm", reread)
    monkeypatch.setattr(m, "_same_tensor", lambda left, right: left.read_bytes() == right.read_bytes())


def test_complete_raw_evidence_permits_only_sample4(monkeypatch, tmp_path):
    root, candidate, review = fixture(tmp_path); allowed(monkeypatch, candidate)
    result = m.verify(**args(root, candidate, review))
    assert result["permit"] is True
    assert tuple(result["cases"]) == m.SAMPLE4
    assert result["admitted"] is result["model_admitted"] is False


@pytest.mark.parametrize("change, expected", [
    (lambda raw: raw["cases"].pop(m.SAMPLE4[-1]), "four raw warm"),
    (lambda raw: raw["cases"][m.SAMPLE4[0]]["candidate"]["warm"].update(text="tampered"), "summary differs"),
    (lambda raw: raw["cases"][m.SAMPLE4[0]]["candidate"]["process_identity"].update(pid=10, start_ticks=110, execution_id="10:110"), "reuse a physical process"),
])
def test_raw_mismatch_never_upgrades_to_permit(monkeypatch, tmp_path, change, expected):
    root, candidate, review = fixture(tmp_path); allowed(monkeypatch, candidate); unseal(root)
    raw_path = root / "result.json"; raw = json.loads(raw_path.read_text()); change(raw); put(raw_path, raw)
    # Re-seal the manifest and external review around the changed bytes: semantic validation must still reject it.
    ir = json.loads(review.read_text()); ir["result_sha256"] = sha(raw_path); put(review, ir)
    closure = json.loads((root / "round.json").read_text()); closure["independent_review_sha256"] = sha(review); put(root / "round.json", closure)
    lines = []
    for line in (root / "MANIFEST.sha256").read_text().splitlines():
        _, rel = line.split("  ", 1); lines.append(f"{sha(root / rel)}  {rel}\n")
    (root / "MANIFEST.sha256").write_text("".join(lines))
    seal(root)
    result = m.verify(**args(root, candidate, review))
    assert result["permit"] is False
    assert expected in result["reasons"][0]


def test_role_signed_zero_byte_difference_fails(monkeypatch, tmp_path):
    root, candidate, review = fixture(tmp_path); allowed(monkeypatch, candidate); unseal(root)
    raw = json.loads((root / "result.json").read_text())
    path = root / "arms" / m.SAMPLE4[0] / "candidate" / "dump" / "conv_states.pt"
    path.write_bytes(b"signed-zero-different")
    raw["cases"][m.SAMPLE4[0]]["candidate"]["restore_roles"]["conv_states"]["resume"]["sha256"] = sha(path)
    put(root / "result.json", raw)
    ir = json.loads(review.read_text()); ir["result_sha256"] = sha(root / "result.json"); put(review, ir)
    closure = json.loads((root / "round.json").read_text()); closure["independent_review_sha256"] = sha(review); put(root / "round.json", closure)
    lines=[]
    for line in (root / "MANIFEST.sha256").read_text().splitlines():
        _, rel=line.split("  ",1); lines.append(f"{sha(root/rel)}  {rel}\n")
    (root / "MANIFEST.sha256").write_text("".join(lines))
    seal(root)
    result=m.verify(**args(root,candidate,review))
    assert result["permit"] is False and "restore dtype/shape/uint8 bytes differ" in result["reasons"][0]


def test_tampered_manifest_or_unaccepted_t17_falls_back(monkeypatch, tmp_path):
    root, candidate, review = fixture(tmp_path); allowed(monkeypatch, candidate); unseal(root)
    (root / "result.json").write_text("{}")
    seal(root)
    result = m.verify(**args(root, candidate, review))
    assert result["permit"] is False and "manifest payload SHA" in result["reasons"][0]
    monkeypatch.setattr(m, "_load_gate", lambda _: SimpleNamespace(CANDIDATE_COMMIT=candidate, verify_accepted_t17=lambda *_: (_ for _ in ()).throw(ValueError("T17 rejected"))))
    result = m.verify(**args(root, candidate, review))
    assert result["permit"] is False


def test_pinned_gate_source_and_tag_format_fail_closed(monkeypatch, tmp_path):
    root, candidate, review = fixture(tmp_path); allowed(monkeypatch, candidate)
    bad = args(root, candidate, review); bad["expected_gate_case_sha256"] = "0" * 64
    # Restore real source loader so the caller hash is exercised.
    monkeypatch.undo()
    result = m.verify(**bad)
    assert result["permit"] is False and "source SHA" in result["reasons"][0]
    assert m._TAG.fullmatch("E2-base.1@" + candidate[:8])
    assert m._TAG.fullmatch("E2-base.1@not-a-commit") is None




def test_real_torch_uint8_detects_signed_zero_when_available(tmp_path):
    torch = pytest.importorskip("torch")
    plus, minus = tmp_path / "plus.pt", tmp_path / "minus.pt"
    torch.save(torch.tensor([0.0], dtype=torch.float32), plus)
    torch.save(torch.tensor([-0.0], dtype=torch.float32), minus)
    assert m._same_tensor(plus, minus) is False
    torch.save(torch.tensor([0], dtype=torch.int32), minus)
    assert m._same_tensor(plus, minus) is False


def test_tag_suffix_mismatch_fails_before_git(monkeypatch, tmp_path):
    called = []
    monkeypatch.setattr(m.subprocess, "check_output", lambda *_args, **_kwargs: called.append(1))
    with pytest.raises(m.ClosureError, match="E2-base.1"):
        m._verify_tag("E2-base.1@deadbeef", "2" * 40, tmp_path)
    assert called == []



def test_noncanonical_absolute_arm_falls_back(monkeypatch, tmp_path):
    root, candidate, review = fixture(tmp_path); allowed(monkeypatch, candidate); unseal(root)
    raw = json.loads((root / "result.json").read_text())
    raw["cases"][m.SAMPLE4[0]]["candidate"]["arm"] = "/tmp/foreign-arm"
    put(root / "result.json", raw)
    ir = json.loads(review.read_text()); ir["result_sha256"] = sha(root / "result.json"); put(review, ir)
    closure = json.loads((root / "round.json").read_text()); closure["independent_review_sha256"] = sha(review); put(root / "round.json", closure)
    lines = [f"{sha(root / line.split('  ', 1)[1])}  {line.split('  ', 1)[1]}\n" for line in (root / "MANIFEST.sha256").read_text().splitlines()]
    (root / "MANIFEST.sha256").write_text("".join(lines))
    seal(root)
    result = m.verify(**args(root, candidate, review))
    assert result["permit"] is False and "origin is not canonical" in result["reasons"][0]


def test_partial_manifest_and_writable_tree_fail_closed(monkeypatch, tmp_path):
    root, candidate, review = fixture(tmp_path); allowed(monkeypatch, candidate); unseal(root)
    lines = (root / "MANIFEST.sha256").read_text().splitlines()
    (root / "MANIFEST.sha256").write_text("\n".join(lines[1:]) + "\n")
    seal(root)
    result = m.verify(**args(root, candidate, review))
    assert result["permit"] is False and "manifest inventory" in result["reasons"][0]
    unseal(root)
    with pytest.raises(m.ClosureError, match="writable"):
        monkeypatch.setattr(m.os, "name", "posix")
        m._sealed_tree(root)


def test_raw_reader_rejects_result_summary_that_disagrees_with_retained_receipts(monkeypatch, tmp_path):
    root = tmp_path / "round"; arm_dir = root / "arms" / "case"; (arm_dir / "dump").mkdir(parents=True)
    for name in ("donor.json", "hit.json", "observations.jsonl", "dump/index.jsonl", "serve.log", "owned_process.json"):
        (arm_dir / name).write_text("{}")
    manifest = {path.relative_to(root).as_posix(): sha(path) for path in root.rglob("*") if path.is_file()}
    (arm_dir / "owned_process.json").write_text("{}")
    manifest[(arm_dir / "owned_process.json").relative_to(root).as_posix()] = sha(arm_dir / "owned_process.json")
    class Art:
        @staticmethod
        def request_evidence(_arm, request, cached, maximum):
            if request == "donor":
                return {"input_ids": list(range(8193)), "tokens": [1, 2], "response": {"text": "donor"}, "input_sha256": "a" * 64, "actual_cached_tokens": cached, "uid": "d"}
            return {"input_ids": list(range(8193)) + [5], "tokens": [3] * 128, "response": {"text": "actual"}, "input_sha256": "a" * 64, "actual_cached_tokens": cached, "uid": "h"}
    monkeypatch.setattr(m, "_load_artifacts", lambda *_: Art)
    arm = {"arm": str(m.CANONICAL_ROUNDS_POSIX / m.RID / "arms/case"), "actual_cached_tokens": 8192,
           "warm": {"token_ids": [9] * 128, "text": "forged", "input_ids_sha256": "a" * 64}}
    with pytest.raises(m.ClosureError, match="summary differs"):
        m._raw_warm(root, manifest, arm, {"name": m.SAMPLE4[0], "length": 8192, "context": [1, 2]}, {"artifacts": "b" * 64})



def test_full_warm_raw_reader_path_with_real_tensors_when_available(monkeypatch, tmp_path):
    torch = pytest.importorskip("torch")
    artifact_spec = importlib.util.spec_from_file_location("actual_artifacts", Path(m.HERE) / "t17_d14_artifacts.py")
    artifacts = importlib.util.module_from_spec(artifact_spec); artifact_spec.loader.exec_module(artifacts)
    root, candidate, review = fixture(tmp_path); unseal(root)
    raw = json.loads((root / "result.json").read_text())

    def bind_arm(arm, name):
        length, tail = map(int, __import__("re").findall(r"\d+", name))
        local = root / "arms" / name / ("control" if arm["candidate_commit"] == m.CONTROL_COMMIT else "candidate")
        ids = list(range(length + tail)); donor_ids = ids[:length + 1]
        rows = []
        for request, request_ids, cached, maximum, uid, tokens in (
            ("donor", donor_ids, 0, 2, "donor", [7, 8]), ("hit", ids, length, 128, "hit", list(range(128))),
        ):
            start = len(rows); input_sha = artifacts.ids_sha(request_ids)
            rows.extend([
                {"kind": "input", "uid": uid, "input_ids": request_ids, "input_length": len(request_ids),
                 "ids_int32le_sha256": input_sha, "sampling": {"temperature": 0.0, "max_tokens": maximum}},
                {"kind": "admitted", "uid": uid, "prompt_tokens": len(request_ids), "cached_tokens": cached},
                {"kind": "prefill", "uid": uid, "cached_tokens": cached},
                *[{"kind": "token", "uid": uid, "token": token, "finished": index == len(tokens)-1}
                  for index, token in enumerate(tokens)],
            ])
            response = {"uid": uid, "text": "actual output", "finished": True, "finish_reason": "length",
                        "usage": {"prompt_tokens": len(request_ids), "cached_tokens": cached, "completion_tokens": len(tokens)},
                        "input_ids_sha256": input_sha}
            raw_file = local / f"{request}.raw.json"; put(raw_file, response)
            receipt = {"payload": {"input_ids": request_ids, "max_tokens": maximum}, "response": response, "status": 200,
                       "response_sha256": sha(raw_file), "expected_input_ids_sha256": input_sha,
                       "observation_range": {"start": start, "end": len(rows)}, "raw_response_file": raw_file.name}
            put(local / f"{request}.json", receipt)
        # The actual raw reader binds this restore observation to the dump index.
        hit_start = next(index for index, row in enumerate(rows) if row.get("kind") == "input" and row.get("uid") == "hit")
        rows.insert(hit_start + 3, {"kind": "restore-device", "uid": "hit", "cached_tokens": length, "src": 1, "dst": 2})
        hit_receipt = json.loads((local / "hit.json").read_text()); hit_receipt["observation_range"]["end"] += 1
        put(local / "hit.json", hit_receipt)
        (local / "observations.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        (local / "serve.log").write_text("retained fixture service log\n", encoding="utf-8")
        put(local / "owned_process.json", arm["process_identity"])
        donor_files, resume_files = {}, {}
        for role in m.ROLES:
            donor_path = local / "dump" / ("donor_" + role.replace(":", "_") + ".pt")
            resume_path = local / "dump" / arm["restore_roles"][role]["resume"]["file"]
            before = torch.tensor([length - 2, length - 1], dtype=torch.int64).reshape(2, 1) if role == "slot:ple_ngram_ctx" else torch.tensor([[1.0]], dtype=torch.float32)
            after = torch.cat((before, before), dim=1)
            torch.save(before, donor_path); torch.save(after, resume_path)
            donor_files[role], resume_files[role] = donor_path.name, resume_path.name
        (local / "dump" / "index.jsonl").write_text("".join(json.dumps(row) + "\n" for row in (
            {"kind": "donate", "uid": "donor", "length": length, "dev_slots": [1], "seq": 1, "files": donor_files},
            {"kind": "resume-device", "uid": "hit", "length": length, "dev_slots": [1, 2], "seq": 2,
             "note": json.dumps({"src": 1, "dst": 2}), "files": resume_files},
        )))
        donor = artifacts.request_evidence(local, "donor", 0, 2); hit = artifacts.request_evidence(local, "hit", length, 128)
        case = {"name": name, "length": length, "context": ids[length-2:length]}
        _, _, _, roles = artifacts._validate_states(case, local / "dump", donor, hit,
                                                     read=artifacts.load_tensor, equal=artifacts.bit_equal)
        arm["restore_roles"] = roles
        arm["actual_cached_tokens"] = length
        arm["warm"] = {"token_ids": list(range(128)), "text": "actual output", "input_ids_sha256": artifacts.ids_sha(ids)}

    for name, row in raw["cases"].items():
        bind_arm(row["control"], name); bind_arm(row["candidate"], name)
    put(root / "result.json", raw)
    ir = json.loads(review.read_text()); ir["result_sha256"] = sha(root / "result.json"); put(review, ir)
    closure = json.loads((root / "round.json").read_text()); closure["independent_review_sha256"] = sha(review); put(root / "round.json", closure)
    paths = [path for path in root.rglob("*") if path.is_file() and path.name not in {"round.json", "MANIFEST.sha256"} and not path.relative_to(root).as_posix().startswith("round_history/")]
    (root / "MANIFEST.sha256").write_text("".join(f"{sha(path)}  {path.relative_to(root).as_posix()}\n" for path in paths))
    seal(root)
    gate = SimpleNamespace(CANDIDATE_COMMIT=candidate, verify_accepted_t17=lambda *_: {"rid": "E2-R034a"})
    monkeypatch.setattr(m, "_load_gate", lambda *_: gate); monkeypatch.setattr(m, "_verify_tag", lambda *args: {"tag": args[0]})
    monkeypatch.setattr(m, "_d04_history", lambda *_: None); monkeypatch.setattr(m, "_recompute_cold", lambda *_: None)
    monkeypatch.setattr(m, "_accepted_inputs", lambda *_: {name: {"name": name, "length": int(name.split("-")[1]), "context": [int(name.split("-")[1])-2, int(name.split("-")[1])-1], "input_ids_sha256": raw["cases"][name]["control"]["warm"]["input_ids_sha256"]} for name in m.SAMPLE4})
    value = args(root, candidate, review); value["expected_artifacts_sha256"] = sha(Path(m.HERE) / "t17_d14_artifacts.py")
    result = m.verify(**value)
    assert result["permit"] is True, result["reasons"]






