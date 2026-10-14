#!/usr/bin/env python3
"""窗口监视（只读）：每 20 秒查看窗口目录。不发送任何信号，不改任何文件。

退出条件（立即打印事件并退出，让操作者马上报告）：
- 出现 CLEANUP_BLOCKED.md（清场失败）；
- 出现 window_summary.json（窗口已结束，打印终态）；
- 累计两次服务死亡（OOM、worker 退出或启动失败）。
每次服务状态变化时打印一行快照。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

DEATHS = {"oom", "worker_exit", "launch_failed"}


def snapshot(window: Path) -> list[tuple[str, str, object]]:
    rows = []
    for svc in sorted(p for p in window.iterdir() if p.is_dir()):
        summary = svc / "summary.json"
        if summary.exists():
            doc = json.loads(summary.read_text(encoding="utf-8"))
            rows.append((svc.name, str(doc.get("status")), doc.get("done")))
        else:
            rows.append((svc.name, "not_done", None))
    return rows


def main() -> int:
    window = Path(sys.argv[1])
    while not window.exists():
        time.sleep(5)
    last = None
    while True:
        if (window / "CLEANUP_BLOCKED.md").exists():
            print("EVENT cleanup_blocked", (window / "CLEANUP_BLOCKED.md").read_text(encoding="utf-8").strip(), flush=True)
            return 2
        if (window / "window_summary.json").exists():
            doc = json.loads((window / "window_summary.json").read_text(encoding="utf-8"))
            print("EVENT window_summary terminal=", doc["terminal"], "deaths=", doc["deaths"], flush=True)
            return 0
        rows = snapshot(window)
        if rows != last:
            print(time.strftime("%H:%M:%S"), rows, flush=True)
            last = rows
        deaths = [row for row in rows if row[1] in DEATHS]
        if len(deaths) >= 2:
            print("EVENT second_death", deaths, flush=True)
            return 4
        time.sleep(20)


if __name__ == "__main__":
    raise SystemExit(main())
