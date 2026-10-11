#!/usr/bin/env python3
"""E2-R046f remaining G4/T06 preparation; retain independently accepted R046e G3 pair.

Default execution is inert.  The formal path is fail-closed until its sealed
startup review is present; it uses only the ordinary-session client and never
falls back to the old pause/ACK client.
"""
from __future__ import annotations

import argparse
import datetime
import getpass
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
import sys
import shutil
import time
import urllib.request
import runpy
from pathlib import Path

RID = "E2-R046f"
CANDIDATE = "4fc2320dc0a29422ab61e383e5e1579460e9926e"
ROOT = Path("/data2/FreeToken")
WT = ROOT / "wt/e2d07-trace-backpressure"
VENV = ROOT / "venv"
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
HERE = Path(__file__).resolve().parent
D07_SOURCE = HERE / "d07_g3g4_prepare.py"
STARTUP_V3 = HERE / "r046c_t06_ordinary_startup_v4.py"
MEMORY_STARTUP = HERE / "r046c_ordinary_memory_startup_v2.py"
MEMORY_OBSERVER = HERE / "r056_performance_memory_observer.py"
CLIENT_V3 = HERE / "r046e_t06_ordinary_client_v4.py"
CLIENT_V2 = HERE / "r046c_t06_ordinary_client_v2.py"
SESSION_DRIVER = HERE / "r046c_ordinary_seed_driver.py"
ROUTE_ANALYZER = HERE / "r046c_route_analyze_ordinary_v1.py"
PORT_SOURCE = HERE / "ft_batch_port_pair_v1.py"
ARGS_PARSER = HERE / "d04_original/serve_args_diff.py"
NATIVE_PROVENANCE = ROOT / "runs/dev_R046d/r062_native_provenance_20261007.json"
NATIVE_PROVENANCE_SHA256 = "c03de16a78e6b855ca84eaa3dec81ea56b8fbe0eae98548e9c07ee6d16551d13"
SEED_CLIENT = HERE / "r046_seed_agent_trace_v2.py"
NATIVE_SOURCE_RELATIVE = (Path("python/freetoken/kernel/csrc/pinned_tensor.cpp"),
                          Path("python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp"))
WINDOW = 98304
COMPLETION_RESERVE = 2048
MEMORY_RATIO = "0.88"
SEEDS = {
    "seed12k": "1bcb7214c78f16258c8689e8f57f2d72f0930f9924c58ae1a18763e18c364153",
    "seed_45k": "499c39e4e601d8c61e8305265569c5055083eb14e5da9940b10c656f5e9c97e9",
    "seed_real": "8fe6b36da6c19eabb4a259535a9835f20e41921d4d7023ec7aaa0063c8b50bf3",
}


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def md5(path: Path) -> str:
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")


def window_contract() -> dict:
    return {"kv_reserve_tokens": WINDOW, "max_seq_len_override": WINDOW,
            "completion_reserve_tokens": COMPLETION_RESERVE,
            "max_prompt_tokens": WINDOW - COMPLETION_RESERVE}


def load_d07(source: Path = D07_SOURCE):
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("R046c requires D07 lifecycle source")
    spec = importlib.util.spec_from_file_location("r046c_d07_lifecycle", source)
    module = importlib.util.module_from_spec(spec); assert spec.loader
    spec.loader.exec_module(module)
    module.CANDIDATE, module.WORKTREE, module.RID = CANDIDATE, WT, RID
    return module


def load_client(source: Path = CLIENT_V3):
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("R046c ordinary client v3 is unavailable")
    spec = importlib.util.spec_from_file_location("r046c_ordinary_client_v3", source)
    module = importlib.util.module_from_spec(spec); assert spec.loader
    spec.loader.exec_module(module)
    return module


def apply_window(d07):
    original = d07.serve_argv
    def argv(port: int):
        value = list(original(port))
        for flag, expected in (("--memory-ratio", MEMORY_RATIO), ("--kv-reserve-tokens", str(WINDOW)),
                               ("--max-seq-len-override", str(WINDOW))):
            if flag not in value:
                raise RuntimeError(f"R046c missing service argument {flag}")
            value[value.index(flag) + 1] = expected
        return value
    d07.serve_argv = argv
    return d07


def require_predecessors(d07):
    """Read only canonical closure metadata; never rehash predecessor raw data."""
    closures = {}
    for rid, verdict in (("E2-R062-gate-D07", "kept"), ("E2-R059-gate-D07", "kept"), ("E2-R058", "measured"),
                         ("E2-R041-gate-D17", "kept"), ("E2-R046e", "failed_harness")):
        closures[rid] = d07.require_closed_round(rid, verdict)
    return closures


def seed_paths(root: Path = ROOT / "wt/e1r003") -> dict[str, Path]:
    paths = {role: root / f"{role}.txt" for role in SEEDS}
    for role, path in paths.items():
        if path.is_symlink() or not path.is_file() or sha(path) != SEEDS[role]:
            raise RuntimeError(f"R046c seed raw bytes differ: {role}")
    return paths


def require_native_provenance(worktree=WT):
 proof,proof_sha=NATIVE_PROVENANCE,NATIVE_PROVENANCE_SHA256
 proof,worktree=Path(proof),Path(worktree)
 if proof.is_symlink() or not proof.is_file() or proof.stat().st_mode&0o222 or sha(proof)!=proof_sha: raise RuntimeError('R046e native proof differs')
 value=json.loads(proof.read_text())
 if value.get('schema')!='ft_r062_native_provenance/v1' or value.get('candidate_commit')!=CANDIDATE or value.get('parent_commit')!='151ee718b88882b57dba75317bb53c697d5f235f' or value.get('kernel_source_diff_empty') is not True: raise RuntimeError('R046e native identity differs')
 native={}
 for name,row in value.get('native',{}).items():
  path=Path(row.get('candidate_path',''))
  if path.parent!=worktree/'python/freetoken/kernel' or path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222 or not row.get('candidate_regular_copy') or sha(path)!=row.get('sha256') or path.stat().st_size!=row.get('size'): raise RuntimeError('R046e native artifact differs: '+name)
  native[name]={'path':str(path),'sha256':row['sha256'],'size':row['size'],'regular_copy':True}
 if set(native)!={'_cpu_moe','_pinned_tensor'}: raise RuntimeError('R046e native module set differs')
 return {'path':str(proof),'sha256':proof_sha,'native':native}


