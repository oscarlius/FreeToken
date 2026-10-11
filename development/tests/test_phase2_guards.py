from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


DEVELOPMENT = Path(__file__).parents[1]
REPO_ROOT = Path(os.environ.get("PHASE2_REPO_ROOT", DEVELOPMENT.parent))


def load_module(name: str):
    path = DEVELOPMENT / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"phase2_guard_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_path_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


T04 = load_module("t04_logits_phase2")
T10P1 = load_module("t10_raw_phase1")
T10P2 = load_module("t10_logits_stage2")
SELF_CHECK = load_module("d03_gpu_selfcheck")


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def token_record(module, *, uid: int, pid: int, prompt: list[int], generated: list[int]) -> dict:
    digest = module.ids_digest if hasattr(module, "ids_digest") else module.idsha
    return {
        "schema": "ft_dev_tokens/v1",
        "uid": uid,
        "pid": pid,
        "prompt_length": len(prompt),
        "prompt_ids": prompt,
        "generated_ids": generated,
        "prompt_ids_sha256_int32le": digest(prompt),
        "generated_ids_sha256_int32le": digest(generated),
        "input_ids_sha256_int32le": digest(prompt + generated),
        "finish_reason": "length",
        "matched_stop": None,
    }


def capture_result(module, *, uid: int, sequence: int, prompt: list[int]) -> dict:
    digest = module.ids_digest if hasattr(module, "ids_digest") else module.idsha
    return {
        "uid": uid,
        "dump_seq": sequence,
        "k": 1,
        "input_length": len(prompt),
        "input_sha256": digest(prompt),
        "positions": [len(prompt) - 1],
    }


def fake_capture_run(result: dict):
    def run(argv, **kwargs):
        endpoint = argv[argv.index("--base-url") + 1]
        assert endpoint == "http://127.0.0.1:8095"
        kwargs["stdout"].write(json.dumps(result) + "\n")
        return SimpleNamespace(returncode=0)
    return run


def write_selfcheck_manifest(root: Path, token_path: Path) -> None:
    members = [token_path, root / "selfcheck.json", root / "admission.json"]
    (root / "MANIFEST.sha256").write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root)}\n"
            for path in members
        ),
        encoding="utf-8",
    )


def t04_fixture(tmp_path: Path, monkeypatch, *, result_uid=7, index_uid=7,
                token_prompt=None, pgid=101, tamper_prompt_sha=False):
    prompt = list(range(T04.G4_PROMPT_LENGTH))
    capture_prompt = prompt + [99]
    if token_prompt is None:
        token_prompt = capture_prompt
    arm = tmp_path / "arm"
    dump = arm / "logits"
    dump.mkdir(parents=True)
    write_json(arm / "owned_process.json", {"pid": 901, "pgid": 101})
    result = capture_result(T04, uid=result_uid, sequence=4, prompt=capture_prompt)
    write_json(dump / "index.jsonl", {
        "kind": "logits", "uid": index_uid, "seq": 4,
    })
    token = token_record(T04, uid=result_uid, pid=990, prompt=token_prompt, generated=[100])
    if tamper_prompt_sha:
        token["prompt_ids_sha256_int32le"] = "0" * 64
    write_json(dump / f"tokens_uid{result_uid}_pid990.json", token)
    instance = T04.Phase2.__new__(T04.Phase2)
    instance.args = SimpleNamespace(k=1)
    instance._input_length = len(prompt) + 1
    monkeypatch.setattr(T04.subprocess, "run", fake_capture_run(result))
    monkeypatch.setattr(T04.os, "getpgid", lambda _pid: pgid, raising=False)
    return instance, arm, prompt


def test_t04_capture_binds_real_index_terminal_uid_sha_and_pgid(tmp_path, monkeypatch):
    instance, arm, prompt = t04_fixture(tmp_path, monkeypatch)
    prefix, suffix = tmp_path / "prefix.json", tmp_path / "suffix.json"
    write_json(prefix, prompt)
    write_json(suffix, [99])
    result = instance.run_capture(arm, {}, prefix, suffix, restore=False)
    assert result["capture_pid"] == 990
    assert json.loads((arm / "capture.json").read_text())["uid"] == 7
    assert json.loads(prefix.read_text()) == prompt
    assert json.loads(suffix.read_text()) == [99]
    assert prompt[0] == 0


