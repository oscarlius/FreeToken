"""Remote read-only H2 rollback preflight collector; no service startup path."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


sys.dont_write_bytecode = True
RUN = Path("/data2/FreeToken/runs/dev_release/rollback_preflight_20261009_1340_v1")
INPUT = RUN / "h2_input.json"
HISTORY = Path("/data2/_shared/runs/ft_rounds/_e0/paper_headroom_20261003/serve_final_8192.log")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(argv: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> dict[str, object]:
    completed = subprocess.run(argv, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return {"argv": argv, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def write_command(name: str, result: dict[str, object]) -> dict[str, object]:
    (RUN / f"{name}.stdout.txt").write_text(str(result["stdout"]), encoding="utf-8")
    (RUN / f"{name}.stderr.txt").write_text(str(result["stderr"]), encoding="utf-8")
    return {"argv": result["argv"], "returncode": result["returncode"], "stdout_sha256": sha256(RUN / f"{name}.stdout.txt"), "stderr_sha256": sha256(RUN / f"{name}.stderr.txt")}


def history_evidence() -> dict[str, object]:
    result: dict[str, object] = {"path": str(HISTORY), "exists": HISTORY.is_file()}
    if not HISTORY.is_file():
        result["usage_evidence"] = "absent: history log does not exist"
        return result
    lines = HISTORY.read_text(encoding="utf-8", errors="replace").splitlines()
    result["full_file_sha256"] = sha256(HISTORY)
    result["size_bytes"] = HISTORY.stat().st_size
    for label, pattern in (("cached_rows", r"cached_rows"), ("usage", r"usage")):
        matches = [{"line": number, "text": line[:1000]} for number, line in enumerate(lines, 1) if re.search(pattern, line, re.IGNORECASE)]
        result[f"{label}_matches"] = matches
    result["usage_evidence"] = "present in bounded matching lines" if result["usage_matches"] else "absent: no usage field in serve_final_8192.log"
    candidate_reports = []
    parent = HISTORY.parent
    for path in sorted(parent.glob("*")):
        if path.is_file() and re.search(r"req.*sdk.*report|sdk.*report", path.name, re.IGNORECASE):
            report_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            usage = [{"line": number, "text": line[:1000]} for number, line in enumerate(report_lines, 1) if re.search(r"usage", line, re.IGNORECASE)]
            candidate_reports.append({"path": str(path), "sha256": sha256(path), "usage_matches": usage})
    result["existing_req_sdk_reports"] = candidate_reports
    return result


def main() -> int:
    if not RUN.is_dir() or not INPUT.is_file():
        raise SystemExit("owned run directory/input absent; refusing to write elsewhere")
    packet = json.loads(INPUT.read_text(encoding="utf-8"))
    worktree = Path(packet["rollback"]["worktree"])
    expected_commit = packet["rollback"]["commit"]
    before = write_command("git_status_before", invoke(["git", "status", "--porcelain", "--untracked-files=all", "--ignored"], cwd=worktree))
    head = write_command("git_head", invoke(["git", "rev-parse", "HEAD"], cwd=worktree))

    env = dict(os.environ)
    removed = sorted(key for key in env if key.startswith("FT_") or key in {"PYTHONPATH", "CUDA_VISIBLE_DEVICES"})
    for key in removed:
        env.pop(key, None)
    required = packet["clean_environment_rule"]["required"]
    env.update(PYTHONDONTWRITEBYTECODE=required["PYTHONDONTWRITEBYTECODE"], PYTHONUNBUFFERED=required["PYTHONUNBUFFERED"], PYTHONPATH=required["PYTHONPATH"], VIRTUAL_ENV=required["VIRTUAL_ENV"], CUDA_VISIBLE_DEVICES="", MASTER_PORT=required["MASTER_PORT"])
    env["PATH"] = str(Path(required["VIRTUAL_ENV"]) / "bin") + ":" + env.get("PATH", "")
    help_result = write_command("ft_serve_help", invoke([str(Path(required["VIRTUAL_ENV"]) / "bin" / "ft"), "serve", "--help"], cwd=RUN, env=env))
    help_text = (RUN / "ft_serve_help.stdout.txt").read_text(encoding="utf-8", errors="replace") + "\n" + (RUN / "ft_serve_help.stderr.txt").read_text(encoding="utf-8", errors="replace")
    available = set(re.findall(r"--[A-Za-z0-9][A-Za-z0-9-]*", help_text))
    expected_options = [item for item in packet["rollback_argv"] if item.startswith("--")]
    option_check = [{"option": option, "present_in_help": option in available} for option in expected_options]
    after = write_command("git_status_after", invoke(["git", "status", "--porcelain", "--untracked-files=all", "--ignored"], cwd=worktree))
    status_before = (RUN / "git_status_before.stdout.txt").read_text(encoding="utf-8")
    status_after = (RUN / "git_status_after.stdout.txt").read_text(encoding="utf-8")
    actual_head = (RUN / "git_head.stdout.txt").read_text(encoding="utf-8").strip()
    receipt = {
        "schema": "ft_release_rollback_h2_preflight/v1",
        "input_sha256": sha256(INPUT),
        "rollback": {"worktree": str(worktree), "expected_commit": expected_commit, "actual_head": actual_head,
                     "status_before_empty": status_before == "", "status_after_empty": status_after == ""},
        "commands": {"git_status_before": before, "git_head": head, "ft_serve_help": help_result, "git_status_after": after},
        "help_environment": {"cwd": str(RUN), "PYTHONDONTWRITEBYTECODE": env["PYTHONDONTWRITEBYTECODE"], "PYTHONPATH": env["PYTHONPATH"], "CUDA_VISIBLE_DEVICES": env["CUDA_VISIBLE_DEVICES"], "removed_environment_keys": removed},
        "rollback_argv_option_check": option_check,
        "unsupported_options": [item["option"] for item in option_check if not item["present_in_help"]],
        "history": history_evidence(),
        "execution": {"ft_subcommand": ["serve", "--help"], "model_service_started": False, "endpoint_calls": 0, "gpu_acquired": False},
    }
    (RUN / "preflight_receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # A missing option, nonempty rollback worktree, wrong HEAD, or failed help is a hard preflight failure.
    return 0 if (actual_head == expected_commit and status_before == status_after == "" and help_result["returncode"] == 0 and not receipt["unsupported_options"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