def packet(worktree: Path = WT) -> dict:
    d07 = apply_window(load_d07())
    candidate = d07.checked_worktree(worktree)
    if candidate.get("commit") != CANDIDATE:
        raise RuntimeError("R046c candidate worktree commit differs")
    native = require_native_provenance(worktree)
    return {
        "schema": "ft_r046c_d07_t06_prepare/v1", "rid": RID, "candidate_commit": CANDIDATE,
        "candidate": candidate, "window": window_contract(), "memory_ratio": MEMORY_RATIO,
        "seeds": [{"role": role, "path": str(path), "raw_sha256": SEEDS[role]} for role, path in seed_paths().items()],
        "g3": {"preserved": require_preserved_g3(d07), "GPU_rerun": False},
        "g4": {"route_uid_source": "ordinary_v3 UserMsg and DetokenizeMsg sidecars", "new_token_source": "ordinary_v3 token sidecar"},
        "t06": {"arms": ["G_seed12k", "G_seed_45k", "G_seed_real", "G_two"],
                "d15_training_route": "G_seed12k/route", "heldout_routes": ["G_seed_45k/route", "G_seed_real/route", "G_two/route"],
                "pause_endpoint": False, "ordinary_client": str(CLIENT_V3), "startup_wrapper": str(STARTUP_V3),
                "ordinary_route_analyzer": str(ROUTE_ANALYZER)},
        "native_provenance": native,
        "source_sha256": {path.name: sha(path) for path in (D07_SOURCE, STARTUP_V3, MEMORY_STARTUP, MEMORY_OBSERVER, CLIENT_V3, CLIENT_V2, SESSION_DRIVER, SEED_CLIENT, ROUTE_ANALYZER, PORT_SOURCE, ARGS_PARSER)},
        "prior_history": {"E2-R040": "failed_harness metadata retained; not a R046c startup gate"},
        "run_requires": ["E2-R062-gate-D07 kept", "E2-R059-gate-D07 kept", "E2-R058 measured", "E2-R041-gate-D17 kept", "E2-R046e failed_harness with accepted G3 pair",
                         "explicit --run", "R startup review", "GPU idle", "atomic owned lock"],
        "timing": "excluded from performance claims",
    }


def _ordinary_environment(d07, worktree: Path, trace_dir: Path | None) -> dict:
    env = d07.clean_environment(worktree, trace_dir=trace_dir)
    # D07's historic trace helper enables pause too.  R046c owns the only
    # permitted divergence: trace is a single variable and pause is absent.
    env.pop("FT_DEV_PAUSE_ENDPOINT", None)
    if bool(env.get("FT_DEV_ROUTE_TRACE")) != (trace_dir is not None):
        raise RuntimeError("R046c trace environment differs")
    if "FT_DEV_PAUSE_ENDPOINT" in env:
        raise RuntimeError("R046c must keep pause endpoint disabled")
    return env


def load_port_pair(source: Path = PORT_SOURCE):
    if source.is_symlink() or not source.is_file():
        raise RuntimeError("R046c port-pair source unavailable")
    spec = importlib.util.spec_from_file_location("r046c_port_pair", source)
    module = importlib.util.module_from_spec(spec); assert spec.loader
    spec.loader.exec_module(module)
    return module


def private_port_pair() -> tuple[int, dict]:
    module = load_port_pair(); port = module.dynamic_port(); receipt = module.port_receipt(port)
    if receipt.get("api") != port or receipt.get("tcpstore") != port + 1 or {port, port + 1} & {8095, 8099}:
        raise RuntimeError("R046c private API/TCPStore port pair differs")
    return port, receipt