@pytest.mark.parametrize(
    ("result_uid", "index_uid", "token_prompt", "pgid", "tamper_prompt_sha", "error"),
    [
        (7, 7, None, 999, False, "process group"),
        (7, 8, None, 101, False, "UID/sequence"),
        (7, 7, list(range(T04.G4_PROMPT_LENGTH - 1)), 101, False, "prompt length"),
        (7, 7, None, 101, True, "ID hashes"),
    ],
)
def test_t04_capture_rejects_foreign_pgid_uid_or_terminal_input(
    tmp_path, monkeypatch, result_uid, index_uid, token_prompt, pgid, tamper_prompt_sha, error
):
    instance, arm, prompt = t04_fixture(
        tmp_path, monkeypatch, result_uid=result_uid, index_uid=index_uid,
        token_prompt=token_prompt, pgid=pgid, tamper_prompt_sha=tamper_prompt_sha,
    )
    prefix, suffix = tmp_path / "prefix.json", tmp_path / "suffix.json"
    write_json(prefix, prompt)
    write_json(suffix, [99])
    with pytest.raises(ValueError, match=error):
        instance.run_capture(arm, {}, prefix, suffix, restore=False)
    assert not (arm / "capture.json").exists()


def test_t10_stage2_capture_binds_index_terminal_and_owned_pgid(tmp_path, monkeypatch):
    arm = tmp_path / "arm"
    dump = arm / "logits"
    dump.mkdir(parents=True)
    prefix = [1, 2]
    result = capture_result(T10P2, uid=3, sequence=8, prompt=[1, 2, 3])
    write_json(arm / "owned_process.json", {"pid": 88, "pgid": 55})
    write_json(dump / "index.jsonl", {"kind": "logits", "uid": 3, "seq": 8})
    write_json(dump / "tokens_uid3_pid777.json", token_record(T10P2, uid=3, pid=777, prompt=[1, 2, 3], generated=[4]))
    instance = T10P2.Run.__new__(T10P2.Run)
    monkeypatch.setattr(T10P2.subprocess, "run", fake_capture_run(result))
    monkeypatch.setattr(T10P2.os, "getpgid", lambda _pid: 55, raising=False)
    captured = instance.capture(arm, {}, prefix, [3])
    assert captured["capture_pid"] == 777
    assert json.loads((arm / "capture.json").read_text())["input_sha256"] == T10P2.idsha([1, 2, 3])


def canonical_g4_selfcheck_chain(tmp_path: Path, monkeypatch) -> tuple[Path, Path, Path]:
    """Create the on-disk D03 chain consumed by T04, without mocking its verifier."""
    root = tmp_path / "gpu_selfcheck_c30ae0d_urlfix"
    token_path = root / "candidate_boundary" / "tokens_uid7_pid990.json"
    token_path.parent.mkdir(parents=True)
    trace = tmp_path / "trace_rev.json"
    write_json(trace, {"trace": "canonical"})

    prompt = list(range(T04.G4_PROMPT_LENGTH))
    generated = list(range(100, 132))
    terminal = token_record(T04, uid=7, pid=990, prompt=prompt, generated=generated)
    write_json(token_path, terminal)
    binding = {
        "path": str(token_path.resolve()),
        "sha256": hashlib.sha256(token_path.read_bytes()).hexdigest(),
        "uid": 7,
        "pid": 990,
        "prompt_sha256_int32le": T04.ids_digest(prompt),
        "generated_sha256_int32le": T04.ids_digest(generated),
        "generated_length": len(generated),
    }
    report = {
        "mode": "development_selfcheck_not_acceptance",
        "cold_eq": "parent_off=candidate_off=candidate_on_state_logits",
        "g4_boundaries": [448, 4544, 8640, 12672, 14144, 18240, 21504],
        "g4_terminal_binding": binding,
    }
    admission = {
        "parent_commit": SELF_CHECK.PARENT_COMMIT,
        "candidate_commit": SELF_CHECK.CANDIDATE_COMMIT,
        "trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
    }
    write_json(root / "selfcheck.json", report)
    write_json(root / "admission.json", admission)
    write_selfcheck_manifest(root, token_path)
    raw_binding = tmp_path / "raw_binding.json"
    write_json(raw_binding, {
        "trace_sha256": admission["trace_sha256"],
        "messages_sha": "3550ee9010430096",
        "request_sha256": "a" * 64,
        "raw_ids_sha256": T04.ids_digest(prompt),
        "input_length": len(prompt),
    })
    monkeypatch.setattr(SELF_CHECK, "SELF_CHECK_OUTPUT", root)
    return root, token_path, raw_binding


