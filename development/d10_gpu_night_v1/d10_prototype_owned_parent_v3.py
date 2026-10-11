"""Actual one-service D10 prototype with D07-owned controller/child custody.

The live path is intentionally narrow: one enabled service and four frozen
AIPerf profiles (two original R045 and two ignore-EOS-256), or an honest
terminal failure.  ``filedry`` injects only process/network dependencies; it
executes the same controller and child functions.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

HERE = Path(__file__).resolve().parent
ROOT = Path("/data2/FreeToken")
RID = "E2-D10-PROTOTYPE-night-20261010"
CANDIDATE = "22ff3a389eae3724cdca9a45f2e19577082a2032"
PARENT = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"
WT = ROOT / "wt/d10-staggered-v1"
PROVENANCE = HERE / "d10_native_provenance_v2.json"
REUSE_SHA = "de2f510f8734b5c5595b8d5a7c2308fa8bccea58fdb08acdbc55645e781f44b3"
FLAG = "--d10-staggered-decode"
MAX_CALLS = 8


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def d07():
    module = load(HERE / "d07_g3g4_prepare.py", "d10_v3_d07")
    module.CANDIDATE = CANDIDATE
    module.RID = RID
    return module


def aiperf():
    return load(HERE / "d10_aiperf_runner_v4.py", "d10_v3_aiperf")


def argv_sha(argv: list[str]) -> str:
    return hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()


def reserve_pair(api_port: int, tcpstore_port: int):
    held = []
    try:
        for port in (api_port, tcpstore_port):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            held.append(sock)
        return held
    except BaseException:
        for sock in held:
            sock.close()
        raise


def release_pair(held) -> None:
    for sock in held:
        sock.close()


def port_from_argv(argv: list[str], flags: tuple[str, ...]) -> int:
    values = []
    for flag in flags:
        if argv.count(flag) == 1:
            values.append(int(argv[argv.index(flag) + 1]))
    if len(values) != 1 or not 1024 <= values[0] <= 65535:
        raise RuntimeError("service port argument is absent or ambiguous")
    return values[0]


def child_argv(admission: Path, batch: int, receipt: Path) -> list[str]:
    return [str(ROOT / "venv/bin/python"), str(Path(__file__).resolve()), "--run", "--owned-child",
            "--admission", str(admission), "--batch", str(batch), "--launch-receipt", str(receipt)]


def validate_candidate() -> dict:
    if WT.is_symlink():
        raise RuntimeError("candidate worktree is symlinked")
    head = subprocess.check_output(["git", "-C", str(WT), "rev-parse", "HEAD"], text=True).strip()
    dirty = subprocess.check_output(["git", "-C", str(WT), "status", "--porcelain", "--untracked-files=no"], text=True)
    source = WT / "python/freetoken/server/args.py"
    provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    receipt = Path(provenance["reuse_receipt"])
    if (head != CANDIDATE or dirty or not source.is_file() or FLAG not in source.read_text(encoding="utf-8")
            or provenance.get("parent_commit") != PARENT or provenance.get("candidate_commit") != CANDIDATE
            or provenance.get("reuse_receipt_sha256") != REUSE_SHA or not receipt.is_file() or sha(receipt) != REUSE_SHA):
        raise RuntimeError("candidate source, HEAD, or native-reuse receipt differs")
    checked = {}
    for name, wanted in provenance["regular_extensions"]["candidate"]["sha256"].items():
        path = WT / "python/freetoken/kernel" / f"{name}.cpython-310-x86_64-linux-gnu.so"
        size = provenance["regular_extensions"]["candidate"]["size"][name]
        if path.is_symlink() or not path.is_file() or path.stat().st_size != size or sha(path) != wanted:
            raise RuntimeError("native copied bytes differ: " + name)
        checked[name] = {"sha256": wanted, "size": size}
    return {"head": head, "tracked_clean": True, "source_flag": FLAG, "source_sha256": sha(source),
            "native_provenance_sha256": sha(PROVENANCE), "native_reuse_receipt_sha256": REUSE_SHA,
            "native_extensions": checked}


def require_admission(path: Path, runner) -> dict:
    """Validate root approval plus the prior real D09 terminal bindings."""
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError("sealed root admission required")
    doc = runner.require_admission(path)  # also verifies every D09 terminal+manifest hash
    expected = {"prototype_rid": RID, "candidate": CANDIDATE, "parent_commit": PARENT,
                "d10_flag": FLAG, "native_provenance_sha256": sha(PROVENANCE), "calls_max": MAX_CALLS,
                "services_max": 1}
    if any(doc.get(key) != value for key, value in expected.items()):
        raise RuntimeError("D10 prototype admission binding differs")
    closure = doc.get("t16_closure")
    if not isinstance(closure, dict) or set(closure) != {"rid", "verdict", "round_json_sha256", "manifest_sha256"}:
        raise RuntimeError("closed D04 T16 hash binding is required")
    if closure["rid"] != "E2-D10-T16-night-20261010" or closure["verdict"] != "kept":
        raise RuntimeError("prototype requires the kept D10 T16 closure")
    service = doc.get("service")
    if not isinstance(service, dict) or set(service) != {"argv", "cwd", "endpoint", "api_port", "tcpstore_port"}:
        raise RuntimeError("root service binding shape differs")
    argv = service["argv"]
    api = port_from_argv(argv, ("--port",))
    tcp = port_from_argv(argv, ("--tcpstore-port", "--tcp-store-port"))
    if (len(argv) < 2 or not argv[0].endswith("python") or not argv[1].endswith(".py") or FLAG not in argv
            or api != service["api_port"] or tcp != service["tcpstore_port"] or service["endpoint"] != f"http://127.0.0.1:{api}"):
        raise RuntimeError("root service argv or endpoint differs")
    return doc


def require_t16_closure(doc: dict, gate) -> dict:
    """Use D07's sealed D04 registry, then bind both immutable closure hashes."""
    closure = doc["t16_closure"]
    round_json = gate.require_closed_round(closure["rid"], closure["verdict"])
    manifest = round_json.with_name("MANIFEST.sha256")
    if sha(round_json) != closure["round_json_sha256"] or sha(manifest) != closure["manifest_sha256"]:
        raise RuntimeError("closed D04 T16 hash binding differs")
    return closure