def require_memory_evidence(directory: Path) -> dict:
    """Fail closed unless the model worker sampled load plus each request boundary."""
    path = directory / "model_process_cuda.jsonl"
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("R046c model-process memory evidence is missing")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    loaded = [row for row in rows if row.get("schema") == "ft_r056_model_memory/v1" and row.get("event") == "model_loaded"]
    before = [row for row in rows if row.get("event") == "request_before"]
    after = [row for row in rows if row.get("event") == "request_after"]
    if len(loaded) != 1 or not before or {row.get("uid") for row in before} != {row.get("uid") for row in after}:
        raise RuntimeError("R046c memory observer lacks load/request-before/request-after coverage")
    birth, service_birth = loaded[0].get("worker_birth"), loaded[0].get("service_birth")
    def normalized(value):
        if not isinstance(value, dict): return None
        keys = ("pid", "start_ticks", "execution_id", "pgid", "session")
        return {key: value.get(key) for key in keys}
    owned_path = directory / "owned_process.json"
    if owned_path.is_symlink() or not owned_path.is_file():
        raise RuntimeError("R046c memory observer lacks owned service identity")
    owned_birth = json.loads(owned_path.read_text(encoding="utf-8")).get("birth")
    if (normalized(service_birth) != normalized(owned_birth)
            or not isinstance(birth, dict)
            or any(row.get("worker_birth") != birth or row.get("service_birth") != service_birth or row.get("device") != 0 for row in rows)):
        raise RuntimeError("R046c memory observer service/worker/device binding differs")
    observer = directory / "ordinary_observer" / "inputs.jsonl"
    if observer.is_symlink() or not observer.is_file():
        raise RuntimeError("R046c ordinary observer lacks worker input receipt")
    ordinary_rows = [json.loads(line) for line in observer.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not ordinary_rows or any(normalized(row.get("service_birth")) != normalized(service_birth)
                                or normalized(row.get("worker_birth")) != normalized(birth) for row in ordinary_rows):
        raise RuntimeError("R046c ordinary/memory observer birth binding differs")
    for first in before:
        ending = next(row for row in after if row.get("uid") == first.get("uid"))
        if type(first.get("time_ns")) is not int or type(ending.get("time_ns")) is not int or first["time_ns"] >= ending["time_ns"]:
            raise RuntimeError("R046c memory observer request ordering differs")
    summary = {"schema": "ft_r046c_model_memory_summary/v1", "complete": True,
               "worker_birth": birth, "events": rows, "model_memory_sha256": sha(path)}
    write_new(directory / "model_memory_summary.json", summary)
    return summary


def service_files(d07, directory: Path, worktree: Path, port: int, trace_dir: Path | None, *, ordinary_v3: bool) -> dict:
    env = _ordinary_environment(d07, worktree, trace_dir)
    argv = d07.serve_argv(port)
    if ordinary_v3:
        if any(path.is_symlink() or not path.is_file() for path in (STARTUP_V3, MEMORY_STARTUP, MEMORY_OBSERVER)):
            raise RuntimeError("R046c ordinary/memory startup source is unavailable")
        observer = directory / "ordinary_observer"
        observer.mkdir(parents=True, exist_ok=True)
        # v3 binds each ordinary request to the scheduler's D0 prefill record.
        # This is UID evidence, not a performance measurement switch.
        env.update(FT_DEV_D0="1", FT_DEV_D0_PATH=str(directory / "d0"),
                   R056_MODEL_MEMORY=str(directory / "model_process_cuda.jsonl"), R056_OBSERVE_REQUESTS="1")
        argv = [str(VENV / "bin/python"), str(MEMORY_STARTUP), "--observer-dir", str(observer), "--", *argv[1:]]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ENV.json").write_text(json.dumps({key: env[key] for key in sorted(env) if key.startswith("FT_") or key in {"CUDA_VISIBLE_DEVICES", "PYTHONPATH", "VIRTUAL_ENV"}}, sort_keys=True) + "\n", encoding="utf-8")
    (directory / "SERVE_CMD.txt").write_text(json.dumps(argv) + "\n", encoding="utf-8")
    expected = {flag.removeprefix("--").replace("-", "_"): argv[argv.index(flag) + 1]
                for flag in ("--memory-ratio", "--kv-reserve-tokens", "--max-seq-len-override", "--mamba-host-slots")}
    write_new(directory / "serve_args_expected.json", {"schema": "ft_r046c_serve_args_expected/v1", "expected": expected,
              "trace": str(trace_dir) if trace_dir is not None else None, "pause_endpoint": False,
              "d0": True, "d0_path": str(directory / "d0"), "actual_parsed_args_required_after_health": True})
    (directory / "serve.log").open("x", encoding="utf-8").close()
    return {"env": env, "argv": argv, "observer": directory / "ordinary_observer"}


def write_actual_args(directory: Path) -> dict:
    if ARGS_PARSER.is_symlink() or not ARGS_PARSER.is_file():
        raise RuntimeError("R046c parsed-args source unavailable")
    parser = runpy.run_path(str(ARGS_PARSER)).get("parse")
    if not callable(parser):
        raise RuntimeError("R046c parsed-args parser differs")
    parsed = parser(str(directory / "serve.log"))
    expected = json.loads((directory / "serve_args_expected.json").read_text())["expected"]
    if any(str(parsed.get(key)) != value for key, value in expected.items()):
        raise RuntimeError("R046c actual parsed server arguments differ")
    write_new(directory / "serve_args_actual.json", {"schema": "ft_r046c_serve_args_actual/v1", "parsed": parsed})
    (directory / "serve_args.txt").write_text(json.dumps(parsed, sort_keys=True) + "\n", encoding="utf-8")
    return parsed


def write_g3_args_diff(off: Path, on: Path) -> dict:
    left = json.loads((off / "serve_args_actual.json").read_text())["parsed"]
    right = json.loads((on / "serve_args_actual.json").read_text())["parsed"]
    differences = {key: [left.get(key), right.get(key)] for key in left.keys() | right.keys() if left.get(key) != right.get(key)}
    if set(differences) - {"_unique_suffix"}:
        raise RuntimeError("R046c G3 parsed server args differ beyond PID")
    left_env, right_env = json.loads((off / "ENV.json").read_text()), json.loads((on / "ENV.json").read_text())
    raw_env_differences = {key: [left_env.get(key), right_env.get(key)] for key in left_env.keys() | right_env.keys() if left_env.get(key) != right_env.get(key)}
    expected_raw = {"FT_DEV_ROUTE_TRACE": [None, str(on / "route")],
                    "FT_DEV_D0_PATH": [str(off / "d0"), str(on / "d0")]}
    if raw_env_differences != expected_raw:
        raise RuntimeError("R046c G3 environment differs beyond trace and per-arm D0 output")
    normalized_left, normalized_right = dict(left_env), dict(right_env)
    normalized_left["FT_DEV_D0_PATH"] = normalized_right["FT_DEV_D0_PATH"] = "<per-arm>/d0"
    normalized_differences = {key: [normalized_left.get(key), normalized_right.get(key)]
                              for key in normalized_left.keys() | normalized_right.keys()
                              if normalized_left.get(key) != normalized_right.get(key)}
    if normalized_differences != {"FT_DEV_ROUTE_TRACE": [None, str(on / "route")]}:
        raise RuntimeError("R046c G3 normalized environment differs beyond route trace")
    value = {"schema": "ft_r046c_g3_serve_args_diff/v1", "parsed_differences": differences,
             "raw_environment_differences": raw_env_differences,
             "normalized_environment_differences": normalized_differences,
             "declared_output_path_differences": {"FT_DEV_D0_PATH": "per-arm D0 output path"},
             "pause_endpoint": False, "d0": True,
             "memory_ratio": MEMORY_RATIO, "window": window_contract()}
    write_new(on.parent / "g3_serve_args_diff.json", value)
    return value


def require_ordinary_session_driver() -> None:
    """Do not silently fall back to the frozen ft_dev-ACK agent client."""
    for path in (CLIENT_V3, CLIENT_V2, STARTUP_V3, MEMORY_STARTUP, MEMORY_OBSERVER, SESSION_DRIVER, SEED_CLIENT, ROUTE_ANALYZER, PORT_SOURCE):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("R046c ordinary session source unavailable: " + str(path))


def _ordinary_driver_args(worktree: Path, directory: Path, port: int, route: Path) -> list[str]:
    require_ordinary_session_driver()
    return [str(VENV / "bin/python"), str(SESSION_DRIVER), "--client", str(CLIENT_V3),
            "--original", str(worktree / "scripts/_agent_trace_original.py"), "--worktree", str(worktree),
            "--tokenizer-path", str(ROOT / "models/Qwen3.8-Flash-Next-NVFP4-overlay"), "--tool-root", str(worktree),
            "--base-url", f"http://127.0.0.1:{port}/v1", "--directory", str(directory), "--d0", str(directory / "d0_prefill.jsonl"),
            "--route", str(route), "--inputs", str(directory / "ordinary_observer/inputs.jsonl"),
            "--tokens", str(directory / "ordinary_observer/tokens.jsonl"), "--model", "Qwen3.8-Flash-Next-NVFP4"]


def invoke_seed_session(worktree: Path, port: int, role: str, seed: Path, directory: Path, route: Path) -> Path:
    if role not in SEEDS: raise RuntimeError("R046c seed role differs")
    out = directory / f"trace_{role}.json"
    command = [*_ordinary_driver_args(worktree, directory, port, route), "--generate", "--seed-file", str(seed),
               "--seed-sha256", SEEDS[role], "--out", str(out)]
    subprocess.run(command, cwd=worktree, env=_ordinary_environment(apply_window(load_d07()), worktree, route), check=True)
    value = json.loads(out.read_text(encoding="utf-8")); meta = value.get("meta", {})
    if (value.get("schema") != "ft_r046c_ordinary_seed_trace/v1" or meta.get("seed_raw_sha256") != SEEDS[role]
            or meta.get("completed_k", 0) < 1 or meta.get("completed_k", 0) > 12
            or meta.get("window") != WINDOW or meta.get("completion_reserve_tokens") != COMPLETION_RESERVE):
        raise RuntimeError("R046c seed ordinary session result differs")
    return out


def invoke_two_session(worktree: Path, port: int, directory: Path, route: Path) -> Path:
    out = directory / "two_decode.json"
    subprocess.run([*_ordinary_driver_args(worktree, directory, port, route), "--two", "--out", str(out)],
                   cwd=worktree, env=_ordinary_environment(apply_window(load_d07()), worktree, route), check=True)
    value = json.loads(out.read_text(encoding="utf-8"))
    if value.get("schema") != "ft_r046c_ordinary_two_decode/v1" or value.get("same_prompt") is not False or value.get("parallel") is not True:
        raise RuntimeError("R046c ordinary two-decode result differs")
    return out


def invoke_ordinary_analysis(worktree: Path, route: Path, trace: Path, serve_log: Path, output: Path) -> dict:
    if ROUTE_ANALYZER.is_symlink() or not ROUTE_ANALYZER.is_file():
        raise RuntimeError("R046c ordinary route analyzer is unavailable")
    subprocess.run([str(VENV / "bin/python"), str(ROUTE_ANALYZER), str(route), "--ordinary-traces", str(trace),
                    "--serve-log", str(serve_log), "--out", str(output)],
                   cwd=worktree, env=_ordinary_environment(apply_window(load_d07()), worktree, route), check=True)
    value = json.loads(output.read_text(encoding="utf-8"))
    if value.get("analysis_scope") != "ordinary_worker_token_bound_requests" or value.get("ordinary_worker_token_bound") is not True:
        raise RuntimeError("R046c ordinary route analysis differs")
    return value


def manifest(run: Path, g3g4: dict, arms: list[dict], owner: dict) -> dict:
    validate_reused_g3(g3g4)
    roles = [arm.get("role") for arm in arms]
    if roles != ["seed12k", "seed_45k", "seed_real", "two"]:
        raise RuntimeError("R046c manifest arm order differs")
    for arm in arms:
        role = arm["role"]
        if role in SEEDS:
            if arm.get("directory") != f"G_{role}" or arm.get("kind") != "generate" or arm.get("rounds") != 12 or arm.get("max_tokens") != 2048 or arm.get("seed_raw_sha256") != SEEDS[role]:
                raise RuntimeError("R046c seed manifest arm differs")
            arm["d15_training_input"] = role == "seed12k"
        elif arm.get("directory") != "G_two" or arm.get("kind") != "two-decode" or arm.get("same_prompt") is not False or arm.get("ctx") != 8000 or arm.get("max_tokens") != 256:
            raise RuntimeError("R046c two-decode manifest arm differs")
        else:
            arm["d15_training_input"] = False
    return {"schema": "ft_r046c_route_manifest/v1", "rid": RID, "candidate_commit": CANDIDATE,
            "memory_ratio": MEMORY_RATIO, "window": window_contract(), "service": {"gpu_owner": owner},
            "g3g4": g3g4, "arms": arms, "d15_training_route": "G_seed12k/route",
            "heldout_routes": ["G_seed_45k/route", "G_seed_real/route", "G_two/route"],
            "timing": "excluded; trace disables CUDA graph only in trace-on services"}


def validate_manifest(path: Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if (value.get("schema"), value.get("rid"), value.get("candidate_commit"), value.get("memory_ratio"), value.get("window")) != ("ft_r046c_route_manifest/v1", RID, CANDIDATE, MEMORY_RATIO, window_contract()):
        raise RuntimeError("R046c manifest identity differs")
    validate_reused_g3(value.get("g3g4", {}))
    expected = {"seed12k": ("G_seed12k", True), "seed_45k": ("G_seed_45k", False), "seed_real": ("G_seed_real", False), "two": ("G_two", False)}
    arms = value.get("arms")
    if not isinstance(arms, list) or len(arms) != 4:
        raise RuntimeError("R046c manifest arms differ")
    for arm in arms:
        expected_arm = expected.get(arm.get("role"))
        if expected_arm is None or (arm.get("directory"), arm.get("d15_training_input")) != expected_arm:
            raise RuntimeError("R046c manifest train/heldout binding differs")
    if value.get("d15_training_route") != "G_seed12k/route" or value.get("heldout_routes") != ["G_seed_45k/route", "G_seed_real/route", "G_two/route"]:
        raise RuntimeError("R046c manifest train/heldout route differs")
    return value


def copy_execution_sources(target: Path, worktree: Path) -> dict:
    """Exercise the future package's writable copies and bind each byte source."""
    runtime, inputs = target / "runtime_sources", target / "input_sources"
    runtime.mkdir(); inputs.mkdir(); records = {}
    sources = [(Path(__file__), Path(__file__).name), (D07_SOURCE, D07_SOURCE.name), (STARTUP_V3, STARTUP_V3.name),
               (MEMORY_STARTUP, MEMORY_STARTUP.name), (MEMORY_OBSERVER, MEMORY_OBSERVER.name),
               (CLIENT_V3, CLIENT_V3.name), (CLIENT_V2, CLIENT_V2.name), (SESSION_DRIVER, SESSION_DRIVER.name),
               (SEED_CLIENT, SEED_CLIENT.name), (ROUTE_ANALYZER, ROUTE_ANALYZER.name), (PORT_SOURCE, PORT_SOURCE.name),
               (ARGS_PARSER, Path("d04_original") / ARGS_PARSER.name),
               (worktree / "scripts/_agent_trace_original.py", Path("candidate/scripts/_agent_trace_original.py")),
               *((worktree / relative, Path("candidate") / relative) for relative in NATIVE_SOURCE_RELATIVE)]
    for source, relative in sources:
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f"R046c file-dry source unavailable: {source}")
        target_path = runtime / relative; target_path.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target_path); target_path.chmod(0o600)
        if target_path.stat().st_mode & 0o222 == 0:
            raise RuntimeError("R046c file-dry copy inherited readonly mode")
        records[str(source)] = {"copy": str(target_path), "sha256": sha(target_path), "md5": md5(target_path),
                                "mode": oct(target_path.stat().st_mode & 0o777)}
    for role, source in seed_paths().items():
        target_path = inputs / f"{role}.txt"; shutil.copy2(source, target_path); target_path.chmod(0o600)
        if sha(target_path) != SEEDS[role] or target_path.stat().st_mode & 0o222 == 0:
            raise RuntimeError("R046c file-dry seed copy differs or is readonly")
        records[str(source)] = {"copy": str(target_path), "sha256": sha(target_path), "md5": md5(target_path),
                                "mode": oct(target_path.stat().st_mode & 0o777)}
    return records


