"""Build a static H2 input binding from the current release_config.py.

This script does not contact the server or execute ft.  It preserves the
release-config option list but intentionally changes CUDA_VISIBLE_DEVICES to an
empty string for a read-only `ft serve --help` inspection.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path


OPS = Path(__file__).resolve().parents[2]
CONFIG_PATH = OPS / "release_config.py"
OUT = Path(__file__).resolve().parents[1] / "h2_input.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remote_path(value: object) -> str:
    """Undo Windows Path rendering of the POSIX paths declared in the config."""
    return str(value).replace("\\", "/")


def main() -> int:
    spec = importlib.util.spec_from_file_location("h2_release_config", CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    # Feed only sentinel values so no host environment is copied into evidence.
    parent = {"FT_SENTINEL": "remove", "PYTHONPATH": "remove", "CUDA_VISIBLE_DEVICES": "remove", "KEEP": "keep"}
    env = module.environment("rollback", parent=parent)
    env["CUDA_VISIBLE_DEVICES"] = ""
    remote_argv = [remote_path(item) if isinstance(item, (str, Path)) else item for item in module.serve_argv("rollback")]
    receipt = {
        "schema": "ft_release_rollback_h2_input/v1",
        "source": {"path": str(CONFIG_PATH), "sha256": sha256(CONFIG_PATH)},
        "rollback": {"worktree": remote_path(module.MODES["rollback"][0]), "commit": module.MODES["rollback"][1]},
        "clean_environment_rule": {
            "removed_from_parent": ["FT_*", "PYTHONPATH", "CUDA_VISIBLE_DEVICES"],
            "required": {key: (remote_path(env[key]) if key in {"PYTHONPATH", "VIRTUAL_ENV"} else env[key]) for key in ("PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED", "PYTHONPATH", "VIRTUAL_ENV", "CUDA_VISIBLE_DEVICES", "MASTER_PORT")},
            "help_only_override": {"CUDA_VISIBLE_DEVICES": ""}
        },
        "rollback_argv": remote_argv,
        "execution": {"operation": "ft serve --help", "cwd": "/data2/FreeToken/runs/dev_release/rollback_preflight_20261009_1340_v1", "no_model_serve": True, "no_endpoint_calls": True, "no_gpu": True},
    }
    OUT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUT), "config_sha256": receipt["source"]["sha256"], "argv_options": sum(item.startswith("--") for item in receipt["rollback_argv"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
