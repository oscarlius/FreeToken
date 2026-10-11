"""Root-only, no-side-effect preflight for R067d-retry2.

This is intentionally not a launcher.  It renders one exact fresh-RID service
plan and validates imports, source pins, schedules and native ABI reuse before
an independently reviewed root-controlled execution may exist.
"""
from __future__ import annotations
import hashlib, json, os, subprocess
from pathlib import Path
import r067e_packet as packet

HERE = Path(__file__).resolve().parent
WORKTREE = Path("/data2/FreeToken/wt/r067e-20261010")
COMMIT = "b86190d78be3b1b4b55f989c98ce963630e425dd"
OBSERVER = Path("/data2/FreeToken/development/r067d_short_tail_retry1_20261010/tooling/t17_d14_observe.py")
ROUTE_STARTUP = Path("/data2/FreeToken/development/r067d_short_tail_retry1_20261010/tooling/t17_d14_startup.py")
STARTUP = HERE / "r067e_startup.py"
IMPORT_SOURCES = ("python/freetoken/engine/engine.py", "python/freetoken/kvcache/linear_state_pool.py", "python/freetoken/models/qwen4_exp/ple.py")
BASE = packet.RETRY1 / "R067D_RETRY1_CONFIG_CPU_ONLY.json"


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def input_hash(service: dict) -> str:
    return service["request"]["input_ids_sha256"]


def build_plan() -> dict:
    base = json.loads(BASE.read_text())
    input_binding = dict(base["input_binding"])
    input_path = Path(input_binding["path"])
    if not input_path.is_file() or sha(input_path) != input_binding["sha256"]:
        raise RuntimeError("exact-ID input binding differs from retry1 pin")
    services = []
    hot_hash = {prefix: packet.state_bundle_hash(Path(f"{packet.HOT_RUN}/hot_p{prefix}/state_dump"))
                for prefix in (8192, 8256)}
    for old in base["services"]:
        service = json.loads(json.dumps(old))
        name = service["name"]
        arm = f"{packet.REMOTE_RUN}/services/{name}"
        service["worktree"] = str(WORKTREE)
        service["service_dir"] = service["cwd"] = arm
        service["argv"][5] = f"{arm}/r067e_startup.py"
        service["env"].update({
            "FT_DEV_STATE_DUMP": f"{arm}/state_dump",
            "FT_T17_INPUT_RECEIPTS": f"{arm}/input_receipts",
            "FT_T17_OBSERVATIONS": f"{arm}/observations.jsonl",
            "PYTHONPATH": f"{arm}:{WORKTREE}/python",
        })
        source_pins = {relative: sha(WORKTREE / relative) for relative in IMPORT_SOURCES}
        service["env"].update({
            "FT_DEV_R067E_WORKTREE": str(WORKTREE), "FT_DEV_R067E_WORKTREE_COMMIT": COMMIT,
            "FT_DEV_R067E_ENGINE_SHA256": sha(WORKTREE / "python/freetoken/engine/engine.py"),
            "FT_DEV_R067E_ROUTE_SOURCE": str(ROUTE_STARTUP), "FT_DEV_R067E_ROUTE_SOURCE_SHA256": sha(ROUTE_STARTUP),
            "FT_DEV_R067E_STARTUP_SHA256": sha(STARTUP), "FT_DEV_R067E_IMPORT_PINS": json.dumps(source_pins, sort_keys=True),
        })
        if service["kind"] == "cold":
            prefix = int(name.split("_p", 1)[1].split("_", 1)[0])
            tail = int(name.rsplit("_t", 1)[1])
            service["env"].update({
                "FT_DEV_COLD_DONOR_GUARD": "1", "FT_DEV_COLD_DONOR_BOUNDARY": str(prefix),
                "FT_DEV_COLD_DONOR_EXPECTED_STATE_SHA256": hot_hash[prefix],
                "FT_DEV_COLD_DONOR_INPUT_IDS_SHA256": input_hash(service),
                "FT_DEV_PREFILL_SCHEDULE": f"{packet.REMOTE_DEV}/schedules/{name}.json",
            })
            schedule_path = HERE / "schedules" / f"{name}.json"
            if schedule_path.is_symlink() or not schedule_path.is_file():
                raise RuntimeError("retry2 cold schedule source absent: " + str(schedule_path))
            inherited = dict(service["schedule"])
            service["schedule"] = {"path": str(schedule_path), "sha256": sha(schedule_path),
                                   "derived_from": inherited["path"], "inherited_sha256": inherited["sha256"]}
            assert "--cache-type" not in service["argv"]
        else:
            for key in list(service["env"]):
                assert not key.startswith("FT_DEV_COLD_DONOR_")
        services.append(service)
    assert len(services) == 10 and sum(len(x.get("requests", [x.get("request")])) for x in services) == 14
    return {"rid": packet.RID, "worktree": str(WORKTREE), "commit": COMMIT,
            "engine_sha256": sha(WORKTREE / "python/freetoken/engine/engine.py"),
            "observer_sha256": sha(OBSERVER), "services": services,
            "input_binding": input_binding,
            "budget": {"services": 10, "generation_calls": 14},
            "cold_schedule_derivation": "[0,512) ordinary; recorded hot layer-major subblocks; one-token rewind plus configured tail",
            "execution": "root-only after independent review; this file does not start processes"}


