#!/usr/bin/env python3
"""A2 窗口进度（只读）：每个服务的记录条数、状态、就绪与结束标记、serve.log 中的 OOM / worker 标记，以及 GPU 显存。

不写任何文件，不发送请求，不改变进程。运行目录与窗口进程 PID 从命令行给出。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

RUN = Path("/data2/FreeToken/runs/dev_ophak_task_a2_20261011/window02")
WINDOW = RUN / "window"
SERVICES = ("A1_on", "B1_off", "B2_off", "A2_on")
MARKERS = ("out of memory", "backend worker", "worker_restarting")


def rows_of(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(pid: int) -> None:
    print(time.strftime("%H:%M:%S"), "runner", "alive" if Path(f"/proc/{pid}").exists() else "gone")
    for svc in SERVICES:
        directory = WINDOW / svc
        if not directory.exists():
            continue
        rows = rows_of(directory / "requests.jsonl")
        log_path = directory / "serve.log"
        log = log_path.read_text(encoding="utf-8", errors="replace").splitlines() if log_path.exists() else []
        hits = [line[:140] for line in log if any(m in line.lower() for m in MARKERS)]
        statuses = sorted({str(r.get("status")) for r in rows})
        print(f"{svc}: records={len(rows)} statuses={statuses} ready={(directory / 'memory_ready.json').exists()} "
              f"done={(directory / 'summary.json').exists()} log_lines={len(log)} markers={len(hits)}")
        if rows:
            last = rows[-1]
            ttft = last.get("ttft_s")
            print(f"   last {last.get('key')} {last.get('status')} ttft={None if ttft is None else round(ttft, 2)} "
                  f"total={round(last.get('total_s') or 0, 1)} mem={last.get('memory_before_mib')}->{last.get('memory_after_mib')}")
        for hit in hits[:2]:
            print("   MARK", hit)
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"],
                         capture_output=True, text=True).stdout.strip()
    print("gpu", gpu)


if __name__ == "__main__":
    main(int(sys.argv[1]))
