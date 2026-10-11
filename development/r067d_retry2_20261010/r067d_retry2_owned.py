"""Root controller and controller-bound child for the real R067d retry2 run.

``--cpu-fake`` exercises the same lifecycle as ``--run`` after replacing only
process, HTTP, lock and GPU effects.  It cannot be mistaken for a GPU result.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = Path("/data2/FreeToken")
RID = "E2-R067d-d20-short-tail-retry2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put_new(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_manifest() -> dict[str, str]:
    names = ("r067d_retry2_owned.py", "r067d_retry2_actual.py", "r067d_retry2_runner.py", "r067d_retry2_packet.py", "r067d_retry2_startup.py", "NATIVE_ABI_CPU_PROOF.json")
    return {name: sha(HERE / name) for name in names}


def load_plan(*, materialize: bool) -> tuple[Any, dict[str, Any], dict[str, Any] | None]:
    import sys
    sys.path.insert(0, str(HERE))
    import r067d_retry2_runner as runner
    # The packet and its eight schedules are an append-only root artifact.  A
    # controller consumes the current sealed packet when present; it never
    # regenerates a second schedule authority just to launch a child.
    current = HERE / "R067D_RETRY2_ROOT_PACKET.json"
    preflight = runner.filedry()
    if current.is_file():
        plan = json.loads(current.read_text())
        identity_matches = all(plan.get(key) == preflight.get(key) for key in ("rid", "worktree", "commit", "engine_sha256", "input_binding"))
        for service in plan["services"]:
            if service["kind"] == "cold":
                schedule = service["schedule"]
                if sha(Path(schedule["path"])) != schedule["sha256"]:
                    raise RuntimeError("sealed cold schedule differs")
        if identity_matches:
            return runner, plan, {"packet": str(current), "packet_sha256": sha(current), "reused_current_packet": True}
        # A stale root packet cannot be an execution authority.  Its immutable
        # schedule bytes may still be reused only after they are derived again
        # from the current hot observations and bound into current preflight.
        schedules = runner.packet.render_packet(
            {8192: Path(f"{runner.packet.HOT_RUN}/hot_p8192/observations.jsonl"), 8256: Path(f"{runner.packet.HOT_RUN}/hot_p8256/observations.jsonl")},
            {8192: Path(f"{runner.packet.HOT_RUN}/hot_p8192/state_dump/donate_0001_dev_conv_states.pt"), 8256: Path(f"{runner.packet.HOT_RUN}/hot_p8256/state_dump/donate_0001_dev_conv_states.pt")},
        )["schedules"]
        for service in preflight["services"]:
            if service["kind"] != "cold":
                continue
            prefix = int(service["name"].split("_p", 1)[1].split("_", 1)[0])
            tail = int(service["name"].rsplit("_t", 1)[1])
            expected = [*schedules[f"p{prefix}"]["schedule"][:2], {"start": prefix, "end": prefix + tail, "mode": "ordinary", "subchunks": [tail]}]
            runner.packet.parse_schedule(expected)
            path = HERE / "schedules" / f"{service['name']}.json"
            actual = json.loads(path.read_text())
            if actual != expected:
                raise RuntimeError("stale root schedule differs from current hot observations")
            service["schedule"] = {"path": str(path), "sha256": sha(path), "derived_from": schedules[f"p{prefix}"]["source_observations"]}
        return runner, preflight, {"stale_root_packet_rejected": {"path": str(current), "sha256": sha(current)}, "current_preflight_schedule_rebinding": True}
    if materialize:
        receipt = runner.materialize_root_packet()
        plan = json.loads(Path(receipt["packet"]).read_text())
    else:
        plan, receipt = preflight, None
    return runner, plan, receipt


def admission(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    document = json.loads(path.read_text())
    expected = {"schema": "ft_r067d_retry2_admission/v1", "admit": True, "rid": RID, "worktree_commit": plan["commit"], "engine_sha256": plan["engine_sha256"], "source_sha256": source_manifest(), "services_max": 10, "generation_calls_max": 14}
    if any(document.get(key) != value for key, value in expected.items()):
        raise RuntimeError("retry2 admission identity/source differs")
    return document


def child_argv(admission_path: Path, batch: int, receipt: Path) -> list[str]:
    return [str(ROOT / "venv/bin/python"), str(Path(__file__).resolve()), "--run", "--owned-child", "--admission", str(admission_path), "--batch", str(batch), "--receipt", str(receipt)]


def d07_module():
    return load(ROOT / "development/d07_g3g4_prepare.py", "r067d_retry2_d07")


def runtime_sources(plan: dict[str, Any], d07=None) -> dict[str, str]:
    """Bind every imported execution helper in the launch receipt, not just code here."""
    sources = dict(source_manifest())
    if d07 is None or plan["commit"] == "fake-commit":
        return sources
    sources[str(ROOT / "development/d07_g3g4_prepare.py")] = sha(ROOT / "development/d07_g3g4_prepare.py")
    source_d07 = d07 if hasattr(d07, "OWNED_SOURCE") else d07_module()
    protocol = source_d07.OWNED_SOURCE / "t17_owned_launch_protocol.py"
    sources[str(protocol)] = sha(protocol)
    atomic = ROOT / "runs/plan_batches/e2_launch.py"
    sources[str(atomic)] = sha(atomic)
    for name in ("t17_d14_runner.py", "t17_d14_artifacts.py"):
        source = HERE.parent / "r067_d20_short_tail_v1" / "t17_existing" / name
        sources[str(source)] = sha(source)
    binding = plan.get("input_binding")
    if not isinstance(binding, dict) or set(binding) < {"path", "sha256"}:
        raise RuntimeError("real plan lacks exact-ID input binding")
    input_path = Path(binding["path"])
    if input_path.is_symlink() or not input_path.is_file() or sha(input_path) != binding["sha256"]:
        raise RuntimeError("exact-ID input binding source differs")
    sources[str(input_path)] = binding["sha256"]
    for service in plan["services"]:
        if service["kind"] == "cold":
            schedule = service.get("schedule", {})
            path = Path(schedule.get("path", ""))
            if path.is_symlink() or not path.is_file() or sha(path) != schedule.get("sha256"):
                raise RuntimeError("cold schedule source pin differs")
            sources[str(path)] = schedule["sha256"]
        for key in ("FT_DEV_R067D_OBSERVER_SOURCE",):
            source = Path(service["env"][key])
            sources[str(source)] = sha(source)
        for relative, digest in json.loads(service["env"]["FT_DEV_R067D_IMPORT_PINS"]).items():
            source = Path(service["env"]["FT_DEV_R067D_WORKTREE"]) / relative
            if sha(source) != digest:
                raise RuntimeError("runtime source pin differs: " + str(source))
            sources[str(source)] = digest
    return sources


def controller(admission_path: Path, *, popen=None, d07=None, plan: dict[str, Any] | None = None, materialize: bool = True) -> dict[str, Any]:
    """Create an immutable launch receipt, spawn, then atomically bind birth."""
    _runner, resolved, packet = load_plan(materialize=materialize) if plan is None else (None, plan, None)
    document = admission(admission_path, resolved)
    d07 = d07 or d07_module()
    d07.RID = RID
    d07.CANDIDATE = resolved["commit"]
    owned = d07.load_owned_lifecycle()
    batch, receipt_path = int(document["batch"]), Path(document["receipt_path"])
    argv = child_argv(admission_path, batch, receipt_path)
    reserved = {"schema": "ft_r067d_retry2_owned_launch/v1", "state": "reserved", "rid": RID, "batch": batch, "candidate_commit": resolved["commit"], "argv_sha256": d07.argv_sha256(argv), "controller": d07.process_birth(), "admission_sha256": sha(admission_path), "source_manifest": runtime_sources(resolved, d07), "packet": packet}
    if popen is None:
        helper = owned.verified_module(ROOT / "runs/plan_batches/e2_launch.py", d07.ATOMIC_HELPER_SHA, "r067d_retry2_atomic_launcher")
        receipt = owned.reserve_process(helper, batch, RID, argv, receipt_path, reserved)
        process = SimpleNamespace(pid=receipt["batch_pid"])
    else:
        process = popen(argv, start_new_session=True)
        receipt = {**reserved, "state": "launched", "batch_pid": process.pid}
        put_new(receipt_path, receipt)
    birth = d07.process_identity(process.pid)
    if birth is None or birth.get("pid") != process.pid or not isinstance(birth.get("start_ticks"), int):
        raise RuntimeError("controller cannot bind child PID birth")
    child = {"pid": birth["pid"], "start_ticks": birth["start_ticks"],
             "execution_id": f"{birth['pid']}:{birth['start_ticks']}"}
    # D07 validates the receipt inode before atomic replacement.
    published = d07.publish_child_binding(receipt_path, receipt, child, lifecycle=owned)
    return {"pid": process.pid, "birth": child, "receipt": str(receipt_path), "argv": argv, "receipt_sha256": sha(receipt_path), "packet": packet, "published": published}


def child(admission_path: Path, batch: int, receipt_path: Path, *, d07=None, plan: dict[str, Any] | None = None, effects=None) -> dict[str, Any]:
    """Validate the controller receipt and run the one actual lifecycle."""
    _runner, resolved, _ = load_plan(materialize=False) if plan is None else (None, plan, None)
    document = admission(admission_path, resolved)
    if batch != int(document["batch"]):
        raise RuntimeError("controller-child batch differs")
    d07 = d07 or d07_module()
    d07.RID = RID
    d07.CANDIDATE = resolved["commit"]
    receipt = d07.require_child_receipt(receipt_path, batch, Path(resolved["worktree"]), ROOT / "runs/dev_R067", rid=RID, expected_argv=child_argv(admission_path, batch, receipt_path), schema="ft_r067d_retry2_owned_launch/v1")
    from r067d_retry2_actual import Effects, RUN, UnsafeCleanupError, run_child, wait_gpu_idle
    if effects is None:
        child_identity = receipt["child"]
        run_dir = RUN.parent / f"{RID}_batch{batch}_{child_identity['pid']}_{child_identity['start_ticks']}"
        effects = Effects(d07=d07, owned=d07.load_owned_lifecycle(), plan=resolved, run_dir=run_dir)
    run_dir = getattr(effects, "run_dir", RUN)
    if run_dir.exists() and not isinstance(effects, FakeEffects):
        raise RuntimeError("new child requires a unique, empty run directory")
    owner = d07.take_d07_gpu_lock(RID, batch)
    released = run_started = False
    try:
        run_dir.mkdir(parents=True, exist_ok=isinstance(effects, FakeEffects))
        put_new(run_dir / "launch_binding.json", {"batch": batch, "receipt": str(receipt_path), "receipt_sha256": sha(receipt_path), "admission_sha256": sha(admission_path), "source_manifest": source_manifest(), "runtime_sources": runtime_sources(resolved, d07), "child": receipt["child"], "gpu_owner": owner})
        wait_gpu_idle(d07)
        run_started = True
        terminal = run_child(resolved, batch=batch, effects=effects, run_dir=run_dir)
        wait_gpu_idle(d07)
    except UnsafeCleanupError as exc:
        put_new(run_dir / "unsafe_cleanup.json", {"schema": "ft_r067d_retry2_unsafe_cleanup/v1", "error": repr(exc), "gpu_lock_preserved": True, "product_acceptance": False})
        raise RuntimeError("unsafe cleanup preserves lock: " + repr(exc)) from exc
    except BaseException:
        # A prelaunch or product failure has no unsafe cleanup marker.  Confirm
        # idle before releasing the child-owned D07 lock, then preserve its error.
        if run_started:
            wait_gpu_idle(d07)
        d07.release_d07_gpu_lock(owner)
        released = True
        raise
    else:
        d07.release_d07_gpu_lock(owner)
        released = True
        return terminal
    finally:
        if not released and not (run_dir / "unsafe_cleanup.json").exists():
            # Do not silently retain a lock for a failure that completed cleanup.
            # The except branches above either release it or record why release is unsafe.
            put_new(run_dir / "unsafe_cleanup.json", {"schema": "ft_r067d_retry2_unsafe_cleanup/v1", "error": "child exited before D07 release", "gpu_lock_preserved": True, "product_acceptance": False})


class FakeD07:
    """CPU-only implementation of D07 identities, receipt and cleanup seams."""
    RID = RID
    CANDIDATE = "fake-commit"

    def __init__(self):
        self.gpu_events: list[str] = []

    @staticmethod
    def argv_sha256(argv):
        return hashlib.sha256(json.dumps(argv, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def process_birth():
        return {"pid": 1, "start_ticks": 1, "execution_id": "1:1"}

    @staticmethod
    def process_identity(pid):
        return {"pid": pid, "start_ticks": pid + 100, "execution_id": f"{pid}:{pid + 100}", "pgid": pid, "session": pid, "state": "R"}

    def load_owned_lifecycle(self):
        return SimpleNamespace(publish_receipt=self.publish_receipt, stop_owned_process=lambda *args: None, owned_group_alive=lambda pid: False)

    def take_d07_gpu_lock(self, rid, batch):
        self.gpu_events.append("take")
        return {"owner": rid, "batch": batch, "lock_token": "fake", "lock_inode": 1, "lock_device": 1}

    def release_d07_gpu_lock(self, owner):
        assert owner["owner"] == RID
        self.gpu_events.append("release")

    def require_gpu_idle(self):
        self.gpu_events.append("idle")
        return [0]

    @staticmethod
    def publish_receipt(path, identity, value):
        path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")

    @staticmethod
    def publish_child_binding(path, receipt, child, *, lifecycle):
        value = {**receipt, "child": child}
        lifecycle.publish_receipt(path, (0, 0), value)
        return value

    def require_child_receipt(self, path, batch, worktree, output_root, **kwargs):
        value = json.loads(path.read_text())
        assert value["state"] == "launched" and value["batch"] == batch and value["child"]["pid"] == value["batch_pid"]
        assert set(value["child"]) == {"pid", "start_ticks", "execution_id"}
        assert value["child"]["execution_id"] == f"{value['child']['pid']}:{value['child']['start_ticks']}"
        return value


class FakeEffects:
    """A deterministic CPU fake with observably real lifecycle transitions."""

    def __init__(self, root: Path):
        self.run_dir = root / "run"
        self.run_dir.mkdir()
        self.events: list[str] = []
        self.pid = 200

    def materialize(self, service):
        arm = self.run_dir / "services" / service["name"]
        arm.mkdir(parents=True)
        # Target-Linux file-dry uses the real wrapper/schedule sources and their
        # pins.  Only spawn, HTTP, GPU and lock effects remain fake.
        if "FT_DEV_R067D_STARTUP_SHA256" in service["env"]:
            import shutil
            wrapper = arm / "r067d_retry2_startup.py"
            shutil.copyfile(HERE / "r067d_retry2_startup.py", wrapper)
            assert not wrapper.is_symlink() and sha(wrapper) == service["env"]["FT_DEV_R067D_STARTUP_SHA256"]
            if service["kind"] == "cold":
                source = HERE / "schedules" / f"{service['name']}.json"
                target = arm / "prefill_schedule.json"
                assert source.is_file() and sha(source) == service["schedule"]["sha256"]
                shutil.copyfile(source, target)
                assert sha(target) == service["schedule"]["sha256"]
        self.events.append("materialize:" + service["name"])
        return arm, dict(service["env"])

    def start(self, service, arm, env):
        self.pid += 1
        self.events.append("start:" + service["name"])
        return SimpleNamespace(pid=self.pid, poll=lambda: None, returncode=None)

    def ready(self, service, process, arm):
        self.events.append("ready:" + service["name"])

    def ids(self, service, item, prefix, tail):
        self.events.append("ids:" + service["name"])
        return [1] * (prefix + tail)

    def request(self, service, item, ids, arm, request_label):
        self.events.append("request:" + service["name"] + ":" + request_label)
        prefix = int(service["name"].split("_p", 1)[1].split("_", 1)[0])
        tail = item.get("tail", int(service["name"].rsplit("_t", 1)[1]) if service["kind"] == "cold" else 1)
        cached = prefix if service["kind"] == "hot" and item["role"] != "seed" else 0
        new = tail if cached else len(ids)
        window = f'Prefill batch, #new-seq: 1, #new-token: {new}, #cached-token: {cached}\nPOST /internal/t17/exact-ids HTTP/1.1" 200 OK\n'.encode()
        raw = {"response": {"usage": {"prompt_tokens": len(ids), "cached_tokens": cached, "completion_tokens": item["max_tokens"]}}, "response_sha256": "fake"}
        return raw, window, {"sampled_token_ids": [7] * item["max_tokens"], "raw_text": "fake"}

    def cleanup(self, service, process, arm):
        self.events.append("cleanup:" + service["name"])


def fake_plan(tmp: Path) -> dict[str, Any]:
    services = []
    for prefix in (8192, 8256):
        services.append({"name": f"hot_p{prefix}", "kind": "hot", "env": {}, "argv": ["python"], "requests": [{"role": "seed", "tail": 1, "max_tokens": 2, "input_ids_sha256": "fake"}, {"role": "query", "tail": 1, "max_tokens": 128, "input_ids_sha256": "fake"}, {"role": "query", "tail": 64, "max_tokens": 128, "input_ids_sha256": "fake"}]})
        for tail in (1, 64):
            for arm in ("A", "B"):
                services.append({"name": f"cold_{arm}_p{prefix}_t{tail}", "kind": "cold", "env": {"FT_DEV_COLD_DONOR_GUARD": "1", "FT_DEV_COLD_DONOR_EXPECTED_STATE_SHA256": "fake"}, "argv": ["python"], "request": {"role": "cold_one_shot", "tail": tail, "max_tokens": 128, "input_ids_sha256": "fake"}})
    return {"rid": RID, "commit": "fake-commit", "engine_sha256": "fake", "worktree": str(tmp), "services": services}


def fake_positive(tmp: Path, *, real_plan: bool = False) -> dict[str, Any]:
    _runner, plan, _packet = load_plan(materialize=False) if real_plan else (None, fake_plan(tmp), None)
    admission_path, receipt_path = tmp / "admission.json", tmp / "receipt.json"
    put_new(admission_path, {"schema": "ft_r067d_retry2_admission/v1", "admit": True, "rid": RID, "worktree_commit": plan["commit"], "engine_sha256": plan["engine_sha256"], "source_sha256": source_manifest(), "services_max": 10, "generation_calls_max": 14, "batch": 1, "receipt_path": str(receipt_path)})
    d07 = FakeD07()
    launch = controller(admission_path, popen=lambda argv, **kwargs: SimpleNamespace(pid=7), d07=d07, plan=plan, materialize=False)
    effects = FakeEffects(tmp)
    terminal = child(admission_path, 1, receipt_path, d07=d07, plan=plan, effects=effects)
    assert terminal["actual_services"] == 10 and terminal["actual_generation_calls"] == 14
    assert len([event for event in effects.events if event.startswith("start:")]) == 10
    assert len([event for event in effects.events if event.startswith("request:")]) == 14
    assert len([event for event in effects.events if event.startswith("cleanup:")]) == 10
    return {"schema": "ft_r067d_retry2_cpu_lifecycle/v1", "real_plan_admission": real_plan, "synthetic_effects": ["process", "http", "gpu", "lock"], "controller": launch, "terminal": terminal, "events": effects.events, "gpu_lock_events": d07.gpu_events, "gpu_started": False, "http_generation": False, "service_started": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--owned-child", action="store_true")
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--cpu-fake", type=Path)
    parser.add_argument("--cpu-filedry-real", type=Path)
    args = parser.parse_args()
    if args.cpu_fake:
        print(json.dumps(fake_positive(args.cpu_fake), sort_keys=True))
    elif args.cpu_filedry_real:
        print(json.dumps(fake_positive(args.cpu_filedry_real, real_plan=True), sort_keys=True))
    elif args.run and not args.owned_child:
        print(json.dumps(controller(args.admission), sort_keys=True))
    elif args.run and args.owned_child:
        print(json.dumps(child(args.admission, args.batch, args.receipt), sort_keys=True))
    else:
        parser.error("controller, child, or cpu fake required")


if __name__ == "__main__":
    main()