def filedry() -> dict:
    assert subprocess.check_output(["git", "-C", str(WORKTREE), "rev-parse", "HEAD"], text=True).strip() == COMMIT
    assert not subprocess.check_output(["git", "-C", str(WORKTREE), "status", "--porcelain", "--untracked-files=all"], text=True)
    code = "import freetoken.engine.engine as e; assert hasattr(e.Engine, '_verify_dev_cold_donor_guard')"
    env = dict(os.environ, PYTHONPATH=str(WORKTREE / "python"), CUDA_VISIBLE_DEVICES="", PYTHONDONTWRITEBYTECODE="1")
    subprocess.run(["/data2/FreeToken/venv/bin/python", "-c", code], cwd=WORKTREE, env=env, check=True)
    return build_plan()


def materialize_root_packet() -> dict:
    """Write the sole root-reviewable execution packet; never start a process."""
    source = {8192: Path(f"{packet.HOT_RUN}/hot_p8192/observations.jsonl"),
              8256: Path(f"{packet.HOT_RUN}/hot_p8256/observations.jsonl")}
    schedules = packet.render_packet(source, {8192: Path(f"{packet.HOT_RUN}/hot_p8192/state_dump/donate_0001_dev_conv_states.pt"),
                                               8256: Path(f"{packet.HOT_RUN}/hot_p8256/state_dump/donate_0001_dev_conv_states.pt")})["schedules"]
    schedule_dir = HERE / "schedules"
    schedule_dir.mkdir(exist_ok=False)
    base_services = json.loads(BASE.read_text())["services"]
    for service in base_services:
        if service["kind"] != "cold":
            continue
        prefix = int(service["name"].split("_p", 1)[1].split("_", 1)[0])
        tail = int(service["name"].rsplit("_t", 1)[1])
        seed = schedules[f"p{prefix}"]["schedule"][:2]
        schedule = [*seed, {"start": prefix, "end": prefix + tail, "mode": "ordinary", "subchunks": [tail]}]
        packet.parse_schedule(schedule)
        target = schedule_dir / f"{service['name']}.json"
        target.write_text(json.dumps(schedule, indent=2) + "\n")
    plan = filedry()
    target = HERE / "R067E_ROOT_PACKET.json"
    assert not target.exists(), target
    target.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    return {"packet": str(target), "packet_sha256": sha(target), "schedule_count": 8,
            "gpu_started": False, "http_generation": False, "service_started": False}