# Keep the v1 file-dry callsite name while both paths use the same byte-copy
# contract.  Formal execution must never reintroduce copy2's readonly mode.
def copy_filedry_sources(target: Path, worktree: Path) -> dict:
    return copy_execution_sources(target, worktree)


def foreign_lock_snapshot(lock: Path) -> dict:
    """Prove a dry run neither consumes nor mutates another owner's lock."""
    lock = Path(lock)
    if lock.is_symlink():
        raise RuntimeError("R046c file-dry foreign lock is a symlink")
    if not lock.exists():
        return {"state": "absent"}
    if not lock.is_file():
        raise RuntimeError("R046c file-dry foreign lock is not a regular file")
    stat = lock.stat()
    return {"state": "present", "inode": stat.st_ino, "bytes_sha256": sha(lock), "size": stat.st_size}


def require_foreign_lock_unchanged(before: dict, after: dict) -> None:
    if before != after:
        raise RuntimeError("R046c file-dry changed foreign GPU lock evidence")


def file_dry_run(worktree: Path = WT, output_root: Path = ROUNDS) -> dict:
    if sys.platform != "linux":
        raise RuntimeError("R046c --dry-run requires Linux")
    d07 = apply_window(load_d07())
    foreign_before = foreign_lock_snapshot(d07.LOCK)
    admission = packet(worktree); closures = require_predecessors(d07)
    target = output_root / f".filedry_{RID}"
    if target.exists():
        raise RuntimeError("R046c dry-run directory already exists")
    target.mkdir(mode=0o700)
    source_copies = copy_filedry_sources(target, worktree)
    port, pair = private_port_pair()
    services = []
    for name, trace, ordinary in (("G_seed12k", target / "G_seed12k/route", True), ("G_seed_45k", target / "G_seed_45k/route", True),
                                  ("G_seed_real", target / "G_seed_real/route", True), ("G_two", target / "G_two/route", True)):
        prepared = service_files(d07, target / ("g3g4/" + name if name.startswith("g3_") else name), worktree, port, trace, ordinary_v3=ordinary)
        if ordinary:
            probe = prepared["observer"] / "filedry_writable_probe.json"
            write_new(probe, {"schema": "ft_r046c_filedry_writable_probe/v1", "arm": name})
        services.append({"name": name, "port": port, "port_pair": pair, "argv": prepared["argv"], "pause_endpoint": "FT_DEV_PAUSE_ENDPOINT" in prepared["env"], "trace": trace is not None})
    foreign_after = foreign_lock_snapshot(d07.LOCK)
    require_foreign_lock_unchanged(foreign_before, foreign_after)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    receipt = {"schema": "ft_r046c_file_dry/v1", "rid": RID, "candidate_commit": CANDIDATE, "passed": True,
               "formal_rid_directory_created": False, "service_started": False, "requests_sent": False, "gpu_lock_taken": False, "batch_allocated": False,
               "identity": {"time": now, "uid": getattr(os, "getuid", lambda: None)(), "user": getpass.getuser(),
                            "cwd": str(Path.cwd().resolve()), "script": str(Path(__file__).resolve())},
               "port_pair": pair, "foreign_lock_before": foreign_before, "foreign_lock_after": foreign_after,
               "packet_sha256": hashlib.sha256(json.dumps(admission, sort_keys=True).encode()).hexdigest(), "closures": {rid: str(path) for rid, path in closures.items()}, "services": services,
               "runtime_input_copies": source_copies}
    write_new(target / "dry_run_receipt.json", receipt)
    return {**receipt, "path": str(target / "dry_run_receipt.json"), "sha256": sha(target / "dry_run_receipt.json")}