def test_selfcheck_logits_capture_uses_service_origin_not_v1_base(tmp_path, monkeypatch):
    argv = SELF_CHECK.SelfCheck.logits_capture_argv(
        tmp_path / "arm", tmp_path / "prefix.json", tmp_path / "suffix.json"
    )
    assert argv[argv.index("--base-url") + 1] == "http://127.0.0.1:8095"

    root, token_path, raw_binding = canonical_g4_selfcheck_chain(tmp_path, monkeypatch)
    source = T04.verify_g4_source(
        SELF_CHECK, token_path, raw_binding, tmp_path / "trace_rev.json",
        SELF_CHECK.CANDIDATE_COMMIT,
    )
    assert source["terminal_binding"]["prompt_sha256_int32le"] == T04.ids_digest(
        list(range(T04.G4_PROMPT_LENGTH))
    )

    report_path = root / "selfcheck.json"
    report = json.loads(report_path.read_text())
    report["g4_terminal_binding"]["generated_length"] = 31
    write_json(report_path, report)
    write_selfcheck_manifest(root, token_path)
    with pytest.raises(ValueError, match="terminal binding"):
        T04.verify_g4_source(
            SELF_CHECK, token_path, raw_binding, tmp_path / "trace_rev.json",
            SELF_CHECK.CANDIDATE_COMMIT,
        )

    report["g4_terminal_binding"]["generated_length"] = 32
    write_json(report_path, report)
    token = json.loads(token_path.read_text())
    token["generated_ids"] = [101]
    write_json(token_path, token)
    with pytest.raises(ValueError, match="manifest member mismatch"):
        T04.verify_g4_source(
            SELF_CHECK, token_path, raw_binding, tmp_path / "trace_rev.json",
            SELF_CHECK.CANDIDATE_COMMIT,
        )