def require_receipt(gate, receipt: Path, batch: int, admission: Path) -> dict:
    expected = {"schema": "ft_d10_prototype_launch/v3", "state": "launched", "rid": RID,
                "batch": batch, "candidate_commit": CANDIDATE,
                "argv_sha256": gate.argv_sha256(child_argv(admission, batch, receipt))}
    mine = gate.process_birth()
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if receipt.is_symlink():
            raise RuntimeError("child receipt is symlinked")
        if receipt.is_file():
            value = json.loads(receipt.read_text(encoding="utf-8"))
            if any(value.get(k) != v for k, v in expected.items()) or value.get("child") != mine:
                raise RuntimeError("child receipt binding differs")
            return value
        time.sleep(.05)
    raise RuntimeError("child receipt did not become bound")


def controller(admission: Path, deps=None) -> dict:
    gate = deps.gate if deps else d07()
    runner = deps.runner if deps else aiperf()
    require_admission(admission, runner)
    require_t16_closure(runner.require_admission(admission), gate)
    (deps.validate_candidate() if deps else validate_candidate())
    if gate.LOCK.exists() or gate.LOCK.is_symlink():
        raise RuntimeError("foreign GPU lock exists")
    lifecycle = gate.load_owned_lifecycle()
    helper = lifecycle.verified_module(ROOT / "runs/plan_batches/e2_launch.py", gate.ATOMIC_HELPER_SHA, "d10_prototype_atomic")
    batch = helper.next_batch(gate.ROUNDS)
    receipt = (deps.root / "launch.json") if deps else ROOT / "runs/dev_D10" / f"prototype_{RID}_batch{batch}.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    reserved = {"schema": "ft_d10_prototype_launch/v3", "state": "reserved", "rid": RID, "batch": batch,
                "candidate_commit": CANDIDATE, "argv_sha256": gate.argv_sha256(child_argv(admission, batch, receipt)),
                "controller": gate.process_birth(), "scope": {"services_max": 1, "generation_calls_max": MAX_CALLS}}
    got = lifecycle.reserve_process(helper, batch, RID, child_argv(admission, batch, receipt), receipt, reserved)
    return gate.publish_child_binding(receipt, got, gate.process_identity(got["batch_pid"]), lifecycle=lifecycle)


