"""R062 v5 binds the complete retained launch dependency closure."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE / "r062_d07_owned_launch_v4.py"
RETAINED = (
    "r059_d07_owned_launch.py",
    "r062_d07_owned_launch.py",
    "r062_d07_owned_launch_v2.py",
    "r062_d07_owned_launch_v3.py",
    "r062_d07_owned_launch_v4.py",
    "t16_r059_d07_candidate.py",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def runtime():
    spec = importlib.util.spec_from_file_location("r062_retained_v4", PREVIOUS)
    previous = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(previous)
    module = previous.runtime()
    module.__file__ = str(Path(__file__).resolve())
    module.DEV = HERE
    old_sources = module.source_hashes

    def sources(card):
        result = old_sources(card)
        for name in (*RETAINED, Path(__file__).name):
            result[name] = sha(HERE / name)
        return result

    module.source_hashes = sources
    module.dry_run_receipt_path = lambda card: (
        module.ROOT / "runs/dev_T16/reviews"
        / "E2-R062-gate-D07_file_dry_run_v5.json"
    )
    module.review_path = lambda card: (
        module.ROOT / "runs/dev_T16/reviews"
        / "E2-R062-gate-D07_startup_review_v5.json"
    )
    return module


if __name__ == "__main__":
    runtime().main()