def test_t10_phase1_frontend_requires_actual_reverse_and_forward_trace_digests(tmp_path, monkeypatch):
    def trace_rows():
        rows = []
        for index in range(12):
            messages = [{"role": "user", "content": f"round {index}"}]
            digest = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
            rows.append({"messages": messages, "record": {"messages_sha": digest}})
        return rows

    reverse, forward = tmp_path / "reverse.json", tmp_path / "forward.json"
    write_json(reverse, {"rounds": trace_rows()})
    write_json(forward, {"rounds": list(reversed(trace_rows()))})
    frontend = tmp_path / "frontend.json"
    frontend_rows = []
    for entry in trace_rows():
        message_sha = entry["record"]["messages_sha"]
        prompt_ids = [len(frontend_rows) + 1]
        frontend_rows.append({
            "messages_sha": message_sha,
            "prompt_ids": prompt_ids,
            "prompt_ids_sha256_int32le": T10P1.digest(prompt_ids),
            "prompt_length": 1,
        })
    write_json(frontend, {
        "schema": "t10_frontend_tokens/v1",
        "candidate_commit": T10P1.CANDIDATE_COMMIT,
        "reverse_trace_sha256": hashlib.sha256(reverse.read_bytes()).hexdigest(),
        "forward_trace_sha256": hashlib.sha256(forward.read_bytes()).hexdigest(),
        "rounds": frontend_rows,
    })
    monkeypatch.setattr(T10P1, "FRONTEND_PATH", frontend)
    monkeypatch.setattr(T10P1, "FRONTEND_SHA", hashlib.sha256(frontend.read_bytes()).hexdigest())
    assert len(T10P1.frontend(
        frontend, T10P1.CANDIDATE_COMMIT,
        hashlib.sha256(reverse.read_bytes()).hexdigest(),
        hashlib.sha256(forward.read_bytes()).hexdigest(), reverse, forward,
    )[1]) == 12
    tampered = json.loads(forward.read_text())
    tampered["rounds"][0]["record"]["messages_sha"] = "not-the-message-digest"
    write_json(forward, tampered)
    frontend_document = json.loads(frontend.read_text())
    frontend_document["forward_trace_sha256"] = hashlib.sha256(forward.read_bytes()).hexdigest()
    write_json(frontend, frontend_document)
    monkeypatch.setattr(T10P1, "FRONTEND_SHA", hashlib.sha256(frontend.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match="digest mismatch"):
        T10P1.frontend(
            frontend, T10P1.CANDIDATE_COMMIT,
            hashlib.sha256(reverse.read_bytes()).hexdigest(),
            hashlib.sha256(forward.read_bytes()).hexdigest(), reverse, forward,
        )


def test_t10_stage2_main_forwards_phase1_round_json(tmp_path, monkeypatch):
    manifest = tmp_path / "phase1_manifest.json"
    round_json = tmp_path / "round.json"
    manifest.write_text("{}", encoding="utf-8")
    round_json.write_text("{}", encoding="utf-8")
    captured = {}

    def fake_runner(args):
        captured["args"] = args
        return SimpleNamespace(run=lambda: None)

    monkeypatch.setattr(T10P2, "Run", fake_runner)
    monkeypatch.setattr(T10P2, "os", SimpleNamespace(name="posix"))
    monkeypatch.setattr(T10P2.sys, "argv", [
        "t10_logits_stage2.py", "--run", "--batch", "51",
        "--candidate-commit", T10P2.CANDIDATE_COMMIT,
        "--phase1-manifest", str(manifest),
        "--phase1-round-json", str(round_json),
    ])
    T10P2.main()
    assert captured["args"].phase1_manifest == manifest
    assert captured["args"].phase1_round_json == round_json


def phase1_fixture(tmp_path: Path, monkeypatch):
    root = tmp_path / "rounds" / "E2-R012"
    root.mkdir(parents=True)
    frontend = tmp_path / "frontend.json"
    frontend_rows = [{"messages_sha": f"m{index:02d}"} for index in range(12)]
    write_json(frontend, {"rounds": frontend_rows})
    frontend_sha = hashlib.sha256(frontend.read_bytes()).hexdigest()
    manifest = root / "phase1_manifest.json"
    write_json(manifest, {
        "schema": "t10_engine_tokens/v1", "rid": "E2-R012",
        "frontend_manifest_sha256": frontend_sha, "arms": {}, "forkpoints": [],
    })
    write_json(root / "round.json", {"round_id": "E2-R012", "card": "T10"})
    write_json(root / "round_metadata.json", {"rid": "E2-R012", "status": "complete_measurements_pending_review"})
    write_json(root / "admission.json", {"candidate_commit": T10P2.CANDIDATE_COMMIT})
    entries = []
    for path in sorted(root.iterdir()):
        entries.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n")
    (root / "MANIFEST.sha256").write_text("".join(entries), encoding="utf-8")
    monkeypatch.setattr(T10P2, "ROUNDS", root.parent)
    monkeypatch.setattr(T10P2, "ROOT", REPO_ROOT)
    monkeypatch.setattr(T10P2, "FRONTEND_PATH", frontend)
    monkeypatch.setattr(T10P2, "FRONTEND_SHA", frontend_sha)
    writer_path = REPO_ROOT / "scripts" / "round_json_append.py"
    writer = load_path_module("phase2_guard_round_json_append", writer_path)
    expected = [T10P2.PY, str(writer_path), str(root), "check"]

    def validate_writer_command(argv, **_kwargs):
        assert argv == expected
        with monkeypatch.context() as scoped:
            scoped.setattr(writer.sys, "argv", [str(writer_path), str(root), "check"])
            parsed = writer.parse_args()
            assert parsed.round_dir == root
            assert parsed.command == "check"
        with monkeypatch.context() as scoped:
            scoped.setattr(writer.sys, "argv", [str(writer_path), "check", "--round", str(root / "round.json")])
            with pytest.raises(SystemExit):
                writer.parse_args()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(T10P2.subprocess, "run", validate_writer_command)
    instance = T10P2.Run.__new__(T10P2.Run)
    instance.a = SimpleNamespace(phase1_manifest=manifest, phase1_round_json=root / "round.json", candidate_commit=T10P2.CANDIDATE_COMMIT)
    return instance, root, manifest


def test_t10_sealed_phase1_verifies_each_manifest_member(tmp_path, monkeypatch):
    instance, _root, manifest = phase1_fixture(tmp_path, monkeypatch)
    assert instance.sealed_phase1()[1]["schema"] == "t10_engine_tokens/v1"
    manifest.write_text(manifest.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        instance.sealed_phase1()


def make_phase1_tokens(root: Path, module, *, mismatch=False):
    messages = [f"m{index:02d}" for index in range(12)]
    arms = {}
    for arm_name in ("B1", "B2", "B3"):
        arms[arm_name] = {"cold": {}, "warm": {}}
        for phase in ("cold", "warm"):
            directory = root / arm_name / "logits"
            directory.mkdir(parents=True, exist_ok=True)
            for index, message in enumerate(messages):
                generated = [50]
                if mismatch and message == "m00" and arm_name == "B3" and phase == "warm":
                    generated = [51]
                prompt = [index + 1]
                record = token_record(module, uid=index + 1, pid=1000 + index, prompt=prompt, generated=generated)
                path = directory / f"tokens_uid{index + 1}_pid{1000 + index}_{phase}.json"
                write_json(path, record)
                arms[arm_name][phase][message] = {
                    "terminal_file": path.name,
                    "terminal_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "uid": record["uid"], "pid": record["pid"],
                    "prompt_ids": prompt, "generated_ids": generated,
                }
    return messages, arms


def test_t10_recompute_requires_all_72_raw_tokens_and_preserves_k_zero(tmp_path, monkeypatch):
    frontend = tmp_path / "frontend.json"
    messages = [f"m{index:02d}" for index in range(12)]
    write_json(frontend, {"rounds": [{"messages_sha": message} for message in messages]})
    monkeypatch.setattr(T10P2, "FRONTEND_PATH", frontend)
    root = tmp_path / "E2-R012"
    root.mkdir()
    _messages, arms = make_phase1_tokens(root, T10P2, mismatch=True)
    instance = T10P2.Run.__new__(T10P2.Run)
    document = {"arms": arms}
    forks = instance.recompute_forks(root, document)
    assert len(forks) == 1
    assert forks[0]["messages_sha"] == "m00"
    assert forks[0]["k"] == 0 and forks[0]["common_generated_ids"] == []

    _messages, equal_arms = make_phase1_tokens(tmp_path / "equal", T10P2, mismatch=False)
    assert instance.recompute_forks(tmp_path / "equal", {"arms": equal_arms}) == []

    del arms["B2"]["warm"]["m11"]
    with pytest.raises(ValueError, match="exact canonical 12 keys"):
        instance.recompute_forks(root, {"arms": arms})

    _messages, invalid_arms = make_phase1_tokens(tmp_path / "invalid", T10P2, mismatch=True)
    broken = invalid_arms["B1"]["cold"]["m00"]
    broken_path = tmp_path / "invalid" / "B1" / "logits" / broken["terminal_file"]
    invalid = json.loads(broken_path.read_text())
    invalid["input_ids_sha256_int32le"] = "0" * 64
    write_json(broken_path, invalid)
    broken["terminal_sha256"] = hashlib.sha256(broken_path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="unbound sealed terminal"):
        instance.recompute_forks(tmp_path / "invalid", {"arms": invalid_arms})
