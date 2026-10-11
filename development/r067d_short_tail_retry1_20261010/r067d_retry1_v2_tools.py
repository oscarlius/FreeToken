"""V2 runtime environment renderer for the R067d retry-1 prepared packet.

The immutable retry-1 configuration deliberately remains an audit record.  This
module renders its four filesystem environment bindings at execution time, to
the same service directory used by argv/cwd.
"""
from __future__ import annotations

from r067d_cpu_prep import *  # Reuse the frozen packet's cache and window logic.
import r067d_cpu_prep as base

RID = base.RID
_PATH_KEYS = ("FT_DEV_STATE_DUMP", "FT_T17_INPUT_RECEIPTS", "FT_T17_OBSERVATIONS", "PYTHONPATH")
_OLD_RID = "E2-R067d-d20-short-tail-v1"

def actual_environment(service: dict) -> dict:
    env = dict(service["env"])
    arm = str(service["service_dir"])
    old_arm = f"/data2/FreeToken/runs/dev_R067/{_OLD_RID}/services/{service['name']}"
    for key in _PATH_KEYS:
        assert old_arm in env[key], (service["name"], key, env[key])
        env[key] = env[key].replace(old_arm, arm)
        assert arm in env[key], (service["name"], key, env[key])
        assert _OLD_RID not in env[key], (service["name"], key, env[key])
    assert env["MASTER_PORT"] == str(service["port_pair"]["tcpstore"])
    return env

def verify_service_binding(service: dict) -> None:
    base.verify_service_binding(service)
    actual_environment(service)
