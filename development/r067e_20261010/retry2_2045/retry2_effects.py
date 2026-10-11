"""Real task-owned Effects adapter for R067e retry2.

It retains the parent's real spawn/readiness/exact-ID/evidence/cleanup methods.
Only materialization switches the startup file, and cold requests require the
pre-Engine-guard receipt written by the task-owned adapter.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from retry2_execution import HERE, PARENT, sha


def _parent_actual():
    spec = importlib.util.spec_from_file_location("r067e_actual_retry2_parent", PARENT / "r067e_actual.py")
    module = importlib.util.module_from_spec(spec); assert spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Retry2Effects:
    """Use actual parent effects, with a source-bound task-owned materializer."""

    def __init__(self, **kwargs: Any):
        self.actual = _parent_actual()
        self.base = self.actual.Effects(**kwargs)
        self.plan = self.base.plan
        self.d07, self.owned, self.run_dir = self.base.d07, self.base.owned, self.base.run_dir

    def materialize(self, service: dict[str, Any]):
        plan_arm = Path(service["service_dir"])
        arm = self.run_dir / "services" / service["name"]
        assert plan_arm.name == service["name"] and not arm.exists(), arm
        for key, value in list(service["env"].items()):
            if isinstance(value, str) and value.startswith(str(plan_arm)):
                service["env"][key] = str(arm) + value[len(str(plan_arm)):]
        service["service_dir"] = service["cwd"] = str(arm)
        service["argv"][5] = str(arm / "r067e_retry2_startup.py")
        arm.mkdir(parents=True)
        (arm / "input_receipts").mkdir()
        (arm / "state_dump").mkdir()
        wrapper = arm / "r067e_retry2_startup.py"
        shutil.copyfile(HERE / "retry2_startup.py", wrapper)
        assert not wrapper.is_symlink() and sha(wrapper) == service["env"]["FT_DEV_R067E_STARTUP_SHA256"]
        parent_startup = arm / "r067e_startup.py"
        shutil.copyfile(PARENT / "r067e_startup.py", parent_startup)
        assert not parent_startup.is_symlink() and sha(parent_startup) == self.plan["source_manifest"]["parent/r067e_startup.py"]
        if service["kind"] == "cold":
            source = PARENT / "schedules" / f"{service['name']}.json"
            target = arm / "prefill_schedule.json"
            assert source.is_file() and sha(source) == service["schedule"]["sha256"]
            shutil.copyfile(source, target)
            assert not target.is_symlink() and sha(target) == service["schedule"]["sha256"]
            service["env"]["FT_DEV_PREFILL_SCHEDULE"] = str(target)
        if Path(service["worktree"]) != Path(self.plan["worktree"]):
            raise RuntimeError("service worktree differs from source-pinned plan")
        env = self.d07.clean_environment(Path(self.plan["worktree"]))
        env.update(service["env"])
        self.actual.put_new(arm / "environment.json", {key: env[key] for key in service["env"]})
        self.actual.put_new(arm / "argv.json", {"argv": service["argv"], "argv_sha256": self.d07.argv_sha256(service["argv"])})
        return arm, env

    def start(self, service, arm, env):
        self.actual.wait_gpu_idle(self.d07)
        if Path(service["argv"][5]) != arm / "r067e_retry2_startup.py":
            raise RuntimeError("retry2 startup path differs from materialized adapter")
        if sha(Path(service["argv"][5])) != service["env"]["FT_DEV_R067E_STARTUP_SHA256"]:
            raise RuntimeError("retry2 startup adapter hash differs")
        self.base.probe((service["port_pair"]["api"], service["port_pair"]["tcpstore"]), self.run_dir / "port_failures" / service["name"], 120)
        log = (arm / "serve.log").open("xb")
        try:
            return subprocess.Popen(service["argv"], cwd=arm, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            log.close()

    def ready(self, service, process, arm):
        return self.base.ready(service, process, arm)

    def ids(self, service, item, prefix, tail):
        return self.base.ids(service, item, prefix, tail)

    def request(self, service, item, ids, arm, request_label):
        result = self.base.request(service, item, ids, arm, request_label)
        if service["kind"] == "cold":
            receipt = Path(service["env"]["FT_DEV_COLD_DONOR_PRE_GUARD_RECEIPT"])
            if not receipt.is_file():
                raise RuntimeError("failed_harness: cold pre-guard receipt absent")
            proof = json.loads(receipt.read_text())
            if proof.get("phase") != "before_engine_guard" or proof.get("equal") is not True:
                raise RuntimeError("failed_harness: cold pre-guard receipt differs")
            if proof.get("expected_sha256") != service["env"]["FT_DEV_COLD_DONOR_EXPECTED_STATE_SHA256"]:
                raise RuntimeError("failed_harness: cold pre-guard expected hash differs")
        return result

    def cleanup(self, service, process, arm):
        return self.base.cleanup(service, process, arm)
