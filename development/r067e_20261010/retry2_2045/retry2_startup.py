"""Task-owned R067e retry2 adapter: emit exact Engine-domain cold P hash first."""
from __future__ import annotations

import hashlib
import json
import os
import multiprocessing
from pathlib import Path


def _canonical_digest(pool, snapshot: int) -> str:
    import torch
    digest = hashlib.sha256()
    tensors = {"conv_states": pool.conv_states[:, snapshot], "recurrent_states": pool.recurrent_states[:, snapshot],
               **{f"slot_states/{name}": value[:, snapshot] for name, value in sorted(pool.slot_states.items())}}
    for label, value in tensors.items():
        state = value.detach().to(device="cpu").contiguous()
        digest.update(label.encode("utf-8") + b"\0")
        digest.update(str(tuple(state.shape)).encode("ascii") + b"\0")
        digest.update(str(state.dtype).encode("ascii") + b"\0")
        digest.update(state.view(torch.uint8).numpy().tobytes())
    return digest.hexdigest()


def install_preguard_observer() -> None:
    """Wrap only the opt-in development guard; candidate files remain untouched."""
    from freetoken.engine.engine import Engine
    original = Engine._verify_dev_cold_donor_guard
    if getattr(original, "_r067e_retry2_observer", False):
        return

    def observed(self, batch, snapshot: int, boundary: int):
        receipt = os.environ.get("FT_DEV_COLD_DONOR_PRE_GUARD_RECEIPT")
        if os.environ.get("FT_DEV_COLD_DONOR_GUARD") == "1" and receipt:
            path = Path(receipt)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise RuntimeError("failed_harness: duplicate cold pre-guard receipt")
            actual = _canonical_digest(self.linear_state_pool, snapshot)
            expected = os.environ["FT_DEV_COLD_DONOR_EXPECTED_STATE_SHA256"]
            path.write_text(json.dumps({"schema": "ft_r067e_retry2_preguard/v1", "boundary": boundary,
                "snapshot": snapshot, "engine_canonical_sha256": actual, "expected_sha256": expected,
                "equal": actual == expected, "phase": "before_engine_guard"}, sort_keys=True) + "\n", encoding="utf-8")
            if actual != expected:
                raise RuntimeError("failed_harness: cold pre-guard Engine canonical donor differs")
        return original(self, batch, snapshot, boundary)

    observed._r067e_retry2_observer = True
    Engine._verify_dev_cold_donor_guard = observed


# The parent startup validates the sealed worktree and puts its ``python`` tree
# first on sys.path.  Installing before that would silently observe whichever
# Engine happens to be installed in the controller venv instead of the pinned
# candidate Engine.
from r067e_startup import app  # noqa: E402,F401 -- parent pins worktree and exact-ID route
install_preguard_observer()


def _spawn_probe(queue) -> None:
    """Runs in a fresh spawn interpreter, proving this adapter was imported."""
    from freetoken.engine.engine import Engine
    routes = [(route.path, sorted(route.methods or ())) for route in app.routes]
    queue.put({"adapter_observer": bool(getattr(Engine._verify_dev_cold_donor_guard, "_r067e_retry2_observer", False)),
               "route_present": ("/internal/t17/exact-ids", ["POST"]) in routes,
               "cuda_initialized": __import__("torch").cuda.is_initialized()})


def cpu_startup_probe() -> None:
    context = multiprocessing.get_context("spawn")
    queue = context.Queue(); child = context.Process(target=_spawn_probe, args=(queue,)); child.start()
    proof = queue.get(timeout=60); child.join(60)
    if child.exitcode != 0 or not proof["adapter_observer"] or not proof["route_present"] or proof["cuda_initialized"]:
        raise RuntimeError("retry2 spawned startup probe failed")
    print(json.dumps({"schema": "ft_r067e_retry2_startup_spawn/v1", "gpu_started": False, "worker": proof}, sort_keys=True))

if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--cpu-startup-probe"]:
        cpu_startup_probe()
    else:
        from freetoken.cli import main
        sys.argv = ["ft", *sys.argv[1:]]
        main()
