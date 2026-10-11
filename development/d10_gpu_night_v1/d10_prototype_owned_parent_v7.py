"""D10 V7 owned prototype; root admission is mandatory before any GPU action.

The module deliberately has no automatic run path.  The controller is the only
writer of a D07-style child receipt; the child consumes that receipt, keeps its
own D07 lock until owned cleanup has been proven, and can only report a pending
measurement for independent review.
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
WT = ROOT / "wt/d10-staggered-v1"
RID = "E2-D10-PROTOTYPE-night-20261010-v7"
CANDIDATE = "22ff3a389eae3724cdca9a45f2e19577082a2032"
PARENT = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"
FLAG = "--d10-staggered-decode"
MAX_CALLS = 8
NATIVE_PROVENANCE = HERE / "d10_native_provenance_v2.json"
ACTUAL = ("d10_prototype_owned_parent_v7.py", "d10_aiperf_runner_v8.py", "d10_aiperf_parse_v7.py",
          "d10_branch_startup_v4.py", "d10_branch_probe_v4.py", "d07_g3g4_prepare.py",
          "inputs_r045_v7.jsonl", "inputs_ignore_eos256_v7.jsonl", "d10_native_provenance_v2.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(module)
    return module


def runner(): return load(HERE / "d10_aiperf_runner_v8.py", "d10_runner_v8")


def d07():
    module = load(HERE / "d07_g3g4_prepare.py", "d10_v7_d07")
    # Reuse the actual D07 lifecycle methods while binding this child protocol.
    module.CANDIDATE, module.RID = CANDIDATE, RID
    return module


def put_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2); handle.write("\n")


def append_new(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8") as handle: handle.write(json.dumps(value, sort_keys=True) + "\n")


def reserve_pair(api_port: int):
    held = []
    try:
        for port in (api_port, api_port + 1):
            sock = socket.socket(); sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); sock.bind(("127.0.0.1", port)); held.append(sock)
        return held
    except BaseException:
        for sock in held: sock.close()
        raise


def source_hashes() -> dict[str, str]: return {name: sha(HERE / name) for name in ACTUAL}


def _sealed_file(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError(f"sealed dependency required: {path}")
    return {"path": str(path), "sha256": sha(path)}


def _binding(doc: dict, name: str, *, verdict: str | tuple[str, ...] | None = None) -> None:
    value = doc.get(name)
    if not isinstance(value, dict) or not isinstance(value.get("path"), str) or not isinstance(value.get("sha256"), str):
        raise RuntimeError(f"{name} hash binding is absent")
    actual = _sealed_file(Path(value["path"]))
    if actual != {"path": value["path"], "sha256": value["sha256"]}: raise RuntimeError(f"{name} hash binding differs")
    if verdict is not None:
        allowed = (verdict,) if isinstance(verdict, str) else verdict
        if value.get("verdict") not in allowed: raise RuntimeError(f"{name} terminal verdict is not allowed")


def require_admission(path: Path, run=None) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222: raise RuntimeError("sealed V7 admission required")
    doc = json.loads(path.read_text(encoding="utf-8")); run = runner() if run is None else run
    want = {"schema": "ft_d10_prototype_v7_admission/v1", "admit": True, "prototype_rid": RID, "candidate": CANDIDATE,
            "parent": PARENT, "d10_flag": FLAG, "calls_max": MAX_CALLS, "services_max": 1}
    if any(doc.get(k) != v for k, v in want.items()): raise RuntimeError("V7 admission identity/budget differs")
    if doc.get("source_sha256") != source_hashes() or doc.get("runner_source_sha256") != run.source_hashes():
        raise RuntimeError("V7 runtime source binding differs")
    for name in ("native_provenance", "t16_round", "t16_manifest", "t16_history", "d09_terminal", "d09_manifest", "d09_cleanup"):
        _binding(doc, name, verdict=("kept", "failed_harness") if name == "d09_terminal" else "kept")
    native = json.loads(NATIVE_PROVENANCE.read_text(encoding="utf-8"))
    if native.get("candidate_commit") != CANDIDATE or native.get("parent_commit") != PARENT or native.get("native_source_abi_unchanged") is not True:
        raise RuntimeError("native provenance ABI binding differs")
    service = doc.get("service", {}); argv = service.get("argv"); api = service.get("api_port")
    if not isinstance(argv, list) or argv[:2] != ["ft", "serve"] or FLAG not in argv or argv.count("--port") != 1:
        raise RuntimeError("V7 service argv differs")
    if not isinstance(api, int) or int(argv[argv.index("--port") + 1]) != api or service.get("tcpstore_port") != api + 1:
        raise RuntimeError("V7 paired-port binding differs")
    if not isinstance(doc.get("prototype_output"), str) or not isinstance(service.get("endpoint"), str) or not isinstance(service.get("cwd"), str):
        raise RuntimeError("V7 output/service endpoint binding is absent")
    return doc


def child_argv(batch: int, receipt: Path, admission: Path) -> list[str]:
    return [str(ROOT / "venv/bin/python"), str(HERE / "d10_prototype_owned_parent_v7.py"), "--run", "--owned-child",
            "--batch", str(batch), "--launch-receipt", str(receipt), "--admission", str(admission)]


def controller(admission: Path, gate=None):
    if sys.platform != "linux": raise RuntimeError("V7 controller is Linux-only")
    gate = d07() if gate is None else gate; doc = require_admission(admission)
    if gate.LOCK.exists() or gate.LOCK.is_symlink(): raise RuntimeError("foreign GPU lock exists")
    owned = gate.load_owned_lifecycle(); helper = owned.verified_module(ROOT / "runs/plan_batches/e2_launch.py", gate.ATOMIC_HELPER_SHA, "d10_v7_atomic")
    batch = helper.next_batch(gate.ROUNDS); receipt = Path(doc["prototype_output"]).parent / f"launch_{RID}_batch{batch}.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    argv = child_argv(batch, receipt, admission)
    reserved = {"schema": "ft_d07_owned_launch/v2", "state": "reserved", "rid": RID, "batch": batch,
                "candidate_commit": CANDIDATE, "argv_sha256": gate.argv_sha256(argv), "controller": gate.process_birth()}
    got = owned.reserve_process(helper, batch, RID, argv, receipt, reserved)
    birth = owned.process_identity(got["batch_pid"])
    if not birth or birth.get("pid") != got["batch_pid"]: raise RuntimeError("D07 reserved child birth is unavailable")
    child = {"pid": birth["pid"], "start_ticks": birth["start_ticks"], "execution_id": f"{birth['pid']}:{birth['start_ticks']}"}
    return gate.publish_child_binding(receipt, got, child, lifecycle=owned)


class Default:
    def __init__(self): self.gate, self.run = d07(), runner()
    def start(self, argv, cwd, env, log):
        with log.open("xb") as stream: return subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
    def health(self, endpoint):
        with build_opener(ProxyHandler({})).open(endpoint + "/health", timeout=10) as response: return json.loads(response.read())
    def dispatch(self, endpoint, output, index):
        inputs = self.run.ORIGINAL if index < 2 else self.run.FIXED; command = self.run.argv(endpoint, str(output / f"profile{index}"), inputs)
        put_new(output / f"profile{index}.command.json", {"argv": command, "input_sha256": sha(inputs)})
        result = subprocess.run(command, timeout=1800); put_new(output / f"profile{index}.exit.json", {"exit_code": result.returncode})
        if result.returncode: raise RuntimeError("AIPerf group failed")
    def stop(self, process): self.gate.load_owned_lifecycle().stop_owned_process(process, 120, 30)
    def alive(self, pid): return self.gate.load_owned_lifecycle().owned_group_alive(pid)


def child(admission: Path, batch: int, receipt: Path, deps=None) -> Path:
    deps = Default() if deps is None else deps; gate, run = deps.gate, deps.run; doc = require_admission(admission, run)
    output = Path(doc["prototype_output"]); service = doc["service"]; calls = 0; process = None; owner = None; error = None; cleanup = None
    if output.exists() or output.is_symlink(): raise RuntimeError("fresh V7 output required")
    try:
        # The actual D07 child receipt validates controller publication and this process birth.
        gate.require_child_receipt(receipt, batch, WT, output, rid=RID, expected_argv=child_argv(batch, receipt, admission), schema="ft_d07_owned_launch/v2")
        if gate.LOCK.exists() or gate.LOCK.is_symlink(): raise RuntimeError("foreign GPU lock exists")
        owner = gate.take_d07_gpu_lock(RID, batch); gate.require_gpu_idle()
        held = reserve_pair(service["api_port"]); [sock.close() for sock in held]
        # Recheck both ports immediately before spawn, while the owned lock is held.
        held = reserve_pair(service["api_port"]); [sock.close() for sock in held]
        output.mkdir(); put_new(output / "admission_snapshot.json", doc)
        env = gate.clean_environment(WT); event = output / "d10_branch_event.json"
        env.update({"PYTHONPATH": str(HERE) + os.pathsep + str(WT / "python"), "FT_D10_BRANCH_EVENT": str(event),
                    "FT_D10_CANDIDATE": CANDIDATE, "PYTHONDONTWRITEBYTECODE": "1"})
        process = deps.start([str(ROOT / "venv/bin/python"), str(HERE / "d10_branch_startup_v4.py"), *service["argv"][2:]], service["cwd"], env, output / "serve.log")
        deadline = time.monotonic() + 1800
        while time.monotonic() < deadline:
            if process.poll() is not None: raise RuntimeError("service exited before health")
            try:
                if deps.health(service["endpoint"]).get("status") == "ok": break
            except OSError: time.sleep(2)
        else: raise TimeoutError("health timeout")
        aiperf = output / "aiperf"; aiperf.mkdir()
        for group in range(4):
            append_new(output / "budget.jsonl", {"event": "dispatch_reserved", "group": group, "calls_before": calls, "calls_after": calls + 2})
            calls += 2; deps.dispatch(service["endpoint"], aiperf, group)
        try:
            records = run.require_raw_profiles(aiperf)
        except RuntimeError as exc:
            # A complete raw group that misses a measurement threshold is a
            # negative result, never a tooling-success or harness claim.
            raise ValueError(str(exc)) from exc
        branch = json.loads(event.read_text(encoding="utf-8"))
        if branch.get("actual_batch_reqs") != 2 or branch.get("actual_can_use_d10_staggered") is not True: raise ValueError("branch proof not met")
        put_new(output / "raw_response_records.json", {"profiles": records, "actual_generation_calls": calls})
    except ValueError as exc: error = ("not_met", repr(exc))
    except BaseException as exc: error = ("failed_harness", repr(exc))
    finally:
        try:
            if process is not None: deps.stop(process); assert not deps.alive(process.pid)
            held = reserve_pair(service["api_port"]); [sock.close() for sock in held]
        except BaseException as exc: cleanup = repr(exc)
        verdict = "failed_harness" if cleanup or (error and error[0] == "failed_harness") else ("not_met" if error else "measured_pending_independent_review")
        if output.exists(): put_new(output / "terminal.json", {"rid": RID, "verdict": verdict, "error": None if not error else error[1], "cleanup_error": cleanup, "actual_services": int(process is not None), "actual_generation_calls": calls, "candidate_meets_prototype_threshold": verdict == "measured_pending_independent_review", "product_acceptance": False, "lock_retained": bool(cleanup)})
        if owner and not cleanup: gate.release_d07_gpu_lock(owner)
    if cleanup: raise RuntimeError(cleanup)
    if error: raise RuntimeError(error[1])
    return output / "terminal.json"


def filedry() -> dict:
    return {"schema": "ft_d10_v7_filedry/v1", "entrypoint": Path(__file__).name, "source_sha256": source_hashes(),
            "runner": runner().source_hashes(), "budget": {"services_max": 1, "aiperf_calls": MAX_CALLS, "generation_calls": MAX_CALLS},
            "gpu_started": False, "http_started": False, "service_started": False, "compile_started": False}


def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--filedry", action="store_true"); parser.add_argument("--run", action="store_true"); parser.add_argument("--owned-child", action="store_true"); parser.add_argument("--admission", type=Path); parser.add_argument("--batch", type=int); parser.add_argument("--launch-receipt", type=Path); args = parser.parse_args(argv)
    if args.filedry: print(json.dumps(filedry(), sort_keys=True)); return 0
    if not args.run or args.admission is None: parser.error("root controller requires --run --admission")
    if args.owned_child:
        if args.batch is None or args.launch_receipt is None: parser.error("owned child requires batch and receipt")
        child(args.admission, args.batch, args.launch_receipt); return 0
    controller(args.admission); return 0


if __name__ == "__main__": raise SystemExit(main())
