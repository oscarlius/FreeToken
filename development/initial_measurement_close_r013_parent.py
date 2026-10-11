"""Bootstrap an immutable first measurement record; never append a closed round."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile


CONTROL_NAMES = ("round.json", "round_history", "MANIFEST.sha256")
ARM_FILES = ("SERVE_CMD.txt", "serve.log", "serve_args.txt", "ENV.txt")
T00_ARMS = ("PRODUCTION", "D0", "OFF_p1", "ON_p1", "OFF_p2", "ON_p2", "OFF_p3", "ON_p3")
BASE_RE = re.compile(r"[0-9a-f]{40}")
RID_RE = re.compile(r"E2-R\d{3}(?:-p64k)?")


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def assert_owned_tree(directory):
    uid = os.geteuid() if hasattr(os, "geteuid") else None
    for path in [directory, *directory.rglob("*")]:
        if path.is_symlink() or (uid is not None and path.stat().st_uid != uid):
            raise ValueError(f"foreign owner or symlink: {path}")


def finite_numbers(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(finite_numbers(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and finite_numbers(item) for key, item in value.items())
    return False


def live_or_zombie(pid):
    stat = Path(f"/proc/{pid}/stat")
    if not stat.exists():
        return False
    tail = stat.read_text(encoding="utf-8").partition(") ")[2]
    if not tail:
        raise ValueError(f"malformed proc stat for batch pid {pid}")
    return tail[0] != "Z"


def validate_phase_parent(directory, admission, document):
    if "parent_rid" not in admission:
        return
    parent = admission["parent_rid"]
    proof = directory / "phase1_round_proof.json"
    expected_sha = admission.get("phase1_round_proof_sha256")
    if (not isinstance(parent, str) or not RID_RE.fullmatch(parent)
            or document.get("parent") != parent or not proof.is_file()
            or proof.is_symlink() or not isinstance(expected_sha, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha)
            or sha(proof) != expected_sha or read_json(proof).get("round_id") != parent):
        raise ValueError("phase parent differs from admission or copied sealed proof")


def validate(directory, rid, batch, metadata_path, review_path, now):
    if not directory.is_dir():
        raise ValueError(f"open round directory missing: {directory}")
    if any((directory / name).exists() for name in CONTROL_NAMES):
        raise ValueError("initial closure only; existing control artifact refused")
    assert_owned_tree(directory)
    if review_path.parent != directory or metadata_path.parent != directory:
        raise ValueError("review and initial metadata must belong to the open round")

    review = read_json(review_path)
    if review.get("rid") != rid or review.get("batch") != batch or review.get("verdict") != "PASS":
        raise ValueError("independent execution/evidence review required")

    status_path = directory / f"status_batch{batch}.json"
    if not status_path.is_file():
        raise ValueError(f"exact batch status missing: {status_path.name}")
    status = read_json(status_path)
    pid = status.get("batch_pid")
    if (status.get("batch") != batch or type(pid) is not int or pid <= 0):
        raise ValueError("status batch and positive batch_pid are required")
    if status.get("state") not in ("complete_measurements_pending_review", "complete"):
        raise ValueError("measurements are not terminal complete")
    if live_or_zombie(pid):
        raise ValueError("owned batch is still running")

    admission_path = directory / "admission.json"
    if not admission_path.is_file():
        raise ValueError("admission record missing")
    admission = read_json(admission_path)
    document = read_json(metadata_path)
    base = document.get("base")
    commit = base.get("commit") if isinstance(base, dict) else None
    code_version = base.get("code_version") if isinstance(base, dict) else None
    card = document.get("card")
    if (document.get("schema") != "ft_round/v2" or document.get("round_id") != rid
            or document.get("epoch") != 2 or document.get("verdict") != "pending_review"
            or document.get("proposed_verdict") is not None or document.get("verdict_history") != []
            or document.get("retractions") != [] or not isinstance(commit, str)
            or not isinstance(card, str) or not card or not BASE_RE.fullmatch(commit)
            or code_version != f"E2-base@{commit[:7]}" or admission.get("commit") != commit
            or admission.get("code_version") != code_version):
        raise ValueError("invalid initial measurement metadata or admission binding")
    validate_phase_parent(directory, admission, document)
    identities = [status[key] for key in ("gate", "card") if key in status]
    if ("rid" in status and status["rid"] != rid
            or not identities or any(identity != card for identity in identities)):
        raise ValueError("status identity does not bind the round metadata")
    created = document.get("created_at")
    if not isinstance(created, str) or not created:
        raise ValueError("created_at is required")
    try:
        datetime.strptime(created, "%Y-%m-%d %H:%M:%S CST")
    except ValueError as exc:
        raise ValueError("created_at must use YYYY-MM-DD HH:MM:SS CST") from exc

    serve = document.get("serve")
    arms = serve.get("arms") if isinstance(serve, dict) else None
    if not isinstance(arms, dict) or not arms:
        raise ValueError("non-empty serve.arms mapping required")
    for arm in arms:
        if not isinstance(arm, str) or not re.fullmatch(r"[A-Za-z0-9_]+", arm):
            raise ValueError("invalid arm name")
        for filename in ARM_FILES:
            path = directory / arm / filename
            if not path.is_file() or not path.stat().st_size:
                raise ValueError(f"missing required arm artifact: {path}")
    completion_path = directory / "measurements_complete.json"
    if card == "T00":
        if not completion_path.is_file():
            raise ValueError("T00 completion arm declaration missing")
        completion = read_json(completion_path)
        if (status.get("gate") != "T00" or status.get("state") != "complete_measurements_pending_review"
                or completion.get("state") != "complete_measurements_pending_review"
                or completion.get("code_version") != code_version
                or completion.get("arms") != list(T00_ARMS) or set(arms) != set(T00_ARMS)):
            raise ValueError("T00 completion and metadata arms do not bind exactly")
    for candidate in (status, read_json(directory / "measurement_summary.json")
                      if (directory / "measurement_summary.json").is_file() else {}):
        if "arms" in candidate and set(candidate["arms"] if isinstance(candidate["arms"], list) else ()) != set(arms):
            raise ValueError("measurement arm identity differs from metadata")
    results = document.get("results")
    if not isinstance(results, dict) or not results or not finite_numbers(results):
        raise ValueError("results must be a non-empty finite numeric tree")
    wrapper = directory / "batch.sh"
    log = directory.parent / f"batch{batch}.log"
    if not wrapper.is_file() or not wrapper.stat().st_size or not log.is_file():
        raise ValueError("actual batch wrapper and log are required")

    document["closed_at"] = now.strftime("%Y-%m-%d %H:%M:%S CST")
    document["batch_logs"] = [{"path": str(log), "sha256": sha(log)}]
    document["manifest"] = "MANIFEST.sha256"
    document["independent_review_sha256"] = sha(review_path)
    return document


def build_control(directory, document):
    round_bytes = json_bytes(document)
    files = sorted(path for path in directory.rglob("*") if path.is_file())
    manifest_bytes = "".join(
        f"{sha(path)}  ./{path.relative_to(directory).as_posix()}\n" for path in files
    ).encode("utf-8")
    snapshot_name = "round.v001.json"
    sums_bytes = f"{hashlib.sha256(round_bytes).hexdigest()}  {snapshot_name}\n".encode("utf-8")
    return {
        "round.json": round_bytes,
        "round_history/round.v001.json": round_bytes,
        "round_history/SHA256SUMS": sums_bytes,
        "MANIFEST.sha256": manifest_bytes,
    }


def publish(directory, controls, chmod_fn=os.chmod, inject=None):
    """Publish precomputed controls or leave the open-round bytes untouched."""
    originals = {path: path.stat().st_mode for path in [directory, *directory.rglob("*")]}
    created = []
    temp = Path(tempfile.mkdtemp(prefix=".initial-close-", dir=directory.parent))
    try:
        for relative, data in controls.items():
            staged = temp / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(data)
        if inject:
            inject("prepared")
        for relative in ("round.json", "round_history/round.v001.json", "round_history/SHA256SUMS", "MANIFEST.sha256"):
            destination = directory / relative
            if relative.startswith("round_history/") and not (directory / "round_history").exists():
                (directory / "round_history").mkdir()
                created.append(directory / "round_history")
            os.link(temp / relative, destination)
            created.append(destination)
            if relative == "round.json" and inject:
                inject("round_published")
        if inject:
            inject("published")
        paths = [*directory.rglob("*"), directory]
        for path in paths:
            chmod_fn(path, path.stat().st_mode & ~0o222)
    except Exception:
        for path, mode in originals.items():
            try:
                os.chmod(path, mode)
            except OSError:
                pass
        for path in reversed(created):
            try:
                if path.is_dir():
                    path.rmdir()
                else:
                    path.unlink()
            except OSError:
                pass
        raise
    finally:
        shutil.rmtree(temp, ignore_errors=True)


def close(directory, rid, batch, metadata_path, review_path, *, now=None, chmod_fn=os.chmod, inject=None):
    now = now or datetime.now(timezone(timedelta(hours=8)))
    document = validate(directory, rid, batch, metadata_path, review_path, now)
    controls = build_control(directory, document)
    publish(directory, controls, chmod_fn=chmod_fn, inject=inject)
    return document


def _fixture(root, *, rid="E2-R123", batch=7):
    directory = root / rid
    directory.mkdir()
    commit = "a" * 40
    tag = f"E2-base@{commit[:7]}"
    (directory / "admission.json").write_text(json.dumps({"commit": commit, "code_version": tag}))
    (directory / f"status_batch{batch}.json").write_text(json.dumps({"batch": batch, "batch_pid": 999999, "state": "complete", "gate": "TEST"}))
    (directory / "review.json").write_text(json.dumps({"rid": rid, "batch": batch, "verdict": "PASS"}))
    (directory / "batch.sh").write_text("#!/bin/sh\ntrue\n")
    (root / f"batch{batch}.log").write_text("completed\n")
    arm = directory / "P1"
    arm.mkdir()
    for name in ARM_FILES:
        (arm / name).write_text(name + "\n")
    metadata = {
        "schema": "ft_round/v2", "round_id": rid, "epoch": 2, "card": "TEST",
        "verdict": "pending_review", "proposed_verdict": None,
        "verdict_history": [], "retractions": [], "created_at": "2026-10-04 10:00:00 CST",
        "base": {"commit": commit, "code_version": tag},
        "serve": {"arms": {"P1": {}}}, "results": {"ttft_ms": [1.0, 2.0]},
    }
    metadata_path = directory / "measurements.json"
    metadata_path.write_text(json.dumps(metadata, allow_nan=True))
    return directory, metadata_path, directory / "review.json"


def _writable(directory):
    for path in [*directory.rglob("*"), directory]:
        try:
            os.chmod(path, path.stat().st_mode | 0o700)
        except OSError:
            pass


def _source_bytes(directory):
    return {path.relative_to(directory).as_posix(): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def self_test():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)

        def t00_open(rid):
            directory, metadata, review = _fixture(root, rid=rid)
            document = read_json(metadata)
            document["card"] = "T00"
            document["serve"]["arms"] = {name: {} for name in T00_ARMS}
            metadata.write_text(json.dumps(document))
            (directory / "status_batch7.json").write_text(json.dumps({
                "batch": 7, "batch_pid": 999999, "state": "complete_measurements_pending_review", "gate": "T00"}))
            for name in T00_ARMS:
                arm = directory / name
                arm.mkdir(exist_ok=True)
                for filename in ARM_FILES:
                    path = arm / filename
                    if not path.exists():
                        path.write_text(filename + "\n")
            (directory / "measurements_complete.json").write_text(json.dumps({
                "state": "complete_measurements_pending_review", "code_version": document["base"]["code_version"],
                "arms": list(T00_ARMS)}))
            return directory, metadata, review

        directory, metadata, review = _fixture(root)
        document = close(directory, "E2-R123", 7, metadata, review, now=now)
        assert document["closed_at"] == "2026-10-04 00:00:00 CST"
        assert sha(directory / "round.json") == sha(directory / "round_history" / "round.v001.json")
        assert (directory / "MANIFEST.sha256").is_file()
        _writable(directory)

        directory, metadata, review = _fixture(root, rid="E2-R223")
        empty_log = directory.parent / "batch7.log"
        empty_log.write_bytes(b"")
        document = close(directory, directory.name, 7, metadata, review, now=now)
        assert document["batch_logs"][0]["sha256"] == hashlib.sha256(b"").hexdigest()
        _writable(directory)

        directory, metadata, review = _fixture(root, rid="E2-R224")
        (directory.parent / "batch7.log").unlink()
        original = _source_bytes(directory)
        try:
            close(directory, directory.name, 7, metadata, review, now=now)
        except ValueError:
            assert _source_bytes(directory) == original
            assert not any((directory / control).exists() for control in CONTROL_NAMES)
        else:
            raise AssertionError("missing actual batch log accepted")

        directory, metadata, review = t00_open("E2-R222")
        close(directory, "E2-R222", 7, metadata, review, now=now)
        _writable(directory)

        for name in ("missing_gate", "wrong_status_state", "wrong_completion_state", "missing_code_version"):
            directory, metadata, review = t00_open(f"E2-R{230 + len(name):03d}")
            if name == "missing_gate":
                status = read_json(directory / "status_batch7.json"); status.pop("gate")
                (directory / "status_batch7.json").write_text(json.dumps(status))
            elif name == "wrong_status_state":
                status = read_json(directory / "status_batch7.json")
                status["state"] = "complete"
                (directory / "status_batch7.json").write_text(json.dumps(status))
            elif name == "wrong_completion_state":
                completion = read_json(directory / "measurements_complete.json")
                completion["state"] = "complete"
                (directory / "measurements_complete.json").write_text(json.dumps(completion))
            else:
                completion = read_json(directory / "measurements_complete.json"); completion.pop("code_version")
                (directory / "measurements_complete.json").write_text(json.dumps(completion))
            try:
                close(directory, directory.name, 7, metadata, review, now=now)
            except ValueError:
                assert not any((directory / control).exists() for control in CONTROL_NAMES)
            else:
                raise AssertionError(f"{name} T00 status/completion accepted")

        for change in ("wrong_batch", "empty_arms", "bad_base", "nan"):
            directory, metadata, review = _fixture(root, rid=f"E2-R{124 + len(change):03d}")
            document = read_json(metadata)
            if change == "wrong_batch":
                status = directory / "status_batch7.json"
                status.write_text(json.dumps({"batch": 6, "batch_pid": 999999, "state": "complete"}))
            elif change == "empty_arms":
                document["serve"]["arms"] = {}
                metadata.write_text(json.dumps(document))
            elif change == "bad_base":
                document["base"]["commit"] = "short"
                metadata.write_text(json.dumps(document))
            else:
                document["results"] = {"bad": float("nan")}
                metadata.write_text(json.dumps(document, allow_nan=True))
            try:
                close(directory, directory.name, 7, metadata, review, now=now)
            except ValueError:
                assert not any((directory / name).exists() for name in CONTROL_NAMES)
            else:
                raise AssertionError(f"{change} unexpectedly closed")

        directory, metadata, review = _fixture(root, rid="E2-R220")
        source_bytes = _source_bytes(directory)
        try:
            close(directory, "E2-R220", 7, metadata, review, now=now,
                  inject=lambda stage: (_ for _ in ()).throw(RuntimeError("injected")) if stage == "round_published" else None)
        except RuntimeError:
            assert not any((directory / name).exists() for name in CONTROL_NAMES)
            assert _source_bytes(directory) == source_bytes
        else:
            raise AssertionError("mid-publish failure unexpectedly closed")

        directory, metadata, review = _fixture(root, rid="E2-R221")
        source_bytes = _source_bytes(directory)
        try:
            close(directory, "E2-R221", 7, metadata, review, now=now,
                  chmod_fn=lambda *_: (_ for _ in ()).throw(OSError("injected")))
        except OSError:
            assert not any((directory / name).exists() for name in CONTROL_NAMES)
            assert _source_bytes(directory) == source_bytes
        else:
            raise AssertionError("chmod failure unexpectedly closed")
    print("initial_measurement_close self-test: PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rid", nargs="?")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--metadata")
    parser.add_argument("--review")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.rid or args.batch is None or not args.metadata or not args.review:
        parser.error("rid, --batch, --metadata, and --review are required")
    if not RID_RE.fullmatch(args.rid):
        parser.error("leader assigned E2 measurement RID required")
    directory = Path("/data2/_shared/runs/ft_rounds") / args.rid
    document = close(directory, args.rid, args.batch, Path(args.metadata), Path(args.review))
    print(json.dumps({"rid": args.rid, "closed_at": document["closed_at"],
                      "manifest_sha256": sha(directory / "MANIFEST.sha256"),
                      "round_sha256": sha(directory / "round.json")}))


if __name__ == "__main__":
    main()
