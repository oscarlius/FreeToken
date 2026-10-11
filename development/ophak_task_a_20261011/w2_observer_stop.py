#!/usr/bin/env python3
"""W2：停止 -10 观察器（原指令 §4 W2，做法同 GEMINI_OOM §5.2）。

先核对身份（pid、start_ticks、pgrp、cmdline、cwd 与事先核对的值一致），并确认进程组只含观察器自己的两个进程；
再对进程组发 SIGTERM。不用 SIGKILL：超时仍未退出时只报告，不升级。
观察器是只读的看门狗，不发送生成请求。回执写在本工装目录，不写入 Gemini 的证据目录。
"""
from __future__ import annotations

import json
import os
import signal
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORK = Path(__file__).resolve().parent
RUN = "/data2/FreeToken/runs/production/RESTORE481-MORNING-20261011-10"
SAMPLES = Path(RUN) / "overnight_observation" / "samples.jsonl"
GROUP = 2635718
EXPECT = {
    2635718: {"start_ticks": 180885750, "must_contain": "post_night_observer.py"},
    2635719: {"start_ticks": 180885754, "must_contain": f"observe_overnight.py --run-dir {RUN}"},
}
OUT = WORK / "W2_OBSERVER_STOP.json"
WAIT_S = 30.0


def now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def identity(pid: int) -> dict | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except OSError:
        return None
    return {"pid": pid, "state": fields[0], "ppid": int(fields[1]), "pgrp": int(fields[2]),
            "session": int(fields[3]), "start_ticks": int(fields[19]), "cmdline": cmd, "cwd": cwd}


def group_members(pgrp: int) -> list[int]:
    out = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        info = identity(int(entry.name))
        if info and info["pgrp"] == pgrp and info["state"] != "Z":
            out.append(info["pid"])
    return sorted(out)


def alive(pid: int) -> bool:
    info = identity(pid)
    return info is not None and info["state"] != "Z"


def main() -> int:
    before = {pid: identity(pid) for pid in EXPECT}
    problems = []
    for pid, spec in EXPECT.items():
        info = before[pid]
        if info is None:
            problems.append(f"{pid} 已不存在")
            continue
        if info["start_ticks"] != spec["start_ticks"]:
            problems.append(f"{pid} start_ticks 不符（可能是 pid 复用）")
        if spec["must_contain"] not in info["cmdline"]:
            problems.append(f"{pid} cmdline 不符")
        if info["pgrp"] != GROUP:
            problems.append(f"{pid} pgrp={info['pgrp']} 不是 {GROUP}")
    members = group_members(GROUP)
    if set(members) - set(EXPECT):
        problems.append(f"进程组 {GROUP} 含其他进程：{members}")
    receipt = {"schema": "ophak_task_a_w2_observer_stop/v1", "started_at": now(), "run_dir": RUN,
               "group": GROUP, "identity_before": before, "group_members_before": members,
               "problems": problems, "signal": "SIGTERM (process group)", "sigkill_used": False}
    samples_before = sum(1 for _ in SAMPLES.open(encoding="utf-8"))
    receipt["samples_before"] = samples_before
    if problems:
        receipt["result"] = "refused"
        OUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"result": "refused", "problems": problems}, ensure_ascii=False))
        return 3
    os.killpg(GROUP, signal.SIGTERM)
    t0 = time.monotonic()
    while time.monotonic() - t0 < WAIT_S and any(alive(pid) for pid in EXPECT):
        time.sleep(0.5)
    still = [pid for pid in EXPECT if alive(pid)]
    receipt["sent_at"] = now()
    receipt["waited_s"] = round(time.monotonic() - t0, 1)
    receipt["still_alive"] = still
    receipt["result"] = "stopped" if not still else "timeout_no_kill"
    receipt["samples_after"] = sum(1 for _ in SAMPLES.open(encoding="utf-8"))
    OUT.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"result": receipt["result"], "still_alive": still,
                      "samples_before": samples_before, "samples_after": receipt["samples_after"]}, ensure_ascii=False))
    return 0 if not still else 4


if __name__ == "__main__":
    raise SystemExit(main())
