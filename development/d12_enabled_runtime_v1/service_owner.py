"""Per-arm D12 service adapter; not a formal launch entry point.

The enclosing host controller owns scope approval, D07 admission and GPU lock,
namespace setup/START, host birth mapping, terminal review and D04. This module
does not create any of those. before_start is a mandatory integration hook,
not an authorization token. There is deliberately no command-line launcher.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
from types import SimpleNamespace
import urllib.error
import urllib.request

from arm_plan import ARMS, D16_SOURCES, _file, _raw, _require, _sha, _write, recheck_bound_sources, validate_plan


def _load(root, name):
    path = Path(root) / name
    _file(path, D16_SOURCES[name])
    spec = importlib.util.spec_from_file_location("d12_owner_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _directory(path):
    path = Path(path)
    _require(path.is_absolute() and path.resolve() == path and path.is_dir(), "physical owned directory required")
    stat = path.stat()
    _require(stat.st_uid == os.geteuid(), "output directory UID differs")
    return {"device": stat.st_dev, "inode": stat.st_ino, "uid": stat.st_uid}


def _command(argv, **kwargs):
    return subprocess.check_output(argv, text=True, timeout=45, **kwargs).strip()


class ServiceOwner:
    def __init__(self, plan_path, plan_sha256, *, lifecycle=None, file_dry_run=False):
        _require(type(file_dry_run) is bool, "explicit file-dry boolean required")
        self.plan_path, self.plan_sha256 = Path(plan_path), plan_sha256
        self._plan_bytes = _file(self.plan_path, plan_sha256)
        plan = json.loads(self._plan_bytes)
        validate_plan(plan)
        self.root = Path(plan["service_root"])
        _require(not self.plan_path.is_relative_to(self.root), "plan must be outside service output")
        self._legacy = _load(plan["d16"], "r040a_private_port_owner_v3.py")
        self._base = _load(plan["d16"], "t16_private_port_base_runner.py")
        self._base.command = _command
        self._ports = _load(plan["d16"], "ft_batch_port_pair_v1.py")
        self._r040a_file_dry_run = file_dry_run
        self._r040a_private_lifecycle = lifecycle
        if not file_dry_run:
            _require(all(callable(getattr(lifecycle, key, None)) for key in
                         ("process_identity", "stop_owned_process", "owned_group_alive")), "owned lifecycle required")
        self._r040a_private_gpu = SimpleNamespace(time=time, urllib=urllib, put=_write,
                                                protocol={"command": _command})
        self.proc = None
        self.extensions = None
        self._failed = False
        self._busy = False
        self.root.mkdir()
        self._root_identity = _directory(self.root)
        _write(self.root / "owner-binding.json", {"schema": "ft_d12_service_owner_binding/v1",
            "plan": {"path": str(self.plan_path), "sha256": plan_sha256}, "directory": self._root_identity,
            "file_dry_run": file_dry_run, "formal_launch_authorized": False})

    def _check(self):
        _require(_file(self.plan_path, self.plan_sha256) == self._plan_bytes, "owner plan changed")
        _require(_directory(self.root) == self._root_identity, "owner output directory changed")
        plan = json.loads(self._plan_bytes)
        recheck_bound_sources(plan)
        return plan

    def owned_lifecycle(self):
        return self._r040a_private_lifecycle

    def _extensions(self, plan, arm):
        # Reuse the actual native import/fingerprint function with CUDA hidden.
        # It does not use the T17 service wrapper or inherited FT flags.
        environment = {**arm["environment"], "CUDA_VISIBLE_DEVICES": ""}
        value = self._base.Runner.compiled_extensions(
            SimpleNamespace(environment=lambda wt: environment), Path(plan["candidate"]))
        _require(set(value) == {"_cpu_moe", "_pinned_tensor"}, "native extension set differs")
        for row in value.values():
            _file(Path(row["path"]).resolve(), row["sha256"])
        if self.extensions is None:
            self.extensions = value
        _require(value == self.extensions, "compiled extension binding changed between services")
        return value

    def stop(self):
        return self._legacy._stop(self)

    def service(self, name, operation, *, before_start=None):
        """Prepare and run one fixed arm, always stopping after operation/error.

        File dry returns before the same Popen without invoking operation or
        before_start. The formal host caller must implement before_start using
        its admitted, owned control channel; a callback alone proves no scope.
        A failed arm poisons this owner, so it cannot silently continue/retry.
        """
        _require(name in {x[0] for x in ARMS}, "unknown arm")
        _require(not self._failed and not self._busy and self.proc is None, "owner is failed or busy")
        _require(callable(operation), "operation callback required")
        _require(self._r040a_file_dry_run or callable(before_start), "host before_start hook required")
        self._busy = True
        try:
            return self._service(name, operation, before_start)
        except BaseException:
            self._failed = True
            raise
        finally:
            self._busy = False

    def _service(self, name, operation, before_start):
        plan = self._check()
        arm = plan["arms"][name]
        folder = Path(arm["directory"])
        _require(folder.parent == self.root and folder.name == name, "arm directory differs")
        extensions = self._extensions(plan, arm)
        # File dry writes no sockets and sends no health/business requests.
        port_evidence = None if self._r040a_file_dry_run else self._ports.port_receipt(arm["port"])
        folder.mkdir()
        folder_identity = _directory(folder)
        for filename, value in (("argv.json", arm["argv"]), ("environment.json", arm["environment"]),
                                ("compiled_extensions.json", extensions)):
            _write(folder / filename, value)
        with (folder / "SERVE_CMD.txt").open("x") as output:
            output.write(shlex.join(["env", *[k + "=" + v for k, v in sorted(arm["environment"].items())],
                                     *arm["argv"]]) + "\n")
        prepared = {"schema": "ft_d12_pre_popen/v1", "arm": name, "plan_sha256": self.plan_sha256,
                    "argv_sha256": arm["argv_sha256"], "environment_sha256": arm["environment_sha256"],
                    "compiled_extensions": extensions, "directory": folder_identity,
                    "port_probe": port_evidence, "file_dry_run": self._r040a_file_dry_run,
                    "formal_launch_authorized": False, "model_correctness_verified": False}
        _write(folder / "pre-popen.json", prepared)
        with (folder / "serve.log").open("x") as log:
            self._check()
            _require(_directory(folder) == folder_identity, "arm output directory changed")
            if self._r040a_file_dry_run:
                return prepared
            before_start(name, folder)
            # The callback may block on host validation; recheck afterwards.
            self._check()
            _require(_directory(folder) == folder_identity, "arm output directory changed")
            for row in extensions.values():
                _file(Path(row["path"]).resolve(), row["sha256"])
            self.port = arm["port"]
            self.base_url = f"http://127.0.0.1:{self.port}"
            self.proc = subprocess.Popen(arm["argv"], env=arm["environment"], cwd=plan["candidate"],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, close_fds=True)
            self.service_birth = None
            try:
                birth = self.owned_lifecycle().process_identity(self.proc.pid)
                _require(birth is not None and type(birth.get("start_ticks")) is int and birth["start_ticks"] > 0
                         and birth.get("pid") == birth.get("pgid") == birth.get("session") == self.proc.pid
                         and birth.get("state") != "Z", "service birth/group/session differs")
                self.service_birth = birth
                _write(folder / "owned_process.json", {"birth": birth, "port": self.port,
                                                       "plan_sha256": self.plan_sha256})
                self._legacy._ready_health(self, folder)
                self._check()
                return operation(self, folder)
            finally:
                self.stop()
                _write(folder / "service-stopped.json", {"birth": self.service_birth, "owned_group_alive": False,
                    "plan_sha256": self.plan_sha256, "scope": "native owner stop completed; caller must verify worker/namespace"})