def child_argv(batch: int, receipt: Path, worktree: Path, output_root: Path) -> list[str]:
    return [str(VENV / "bin/python"), str(Path(__file__).resolve()), "--run", "--owned-child",
            "--batch", str(batch), "--launch-receipt", str(receipt), "--worktree", str(worktree),
            "--output-root", str(output_root)]


def require_receipt(path: Path, batch: int, worktree: Path, output_root: Path):
    return load_d07().require_child_receipt(path, batch, worktree, output_root, rid=RID,
        expected_argv=child_argv(batch, path, worktree, output_root), schema="ft_r046c_owned_launch/v1")


REVIEW_DIR = ROOT / "runs/dev_R046/reviews/E2-R046f-v1"


def require_startup_review() -> dict:
    """Read an independently sealed source-review; this never creates approval."""
    review, pin = REVIEW_DIR / "review.json", REVIEW_DIR / "pin.json"
    for path in (REVIEW_DIR, review, pin):
        if path.is_symlink() or not path.exists() or path.stat().st_mode & 0o222:
            raise RuntimeError("R046c startup review/pin absent, writable, or symlinked")
    binding, document = json.loads(pin.read_text()), json.loads(review.read_text())
    if (binding.get("schema") != "ft_r046c_review_pin/v1" or binding.get("rid") != RID
            or binding.get("review_sha256") != sha(review)
            or document.get("schema") != "ft_r046c_source_startup_review/v1"
            or document.get("rid") != RID or document.get("verdict") != "PASS"
            or document.get("source_execution_ready") is not True
            or document.get("candidate_commit") != CANDIDATE):
        raise RuntimeError("R046c startup review identity differs")
    expected = {str(path): sha(path) for path in (Path(__file__).resolve(), D07_SOURCE, STARTUP_V3, MEMORY_STARTUP,
                MEMORY_OBSERVER, CLIENT_V3, CLIENT_V2, SESSION_DRIVER, SEED_CLIENT, ROUTE_ANALYZER, PORT_SOURCE, ARGS_PARSER)}
    if document.get("sources") != expected:
        raise RuntimeError("R046c startup review source binding differs")
    dry = Path(document.get("file_dry_receipt", ""))
    if (not dry.is_absolute() or dry.is_symlink() or not dry.is_file() or dry.stat().st_mode & 0o222
            or document.get("file_dry_receipt_sha256") != sha(dry)
            or binding.get("file_dry_receipt_sha256") != sha(dry)):
        raise RuntimeError("R046c startup review file-dry binding differs")
    dry_value = json.loads(dry.read_text(encoding="utf-8"))
    copies = dry_value.get("runtime_input_copies")
    required_seed_hashes = set(SEEDS.values())
    if (dry_value.get("schema") != "ft_r046c_file_dry/v1" or dry_value.get("rid") != RID
            or dry_value.get("candidate_commit") != CANDIDATE or dry_value.get("passed") is not True
            or not isinstance(copies, dict) or not required_seed_hashes <= {row.get("sha256") for row in copies.values() if isinstance(row, dict)}
            or not all(str(WT / relative) in copies for relative in NATIVE_SOURCE_RELATIVE)):
        raise RuntimeError("R046c startup review lacks bound dry source/native/seed inputs")
    return {"path": str(review), "sha256": sha(review), "pin_sha256": sha(pin)}


