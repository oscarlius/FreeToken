"""CPU-only spawn proof for the root-owned D15 window observer.

It loads the existing observer in a fresh multiprocessing interpreter and calls
its real ``install`` factory hook.  It does not construct an Engine, open a
port, take a lock, or issue an API request.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path

WINDOW_OBSERVER = Path("/data2/FreeToken/development/d15_window_ab_20261010/window_observer.py")
WINDOW_OBSERVER_SHA256 = "02a2a940648d3b7ae47056c800d2dbbe8b4ba877619b5e8174fc3026b529fc84"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _birth() -> dict[str, int | str]:
    fields = (Path("/proc") / str(os.getpid()) / "stat").read_text().rpartition(") ")[2].split()
    ticks = int(fields[19])
    return {"pid": os.getpid(), "start_ticks": ticks, "execution_id": f"{os.getpid()}:{ticks}", "pgid": int(fields[2]), "session": int(fields[3])}


def _window_observer_spawn_entry(queue, observer_dir: str) -> None:
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    import torch
    if torch.cuda.is_initialized():
        raise RuntimeError("CUDA was initialized before the CPU probe")
    if WINDOW_OBSERVER.is_symlink() or _sha(WINDOW_OBSERVER) != WINDOW_OBSERVER_SHA256:
        raise RuntimeError("root-owned window observer source pin differs")
    spec = importlib.util.spec_from_file_location("d15_window_observer_cpu_probe", WINDOW_OBSERVER)
    module = importlib.util.module_from_spec(spec); assert spec and spec.loader
    spec.loader.exec_module(module)
    from freetoken.engine.engine import Engine
    before = Engine.__init__
    directory = Path(observer_dir)
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    os.environ["R046C_T06_SERVICE_BIRTH"] = json.dumps(_birth(), sort_keys=True)
    module.install(directory)
    queue.put({"window_observer_path": str(WINDOW_OBSERVER), "window_observer_sha256": _sha(WINDOW_OBSERVER),
               "factory_install_called": True, "engine_constructor_hooked": Engine.__init__ is not before,
               "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"), "cuda_initialized": torch.cuda.is_initialized(),
               "observer_directory_empty": not any(directory.iterdir())})


def run(receipt: Path) -> dict:
    if receipt.exists() or receipt.is_symlink():
        raise RuntimeError("probe receipt must be a new regular path")
    observer_dir = receipt.with_name(receipt.stem + "_observer")
    if observer_dir.exists() or observer_dir.is_symlink():
        raise RuntimeError("probe observer directory already exists")
    context = multiprocessing.get_context("spawn")
    queue = context.Queue(); child = context.Process(target=_window_observer_spawn_entry, args=(queue, str(observer_dir)))
    child.start(); proof = queue.get(timeout=60); child.join(60)
    if child.exitcode != 0 or not proof["factory_install_called"] or not proof["engine_constructor_hooked"] or proof["cuda_initialized"]:
        raise RuntimeError("window observer CPU spawn probe failed")
    value = {"schema": "ft_r067e_window_observer_cpu_spawn/v1", "gpu_started": False, "service_started": False,
             "http_called": False, "gpu_lock_acquired": False, "worker": proof}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2); stream.write("\n")
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--receipt", required=True, type=Path)
    print(json.dumps(run(parser.parse_args().receipt), sort_keys=True))
