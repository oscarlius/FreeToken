#!/usr/bin/env python3
"""Prepare or explicitly run the f506 D03 G4/G5 GPU self-check.

This continuation never treats the c30 self-check as evidence for f506.  It
loads the historical protocol only after pinning its exact source bytes, then
binds every G4/G5 input to a fresh raw-ID manifest produced from the f506
candidate tokenizer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


HERE = Path(__file__).resolve().parent
BASE_PATH = HERE / "d03_gpu_selfcheck.py"
BASE_SHA256 = "4cf751a93457ef28a88fc175004c86d12130b84943193cb43c55254c2e0fb453"
PARENT_COMMIT = "c30ae0d7003c3bbbf56867ce74da797332fa7ed5"
CANDIDATE_COMMIT = "f5067bbe05da51d5f78185213435a8be095a684a"
ROOT = Path("/data2/FreeToken")
PARENT = ROOT / "wt" / "e1r003st"
CANDIDATE = ROOT / "wt" / "e2d03-continuation"
OUTPUT = ROOT / "runs" / "dev_D03" / "gpu_selfcheck_f5067bb"
RAW_SCHEMA = "ft_d03_f506_raw_ids/v1"
TOKENIZER_SOURCES = (
    Path("python/freetoken/server/api_models.py"),
    Path("python/freetoken/server/openai_api.py"),
    Path("python/freetoken/message/__init__.py"),
    Path("python/freetoken/tokenizer/tokenize.py"),
    Path("python/freetoken/utils/__init__.py"),
)
TOKENIZER_CONSTRUCTION = "ChatCompletionRequest -> chat_request_to_genspec -> TokenizeManager.tokenize"
MODEL_PATH = ROOT / "models/Qwen3.8-Flash-Next-NVFP4-overlay"
TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "chat_template.jinja")
REQUIRED_TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")
# Historical T04 evidence is carried forward as a fixed failure envelope, not
# as an acceptance threshold this continuation may adjust.
HISTORICAL_ENVELOPE = {"points": 814, "outside_points": 199, "max_finite_ratio": 5.489091417}
REQUIRED_BOUNDARY = 12672
STOP_STEPS = ((signal.SIGINT, 30), (signal.SIGTERM, 15), (getattr(signal, "SIGKILL", 9), 10))


# Read precisely once before compile: a changing historical runner is a hard
# failure rather than an opportunity for an old protocol to slip underneath us.
BASE_BYTES = BASE_PATH.read_bytes()
if hashlib.sha256(BASE_BYTES).hexdigest() != BASE_SHA256:
    raise RuntimeError(f"historical runner SHA256 mismatch: {BASE_PATH}")
_protocol: dict[str, object] = {"__file__": str(BASE_PATH), "__name__": "_d03_c30_protocol"}
exec(compile(BASE_BYTES, str(BASE_PATH), "exec"), _protocol)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokenizer_assets():
    for name in REQUIRED_TOKENIZER_FILES:
        if not (MODEL_PATH / name).is_file():
            raise ValueError("required tokenizer asset missing: " + name)
    hashes = {name: sha256(MODEL_PATH / name) for name in TOKENIZER_FILES
              if (MODEL_PATH / name).is_file()}
    absent = [name for name in TOKENIZER_FILES if not (MODEL_PATH / name).exists()]
    return hashes, absent


def process_birth(pid):
    fields = (Path('/proc') / str(pid) / 'stat').read_text().rpartition(') ')[2].split()
    if len(fields) < 20 or int(fields[2]) != pid or int(fields[3]) != pid:
        raise RuntimeError('owned service birth or session cannot be verified')
    return {'pid': pid, 'starttime': int(fields[19]),
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def raw_binding(path: Path, trace_digest: str, record: dict, request_digest: str, tail_k: int):
    """Require a fresh f506 tokenizer-bound raw-ID manifest; never encode text here."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = data.get("ids")
    if data.get("schema") != RAW_SCHEMA:
        raise ValueError("raw manifest is not the f506 tokenizer-bound schema")
    if not isinstance(ids, list) or not ids or any(type(token) is not int or not 0 <= token <= 2**31 - 1 for token in ids):
        raise ValueError("raw ID manifest must contain a non-empty flat int32 ids list")
    packed = b"".join(token.to_bytes(4, "little", signed=True) for token in ids)
    digest = hashlib.sha256(packed).hexdigest()
    tokenizer = data.get("candidate_tokenizer")
    expected_sources = {str(source): sha256(CANDIDATE / source) for source in TOKENIZER_SOURCES}
    expected_files, absent_files = tokenizer_assets()
    if not isinstance(tokenizer, dict):
        raise ValueError("raw manifest lacks candidate tokenizer provenance")
    if (data.get("candidate_commit") != CANDIDATE_COMMIT
            or data.get("candidate_worktree") != str(CANDIDATE)
            or data.get("trace_sha256") != trace_digest
            or data.get("messages_sha") != record.get("messages_sha")
            or data.get("request_sha256") != request_digest
            or data.get("raw_ids_sha256") != digest
            or data.get("input_length") != len(ids)
            or tokenizer.get("manager_module") != "freetoken.tokenizer.tokenize.TokenizeManager"
            or tokenizer.get("construction") != TOKENIZER_CONSTRUCTION
            or tokenizer.get("source_sha256") != expected_sources
            or not expected_files
            or tokenizer.get("model_files_sha256") != expected_files
            or tokenizer.get("absent_model_files") != absent_files
            or tokenizer.get("encoded_ids_sha256_int32le") != digest):
        raise ValueError("raw manifest does not bind f506 candidate tokenizer and exact input IDs")
    if not 1 <= tail_k <= 64 or len(ids) < tail_k:
        raise ValueError("tail K must be within 1..64 and not exceed fixed input length")
    return ids, digest