def require_output_root(worktree: Path, output_root: Path) -> None:
    if worktree != WT or output_root != ROUNDS:
        raise RuntimeError("R046c requires canonical worktree and output root")
    for path in (worktree, output_root):
        if ".." in path.parts or any(item.is_symlink() for item in (path, *path.parents)):
            raise RuntimeError("R046c canonical path is symlinked")


def _stop_service(d07, process) -> None:
    if process is None:
        return
    try:
        d07.load_owned_lifecycle().stop_owned_process(process)
    except BaseException as error:
        error.owned_process, error.owned_cleanup_failed = process, True
        raise


def start_service(d07, directory: Path, worktree: Path, port: int, trace_dir: Path | None, *, ordinary_v3: bool):
    """Start one private-PGID service using this round's wrapper and arguments."""
    prepared = service_files(d07, directory, worktree, port, trace_dir, ordinary_v3=ordinary_v3)
    log = (directory / "serve.log").open("a", encoding="utf-8")
    process = subprocess.Popen(prepared["argv"], cwd=worktree, env=prepared["env"], stdout=log,
                               stderr=subprocess.STDOUT, start_new_session=True)
    try:
        birth = d07.load_owned_lifecycle().process_identity(process.pid)
        if birth is None or birth.get("pgid") != process.pid or birth.get("session") != process.pid:
            raise RuntimeError("R046c service lacks a private process group/session")
        write_new(directory / "owned_process.json", {"pid": process.pid, "pgid": process.pid, "port": port, "birth": birth})
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"R046c service exited during startup: {process.returncode}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as response:
                    health = json.load(response)
                if health.get("status") == "ok":
                    write_new(directory / "health.json", health)
                    write_actual_args(directory)
                    return process
            except (OSError, ValueError):
                pass
            time.sleep(2)
        raise TimeoutError("R046c owned service did not become healthy")
    except BaseException:
        try:
            _stop_service(d07, process)
        except BaseException:
            raise
        raise
    finally:
        log.close()


PRESERVED_G3_RID = "E2-R046e"
PRESERVED_G3_REVIEW_SHA256 = "c87227a64bc879c264f800517f355ef7ee3816c869555dd534e8f3fba3134bf6"


def validate_reused_g3(g3g4: dict) -> None:
    reused = g3g4.get("reused_g3", {})
    if (reused.get("rid") != PRESERVED_G3_RID or reused.get("candidate_commit") != CANDIDATE
            or reused.get("independent_review_sha256") != PRESERVED_G3_REVIEW_SHA256
            or reused.get("GPU_rerun") is not False or reused.get("window") != WINDOW
            or reused.get("memory_ratio") != MEMORY_RATIO or reused.get("pause_enabled") is not False):
        raise RuntimeError("R046f manifest lacks accepted same-configuration G3 binding")


