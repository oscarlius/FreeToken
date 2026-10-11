"""Classify launcher versus ft options after the immutable first H2 capture."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


RUN = Path("/data2/FreeToken/runs/dev_release/rollback_preflight_20261009_1340_v1")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    first = json.loads((RUN / "preflight_receipt.json").read_text(encoding="utf-8"))
    packet = json.loads((RUN / "h2_input.json").read_text(encoding="utf-8"))
    run = subprocess.run(["numactl", "--help"], cwd=RUN, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    (RUN / "numactl_help.stdout.txt").write_text(run.stdout, encoding="utf-8")
    (RUN / "numactl_help.stderr.txt").write_text(run.stderr, encoding="utf-8")
    numactl_text = run.stdout + "\n" + run.stderr
    argv = packet["rollback_argv"]
    ft_start = argv.index("serve") + 1
    launcher_options = [item for item in argv[:ft_start] if item.startswith("--")]
    ft_options = [item for item in argv[ft_start:] if item.startswith("--")]
    ft_help = (RUN / "ft_serve_help.stdout.txt").read_text(encoding="utf-8")
    availability = set(re.findall(r"--[A-Za-z0-9][A-Za-z0-9-]*", ft_help))
    option_check = {
        "launcher_numactl": [{"option": option, "present_in_numactl_help": option.split("=", 1)[0] in numactl_text} for option in launcher_options],
        "ft_serve": [{"option": option, "present_in_ft_serve_help": option in availability} for option in ft_options],
    }
    history = first["history"]
    summary = {
        "schema": "ft_release_rollback_h2_preflight_supplement/v1",
        "first_receipt_sha256": sha256(RUN / "preflight_receipt.json"),
        "rollback_head": first["rollback"]["actual_head"],
        "status_before_empty": first["rollback"]["status_before_empty"],
        "status_after_empty": first["rollback"]["status_after_empty"],
        "ft_serve_help_returncode": first["commands"]["ft_serve_help"]["returncode"],
        "option_check": option_check,
        "unsupported_launcher_options": [item["option"] for item in option_check["launcher_numactl"] if not item["present_in_numactl_help"]],
        "unsupported_ft_options": [item["option"] for item in option_check["ft_serve"] if not item["present_in_ft_serve_help"]],
        "history_bounded": {"full_file_sha256": history.get("full_file_sha256"), "cached_rows_match_count": len(history.get("cached_rows_matches", [])), "usage_match_count": len(history.get("usage_matches", [])), "usage_first_8": history.get("usage_matches", [])[:8], "existing_req_sdk_reports": history.get("existing_req_sdk_reports", [])},
        "terminal_preflight_status": "blocked_dirty_rollback_worktree" if not first["rollback"]["status_before_empty"] else "not_admitted",
        "execution": {"additional_command": ["numactl", "--help"], "model_service_started": False, "endpoint_calls": 0, "gpu_acquired": False},
    }
    (RUN / "preflight_supplement.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
