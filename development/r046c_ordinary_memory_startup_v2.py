#!/usr/bin/env python3
"""R046c-only composition of ordinary-v3 binding and worker memory evidence.

This does not change the candidate.  Spawned workers install the two existing
observers in the same process: v3 owns UserMsg/DetokenizeMsg binding, while the
R056 observer owns CUDA memory samples at model load and request boundaries.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
V3 = HERE / "r046c_t06_ordinary_startup_v4.py"
MEMORY = HERE / "r056_performance_memory_observer.py"


def load(name: str, path: Path):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"R046c runtime source unavailable: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); assert spec.loader
    spec.loader.exec_module(module)
    return module


def install(observer_dir: Path) -> None:
    v3, memory = load("r046c_v3_observer", V3), load("r046c_memory_observer", MEMORY)
    if "R056_SERVICE_BIRTH" not in os.environ:
        os.environ["R056_SERVICE_BIRTH"] = json.dumps(v3.birth(), sort_keys=True)
    v3.install(observer_dir)
    memory.install()


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--observer-dir", type=Path, required=True)
    parser.add_argument("ft_args", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    if not options.ft_args or options.ft_args[0] != "--":
        parser.error("pass ft arguments after --")
    if not os.environ.get("R056_MODEL_MEMORY"):
        parser.error("R046c requires R056_MODEL_MEMORY")
    # Bind both observers to the parent service process before spawn.  Workers
    # inherit this exact receipt and record their own worker birth separately.
    service_birth = json.dumps(load("r046c_v3_birth", V3).birth(), sort_keys=True)
    os.environ["R046C_T06_SERVICE_BIRTH"] = service_birth
    os.environ["R056_SERVICE_BIRTH"] = service_birth
    os.environ["R046C_T06_OBSERVER_DIR"] = str(options.observer_dir)
    os.environ["R056_OBSERVE_REQUESTS"] = "1"
    from freetoken.cli import main as ft_main
    sys.argv = ["ft", *options.ft_args[1:]]
    ft_main()
    return 0


if __name__ == "__mp_main__":
    directory = os.environ.get("R046C_T06_OBSERVER_DIR")
    if not directory:
        raise RuntimeError("R046c worker lacks ordinary observer directory")
    install(Path(directory))
elif __name__ == "__main__":
    raise SystemExit(main())
