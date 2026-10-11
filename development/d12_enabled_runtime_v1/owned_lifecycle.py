"""D12-local /proc exit-race repair around the immutable D07 lifecycle.

Only the loaded module instance's process-group observer is replaced. Original
birth reads, signal handling, deadlines and stop logic retain their pinned code.
"""
import hashlib
import os
from pathlib import Path


NATIVE_SHA = "7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf"


def owned_group_alive(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    alive = False
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry / "stat").read_text().rpartition(") ")[2].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if int(fields[2]) != pgid:
            continue
        if int(fields[3]) != pgid:
            raise RuntimeError("process group no longer belongs to the reserved session")
        alive |= fields[0] != "Z"
    return alive


def load_owned_lifecycle(gate):
    if gate.OWNED_PROTOCOL_SHA != NATIVE_SHA:
        raise ValueError("D12 lifecycle requires the pinned D07 protocol")
    module = gate.load_owned_lifecycle()
    if hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest() != NATIVE_SHA:
        raise ValueError("D12 native lifecycle source changed")
    if module.stop_owned_process.__globals__ is not module.__dict__:
        raise ValueError("D12 lifecycle stop does not use its isolated module globals")
    module.owned_group_alive = owned_group_alive
    return module
