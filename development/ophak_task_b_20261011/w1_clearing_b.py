#!/usr/bin/env python3
"""W1 清场记录（任务 B，做法同 A2 的 w1_clearing.py）：记录 GPU 占用、容器和 CPU 占用。只记录，不停止任何进程或容器。

判定规则（原指令 §4 W1）：除 481 与本任务外，凡持续占用 GPU、或 CPU 占用超过 50% 的进程或容器，才需要停止。
拿不准的不停，记下来回报。本脚本只输出候选清单和 stopped=[]；若候选非空，由操作者按规则逐项处理并另记。
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORK = Path(__file__).resolve().parent
OUT = WORK / "CLEARED_B.json"
PRODUCTION_ACTIVE = Path("/data2/FreeToken/run/production.active.json")
CPU_LIMIT_PCT = 50.0


def run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=180).stdout


def ppid_of(pid: int) -> int | None:
    try:
        return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
    except (OSError, ValueError, IndexError):
        return None


def is_under(pid: int, ancestor: int) -> bool:
    seen = set()
    current: int | None = pid
    while current and current not in seen:
        if current == ancestor:
            return True
        seen.add(current)
        current = ppid_of(current)
    return False


def cmdline(pid: int) -> str:
    try:
        return " ".join(a.decode(errors="replace") for a in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if a)
    except OSError:
        return ""


def main() -> None:
    active = json.loads(PRODUCTION_ACTIVE.read_text())
    supervisor = int(active["supervisor"]["pid"]) if "supervisor" in active else int(active["gpu_owner"]["pid"])

    smi_apps = [line for line in run(["nvidia-smi", "--query-compute-apps=pid,process_name,used_memory",
                                      "--format=csv,noheader"]).splitlines() if line.strip()]
    gpu_candidates, gpu_production = [], []
    for line in smi_apps:
        pid = int(line.split(",")[0].strip())
        row = {"pid": pid, "line": line, "cmdline": cmdline(pid)}
        (gpu_production if is_under(pid, supervisor) else gpu_candidates).append(row)

    docker = [line for line in run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"]).splitlines() if line.strip()]

    top_n1 = "\n".join(run(["top", "-b", "-n1"]).splitlines()[:25])
    top_two = run(["top", "-b", "-n2", "-d", "3"]).splitlines()
    frames = [i for i, line in enumerate(top_two) if line.startswith("top -")]
    second = top_two[frames[1]:] if len(frames) > 1 else []
    cpu_candidates = []
    for line in second:
        parts = line.split()
        if len(parts) < 12 or not parts[0].isdigit():
            continue
        try:
            cpu = float(parts[8])
        except ValueError:
            continue
        pid = int(parts[0])
        if cpu > CPU_LIMIT_PCT and not is_under(pid, supervisor) and pid != os.getpid():
            cpu_candidates.append({"pid": pid, "cpu_pct": cpu, "command": " ".join(parts[11:]), "cmdline": cmdline(pid)})

    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    doc = {
        "schema": "ophak_task_b_cleared/v1",
        "recorded_at": now,
        "production_supervisor_pid": supervisor,
        "gpu_compute_apps_production": gpu_production,
        "gpu_compute_apps_other": gpu_candidates,
        "docker_containers": docker,
        "top_n1_head25": top_n1,
        "cpu_over_limit_second_sample_other": cpu_candidates,
        "cpu_limit_pct": CPU_LIMIT_PCT,
        "candidates_to_stop": gpu_candidates + cpu_candidates,
        "stopped": [],
        "restore_commands": [],
        "decision": ("候选为空：GPU 上只有 481 的 worker，无其他 GPU 占用；无进程 CPU 占用超过 50%；"
                     "容器均未占用 GPU。未停止任何进程或容器。" if not (gpu_candidates or cpu_candidates)
                     else "存在候选，未自动停止，需操作者逐项判断后另记。"),
    }
    with OUT.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.chmod(OUT, 0o444)
    print(json.dumps({"candidates": len(doc["candidates_to_stop"]), "gpu_production": len(gpu_production),
                      "cpu_over_limit_other": len(cpu_candidates), "decision": doc["decision"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