def require_preserved_g3(d07) -> dict:
    """Use sealed R/D04 metadata; do not reopen predecessor raw measurements."""
    run = d07.require_closed_round(PRESERVED_G3_RID, "failed_harness")
    canonical = run / "round.json"
    doc = json.loads(canonical.read_text(encoding="utf-8"))
    review = run / "metadata/independent_failed_review.json"
    if (review.is_symlink() or not review.is_file() or review.stat().st_mode & 0o222
            or sha(review) != PRESERVED_G3_REVIEW_SHA256
            or doc.get("completed_arms") != ["G3-off", "G3-on"]
            or doc.get("base", {}).get("commit") != CANDIDATE
            or doc.get("serve") != {"window": WINDOW, "memory_ratio": float(MEMORY_RATIO), "G3_pause": False}):
        raise RuntimeError("R046f preserved G3 closure/configuration differs")
    accepted = json.loads(review.read_text(encoding="utf-8"))
    pair = accepted.get("g3_recomputation", {})
    arms = pair.get("arms", [])
    if (accepted.get("rid") != PRESERVED_G3_RID or accepted.get("verdict") != "failed_harness"
            or accepted.get("candidate_commit") != CANDIDATE
            or pair.get("full_text_equal") is not True or pair.get("d0_h2d_d2d_equal") is not True
            or not pair.get("record_contract_equal") or not all(v is True for v in pair["record_contract_equal"].values())
            or [row.get("arm") for row in arms] != ["g3_off", "g3_on"]
            or [row.get("route_directory_exists") for row in arms] != [False, True]
            or any(row.get("record", {}).get("prompt_tokens") != 32064
                   or row.get("record", {}).get("completion_tokens") != 128
                   or row.get("record", {}).get("finish_reason") != "length" for row in arms)
            or not arms[0].get("text_sha256") or arms[0].get("text_sha256") != arms[1].get("text_sha256")):
        raise RuntimeError("R046f preserved G3 independent acceptance differs")
    return {"directory": str(run / "g3g4"),
            "g3": {"same_cold_id": True, "text_utf8_sha256": arms[0]["text_sha256"], "byte_identical": True},
            "reused_g3": {"rid": PRESERVED_G3_RID, "candidate_commit": CANDIDATE,
                         "round_sha256": sha(canonical), "manifest_sha256": sha(run / "MANIFEST.sha256"),
                         "independent_review_sha256": sha(review), "GPU_rerun": False,
                         "window": WINDOW, "memory_ratio": MEMORY_RATIO, "pause_enabled": False}}


def _arm_record(role: str, directory: Path, trace_or_result: Path, summary: Path) -> dict:
    if role in SEEDS:
        return {"role": role, "directory": directory.name, "kind": "generate", "rounds": 12,
                "max_tokens": 2048, "seed_raw_sha256": SEEDS[role], "trace": trace_or_result.name,
                "trace_sha256": sha(trace_or_result), "route_summary": summary.name,
                "route_summary_sha256": sha(summary), "serve_log": "serve.log", "serve_log_sha256": sha(directory / "serve.log")}
    return {"role": "two", "directory": directory.name, "kind": "two-decode", "same_prompt": False,
            "ctx": 8000, "max_tokens": 256, "result": trace_or_result.name, "sha256": sha(trace_or_result),
            "route_summary": summary.name, "route_summary_sha256": sha(summary),
            "serve_log": "serve.log", "serve_log_sha256": sha(directory / "serve.log")}


def run_measurement(d07, worktree: Path, run: Path, owner: dict) -> dict:
    """Keep accepted G3 metadata and run only four remaining ordinary T06 arms."""
    g3g4, arms = require_preserved_g3(d07), []
    for role in (*SEEDS, "two"):
        directory = run / f"G_{role}"; directory.mkdir(); route = directory / "route"; route.mkdir()
        port, process = private_port_pair()[0], None
        try:
            process = start_service(d07, directory, worktree, port, route, ordinary_v3=True)
            if role in SEEDS:
                trace = invoke_seed_session(worktree, port, role, seed_paths()[role], directory, route)
                summary = directory / "route_summary.json"
                invoke_ordinary_analysis(worktree, route, trace, directory / "serve.log", summary)
                require_memory_evidence(directory)
                arms.append(_arm_record(role, directory, trace, summary))
            else:
                result = invoke_two_session(worktree, port, directory, route)
                summary = directory / "route_summary.json"
                if ROUTE_ANALYZER.is_symlink() or not ROUTE_ANALYZER.is_file():
                    raise RuntimeError("R046c ordinary route analyzer is unavailable")
                subprocess.run([str(VENV / "bin/python"), str(ROUTE_ANALYZER), str(route), "--two-decode", str(result),
                                "--serve-log", str(directory / "serve.log"), "--out", str(summary)], cwd=worktree,
                               env=_ordinary_environment(d07, worktree, route), check=True)
                require_memory_evidence(directory)
                arms.append(_arm_record(role, directory, result, summary))
        except BaseException as error:
            error.owned_process = getattr(error, "owned_process", process)
            raise
        finally:
            _stop_service(d07, process)
    seed12_summary = run / "G_seed12k/route_summary.json"
    seed12_analysis = json.loads(seed12_summary.read_text(encoding="utf-8"))
    if (seed12_analysis.get("analysis_scope") != "ordinary_worker_token_bound_requests"
            or not seed12_analysis.get("business_uids") or not seed12_analysis.get("raw_suffix_tokens")):
        raise RuntimeError("R046c G4 lacks worker UID/new-token route evidence")
    g3g4["g4"] = {"route": "G_seed12k/route", "route_summary": "G_seed12k/route_summary.json",
                    "route_summary_sha256": sha(seed12_summary), "business_uids": seed12_analysis["business_uids"],
                    "raw_suffix_tokens": seed12_analysis["raw_suffix_tokens"],
                    "uid_source": "ordinary-v3 UserMsg/DetokenizeMsg"}
    document = manifest(run, g3g4, arms, owner)
    write_new(run / "manifest.json", document); validate_manifest(run / "manifest.json")
    result = {"schema": "ft_r046c_raw_measurement/v1", "round_id": RID, "card": "D07-G3G4+T06",
              "base": {"code_version": "E2-base.1-trace-lm@151ee718", "commit": CANDIDATE},
              "candidate_commit": CANDIDATE, "verdict": "pending_review", "proposed_verdict": "measured",
              "raw_measurement_before_D04": True, "manifest": "manifest.json", "manifest_sha256": sha(run / "manifest.json"),
              "g3g4": g3g4, "timing": "excluded from performance claims"}
    write_new(run / "result.json", result)
    write_new(run / "metadata/pre_d04.json", {"schema": "ft_r046c_pre_d04/v1", "rid": RID,
              "result": "result.json", "result_sha256": sha(run / "result.json"), "verdict": "pending_review",
              "proposed_verdict": "measured", "canonical_round_json_created": False, "canonical_manifest_created": False})
    return result


