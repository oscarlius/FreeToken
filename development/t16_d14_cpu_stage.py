"""Read-only CPU staging checks required before the D14 T16 launcher can run."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import re
import subprocess
import sys

ROOT = Path("/data2/FreeToken")
ROUNDS = Path("/data2/_shared/runs/ft_rounds")
PARENT = "23f2e2caa3395837c9474735ffc83321f3b9b5a1"
NEW = "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42"
R020_GATE_SHA = "b90f82b9484205ca8bdeba4edb60fb419b43e723d235ee4f6df7afb4532326a0"
R020_BINDING_SHA = "68b26775e03d6079ec0a95de4494d09fce97737824b4edf6ae4f4442dce3f5f5"
ADAPTER_SHA = "0451e41128b4d1e0c73f892b375b9fbe70b30a9fbac46bc022500bd3c1b6d8b8"
BASE_SHA = "379948776d42d5429304afb11dafb0d316e641638caf7cad15fb5b5e6be7340f"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_r020(stage: Path) -> dict:
    root = ROUNDS / "E2-R020-gate-D06"
    gate, binding = root / "gate_batch48.json", root / "candidate_binding.json"
    if sha(gate) != R020_GATE_SHA or sha(binding) != R020_BINDING_SHA:
        raise ValueError("R020 raw evidence differs from its reviewed archival replay")
    data = json.loads(gate.read_text())
    arms = data.get("arms")
    if arms != ["PARENT_b48", "NEW_b48", "PARENT_P_b48", "NEW_P_b48"]:
        raise ValueError("R020 does not retain the four expected arms")
    adapter_path, base_path = stage / "t16_candidate_runner_full_tail.py", stage / "t16_full_tail_base_runner.py"
    if sha(adapter_path) != ADAPTER_SHA or sha(base_path) != BASE_SHA:
        raise ValueError("R020 replay adapter/base differs from reviewed full-tail sources")
    namespace = runpy.run_path(str(adapter_path), run_name="ft_t16_d14_r020_adapter")
    runner = object.__new__(namespace["CandidateRunner"])
    runner.parser = runpy.run_path(str(ROOT / "scripts/serve_args_diff.py"))["parse"]
    paths = [root / arm for arm in arms]
    if any(path.is_symlink() or not path.is_dir() for path in paths):
        raise ValueError("R020 raw arm directories are missing")
    replay = runner.compare(paths[0], paths[1], paths[2], paths[3])
    prefill = replay["prefill"]
    if (prefill["parent_rows"], prefill["new_rows"], prefill["all_prefill_events"]) != (13, 13, 13):
        raise ValueError("R020 raw replay no longer proves complete 13-row prefill")
    if prefill["h2d"] != "SAME":
        raise ValueError("R020 raw replay no longer proves H2D equality")
    result = {"gate_sha256": sha(gate), "binding_sha256": sha(binding), "adapter_sha256": sha(adapter_path),
              "base_sha256": sha(base_path), "arms": arms, "replay": replay}
    (stage / "r020_raw_replay.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def isolated_pytest(wt: Path, test: Path, commit: str):
    site = ROOT / "venv/lib/python3.10/site-packages"
    sources = ["python/freetoken/attention/linear.py", "python/freetoken/engine/engine.py",
               "python/freetoken/models/qwen4_exp/model.py"]
    program = "\n".join([
        "import hashlib,json,pathlib,subprocess,sys",
        f"wt=pathlib.Path({str(wt)!r}); test=pathlib.Path({str(test)!r}); site=pathlib.Path({str(site)!r})",
        "sys.path[:0]=[str(wt/'python'),str(wt),str(site)]",
        "import freetoken,pytest",
        "origin=pathlib.Path(freetoken.__file__).resolve()",
        "assert origin.is_relative_to((wt/'python').resolve()),origin",
        "head=subprocess.check_output(['git','-C',str(wt),'rev-parse','HEAD'],text=True).strip()",
        f"assert head == {commit!r},head",
        f"paths={sources!r}",
        "actual={p:hashlib.sha256((wt/p).read_bytes()).hexdigest() for p in paths}",
        "expected={p:hashlib.sha256(subprocess.check_output(['git','-C',str(wt),'show',head+':'+p])).hexdigest() for p in paths}",
        "assert actual == expected,(actual,expected)",
        "print('FT_D14_BINDING='+json.dumps({'head':head,'freetoken':str(origin),'sources':actual},sort_keys=True))",
        "status=pytest.main(['-q','-p','no:cacheprovider',str(test)])",
        "import torch",
        "assert not torch.cuda.is_initialized(), 'CPU staging initialized CUDA'",
        "sys.exit(status)",
    ])
    compile(program, "<isolated-pytest>", "exec")
    env = os.environ.copy()
    env.update(CUDA_VISIBLE_DEVICES="", PYTHONDONTWRITEBYTECODE="1", OMP_NUM_THREADS="4",
               MKL_NUM_THREADS="4", TOKENIZERS_PARALLELISM="false")
    completed = subprocess.run([str(ROOT / "venv/bin/python"), "-S", "-c", program], cwd=wt, env=env,
                               text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    line = next((item.removeprefix("FT_D14_BINDING=") for item in completed.stdout.splitlines()
                 if item.startswith("FT_D14_BINDING=")), None)
    if line is None:
        raise RuntimeError("isolated CPU runner did not prove import binding\n" + completed.stdout)
    if (completed.returncode == 2 or "ERROR collecting" in completed.stdout
            or "errors during collection" in completed.stdout):
        raise RuntimeError("CPU staging hit collection/import failure\n" + completed.stdout)
    summaries = re.findall(
        r"(?m)^\s*=*\s*(\d+) (failed|passed)(?:, \d+ warnings?)? in \d+(?:\.\d+)?s\s*=*\s*$",
        completed.stdout,
    )
    if len(summaries) != 1:
        raise RuntimeError("CPU staging did not emit a pytest result summary\n" + completed.stdout)
    count, outcome = summaries[0]
    return completed.returncode, json.loads(line), completed.stdout, {
        "count": int(count), "outcome": outcome,
    }


def run(stage: Path) -> None:
    if sys.platform != "linux":
        raise ValueError("D14 CPU staging is a Linux-only source proof")
    files = {name: sha(stage / name) for name in (
        "t16_d14_runner.py", "t16_d14_cpu_stage.py", "t16_d14_launch.py",
        "t16_candidate_runner_full_tail.py", "t16_full_tail_base_runner.py",
        "t16_candidate_launch_full_tail.py",
        "t16_legacy_base_runner.py", "tests/test_t16_shared_prefill.py",
        "tests/test_t16_full_tail.py", "tests/test_t16_candidate_runner_full_tail.py",
        "tests/fixtures/t16_failed_full_tail.json",
        "tests/engine/test_layer_major_tracks.py",
    )}
    test = stage / "tests/engine/test_layer_major_tracks.py"
    if not test.is_file() or test.is_symlink():
        raise ValueError("frozen D14 CPU regression test is missing")
    r020 = replay_r020(stage)
    r020["raw_replay_sha256"] = sha(stage / "r020_raw_replay.json")
    commands = []
    for wt, commit, expected in ((ROOT / "wt/e2base", PARENT, 1), (ROOT / "wt/e2d14", NEW, 0)):
        if subprocess.check_output(["git", "-C", str(wt), "rev-parse", "HEAD"], text=True).strip() != commit:
            raise ValueError(f"worktree commit mismatch: {wt}")
        command = [str(ROOT / "venv/bin/python"), "-S", "-c", "<isolated pytest>"]
        returncode, binding, output, pytest_summary = isolated_pytest(wt, test, commit)
        log = stage / ("cpu_baseline.log" if commit == PARENT else "cpu_candidate.log")
        log.write_text(output)
        commands.append({"worktree": str(wt), "commit": commit, "argv": command,
                         "returncode": returncode, "expected_returncode": expected, "binding": binding,
                         "pytest": pytest_summary,
                         "output_path": str(log), "output_sha256": sha(log)})
        if returncode != expected:
            raise RuntimeError(output)
        expected_summary = {"count": 13, "outcome": "failed" if commit == PARENT else "passed"}
        if pytest_summary != expected_summary:
            raise RuntimeError(f"unexpected D14 pytest outcome: {pytest_summary}\n" + output)
    report = {"schema": "ft_t16_d14_cpu_stage/v1", "gpu_started": False, "files": files,
              "r020_read_only_replay": r020, "steps": commands}
    harness_code = (
        "import sys; sys.path.insert(0, '/data2/FreeToken/venv/lib/python3.10/site-packages'); "
        "import pytest; sys.exit(pytest.main(['-q', '-p', 'no:cacheprovider', "
        "'tests/test_t16_shared_prefill.py', 'tests/test_t16_full_tail.py', "
        "'tests/test_t16_candidate_runner_full_tail.py']))"
    )
    process = subprocess.run([str(ROOT / 'venv/bin/python'), '-S', '-c', harness_code], cwd=stage,
                             env={**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'PYTHONDONTWRITEBYTECODE': '1'},
                             capture_output=True, timeout=90)
    log = stage / 'harness_regression.log'
    log.write_bytes(process.stdout + process.stderr)
    if process.returncode or not re.search(r'39 passed in ', process.stdout.decode()):
        raise RuntimeError(log.read_text())
    report['harness_regression'] = {'returncode': 0, 'passed': 39, 'output_path': str(log),
                                    'output_sha256': sha(log), 'actual_failure_fixtures': ['E2-R019-gate-D06', 'E2-R021-gate-D14']}
    (stage / "cpu_validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", type=Path, required=True)
    run(parser.parse_args().stage)
