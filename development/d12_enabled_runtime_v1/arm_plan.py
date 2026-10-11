"""D12 ordinary-capture launch descriptions and CPU native-argument probes.

This module has no service-launch branch. The existing owned lifecycle, a new
approved scope, host observation readiness, and D04 remain caller prerequisites.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

from replay_binding import load_replay_binding
from prompt_tail import validate_d03
from target_model import CONFIG, CONFIG_TARGET, CONFIG_SHA256, MODEL_NAME, SOURCES


CANDIDATE = "8f6a912ea6066f192c37dc74435efc9da0c7591c"
BUNDLE_SHA256 = "282ec437c54b0ba341aac5a0bc31e996ca0d53343d0f48d5b8fa488523ca00e2"
PYTHON = "/data2/FreeToken/venv/bin/python"
ARMS = (("control", True, 0), ("repeat", True, 0),
        ("ordinary_reference", False, 0), ("enabled", True, 256))
D16_SOURCES = {
    "r040a_private_port_owner_v3.py": "a563861d8cb82394ae818a67061ba05b19e7587d0e8f035272e129e75fddd598",
    "t16_private_port_base_runner.py": "76ed60475d3bb86a92ce9a5cf3aa34ca06b5a5297a1ccda9c5312ed6b5b636e9",
    "d16_native_capture_shutdown_v3.py": "9e32df22aa94a9c3faf1116dd32934b065228828451adff76f59e608a7c41795",
    "equiv_suite/__init__.py": "4037f5b3e685ed2c435f915fbeaac99351139378eaeb0d176ed207367ea6b6f2",
    "equiv_suite/service_capture_startup.py": "91102843e3d2b3464b78e7a0431165ab3ca32d488a59e17f8c818f7c2879ee12",
    "equiv_suite/service_capture.py": "aa1beeaa3d3cc2b2434f5fa8d5c8182493a5730606bb5cea50fc86f2b2ed8f60",
    "equiv_suite/sampler_capture.py": "4d509bbcc68a18272af95ab4d738ca8e3e81b30755c964804fb857a46b42b105",
    "ft_batch_port_pair_v1.py": "415c1255ebbba81027c4526acd377f68f87889e31bfb4a58b79053c8abb73a34",
}
# Explicit observation limits, not expected output counts or performance data.
CAPTURES = 8192
CAPTURE_BYTES = 16 * 1024**3
EVENTS = 16384
EVENT_BYTES = 256 * 1024**2
TAIL_HIDDEN_BYTES = 512 * 1024**2


def _require(value, message):
    if not value:
        raise ValueError("D12 arm plan: " + message)


def _raw(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _file(path, digest=None):
    path = Path(path)
    _require(path.is_absolute() and path.resolve() == path and path.is_file(), "physical source required: " + str(path))
    raw = path.read_bytes()
    _require(digest is None or _sha(raw) == digest, "source SHA differs: " + str(path))
    return raw


def _write(path, value):
    with Path(path).open("xb") as output:
        output.write(_raw(value))


def _sources(candidate, runtime, d16, d03, inputs):
    _require(CONFIG.resolve() == CONFIG_TARGET, "model config alias changed")
    _file(CONFIG_TARGET, CONFIG_SHA256)
    paths = [candidate / name for name, digest in SOURCES.items() if _file(candidate / name, digest)]
    paths.append(CONFIG_TARGET)
    paths += [d16 / name for name, digest in D16_SOURCES.items() if _file(d16 / name, digest)]
    paths += validate_d03(d03)
    paths += [p for p in runtime.glob("*.py") if not p.name.startswith(("test_", "native_worker_cpu_fixture"))]
    paths += [p for p in inputs.rglob("*") if p.is_file()]
    return {str(p): _sha(_file(p)) for p in sorted(set(paths))}


def build_plan(*, candidate, runtime, d16, d03, inputs, service_root, execution_prefix, ports):
    """Describe four diagnostic roles; allocate no round, directory, or socket."""
    candidate, runtime, d16, d03, inputs, service_root = map(Path, (candidate, runtime, d16, d03, inputs, service_root))
    for path in (candidate, runtime, d16, d03, inputs, service_root):
        _require(path.is_absolute() and path.resolve() == path, "absolute physical paths required")
    _require(runtime == Path(__file__).resolve().parent, "plan must use this reviewed runtime directory")
    _require(not service_root.exists() and service_root.is_relative_to(Path("/data2/FreeToken/runs/dev_D12")),
             "unused D12 development service root required")
    _require(re.fullmatch(r"d12-[a-z0-9-]{1,80}", execution_prefix) is not None, "D12 proposal execution prefix required")
    _require(len(ports) == 4 and all(type(p) is int and 12000 <= p < 30000 for p in ports)
             and len({x for p in ports for x in (p, p + 1)}) == 8, "four disjoint private port pairs required")
    head = subprocess.check_output(["git", "-C", str(candidate), "rev-parse", "HEAD"], text=True).strip()
    clean = not subprocess.check_output(["git", "-C", str(candidate), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    _require(head == CANDIDATE and clean, "candidate commit or cleanliness differs")
    binding = load_replay_binding(inputs, BUNDLE_SHA256)
    _require([r["uid"] for r in binding["requests"]] == [0, 1, 2]
             and all(r["max_tokens"] == 2048 for r in binding["requests"]), "original three requests required")
    sources = _sources(candidate, runtime, d16, d03, inputs)
    spec = importlib.util.spec_from_file_location("d12_plan_port_rules", d16 / "ft_batch_port_pair_v1.py")
    port_rules = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(port_rules)
    low, high = port_rules.ephemeral_range()
    _require(all(not low <= x <= high for p in ports for x in (p, p + 1)), "planned pair overlaps kernel ephemeral range")
    arms = {}
    for (name, layer_major, threshold), port in zip(ARMS, ports):
        folder = service_root / name
        capture = folder / "dev_D16/capture"
        cli = ["--model-path", str(CONFIG.parent), "--served-model-name", MODEL_NAME,
               "--host", "127.0.0.1", "--port", str(port), "--tp-size", "1", "--gpu", "0", "--dtype", "bfloat16",
               "--memory-ratio", "0.88", "--moe-cache-auto", "--moe-cache-policy", "lru", "--moe-prefill-hit-d2d",
               "--ple-backend", "pinned", "--moe-strategy", "offload", "--quant-backend", "moe.nvfp4=triton",
               "--max-running-requests", "2", "--cuda-graph-max-bs", "2", "--kv-reserve-tokens", "98304",
               "--max-seq-len-override", "98304", "--max-prefill-length", "4096", "--enable-cache-report",
               "--enable-special-token-ckpt", "--tool-call-parser", "qwen3_coder", "--reasoning-parser", "qwen3",
               "--mamba-host-slots", "0", "--disable-moe-prefill-overlap",
               "--moe-prefill-routed-only-max-tokens", str(threshold)]
        if layer_major:
            cli.append("--prefill-layer-major")
        # Construct a small environment rather than inheriting experimental
        # FT/FREETOKEN flags, Python injection paths, or credentials.
        env = {"PATH": "/usr/local/cuda-13.0/bin:/data2/FreeToken/venv/bin:/usr/local/bin:/usr/bin:/bin",
               "LD_LIBRARY_PATH": "/usr/local/cuda-13.0/lib64", "VIRTUAL_ENV": "/data2/FreeToken/venv",
               "HOME": str(Path.home()), "LANG": "C.UTF-8", "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONPATH": ":".join(map(str, (runtime, d16, candidate / "python", candidate / "scripts"))),
               "CUDA_VISIBLE_DEVICES": "0", "FREETOKEN_MAMBA_SSM_DTYPE": "float32",
               "FREETOKEN_DISABLE_OVERLAP_SCHEDULING": "0", "FT_DEV_EXPERT_POLICY": "lru",
               "FT_DEV_EXPERT_ADAPT_EVERY": "0", "FT_DEV_EXPERT_ADAPT_SWAPS": "0",
               "FT_D12_DIAGNOSTIC": "1", "FT_D12_CAPTURE_POLICY": "natural-terminal-v1",
               "FT_D12_REPLAY_INPUT_DIR": str(inputs), "FT_D12_REPLAY_INPUT_SHA256": BUNDLE_SHA256,
               "FT_D12_D0_COVERAGE": "1", "FT_DEV_D0": "1", "FT_DEV_D0_PATH": str(capture / "d12_d0"),
               "FT_D12_PROMPT_TAIL": "1", "FT_D12_D03_ROOT": str(d03), "FT_D12_TAIL_HIDDEN_BYTES": str(TAIL_HIDDEN_BYTES),
               "FT_DEV_STATE_DUMP": str(capture / "d12_state"), "FT_DEV_LOGITS_DUMP": str(capture / "d12_prompt_tail"),
               "FT_D16_SERVICE_CAPTURE_DIR": str(capture), "FT_D16_EXECUTION_ID": execution_prefix + ":" + name,
               "FT_D16_SERVICE_CAPTURE_MAX_CAPTURES": str(CAPTURES), "FT_D16_SERVICE_CAPTURE_MAX_BYTES": str(CAPTURE_BYTES),
               "FT_D12_MAX_EVENTS": str(EVENTS), "FT_D12_MAX_EVENT_BYTES": str(EVENT_BYTES)}
        argv = ["numactl", "--cpunodebind=0,1", "--interleave=all", PYTHON, "-u", str(runtime / "worker_capture.py"), "serve", *cli]
        arms[name] = {"layer_major": layer_major, "threshold": threshold, "port": port, "tcpstore_port": port + 1,
                      "directory": str(folder), "capture": str(capture), "execution_id": env["FT_D16_EXECUTION_ID"],
                      "server_args": cli, "argv": argv, "argv_sha256": _sha(_raw(argv)),
                      "environment": env, "environment_sha256": _sha(_raw(env)), "request_uids": [0, 1, 2]}
    return {"schema": "ft_d12_diagnostic_arm_plan/v1", "scope": "proposal and CPU file dry only",
            "candidate": str(candidate), "candidate_commit": head, "runtime": str(runtime), "d16": str(d16),
            "d03": str(d03), "inputs": str(inputs), "bundle_sha256": BUNDLE_SHA256,
            "service_root": str(service_root), "execution_prefix": execution_prefix, "arms": arms,
            "kernel_ephemeral_range": [low, high], "port_availability_checked": False,
            "source_sha256": sources, "model_config_sha256": CONFIG_SHA256,
            "planned_services": 4, "planned_requests": 12, "approved_new_services": 0,
            "comparisons": {"repeatability": ["control", "repeat"],
                            "legal_reordering_reference": ["control", "ordinary_reference"],
                            "feature": ["control", "enabled"]},
            "functional_rules_frozen": False, "formal_launch_authorized": False,
            "host_proc_observer_ready": False, "output_equivalence_verified": False, "performance_eligible": False,
            "remaining_gates": ["separate default-off R062 acceptance", "functional rules frozen before observations",
                                "owned launch admission and host process observation", "independent terminal review and D04"]}


def validate_plan(plan):
    rebuilt = build_plan(**{key: plan[key] for key in ("candidate", "runtime", "d16", "d03", "inputs", "service_root", "execution_prefix")},
                         ports=[plan["arms"][name]["port"] for name, _, _ in ARMS])
    _require(rebuilt == plan, "plan changed from its declared source and fixed arm contract")


def recheck_bound_sources(plan):
    """Recheck a previously validated immutable plan after output allocation.

    This does not validate a new plan or grant launch authority. The owner must
    retain the original validated plan bytes and separately check its output
    directory identity. No unused-directory rule is relaxed in validate_plan.
    """
    candidate = Path(plan["candidate"])
    head = subprocess.check_output(["git", "-C", str(candidate), "rev-parse", "HEAD"], text=True).strip()
    clean = not subprocess.check_output(["git", "-C", str(candidate), "status", "--porcelain", "--untracked-files=no"], text=True).strip()
    _require(head == plan["candidate_commit"] == CANDIDATE and clean, "bound candidate changed")
    sources = _sources(*(Path(plan[key]) for key in ("candidate", "runtime", "d16", "d03", "inputs")))
    _require(sources == plan["source_sha256"], "bound source set or bytes changed")


def native_probe(plan_path, plan_sha256, name, output):
    """Parse the actual candidate CLI and prepare its worker environment on CPU."""
    plan = json.loads(_file(plan_path, plan_sha256))
    validate_plan(plan)
    _require(Path(output).parent == Path(plan_path).parent, "native probe output must be beside its plan")
    arm = plan["arms"][name]
    expected_env = {**arm["environment"], "CUDA_VISIBLE_DEVICES": ""}
    _require(all(os.environ.get(key) == value for key, value in expected_env.items()), "CPU probe environment differs")
    _require(not any(key.startswith(("FT_", "FREETOKEN_")) and key not in expected_env for key in os.environ),
             "undeclared FreeToken environment flag")
    from worker_capture import prepare_environment
    prepare_environment()
    import torch
    from freetoken.server.args import parse_args
    from target_model import verify_target_model
    from natural_capture import make_policy
    from prompt_tail import load_d03, make_policy as make_tail
    parsed, shell = parse_args(arm["server_args"])
    wanted = {"server_host": "127.0.0.1", "server_port": arm["port"], "served_model_name": MODEL_NAME,
              "model_path": str(CONFIG.parent), "memory_ratio": .88, "moe_cache_auto": True, "moe_cache_policy": "lru",
              "moe_strategy": "offload", "ple_backend": "pinned", "quant_backend": "moe.nvfp4=triton",
              "max_running_req": 2, "cuda_graph_max_bs": 2, "kv_reserve_tokens": 98304, "max_seq_len_override": 98304,
              "max_extend_tokens": 4096, "mamba_host_slots": 0, "moe_prefill_hit_d2d": True, "special_token_ckpt": True,
              "moe_prefill_overlap": False, "prefill_layer_major": arm["layer_major"],
              "moe_prefill_routed_only_max_tokens": arm["threshold"], "enable_cache_report": True,
              "tool_call_parser": "qwen3_coder", "reasoning_parser": "qwen3", "shell_mode": False}
    observed = {key: getattr(parsed, key) for key in wanted}
    _require(observed == wanted and shell is False and parsed.tp_info.size == 1
             and parsed.gpu == ("0",) and parsed.dtype == torch.bfloat16, "native parsed settings differ")
    for module, relative in (("freetoken.server.args", "python/freetoken/server/args.py"),):
        _require(Path(importlib.import_module(module).__file__).resolve() == Path(plan["candidate"]) / relative,
                 "candidate import origin differs")
    for relative in D16_SOURCES:
        module = relative[:-3].replace("/", ".")
        if module.endswith(".__init__"):
            module = module[:-9]
        _require(Path(importlib.import_module(module).__file__).resolve() == Path(plan["d16"]) / relative,
                 "D16 import origin differs")
    geometry = verify_target_model(plan["candidate"], served_model=parsed.served_model_name,
                                  tp_size=parsed.tp_info.size, model_dtype="bfloat16", ssm_dtype="float32")
    binding = load_replay_binding(plan["inputs"], BUNDLE_SHA256)
    natural = make_policy(binding, CAPTURES, CAPTURE_BYTES)
    tail = make_tail(binding, load_d03(plan["d03"]), TAIL_HIDDEN_BYTES)
    _require(not torch.cuda.is_initialized() and not Path(plan["service_root"]).exists(), "CPU probe performed runtime work")
    for path, digest in plan["source_sha256"].items():
        _file(path, digest)
    _file(plan_path, plan_sha256)
    value = {"schema": "ft_d12_arm_native_file_probe/v1", "plan_sha256": plan_sha256, "arm": name,
             "parsed": observed, "parsed_repr": repr(parsed), "target_geometry": geometry,
             "natural_policy": natural, "tail_policy": tail, "cuda_initialized": False,
             "model_service_started": False, "model_requests_sent": False, "formal_launch_authorized": False}
    _write(output, value)
    return value


def file_dry(plan, output):
    """Run each arm through native parsing, never through launch_server."""
    output = Path(output)
    validate_plan(plan)
    _require(output.is_absolute() and output.resolve() == output
             and output.is_relative_to(Path("/data2/FreeToken/runs/dev_D12"))
             and not output.is_relative_to(Path(plan["service_root"])), "independent physical D12 file-dry output required")
    output.mkdir(parents=True, exist_ok=False)
    source = output / "launch-plan.json"
    _write(source, plan)
    digest = _sha(source.read_bytes())
    results = {}
    for name, _, _ in ARMS:
        arm = plan["arms"][name]
        result = output / (name + ".native-probe.json")
        with (output / (name + ".log")).open("x") as log:
            command = [PYTHON, str(Path(plan["runtime"]) / "arm_plan.py"), "--probe-plan", str(source),
                       "--plan-sha256", digest, "--arm", name, "--output", str(result)]
            subprocess.run(command, env={**arm["environment"], "CUDA_VISIBLE_DEVICES": ""},
                           cwd=plan["candidate"], stdout=log, stderr=subprocess.STDOUT, check=True, timeout=90)
        results[name] = {"path": str(result), "sha256": _sha(_file(result))}
    value = {"schema": "ft_d12_arm_file_dry/v1", "plan": {"path": str(source), "sha256": digest},
             "native_probes": results, "model_service_started": False, "model_requests_sent": False,
             "host_proc_observer_ready": False, "formal_launch_authorized": False, "performance_eligible": False}
    _write(output / "file-dry.json", value)
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe-plan", required=True, type=Path)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--arm", required=True, choices=[name for name, _, _ in ARMS])
    parser.add_argument("--output", required=True, type=Path)
    options = parser.parse_args()
    native_probe(options.probe_plan, options.plan_sha256, options.arm, options.output)