def execute(worktree: Path = WT, output_root: Path = ROUNDS, *, owned_child: bool = False,
            batch: int | None = None, launch_receipt: Path | None = None) -> dict:
    if sys.platform != "linux":
        raise RuntimeError("R046c --run requires Linux GPU host")
    require_output_root(worktree, output_root)
    d07 = apply_window(load_d07())
    if not owned_child and (d07.LOCK.exists() or d07.LOCK.is_symlink()):
        raise RuntimeError("foreign GPU lock exists; R046c remains queued")
    review, admission, closures = require_startup_review(), packet(worktree), require_predecessors(d07)
    if not owned_child:
        if (output_root / RID).exists():
            raise RuntimeError("R046c round already exists; no overwrite/retry-in-place")
        owned = d07.load_owned_lifecycle()
        helper = owned.verified_module(ROOT / "runs/plan_batches/e2_launch.py", d07.ATOMIC_HELPER_SHA, "r046c_atomic_launcher")
        batch = helper.next_batch(ROUNDS)
        receipt = ROOT / "runs/dev_D07" / f"launch_{RID}_batch{batch}.json"; receipt.parent.mkdir(parents=True, exist_ok=True)
        argv = child_argv(batch, receipt, worktree, output_root)
        reserved = {"schema": "ft_r046c_owned_launch/v1", "state": "reserved", "rid": RID, "batch": batch,
                    "candidate_commit": CANDIDATE, "argv_sha256": d07.argv_sha256(argv), "controller": d07.process_birth()}
        value = owned.reserve_process(helper, batch, RID, argv, receipt, reserved)
        child = owned.process_identity(value["batch_pid"])
        if child is None or child.get("pid") != value["batch_pid"] or type(child.get("start_ticks")) is not int:
            raise RuntimeError("R046c reserved child birth is unavailable")
        child = {"pid": child["pid"], "start_ticks": child["start_ticks"], "execution_id": f"{child['pid']}:{child['start_ticks']}"}
        return d07.publish_child_binding(receipt, value, child, lifecycle=owned)
    if batch is None or launch_receipt is None:
        raise RuntimeError("R046c owned child requires controller receipt and reserved batch")
    d07.require_child_receipt(launch_receipt, batch, worktree, output_root, rid=RID,
                              expected_argv=child_argv(batch, launch_receipt, worktree, output_root), schema="ft_r046c_owned_launch/v1")
    if (output_root / RID).exists():
        raise RuntimeError("R046c round already exists; no overwrite/retry-in-place")
    owner, run, process, cleanup_failed = d07.take_d07_gpu_lock(RID, batch), None, None, False
    try:
        idle = d07.require_gpu_idle(); run = output_root / RID; run.mkdir()
        source_copies = copy_execution_sources(run, worktree)
        write_new(run / "preflight.json", {**admission, "batch": batch, "gpu_owner": owner, "gpu_memory_mib": idle,
                  "startup_review": review, "closures": {rid: str(path) for rid, path in closures.items()},
                  "runtime_input_copies": source_copies})
        return run_measurement(d07, worktree, run, owner)
    except BaseException as error:
        process, cleanup_failed = getattr(error, "owned_process", process), bool(getattr(error, "owned_cleanup_failed", False))
        if run is not None:
            write_new(run / "failed_harness.json", {"rid": RID, "batch": batch, "gpu_owner": owner, "error": repr(error), "raw_measurement_preserved": True})
            if getattr(error, "measurement_not_met", False):
                write_new(run / "result.json", {"schema": "ft_r046c_raw_measurement/v1", "round_id": RID,
                          "candidate_commit": CANDIDATE, "batch": batch, "verdict": "pending_review",
                          "proposed_verdict": "not_met", "reason": repr(error), "raw_measurement_before_D04": True})
        raise
    finally:
        if cleanup_failed:
            if run is not None: write_new(run / "owned_cleanup.json", {"schema": "ft_r046c_owned_cleanup/v1", "rid": RID, "batch": batch, "gpu_owner": owner, "lock_released": False, "cleanup_failed": True})
            raise RuntimeError("R046c cleanup failed; preserve GPU lock for recovery")
        if process is not None:
            _stop_service(d07, process)
        d07.release_d07_gpu_lock(owner)
        if run is not None: write_new(run / "owned_cleanup.json", {"schema": "ft_r046c_owned_cleanup/v1", "rid": RID, "batch": batch, "candidate_commit": CANDIDATE, "gpu_owner": owner, "lock_released": True})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--file-dry-run", "--dry-run", dest="file_dry_run", action="store_true"); parser.add_argument("--run", action="store_true")
    parser.add_argument("--owned-child", action="store_true", help=argparse.SUPPRESS); parser.add_argument("--batch", type=int); parser.add_argument("--launch-receipt", type=Path)
    parser.add_argument("--worktree", type=Path, default=WT); parser.add_argument("--output-root", type=Path, default=ROUNDS)
    options = parser.parse_args(argv)
    if options.file_dry_run and options.run: parser.error("--file-dry-run and --run differ")
    if options.run:
        value = execute(options.worktree, options.output_root, owned_child=options.owned_child, batch=options.batch, launch_receipt=options.launch_receipt)
    else:
        value = file_dry_run(options.worktree, options.output_root) if options.file_dry_run else packet(options.worktree)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