class DefaultDeps:
    def __init__(self):
        self.gate = d07(); self.runner = aiperf()
    def validate_candidate(self): return validate_candidate()
    def start(self, argv, cwd, env, log):
        with log.open("xb") as handle:
            return subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=handle,
                                    stderr=subprocess.STDOUT, start_new_session=True)
    def health(self, endpoint):
        opener = build_opener(ProxyHandler({}))
        with opener.open(endpoint.rstrip("/") + "/health", timeout=10) as response:
            return json.loads(response.read()), opener
    def run_aiperf(self, admission, endpoint, output):
        """v4's frozen plan, with stdout/stderr retained beside each raw export."""
        self.runner.require_admission(admission); plan = self.runner.filedry()
        if plan["budget"]["aiperf_calls"] != MAX_CALLS: raise RuntimeError("frozen AIPerf budget differs")
        output.mkdir(parents=True, exist_ok=False)
        for index in range(4):
            input_file = self.runner.ORIGINAL if index < 2 else self.runner.INPUT
            command = self.runner.argv(endpoint, str(output / f"profile{index}"), input_file)
            put(output / f"profile{index}.command.json", {"argv": command})
            with (output / f"profile{index}.stdout.log").open("xb") as log:
                result = subprocess.run(command, env=dict(os.environ, NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost"),
                                        stdout=log, stderr=subprocess.STDOUT, timeout=1800)
            put(output / f"profile{index}.exit.json", {"exit_code": result.returncode, "at_unix": time.time()})
            if result.returncode: raise RuntimeError(f"AIPerf profile {index} failed")
    def stop(self, proc): self.gate.load_owned_lifecycle().stop_owned_process(proc, 120, 30)
    def alive(self, pid): return self.gate.load_owned_lifecycle().owned_group_alive(pid)
    def idle(self): return self.gate.require_gpu_idle()


def child(admission: Path, batch: int, receipt: Path, deps=None) -> Path:
    deps = deps or DefaultDeps(); gate = deps.gate; runner = deps.runner
    doc = require_admission(admission, runner); require_t16_closure(doc, gate)
    candidate = deps.validate_candidate(); require_receipt(gate, receipt, batch, admission)
    service = doc["service"]; output = Path(doc["prototype_output"])
    if output.exists() or output.is_symlink():
        raise RuntimeError("prototype output already exists")
    owner = gate.take_d07_gpu_lock(RID, batch); proc = None; reservation = []; cleanup_error = None; error = None
    try:
        output.mkdir(parents=True); put(output / "admission_snapshot.json", doc); put(output / "candidate_binding.json", candidate)
        api, tcp = service["api_port"], service["tcpstore_port"]
        reservation = reserve_pair(api, tcp); put(output / "port_pair_reservation.json", {"api_port": api, "tcpstore_port": tcp, "both_bound_before_spawn": True})
        release_pair(reservation); reservation = []
        event = output / "d10_branch_event.json"; env = gate.clean_environment(WT)
        env.update({"PYTHONDONTWRITEBYTECODE": "1", "FT_D10_BRANCH_EVENT": str(event), "FT_D10_ELIGIBLE_LANES": "2", "FT_D10_CANDIDATE": CANDIDATE,
                    "PYTHONPATH": str(HERE) + os.pathsep + str(WT / "python")})
        program, *program_args = service["argv"]
        wrapper = [str(ROOT / "venv/bin/python"), str(HERE / "d10_branch_startup_v3.py"), "--program", program, "--", *program_args]
        proc = deps.start(wrapper, service["cwd"], env, output / "serve.log")
        put(output / "service_identity.json", {"pid_identity": gate.process_identity(proc.pid), "service_argv": service["argv"], "wrapper_argv": wrapper})
        deadline = time.monotonic() + 1800; health = None
        while time.monotonic() < deadline:
            if proc.poll() is not None: raise RuntimeError("owned service exited before health")
            try:
                health, _ = deps.health(service["endpoint"])
                if health.get("status") == "ok": break
            except (OSError, ValueError): time.sleep(2)
        else: raise TimeoutError("health readiness timeout")
        put(output / "ready.json", {"health": health, "generation_readiness_calls": 0})
        deps.run_aiperf(admission, service["endpoint"], output / "aiperf")
        event_doc = json.loads(event.read_text(encoding="utf-8")) if event.is_file() else {}
        if (event_doc.get("method") != "Engine._forward_d10_staggered_decode" or event_doc.get("entered") is not True
                or event_doc.get("eligible_lanes") != 2 or event_doc.get("candidate_commit") != CANDIDATE or event_doc.get("service_pid") != proc.pid):
            raise RuntimeError("D10 source branch proof absent or ineligible")
        profiles = sorted((output / "aiperf").glob("profile*.exit.json"))
        if len(profiles) != 4 or any(json.loads(p.read_text())["exit_code"] != 0 for p in profiles):
            raise RuntimeError("AIPerf exports are incomplete")
        counts = profile_completion_counts(output / "aiperf")
        if any(len(counts[index]) != 2 or min(counts[index]) <= 30 for index in (0, 1)):
            raise RuntimeError("original R045 profile exports lack two requests over 30 tokens")
        if any(counts[index] != [256, 256] for index in (2, 3)):
            raise RuntimeError("ignore-EOS-256 profile exports lack exact 256-token results")
    except BaseException as exc:
        error = repr(exc)
    finally:
        try:
            if proc is not None:
                deps.stop(proc)
                if deps.alive(proc.pid): raise RuntimeError("owned service group remains alive")
            release_pair(reservation); deps.idle()
            post = reserve_pair(service["api_port"], service["tcpstore_port"]); release_pair(post)
        except BaseException as exc:
            cleanup_error = repr(exc)
        terminal = {"rid": RID, "verdict": "not_met" if error is None and cleanup_error is None else "failed_harness", "error": error,
                    "cleanup_error": cleanup_error, "services": 1, "generation_calls_expected": MAX_CALLS,
                    "profiles_expected": 4, "source_branch_entered": error is None, "post_cleanup_closed": cleanup_error is None,
                    "gpu_lock_released": cleanup_error is None, "lock_retained": cleanup_error is not None, "product_acceptance": False,
                    "independent_terminal_review_required": True}
        if output.exists(): put(output / "terminal.json", terminal)
        if cleanup_error is None: gate.release_d07_gpu_lock(owner)
    if cleanup_error: raise RuntimeError("unsafe cleanup preserves GPU lock: " + cleanup_error)
    if error: raise RuntimeError(error)
    return output / "terminal.json"


def profile_completion_counts(root: Path) -> dict[int, list[int]]:
    """Read raw AIPerf JSON/JSONL exports without accepting a summary as proof."""
    result = {index: [] for index in range(4)}
    for index in range(4):
        profile = root / f"profile{index}"
        for path in profile.rglob("*") if profile.is_dir() else ():
            if not path.is_file() or path.suffix not in {".json", ".jsonl"}: continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try: value = json.loads(line)
                except json.JSONDecodeError: continue
                if isinstance(value, dict) and isinstance(value.get("completion_tokens"), int):
                    result[index].append(value["completion_tokens"])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--run", action="store_true"); parser.add_argument("--owned-child", action="store_true")
    parser.add_argument("--admission", type=Path); parser.add_argument("--batch", type=int); parser.add_argument("--launch-receipt", type=Path)
    args = parser.parse_args()
    if args.run and args.admission and args.owned_child and args.batch and args.launch_receipt:
        child(args.admission, args.batch, args.launch_receipt); return
    if args.run and args.admission and not args.owned_child and args.batch is None and args.launch_receipt is None:
        controller(args.admission); return
    parser.error("select guarded --run --admission")


if __name__ == "__main__": main()
