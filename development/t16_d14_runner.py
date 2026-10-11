"""Frozen D14 adapter for the reviewed T16 full-tail runner.

It intentionally reuses the reviewed D06/D07 implementation and changes only
the immutable candidate binding.  The launcher freezes this file together with
its reviewed dependencies before a GPU process is reserved.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ADAPTER = HERE / "t16_candidate_runner_full_tail.py"
ADAPTER_SHA256 = "0451e41128b4d1e0c73f892b375b9fbe70b30a9fbac46bc022500bd3c1b6d8b8"
BASE = HERE / "t16_full_tail_base_runner.py"
BASE_SHA256 = "379948776d42d5429304afb11dafb0d316e641638caf7cad15fb5b5e6be7340f"
D14 = {
    "card": "D14",
    "parent_wt": "e2base",
    "new_wt": "e2d14",
    "parent_commit": "23f2e2caa3395837c9474735ffc83321f3b9b5a1",
    "new_commit": "e4f32022a5aa4d8734d87d9f6eb15e98c1edde42",
    "ordinary_prefill": False,
}


def _load(path: Path, digest: str, name: str):
    source = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(source).hexdigest() != digest:
        raise RuntimeError(f"reviewed dependency changed: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(source, str(path), "exec"), module.__dict__)
    return module


def main() -> None:
    adapter = _load(ADAPTER, ADAPTER_SHA256, "ft_t16_d14_adapter")
    if hashlib.sha256(BASE.read_bytes()).hexdigest() != BASE_SHA256:
        raise RuntimeError("reviewed full-tail base changed")
    if adapter.CASES.get("D14") != D14:
        raise RuntimeError("D14 binding differs from the shared T16 runner")
    # CandidateRunner records Path(__file__) as the frozen candidate source.
    adapter.__dict__["__file__"] = str(Path(__file__).resolve())
    adapter.main()


if __name__ == "__main__":
    main()
