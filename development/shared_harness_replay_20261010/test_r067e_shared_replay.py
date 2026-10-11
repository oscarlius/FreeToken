"""Shared CPU replay: R067e real Effects materialization plus spawned route probe."""
from __future__ import annotations

import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path

from _shared.experiment_harness.startup_preflight import assert_same_spawn


PACKET = Path(__file__).resolve().parents[1] / "r067e_20261010"
TARGET = Path("/data2/FreeToken")


def test_r067e_real_effects_materialize_all_bound_services_and_spawned_route(tmp_path):
    if not (TARGET / "venv/bin/python").is_file():
        import pytest
        pytest.skip("requires target FT venv")
    sys.path.insert(0, str(PACKET))
    import r067e_owned as owned
    import r067e_runner as runner
    from r067e_actual import Effects, prefix_tail

    class ControlledD07:
        @staticmethod
        def clean_environment(worktree):
            assert worktree == runner.WORKTREE
            return {"VIRTUAL_ENV": str(TARGET / "venv"), "PYTHONPATH": "discarded", "PATH": os.environ["PATH"]}

        @staticmethod
        def argv_sha256(argv):
            return hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()

    plan = runner.filedry()
    effects = Effects(d07=ControlledD07(), owned=None, plan=plan, opener=object(), t17=object(), artifacts=object(), run_dir=tmp_path / "run")
    assert effects.plan["input_binding"] is plan["input_binding"]
    ids_bound = cold_schedules = 0
    materialized = []
    for service in plan["services"]:
        arm, env = effects.materialize(service)
        materialized.append(arm)
        assert Path(service["service_dir"]) == Path(service["cwd"]) == arm
        assert_same_spawn({"argv": service["argv"]}, service["argv"])
        assert Path(service["argv"][5]) == arm / "r067e_startup.py"
        assert env["PYTHONPATH"].startswith(str(arm) + ":")
        if service["kind"] == "cold":
            assert (arm / "prefill_schedule.json").is_file()
            cold_schedules += 1
        for item in service.get("requests") or [service["request"]]:
            prefix, tail = prefix_tail(service, item)
            ids = effects.ids(service, item, prefix, tail)
            assert hashlib.sha256(struct.pack("<%di" % len(ids), *ids)).hexdigest() == item["input_ids_sha256"]
            ids_bound += 1
    assert len(materialized) == len(set(materialized)) == 10
    assert cold_schedules == 8 and ids_bound == 14

    service = plan["services"][0]
    result = subprocess.run(
        [str(TARGET / "venv/bin/python"), str(PACKET / "r067e_startup.py"), "--cpu-startup-probe"],
        cwd=runner.WORKTREE,
        env={**os.environ, **service["env"], "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "FT_DEV_STATE_DUMP": str(tmp_path / "state")},
        capture_output=True, text=True, timeout=90, check=False,
    )
    assert result.returncode == 0, result.stderr
    proof = json.loads(result.stdout)
    assert proof["route_present"] is True and proof["worker"]["cuda_initialized"] is False
