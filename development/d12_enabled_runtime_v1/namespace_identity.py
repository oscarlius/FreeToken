"""Read-only outer-/proc observations for an owned D12 PID namespace.

This module launches nothing and grants no GPU or namespace authority. Callers
must supply the existing owned process's observed birth, retain these results,
and bind them to their own collection/launch receipts before formal use.
"""
from __future__ import annotations

import os
from pathlib import Path
import time


BIRTH = ("pid", "start_ticks", "pgid", "session")
NAMESPACES = ("pid", "user", "mnt", "net")


def _require(value, message):
    if not value:
        raise ValueError("D12 namespace identity: " + message)


def _birth(value):
    _require(isinstance(value, dict) and all(type(value.get(k)) is int and value[k] > 0 for k in BIRTH),
             "positive process birth fields required")
    return {key: value[key] for key in BIRTH}


def _boot():
    return Path("/proc/sys/kernel/random/boot_id").read_text().strip()


def _process(lifecycle, pid):
    identity = lifecycle.process_identity(pid)
    _require(identity is not None and identity.get("state") != "Z", "process is no longer live")
    birth = _birth(identity)
    root = Path("/proc") / str(pid)
    status = dict(line.split(":", 1) for line in (root / "status").read_text().splitlines() if ":" in line)
    fields = (root / "stat").read_text().rpartition(") ")[2].split()
    namespaces = {kind: os.readlink(root / "ns" / kind) for kind in NAMESPACES}
    vectors = {key: list(map(int, status[key].split())) for key in ("NSpid", "NSpgid", "NSsid", "Uid")}
    _require(len(vectors["Uid"]) == 4 and set(vectors["Uid"]) == {os.geteuid()}, "process is outside the observer UID")
    _require(vectors["NSpid"][0] == pid and vectors["NSpgid"][0] == birth["pgid"]
             and vectors["NSsid"][0] == birth["session"]
             and len(vectors["NSpid"]) == len(vectors["NSpgid"]) == len(vectors["NSsid"]),
             "outer namespace PID/group/session vectors disagree")
    again = lifecycle.process_identity(pid)
    _require(again is not None and again.get("state") != "Z" and _birth(again) == birth,
             "process birth changed during observation")
    return {"birth": birth, "ppid": int(fields[1]), "namespaces": namespaces, **vectors}


def _children(pid):
    children = set()
    tasks = list((Path("/proc") / str(pid) / "task").iterdir())
    _require(len(tasks) <= 8192, "owned task observation bound exceeded")
    for task in tasks:
        children.update(map(int, (task / "children").read_text().split()))
    return children


def observe_namespace_init(lifecycle, outer_birth):
    """Bind the new namespace's init to one live, owned outer process."""
    expected = _birth(outer_birth)
    _require(expected["pid"] == expected["pgid"] == expected["session"], "outer process must own its group/session")
    outer = _process(lifecycle, expected["pid"])
    _require(outer["birth"] == expected, "outer process birth differs")
    observer = {kind: os.readlink("/proc/self/ns/" + kind) for kind in NAMESPACES}
    _require(outer["namespaces"]["pid"] == observer["pid"], "outer process is not in the observer PID namespace")
    candidates = []
    for pid in sorted(_children(expected["pid"])):
        member = _process(lifecycle, pid)
        if (member["ppid"] == expected["pid"] and member["NSpid"][-1] == 1
                and len(member["NSpid"]) == len(outer["NSpid"]) + 1
                and member["namespaces"]["pid"] != observer["pid"]):
            candidates.append(member)
    _require(len(candidates) == 1, "owned outer process does not identify one child PID namespace init")
    init = candidates[0]
    _require(init["namespaces"]["net"] == observer["net"]
             and init["namespaces"]["user"] != observer["user"]
             and init["namespaces"]["mnt"] != observer["mnt"], "expected user/mount isolation and shared network are absent")
    root = Path("/proc") / str(init["birth"]["pid"])
    uid_map = [list(map(int, line.split())) for line in (root / "uid_map").read_text().splitlines()]
    gid_map = [list(map(int, line.split())) for line in (root / "gid_map").read_text().splitlines()]
    _require(uid_map == [[0, os.geteuid(), 1]] and gid_map == [[0, os.getegid(), 1]], "root mapping differs from the current user")
    _require(_process(lifecycle, expected["pid"])["birth"] == expected
             and _process(lifecycle, init["birth"]["pid"])["birth"] == init["birth"], "namespace owner changed")
    return {"schema": "ft_d12_owned_pid_namespace/v1", "boot_id": _boot(), "observer_namespaces": observer,
            "observer_uid": os.geteuid(), "outer": outer, "init": init, "uid_map": uid_map, "gid_map": gid_map,
            "observed_monotonic_ns": time.monotonic_ns(), "formal_launch_authorized": False}


def _validate_anchor(lifecycle, anchor):
    _require(anchor.get("schema") == "ft_d12_owned_pid_namespace/v1" and anchor["boot_id"] == _boot()
             and anchor["observer_uid"] == os.geteuid()
             and anchor["observer_namespaces"] == {kind: os.readlink("/proc/self/ns/" + kind) for kind in NAMESPACES},
             "namespace observation domain changed")
    current = observe_namespace_init(lifecycle, anchor["outer"]["birth"])
    _require(all(current[key] == anchor[key] for key in ("outer", "init", "uid_map", "gid_map")),
             "namespace owner or init changed")


def observe_member(lifecycle, anchor, inner_birth):
    """Map a live inner PID/group/session to independently observed outer IDs."""
    expected = _birth(inner_birth)
    _validate_anchor(lifecycle, anchor)
    pending = [anchor["init"]["birth"]["pid"]]
    visited, matches = set(), []
    while pending:
        pid = pending.pop()
        _require(pid not in visited and len(visited) < 4096, "owned process tree changed or exceeded observation bound")
        visited.add(pid)
        identity = lifecycle.process_identity(pid)
        _require(identity is not None, "owned process disappeared during namespace observation")
        if identity.get("state") == "Z":
            continue
        row = _process(lifecycle, pid)
        _require(row["namespaces"]["pid"] == anchor["init"]["namespaces"]["pid"], "unexpected nested PID namespace")
        pending.extend(sorted(_children(pid)))
        if row["NSpid"][-1] == expected["pid"]:
            matches.append(row)
    _require(len(matches) == 1, "inner PID does not identify one live owned member")
    row = matches[0]
    mapped = {"pid": row["NSpid"][-1], "start_ticks": row["birth"]["start_ticks"],
              "pgid": row["NSpgid"][-1], "session": row["NSsid"][-1]}
    _require(mapped == expected, "inner and outer process births differ")
    _require(row["namespaces"] == anchor["init"]["namespaces"], "member escaped the owned namespace set")
    _validate_anchor(lifecycle, anchor)
    _require(_process(lifecycle, row["birth"]["pid"]) == row, "mapped process changed during observation")
    return {"schema": "ft_d12_namespace_member/v1", "namespace_anchor": anchor, "inner_birth": expected,
            "outer_process": row, "observed_monotonic_ns": time.monotonic_ns(),
            "pid_namespace_mapping_verified": True, "model_worker_verified": False,
            "global_listener_exclusivity_verified": False, "formal_launch_authorized": False}
