"""D11-P0 manual precheck v2 (read-only). Prints one JSON object; exit 0 = all gates pass, 3 = some gate fails."""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = "http://172.16.108.9:8095"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # bypass socks5 env proxy
APPROVALS = {"RESTORE481-MORNING-20261011-10", "RESTORE481-MORNING-20261011-11"}
COMMIT = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"
ACTIVE = Path("/data2/FreeToken/run/production.active.json")
STOP_FILE = Path("/data2/FreeToken/plan/GEMINI_D11_P0_STOP.md")
D09_DIR = "/data2/FreeToken/development/gemini_d09_enable_20261011"


def get(path):
    with OPENER.open(BASE + path, timeout=5) as resp:
        return json.load(resp)


def try_(fn, default=None):
    try:
        return fn()
    except Exception as exc:  # each fact degrades to "gate fails", never a crash
        return default if default is not None else {"error": repr(exc)}


def ancestors():
    """This process and every ancestor, so a parent stall_probe.py is not counted as 'another probe'."""
    pids, pid = set(), os.getpid()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        stat = Path(f"/proc/{pid}/stat").read_text()
        pid = int(stat.rsplit(")", 1)[1].split()[1])
    return pids


def procs(pred):
    skip = ancestors()
    out = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit() or int(d.name) in skip:
            continue
        try:
            argv = [a.decode(errors="replace") for a in (d / "cmdline").read_bytes().split(b"\0") if a]
            cwd = os.readlink(d / "cwd")
        except OSError:
            continue
        if argv and pred(argv, cwd):
            out.append(int(d.name))
    return sorted(out)


active = try_(lambda: json.loads(ACTIVE.read_text()), {})
health = try_(lambda: get("/health"), {})
stats = try_(lambda: get("/v1/stats"), {})
ring = try_(lambda: get("/v1/requests?since=0&limit=512"), {})
lock = try_(lambda: json.loads(Path("/data2/_shared/gpu.lock").read_text()), {})
docker = try_(lambda: subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True,
                                     text=True, timeout=20).stdout.split(), [])
gpu_mib = try_(lambda: int(subprocess.check_output(
    ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
    text=True, timeout=20).strip().splitlines()[0]), -1)
serves = procs(lambda a, c: "serve" in a and any(x.endswith("/ft") for x in a))
probes = procs(lambda a, c: any(Path(x).name == "stall_probe.py" for x in a))
d09 = procs(lambda a, c: c.startswith(D09_DIR) and any(Path(x).name in ("runner.py", "b_runner.py") for x in a))
entries = ring.get("entries") or []
facts = {
    "approval_id": active.get("approval_id"),
    "commit": active.get("commit"),
    "service_pid": (active.get("service") or {}).get("pid"),
    "serve_log": active.get("log"),
    "health": [health.get("status"), health.get("maintenance"), health.get("backend_epoch"),
               health.get("restart_attempts")],
    "stats_active": (stats.get("requests") or {}).get("active"),
    "stats_completed": (stats.get("requests") or {}).get("completed"),
    "ring_next": ring.get("next_cursor"),
    "ring_last_ts": entries[-1]["ts"] if entries else None,
    "ft_serve_pids": serves,
    "other_stall_probe_pids": probes,
    "d09_window_pids": d09,
    "gpu_lock_owner": lock.get("owner"),
    "gemini_stop_file": STOP_FILE.exists(),
    "ollama_running": "ollama" in docker,
    "loadavg_1m": round(os.getloadavg()[0], 2),
    "gpu_mem_used_mib": gpu_mib,
}
gates = {
    "approval": facts["approval_id"] in APPROVALS and facts["commit"] == COMMIT,
    "serving": facts["health"][:2] == ["ok", "serving"],
    "restart_budget_intact": facts["health"][2] == 0 and facts["health"][3] == 0,
    "idle_now": facts["stats_active"] == 0,
    "single_ft_serve_is_production": bool(serves) and serves == [facts["service_pid"]],
    "no_other_probe": probes == [],
    "no_d09_window": d09 == [],
    "gpu_lock_is_production": facts["gpu_lock_owner"] == f"production:release:{facts['approval_id']}",
    "no_gemini_stop": not facts["gemini_stop_file"],
    "ollama_stopped": not facts["ollama_running"],
}
print(json.dumps({"facts": facts, "gates": gates, "all_pass": all(gates.values())}, ensure_ascii=False, indent=1))
sys.exit(0 if all(gates.values()) else 3)
