"""The one R067d-retry2 service lifecycle used by both a real and fake child.

This module deliberately owns the operational sequence.  A CPU fake may replace
the four effects exposed by :class:`Effects`, but it must still traverse
materialize -> start -> readiness -> exact-ID request -> evidence -> cleanup.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

HERE = Path(__file__).resolve().parent
RID = "E2-R067d-d20-short-tail-retry2"
ROOT = Path("/data2/FreeToken")
RUN = ROOT / "runs/dev_R067" / RID
RETRY1 = HERE.parent / "r067d_short_tail_retry1_20261010"
BASE = HERE.parent / "r067_d20_short_tail_v1"
VENV = ROOT / "venv"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def append(path: Path, value: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class UnsafeCleanupError(RuntimeError):
    """A service has not reached the post-cleanup state required to release D07."""


def wait_gpu_idle(d07: Any, timeout_s: int = 120, *, clock=time.monotonic, sleep=time.sleep) -> list[int]:
    """Bounded idle wait used before launch and before releasing the child lock."""
    deadline, last = clock() + timeout_s, None
    while True:
        try:
            return d07.require_gpu_idle()
        except RuntimeError as exc:
            last = exc
        if clock() >= deadline:
            raise RuntimeError(f"failed_harness: GPU did not become idle within {timeout_s}s") from last
        sleep(min(1, max(0, deadline - clock())))


def request_items(service: dict[str, Any]) -> list[dict[str, Any]]:
    return service.get("requests") or [service["request"]]


def prefix_tail(service: dict[str, Any], item: dict[str, Any]) -> tuple[int, int]:
    prefix = int(re.search(r"_p(\d+)", service["name"]).group(1))
    tail = item.get("tail")
    if tail is None:
        tail = int(re.search(r"_t(\d+)", service["name"]).group(1)) if service["kind"] == "cold" else 1
    return prefix, int(tail)


def label(item: dict[str, Any], tail: int) -> str:
    return "seed" if item["role"] == "seed" else f"query_t{tail}"


def expected_cache(service: dict[str, Any], item: dict[str, Any], prefix: int) -> int:
    return prefix if service["kind"] == "hot" and item["role"] != "seed" else 0


def validate_window(service: dict[str, Any], item: dict[str, Any], ids: list[int], window: bytes, raw: dict[str, Any], prefix: int, tail: int) -> tuple[list[dict[str, int]], bool]:
    rows = []
    for new_seq, new_tokens, cached_tokens in re.findall(r"#new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)", window.decode(errors="strict")):
        rows.append({"new_sequences": int(new_seq), "new_tokens": int(new_tokens), "cached_tokens": int(cached_tokens)})
    expected = expected_cache(service, item, prefix)
    usage = raw.get("response", {}).get("usage", {})
    valid = bool(rows) and all(row["new_sequences"] == 1 and row["cached_tokens"] == expected for row in rows)
    valid = valid and sum(row["new_tokens"] for row in rows) == (tail if expected else len(ids))
    valid = valid and sum(row["new_tokens"] for row in rows) <= len(ids)
    valid = valid and usage.get("prompt_tokens") == len(ids) and usage.get("cached_tokens") == expected
    valid = valid and usage.get("completion_tokens") == item["max_tokens"]
    valid = valid and window.count(b'POST /internal/t17/exact-ids HTTP/1.1" 200 OK') == 1
    return rows, valid


@dataclass
class Effects:
    """Real effects; tests substitute an instance with the same methods."""

    d07: Any
    owned: Any
    plan: dict[str, Any]
    opener: Any = None
    t17: Any = None
    artifacts: Any = None
    run_dir: Path = RUN

    def __post_init__(self) -> None:
        self.opener = self.opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
        binding = self.plan.get("input_binding")
        if not isinstance(binding, dict) or set(binding) < {"path", "sha256"}:
            raise RuntimeError("real plan lacks exact-ID input binding")
        input_path = Path(binding["path"])
        if input_path.is_symlink() or not input_path.is_file() or sha(input_path) != binding["sha256"]:
            raise RuntimeError("exact-ID input binding source differs")
        self.inputs = json.loads(input_path.read_text())
        self.cases = {(row["prefix"], row["tail"]): row for row in self.inputs["cases"]}
        if not self.cases:
            raise RuntimeError("exact-ID input binding has no cases")
        for service in self.plan["services"]:
            for item in request_items(service):
                prefix, tail = prefix_tail(service, item)
                ids = self.cases[(prefix, tail)]["donor_ids" if item["role"] == "seed" else "input_ids"]
                digest = hashlib.sha256(struct.pack("<%di" % len(ids), *ids)).hexdigest()
                if digest != item["input_ids_sha256"]:
                    raise RuntimeError("exact-ID input binding does not match service pin")
        self.t17 = self.t17 or load(BASE / "t17_existing/t17_d14_runner.py", "r067d_retry2_t17_transport")
        self.artifacts = self.artifacts or load(BASE / "t17_existing/t17_d14_artifacts.py", "r067d_retry2_t17_artifacts")

    @staticmethod
    def probe(ports: tuple[int, int], evidence_dir: Path, timeout_s: int = 120) -> None:
        """Require both owned ports to be bindable before spawn and after cleanup."""
        deadline, last = time.monotonic() + timeout_s, None
        while time.monotonic() <= deadline:
            sockets = []
            try:
                for port in ports:
                    sock = socket.socket()
                    sockets.append(sock)
                    sock.bind(("0.0.0.0", port))
                return
            except OSError as exc:
                last = exc
            finally:
                for sock in sockets:
                    sock.close()
            time.sleep(1)
        evidence_dir.mkdir(parents=True, exist_ok=False)
        for command, name in ((["ss", "-tanp"], "ss-tanp.txt"), (["lsof", "-nP", "-iTCP"], "lsof.txt")):
            try:
                result = subprocess.run(command, text=True, capture_output=True, check=False)
                body = result.stdout + result.stderr
            except FileNotFoundError:
                body = "tool unavailable\n"
            (evidence_dir / name).write_text(body)
        raise RuntimeError(f"failed_harness: port pair {ports} unavailable") from last

    def materialize(self, service: dict[str, Any]) -> tuple[Path, dict[str, str]]:
        plan_arm = Path(service["service_dir"])
        arm = self.run_dir / "services" / service["name"]
        assert plan_arm.name == service["name"] and not arm.exists(), arm
        for key, value in list(service["env"].items()):
            if isinstance(value, str) and value.startswith(str(plan_arm)):
                service["env"][key] = str(arm) + value[len(str(plan_arm)):]
        service["service_dir"] = service["cwd"] = str(arm)
        service["argv"][5] = str(arm / "r067d_retry2_startup.py")
        arm.mkdir(parents=True)
        (arm / "input_receipts").mkdir()
        (arm / "state_dump").mkdir()
        wrapper = arm / "r067d_retry2_startup.py"
        shutil.copyfile(HERE / "r067d_retry2_startup.py", wrapper)
        assert not wrapper.is_symlink() and sha(wrapper) == service["env"]["FT_DEV_R067D_STARTUP_SHA256"]
        if service["kind"] == "cold":
            source = HERE / "schedules" / f"{service['name']}.json"
            target = arm / "prefill_schedule.json"
            assert source.is_file() and sha(source) == service["schedule"]["sha256"]
            shutil.copyfile(source, target)
            assert not target.is_symlink() and sha(target) == service["schedule"]["sha256"]
            service["env"]["FT_DEV_PREFILL_SCHEDULE"] = str(target)
        if Path(service["worktree"]) != Path(self.plan["worktree"]):
            raise RuntimeError("service worktree differs from source-pinned plan")
        env = self.d07.clean_environment(Path(self.plan["worktree"]))
        env.update(service["env"])
        assert env["VIRTUAL_ENV"] == str(VENV) and env["PYTHONPATH"].startswith(str(arm) + ":")
        put_new(arm / "environment.json", {key: env[key] for key in service["env"]})
        put_new(arm / "argv.json", {"argv": service["argv"], "argv_sha256": self.d07.argv_sha256(service["argv"])})
        return arm, env

    def start(self, service: dict[str, Any], arm: Path, env: dict[str, str]):
        wait_gpu_idle(self.d07)
        from r067d_retry2_runner import sha as runner_sha
        assert Path(service["argv"][5]) == arm / "r067d_retry2_startup.py"
        assert runner_sha(arm / "r067d_retry2_startup.py") == service["env"]["FT_DEV_R067D_STARTUP_SHA256"]
        self.probe((service["port_pair"]["api"], service["port_pair"]["tcpstore"]), self.run_dir / "port_failures" / service["name"], 120)
        log = (arm / "serve.log").open("xb")
        try:
            process = subprocess.Popen(service["argv"], cwd=arm, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            log.close()
        return process

    def ready(self, service: dict[str, Any], process: Any, arm: Path) -> None:
        base = f"http://127.0.0.1:{service['port_pair']['api']}"
        deadline = time.monotonic() + 1800
        while True:
            if process.poll() is not None:
                raise RuntimeError(f"service exited before readiness: {process.returncode}")
            if time.monotonic() > deadline:
                raise TimeoutError("health-only readiness exceeded 1800s")
            try:
                with self.opener.open(base + "/health", timeout=10) as response:
                    health = json.loads(response.read())
                if health.get("status") == "ok" and health.get("maintenance") == "serving":
                    put_new(arm / "ready.json", {"health": health, "at": time.time(), "generation_readiness_calls": 0})
                    return
            except (OSError, ValueError):
                pass
            time.sleep(5)

    def ids(self, service: dict[str, Any], item: dict[str, Any], prefix: int, tail: int) -> list[int]:
        case = self.cases[(prefix, tail)]
        ids = case["donor_ids"] if item["role"] == "seed" else case["input_ids"]
        actual = hashlib.sha256(struct.pack("<%di" % len(ids), *ids)).hexdigest()
        assert actual == item["input_ids_sha256"]
        return ids

    def request(self, service: dict[str, Any], item: dict[str, Any], ids: list[int], arm: Path, request_label: str) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
        offset = (arm / "serve.log").stat().st_size
        base = f"http://127.0.0.1:{service['port_pair']['api']}"
        raw = self.t17.exact_id_request(base, ids, item["max_tokens"], output_path=arm / f"{request_label}.json", observations_path=arm / "observations.jsonl")
        with (arm / "serve.log").open("rb") as stream:
            stream.seek(offset)
            window = stream.read()
        (arm / f"{request_label}.serve-window.txt").write_bytes(window)
        evidence = self.artifacts.request_evidence(arm, request_label, expected_cache(service, item, int(re.search(r"_p(\d+)", service["name"]).group(1))), item["max_tokens"])
        return raw, window, evidence

    def cleanup(self, service: dict[str, Any], process: Any, arm: Path) -> None:
        self.owned.stop_owned_process(process, 120, 30)
        alive = self.owned.owned_group_alive(process.pid)
        put_new(arm / "cleanup.json", {"group_alive": alive, "pid": process.pid, "at": time.time()})
        if alive:
            raise RuntimeError("owned service group remains")
        self.probe((service["port_pair"]["api"], service["port_pair"]["tcpstore"]), self.run_dir / "port_rebind_failures" / service["name"], 120)
        wait_gpu_idle(self.d07)


def run_child(plan: dict[str, Any], *, batch: int, effects: Any, run_dir: Path = RUN, write: Callable[[Path, dict[str, Any]], None] = put_new) -> dict[str, Any]:
    """Execute the entire 10-service/14-call protocol through one effect seam."""
    services = plan["services"]
    assert len(services) == 10 and sum(len(request_items(service)) for service in services) == 14
    counts = {"services": 0, "calls": 0}
    hot: dict[tuple[int, int], dict[str, Any]] = {}
    cold: dict[tuple[int, int, str], dict[str, Any]] = {}
    cells: list[dict[str, Any]] = []
    results: dict[str, Any] = {}
    verdict, error, process = "pending", None, None
    try:
        for service in services:
            if counts["services"] >= 10:
                raise RuntimeError("service budget exceeded")
            if service["kind"] == "cold":
                assert service["env"].get("FT_DEV_COLD_DONOR_GUARD") == "1"
                assert service["env"].get("FT_DEV_COLD_DONOR_EXPECTED_STATE_SHA256")
                assert "--cache-type" not in service["argv"]
            arm, env = effects.materialize(service)
            counts["services"] += 1
            append(run_dir / "budget.jsonl", {"event": "service_start_attempt", "service": service["name"], "index": counts["services"], "at": time.time()})
            process = effects.start(service, arm, env)
            write(arm / "owner.json", {"pid": process.pid, "service": service["name"], "batch": batch, "argv": service["argv"]})
            try:
                effects.ready(service, process, arm)
            except BaseException:
                try:
                    effects.cleanup(service, process, arm)
                    process = None
                except BaseException as cleanup_exc:
                    raise UnsafeCleanupError("readiness failed and owned cleanup failed") from cleanup_exc
                raise
            try:
                for item in request_items(service):
                    if counts["calls"] >= 14:
                        raise RuntimeError("generation call budget exceeded")
                    prefix, tail = prefix_tail(service, item)
                    request_label = label(item, tail)
                    ids = effects.ids(service, item, prefix, tail)
                    counts["calls"] += 1
                    append(run_dir / "budget.jsonl", {"event": "generation_call", "service": service["name"], "label": request_label, "index": counts["calls"], "input_sha256": item["input_ids_sha256"], "at": time.time()})
                    raw, window, evidence = effects.request(service, item, ids, arm, request_label)
                    rows, valid = validate_window(service, item, ids, window, raw, prefix, tail)
                    if not valid:
                        raise RuntimeError("failed_harness: exact-ID usage or prefill log differs")
                    if len(evidence["sampled_token_ids"]) != item["max_tokens"]:
                        raise RuntimeError("failed_harness: sampled output count differs")
                    evidence.update(classification="valid", backend_rows=rows, service=service["name"], role=item["role"], prefix=prefix, tail=tail)
                    write(arm / f"{request_label}.evidence.json", evidence)
                    results[f"{service['name']}/{request_label}"] = {"classification": evidence["classification"], "response_sha256": raw.get("response_sha256"), "backend_rows": rows}
                    if service["kind"] == "hot" and item["role"] != "seed":
                        hot[(prefix, tail)] = evidence
                    if service["kind"] == "cold":
                        cold[(prefix, tail, service["name"].split("_")[1])] = evidence
                    if service["kind"] == "cold" and service["name"].split("_")[1] == "B":
                        first, second = cold[(prefix, tail, "A")], cold[(prefix, tail, "B")]
                        row = {"prefix": prefix, "tail": tail, "cold_A_equals_B": first["sampled_token_ids"] == second["sampled_token_ids"] and first["raw_text"] == second["raw_text"]}
                        if not row["cold_A_equals_B"]:
                            verdict = "failed_harness"
                            cells.append(row)
                            raise RuntimeError("failed_harness: cold A/B unstable")
                        row["hot_equals_cold"] = hot[(prefix, tail)]["sampled_token_ids"] == first["sampled_token_ids"] and hot[(prefix, tail)]["raw_text"] == first["raw_text"]
                        row["classification"] = "PASS" if row["hot_equals_cold"] else "not_met"
                        cells.append(row)
                        write(run_dir / f"cell_p{prefix}_t{tail}.json", row)
                        if not row["hot_equals_cold"]:
                            verdict = "not_met"
                            raise RuntimeError("not_met: stable cold differs from hot; stop immediately")
            finally:
                if process is not None:
                    try:
                        effects.cleanup(service, process, arm)
                        process = None
                    except BaseException as cleanup_exc:
                        raise UnsafeCleanupError("owned cleanup failed") from cleanup_exc
        verdict = "PASS" if counts == {"services": 10, "calls": 14} and len(cells) == 4 else "failed_harness"
    except BaseException as exc:
        error = repr(exc)
        if verdict == "pending":
            verdict = "failed_harness"
    finally:
        cleanup_error = None
        if process is not None:
            try:
                effects.cleanup(service, process, arm)
            except BaseException as exc:
                cleanup_error = repr(exc)
                error = error or repr(UnsafeCleanupError("owned cleanup failed"))
            process = None
        terminal = {"schema": "ft_r067d_retry2_actual_terminal/v1", "rid": RID, "batch": batch, "verdict": verdict, "error": error, "actual_services": counts["services"], "actual_generation_calls": counts["calls"], "cells": cells, "requests": results, "cleanup_error": cleanup_error, "failed_harness_retries_max": 2, "product_acceptance": False, "at": time.time()}
        write(run_dir / "terminal.json", terminal)
    if cleanup_error:
        raise UnsafeCleanupError("owned cleanup failed: " + cleanup_error)
    if error:
        raise RuntimeError(error)
    return terminal