def owned_group_members(pgid: int) -> set[int]:
    """Return non-zombie members of exactly the owned process group/session."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return set()
    members: set[int] = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text(encoding="utf-8").rpartition(") ")[2].split()
        except FileNotFoundError:
            continue
        if len(fields) < 4:
            raise RuntimeError(f"malformed proc stat: {entry}")
        state, group, session = fields[0], int(fields[2]), int(fields[3])
        if group != pgid:
            continue
        if session != pgid:
            raise RuntimeError("owned process group no longer belongs to its reserved session")
        if state != "Z":
            members.add(int(entry.name))
    return members


# Set the historical protocol's immutable operational inputs before its methods
# run.  Its G3/G4/G5 execution remains the historical implementation.
_protocol.update({
    "ROOT": ROOT,
    "RUNS": ROOT / "runs" / "dev_D03",
    "PARENT": PARENT,
    "CANDIDATE": CANDIDATE,
    "PARENT_COMMIT": PARENT_COMMIT,
    "CANDIDATE_COMMIT": CANDIDATE_COMMIT,
    "SELF_CHECK_OUTPUT": OUTPUT,
    "raw_binding": raw_binding,
})
if REQUIRED_BOUNDARY not in _protocol["BOUNDARIES"]:
    raise RuntimeError("historical D03 protocol no longer includes the 12672 boundary")
BaseSelfCheck = _protocol["SelfCheck"]


class SelfCheck(BaseSelfCheck):
    """The only f506 deltas are environment, raw binding, and safe cleanup."""

    def environment(self, worktree, arm, *, state=False, logits=False):
        env = super().environment(worktree, arm, state=state, logits=logits)
        # The base clears both development families.  CUDA must be explicit on
        # the GPU host so a CPU-shell inherited empty value cannot hide device 0.
        env["CUDA_VISIBLE_DEVICES"] = "0"
        return env

    @staticmethod
    def _bootstrap(worktree, *, serve: bool) -> str:
        """Construct a -S entrypoint whose import root is the requested tree."""
        root = str(Path(worktree).resolve())
        tail = (
            "from freetoken.cli import main\n"
            "raise SystemExit(main(sys.argv[1:]))\n"
            if serve else
            "from freetoken.tokenizer.tokenize import TokenizeManager\n"
            "from freetoken.server.api_models import ChatCompletionRequest\n"
            "from freetoken.server.openai_api import chat_request_to_genspec\n"
            "from freetoken.message import TokenizeMsg\n"
            "from freetoken.utils import load_tokenizer\n"
            "print(json.dumps({'source': freetoken.__file__}, sort_keys=True))\n"
        )
        return (
            "import json,pathlib,sys\n"
            f"root=pathlib.Path({root!r})\n"
            "sys.path[:0]=[str(root/'python'),str(root)]\n"
            "packages=pathlib.Path(sys.executable).parents[1]/'lib'/"
            "f'python{sys.version_info.major}.{sys.version_info.minor}'/'site-packages'\n"
            "assert packages.is_dir(), packages\n"
            "sys.path.append(str(packages))\n"
            "import freetoken\n"
            "assert freetoken.__file__ == str(root/'python/freetoken/__init__.py'), freetoken.__file__\n"
            + tail
        )

    def gate(self, worktree, commit):
        result = super().gate(worktree, commit)
        proof = _protocol["output"]([
            _protocol["PY"], "-S", "-c", self._bootstrap(worktree, serve=False)
        ], cwd=worktree, env=self.environment(worktree, self.out / "_no_arm"))
        parsed = json.loads(proof)
        expected = str(Path(worktree) / "python/freetoken/__init__.py")
        if parsed != {"source": expected}:
            raise RuntimeError("isolated candidate import proof differs from requested worktree")
        result["isolated_source"] = parsed["source"]
        return result

    def start(self, name, worktree, *, state=False, logits=False,
              host_slots=0, prefill_chunk=4096, layer_major=True):
        if (type(host_slots) is not int or host_slots not in (0, 32)
                or type(prefill_chunk) is not int or prefill_chunk not in (4096, 8192)
                or type(layer_major) is not bool):
            raise ValueError("unsupported D03 validation service configuration")
        arm = self.out / name
        arm.mkdir()
        if state:
            (arm / "state").mkdir()
        if logits:
            (arm / "logits").mkdir()
        env = self.environment(worktree, arm, state=state, logits=logits)
        argv = ["numactl", "--cpunodebind=0,1", "--interleave=all", _protocol["PY"], "-S", "-c",
                self._bootstrap(worktree, serve=True), "serve", "--model-path",
                str(ROOT / "models/Qwen3.8-Flash-Next-NVFP4-overlay"), "--served-model-name", _protocol["MODEL"],
                "--host", "127.0.0.1", "--port", str(_protocol["PORT"]), "--memory-ratio", "0.88", "--moe-cache-auto",
                "--moe-prefill-hit-d2d", "--ple-backend", "pinned", "--moe-strategy", "offload",
                "--quant-backend", "moe.nvfp4=triton", "--max-running-requests", "2", "--cuda-graph-max-bs", "2",
                "--kv-reserve-tokens", "49152", "--max-seq-len-override", "49152", "--max-prefill-length", str(prefill_chunk),
                "--enable-cache-report", "--enable-special-token-ckpt", "--tool-call-parser", "qwen3_coder",
                "--reasoning-parser", "qwen3"]
        if layer_major:
            argv.append("--prefill-layer-major")
        argv += ["--mamba-host-slots", str(host_slots)]
        selected = ["PYTHONPATH", "PYTHONUNBUFFERED", "VIRTUAL_ENV", "PATH", "LD_LIBRARY_PATH", "CUDA_VISIBLE_DEVICES"]
        selected += ["FT_DEV_STATE_DUMP", "FT_DEV_STATE_DUMP_AT"] if state else []
        selected += ["FT_DEV_LOGITS_DUMP"] if logits else []
        (arm / "SERVE_CMD.txt").write_text(
            "env " + " ".join(f"{key}={_protocol['shlex'].quote(env[key])}" for key in selected)
            + " " + _protocol["shlex"].join(argv) + "\n", encoding="utf-8")
        (arm / "ENV.txt").write_text(
            time.strftime("%F %T %Z") + "\n" + _protocol["output"](["hostname"]) + "\n"
            + _protocol["output"](["git", "-C", str(worktree), "log", "-1", "--format=%H %s"]) + "\n"
            + _protocol["output"](["nvidia-smi"]) + "\n" + _protocol["output"](["numactl", "-H"]) + "\n",
            encoding="utf-8")
        with (arm / "serve.log").open("x", encoding="utf-8") as log:
            self.proc = subprocess.Popen(argv, cwd=worktree, env=env, stdout=log, stderr=subprocess.STDOUT,
                                         start_new_session=True)
        if os.getpgid(self.proc.pid) != self.proc.pid or os.getsid(self.proc.pid) != self.proc.pid:
            raise RuntimeError("service did not receive its own process group and session")
        self._service_birth = process_birth(self.proc.pid)
        _protocol["write_new"](arm / "owned_process.json", {"pid": self.proc.pid, "pgid": self.proc.pid,
                                "session": os.getsid(self.proc.pid), "birth": self._service_birth})
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("owned service died during startup")
            try:
                with _protocol["urllib"].request.urlopen(f"http://127.0.0.1:{_protocol['PORT']}/health", timeout=5) as response:
                    health = json.load(response)
                if health.get("status") == "ok":
                    _protocol["write_new"](arm / "health.json", health)
                    parsed = self.parser(str(arm / "serve.log"))
                    suffix = _protocol["ast"].literal_eval(parsed.get("_unique_suffix", ""))
                    if suffix != ".pid=" + str(self.proc.pid):
                        raise ValueError("parsed service PID differs from owned process")
                    text = (arm / "serve.log").read_text(encoding="utf-8", errors="replace")
                    position = text.find("Parsed arguments")
                    if position < 0:
                        raise ValueError("service did not emit parsed arguments")
                    (arm / "serve_args.txt").write_text("\n".join(text[position:].splitlines()[:2]) + "\n", encoding="utf-8")
                    if not state and not logits:
                        if {"FT_DEV_STATE_DUMP", "FT_DEV_STATE_DUMP_AT", "FT_DEV_LOGITS_DUMP"} & env.keys():
                            raise ValueError("D03 diagnostics leaked into the default environment")
                        if (arm / "state").exists() or (arm / "logits").exists():
                            raise ValueError("D03 default path created diagnostic directories")
                    return arm, env
                if health.get("status") == "error":
                    raise RuntimeError(f"health failure: {health}")
            except (OSError, _protocol["urllib"].error.URLError):
                pass
            time.sleep(5)
        raise TimeoutError("service readiness timeout")

    def stop(self):
        if self.proc is None:
            return
        proc = self.proc
        # Any inspection/signal/release failure below is lock-retaining unless
        # the complete group and resource release sequence reaches success.
        self._cleanup_failed = True
        pgid = proc.pid
        for sig, timeout in STOP_STEPS:
            members = owned_group_members(pgid)
            if not members:
                break
            if process_birth(pgid) != getattr(self, '_service_birth', None):
                raise RuntimeError('owned service birth changed; group signal refused')
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                if owned_group_members(pgid):
                    self._cleanup_failed = True
                    raise RuntimeError("owned process group disappeared during cleanup")
            # Keep the unreaped leader until its entire group is gone: its PID
            # remains reserved even when it has exited and descendants survive.
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and owned_group_members(pgid):
                time.sleep(0.25)
        survivors = owned_group_members(pgid)
        if survivors:
            self._cleanup_failed = True
            raise RuntimeError(f"owned process group did not stop: {sorted(survivors)}")
        proc.wait(timeout=1)
        # Retain the base port/GPU-release check after group quiescence.
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            with _protocol["socket"].socket() as sock:
                port_free = sock.connect_ex(("127.0.0.1", _protocol["PORT"])) != 0
            used = _protocol["output"](["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"])
            if port_free and all(int(value) < 1000 for value in used.splitlines()):
                self.proc = None
                self._owned_proc = None
                self._cleanup_failed = False
                return
            time.sleep(2)
        self._cleanup_failed = True
        raise RuntimeError("owned process group stopped but did not release port/GPU")

    def lock_release(self):
        # The base finally block executes this after every stop attempt.  A
        # surviving owned group must retain the lock and handle for operator
        # recovery rather than advertise GPU availability to another runner.
        if getattr(self, "_cleanup_failed", False):
            return
        return super().lock_release()

    def run(self):
        # Fail before taking the GPU lock or creating output if the producer did
        # not give f506-specific raw-token proof.
        if self.args.raw_ids is None:
            raise ValueError("--raw-manifest is required for f506 G4/G5")
        self._cleanup_failed = False
        self._owned_proc = None
        _protocol["__file__"] = str(Path(__file__).resolve())
        return super().run()


def self_test() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        candidate = root / "candidate"
        model = root / "model"
        model.mkdir()
        for name in TOKENIZER_FILES:
            (model / name).write_text(name, encoding="utf-8")
        sources = {}
        for relative in TOKENIZER_SOURCES:
            source = candidate / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(f"# candidate source {relative}\n", encoding="utf-8")
            sources[str(relative)] = sha256(source)
        global CANDIDATE
        old_candidate = CANDIDATE
        old_model = MODEL_PATH
        try:
            CANDIDATE = candidate
            globals()["MODEL_PATH"] = model
            ids = [7, 8, 9]
            packed = b"".join(value.to_bytes(4, "little", signed=True) for value in ids)
            digest = hashlib.sha256(packed).hexdigest()
            manifest = root / "raw.json"
            document = {
                "schema": RAW_SCHEMA, "ids": ids, "candidate_commit": CANDIDATE_COMMIT,
                "candidate_worktree": str(candidate), "trace_sha256": "trace", "messages_sha": "messages",
                "request_sha256": "request", "raw_ids_sha256": digest, "input_length": len(ids),
                "candidate_tokenizer": {"manager_module": "freetoken.tokenizer.tokenize.TokenizeManager",
                                        "construction": TOKENIZER_CONSTRUCTION, "source_sha256": sources,
                                        "model_files_sha256": {name: sha256(model / name) for name in TOKENIZER_FILES},
                                        "absent_model_files": [],
                                        "encoded_ids_sha256_int32le": digest},
            }
            manifest.write_text(json.dumps(document), encoding="utf-8")
            assert raw_binding(manifest, "trace", {"messages_sha": "messages"}, "request", 2)[0] == ids
            document["candidate_commit"] = PARENT_COMMIT
            manifest.write_text(json.dumps(document), encoding="utf-8")
            try:
                raw_binding(manifest, "trace", {"messages_sha": "messages"}, "request", 2)
            except ValueError:
                pass
            else:
                raise AssertionError("old-commit raw evidence was accepted")
        finally:
            CANDIDATE = old_candidate
            globals()["MODEL_PATH"] = old_model
    print("SELFTEST PASS: pinned historical protocol and f506 raw-token binding")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--trace", type=Path, default=_protocol["TRACE"])
    parser.add_argument("--raw-manifest", type=Path, help="new f506 tokenizer-bound raw-ID manifest")
    parser.add_argument("--tail-k", type=int, default=64)
    args = parser.parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if not args.run:
        parser.error("--run is required; this preparation tool never starts a service by default")
    if sys.platform != "linux":
        parser.error("--run requires the Linux GPU host")
    if args.raw_manifest is None:
        parser.error("--raw-manifest is required; c30 raw evidence is refused")
    args.raw_ids = args.raw_manifest
    SelfCheck(args).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
