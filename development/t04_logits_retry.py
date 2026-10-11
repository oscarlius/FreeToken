#!/usr/bin/env python3
"""R015 controlled-capture retry for the frozen T04 phase-two lifecycle.

This runner deliberately inherits the sealed R014 lifecycle source without
changing its RID or module identity.  Only capture request history is replaced:
the retry client issues direct fresh/diagnostic requests or a competing branch
bank before the restore request.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path("/data2/FreeToken")
ROUND_ROOT = Path("/data2/_shared/runs/ft_rounds")
CANDIDATE = ROOT / "wt/e1r003st"
PY = str(ROOT / "venv/bin/python")
PORT = 8095
MODEL = "Qwen3.8-Flash-Next-NVFP4"
RETRY_RID = "E2-R015"
PARENT_COMMIT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
INHERITED_RUNNER = Path(__file__).with_name("t04_logits_phase2.py")
CONTROLLED_CLIENT = Path(__file__).with_name("t04_capture_controlled.py")
INHERITED_RUNNER_SHA256 = (
    "d7226c466e5922ecc4e80d80dc2b634592e1449538587d3232d4f3b9176723eb"
)
CONTROLLED_CLIENT_SHA256 = (
    "14b1eb09a9a49ba4c46176ca3edc5d52b927a07f4c476ae55c1d144c979c50fb"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inherited_runner(path: Path = INHERITED_RUNNER) -> ModuleType:
    """Load the original R014 implementation only after pinning its bytes."""
    source = path.read_bytes()
    if hashlib.sha256(source).hexdigest() != INHERITED_RUNNER_SHA256:
        raise RuntimeError(f"frozen inherited T04 runner SHA mismatch: {path}")
    module = ModuleType("t04_r014_inherited")
    module.__file__ = str(path)
    module.__package__ = ""
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def capture_mode(arm: str) -> str:
    mapping = {
        "candidate_boundary": "diagnostic",
        "restore": "branch-bank",
        "recompute": "fresh",
        "legal": "fresh",
    }
    try:
        return mapping[arm]
    except KeyError as exc:
        raise ValueError(f"unknown T04 retry arm: {arm}") from exc


def controlled_argv(
    *,
    client: Path,
    base_url: str,
    prefix: Path,
    suffix: Path,
    dump: Path,
    mode: str,
) -> list[str]:
    return [
        PY,
        str(client),
        "--base-url",
        base_url,
        "--model",
        MODEL,
        "--prefix",
        str(prefix),
        "--suffix",
        str(suffix),
        "--dump",
        str(dump),
        "--mode",
        mode,
    ]


def _write_new(path: Path, value: object) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


class RetryPhase2:
    """An R015 wrapper around the frozen R014 lifecycle implementation."""

    def __init__(self, args: argparse.Namespace, inherited: ModuleType | None = None):
        self.args = args
        self.inherited = inherited or load_inherited_runner()
        self.phase = self.inherited.Phase2(args)
        self.phase.gate = self.gate
        self.phase.run_capture = self.run_capture
        self._gate_success = False

    @property
    def out(self) -> Path:
        return self.phase.out

    def gate(self) -> dict[str, Any]:
        self._gate_success = False
        if self.args.rid != RETRY_RID:
            raise ValueError(f"RID must be root-assigned {RETRY_RID}")
        if not re.fullmatch(r"[0-9a-f]{40}", self.args.candidate_commit):
            raise ValueError("candidate commit must be an explicit lowercase full SHA-1")
        if self.out.exists():
            raise FileExistsError(f"formal round already exists: {self.out}")
        subprocess.run(
            [
                "git",
                "-C",
                str(CANDIDATE),
                "merge-base",
                "--is-ancestor",
                PARENT_COMMIT,
                self.args.candidate_commit,
            ],
            check=True,
        )
        proof = self.phase.base.gate(CANDIDATE, self.args.candidate_commit)
        if not 1 <= self.args.k <= 64:
            raise ValueError("K must be between one and 64")
        self._gate_success = True
        return proof

    def run_capture(
        self,
        arm: Path,
        env: dict[str, str],
        prefix: Path,
        suffix: Path,
        *,
        restore: bool,
    ) -> dict[str, Any]:
        mode = capture_mode(arm.name)
        if (restore and mode != "branch-bank") or (not restore and mode == "branch-bank"):
            raise ValueError("retry capture arm and restore contract disagree")
        if sha256(CONTROLLED_CLIENT) != CONTROLLED_CLIENT_SHA256:
            raise RuntimeError("controlled-capture client differs from reviewed version")

        argv = controlled_argv(
            client=CONTROLLED_CLIENT,
            base_url=f"http://127.0.0.1:{PORT}",
            prefix=prefix,
            suffix=suffix,
            dump=arm / "logits",
            mode=mode,
        )
        log = arm / "logits_capture.log"
        with log.open("x", encoding="utf-8") as sink:
            subprocess.run(
                argv,
                cwd=CANDIDATE,
                env=env,
                stdout=sink,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=3600,
            )
        lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            raise ValueError("controlled logits capture emitted no JSON")
        result = json.loads(lines[-1])
        if result.get("mode") != mode:
            raise ValueError("controlled capture reports the wrong mode")
        if result.get("k") != self.args.k or result.get("input_length") != self.phase._input_length:
            raise ValueError("capture K/input length differs from immutable P+X input")

        rows = [
            json.loads(line)
            for line in (arm / "logits" / "index.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        matched = [
            row
            for row in rows
            if row.get("kind") == "logits"
            and row.get("uid") == result.get("uid")
            and row.get("seq") == result.get("dump_seq")
        ]
        if len(matched) != 1:
            raise ValueError("logits index lacks unique capture UID/sequence binding")
        candidates = list((arm / "logits").glob(f"tokens_uid{result['uid']}_pid*.json"))
        tokens = [
            self.inherited.read_token_record(
                path,
                max_k=1,
                expected_prompt_length=result["input_length"],
            )
            for path in candidates
        ]
        tokens = [
            item
            for item in tokens
            if item["prompt_length"] == result["input_length"]
            and item["prompt_ids_sha256_int32le"] == result["input_sha256"]
        ]
        if len(tokens) != 1:
            raise ValueError("terminal token record does not uniquely bind logits input UID/SHA")
        owned = json.loads((arm / "owned_process.json").read_text(encoding="utf-8"))
        if os.getpgid(tokens[0]["pid"]) != owned.get("pgid"):
            raise ValueError("terminal token PID is outside owned service process group")
        result["capture_pid"] = tokens[0]["pid"]
        if mode == "branch-bank" and not self.inherited.valid_restore_proof(
            result.get("restore_proof"), result.get("uid"), result.get("cached_len")
        ):
            raise ValueError("branch-bank capture did not prove a real restore")
        _write_new(arm / "capture.json", result)
        return result

    def _archive_retry_sources(self) -> None:
        """Preserve the distinct inherited and retry sources in the final manifest."""
        sources = {
            "t04_logits_phase2.py": INHERITED_RUNNER,
            "t04_logits_retry.py": Path(__file__),
            "t04_capture_controlled.py": CONTROLLED_CLIENT,
        }
        hashes: dict[str, str] = {}
        for name, source in sources.items():
            target = self.out / name
            if not target.exists():
                target.write_bytes(source.read_bytes())
            if sha256(target) != sha256(source):
                raise RuntimeError(f"archived retry source differs: {name}")
            hashes[name] = sha256(source)
        _write_new(self.out / "retry_tool_hashes.json", hashes)

        paths = sorted(
            path for path in self.out.rglob("*") if path.is_file() and path.name != "RUN_MANIFEST.sha256"
        )
        (self.out / "RUN_MANIFEST.sha256").write_text(
            "".join(f"{sha256(path)}  {path.relative_to(self.out)}\n" for path in paths),
            encoding="utf-8",
        )

    def _owns_created_round(self) -> bool:
        """Never alter an existing round merely because a gate attempt failed."""
        if not self._gate_success or not self.out.is_dir():
            return False
        status = self.out / f"status_batch{self.args.batch}.json"
        if not status.is_file():
            return False
        try:
            data = json.loads(status.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        return (
            data.get("rid") == self.args.rid
            and data.get("batch") == self.args.batch
            and data.get("gate") == "T04"
            and data.get("batch_pid") == os.getpid()
            and data.get("pid") == os.getpid()
        )

    def run(self) -> None:
        try:
            self.phase.run()
        finally:
            if self._owns_created_round():
                self._archive_retry_sources()


def self_test() -> None:
    assert capture_mode("candidate_boundary") == "diagnostic"
    assert capture_mode("restore") == "branch-bank"
    assert capture_mode("recompute") == capture_mode("legal") == "fresh"
    argv = controlled_argv(
        client=Path("controlled.py"),
        base_url="http://127.0.0.1:8095",
        prefix=Path("P.json"),
        suffix=Path("X.json"),
        dump=Path("dump"),
        mode="fresh",
    )
    assert argv.count("--mode") == 1 and argv[-1] == "fresh"
    assert INHERITED_RUNNER.name == "t04_logits_phase2.py"
    assert sha256(INHERITED_RUNNER) == INHERITED_RUNNER_SHA256
    assert sha256(CONTROLLED_CLIENT) == CONTROLLED_CLIENT_SHA256
    print("T04 R015 retry self-test PASS: controlled mode mapping and frozen source pins")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--rid", default=RETRY_RID)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--candidate-commit")
    parser.add_argument("--g4-token-file", type=Path)
    parser.add_argument("--raw-binding-manifest", type=Path)
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--k", type=int, default=32)
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if not args.run:
        parser.error("--run is required; no resources are touched otherwise")
    if os.name != "posix":
        parser.error("--run requires Linux")
    required = (args.batch, args.candidate_commit, args.g4_token_file, args.raw_binding_manifest, args.trace)
    if args.batch is None or args.batch < 1 or not all(required[1:]):
        parser.error("--run requires --batch, --candidate-commit, --g4-token-file, --raw-binding-manifest, and --trace")
    if not all(path.is_file() for path in (args.g4_token_file, args.raw_binding_manifest, args.trace)):
        parser.error("input artifact does not exist as a regular file")
    RetryPhase2(args).run()


if __name__ == "__main__":
    main()
