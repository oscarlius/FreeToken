"""Ordinary D12 requests and external process observations for an existing owner.

The reviewed owner alone starts/stops the service and holds its GPU lock. This
adapter adds no launch loop, readiness generation, round allocator, or verdict.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time

from ordinary_sse import _read
from replay_binding import load_replay_binding
from sse_compare import read_native_sse


WIRE_SOURCES = {
    "r049_t21_ordinary_adapter_v8.py": "7458363af04afc65a7453bc1a68ca0ee890b6ec2a8139d4f65b275f5cdcacd24",
    "r046c_t06_ordinary_client_v2.py": "fd82d4bfa46f157040465a0551f85e2a76115f7aafc51c565f260e2e9177a6ce",
}
_BIRTH = ("pid", "start_ticks", "pgid", "session")


def _require(condition, message):
    if not condition:
        raise ValueError("D12 ordinary evidence: " + message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _pid_domain():
    _require(int(Path("/proc/self/stat").read_text().split(" ", 1)[0]) == os.getpid(),
             "/proc view does not match the observer PID namespace")
    return {"boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "pid_namespace": os.readlink("/proc/self/ns/pid")}


def _write(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with Path(path).open("xb") as stream:
        stream.write(raw)
    return {"path": str(path), "sha256": _sha(raw)}


def load_wire_adapter(root):
    root = Path(root).absolute()
    for name, digest in WIRE_SOURCES.items():
        _read(root / name, digest)
    path = root / "r049_t21_ordinary_adapter_v8.py"
    spec = importlib.util.spec_from_file_location("d12_pinned_ordinary_wire", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observe_owned_listener(lifecycle, frontend, port):
    """Observe current-UID holders in the observer PID namespace, including escapees.

    Unprivileged /proc evidence cannot establish cross-UID or continuous socket
    exclusivity. The receipt explicitly preserves both limitations.
    """
    domain = _pid_domain()
    _require(type(port) is int and 1024 <= port < 65535 and port not in (8095, 8099), "private port required")
    current = lifecycle.process_identity(frontend["pid"])
    _require(current is not None and current.get("state") != "Z"
             and all(current.get(key) == frontend.get(key) for key in _BIRTH)
             and frontend["pid"] == frontend["pgid"] == frontend["session"], "frontend listener owner changed")
    scanned_uid = os.getuid()
    _require(scanned_uid == os.geteuid() == Path(f"/proc/{frontend['pid']}").stat().st_uid,
             "frontend is not owned by the current UID")
    namespace = os.readlink(f"/proc/{frontend['pid']}/ns/net")
    _require(namespace == os.readlink("/proc/self/ns/net"), "listener is in a different network namespace")
    _require(os.readlink(f"/proc/{frontend['pid']}/ns/pid") == domain["pid_namespace"],
             "frontend is in a different PID namespace")
    inodes = set()
    for line in Path(f"/proc/{frontend['pid']}/net/tcp").read_text().splitlines()[1:]:
        fields = line.split()
        address, number = fields[1].split(":")
        if fields[3] == "0A" and int(number, 16) == port and address in ("0100007F", "00000000"):
            inodes.add(fields[9])
    _require(len(inodes) == 1, "loopback port does not identify one listening socket")
    inode = next(iter(inodes))
    holders = []
    for entry in sorted(Path("/proc").iterdir(), key=lambda path: path.name):
        if not entry.name.isdecimal():
            continue
        try:
            status = (entry / "status").read_text().splitlines()
        except (FileNotFoundError, ProcessLookupError):
            continue
        uids = [line.split()[1:] for line in status if line.startswith("Uid:")]
        _require(len(uids) == 1 and len(uids[0]) == 4, "process UID observation is incomplete")
        if scanned_uid not in map(int, uids[0]):
            continue
        identity = lifecycle.process_identity(int(entry.name))
        _require(identity is not None, "current-UID process disappeared during listener scan")
        if identity.get("state") == "Z":
            continue
        # Do not filter by group or namespace before inspecting descriptors:
        # a child can keep an inherited socket after setsid() or setns().
        with os.scandir(entry / "fd") as descriptors:
            matches = [fd.path for fd in descriptors if os.readlink(fd.path) == "socket:[" + inode + "]"]
        again = lifecycle.process_identity(identity["pid"])
        _require(again is not None and all(again.get(key) == identity.get(key) for key in _BIRTH),
                 "process birth changed during listener scan")
        if not matches:
            continue
        _require(again.get("state") != "Z" and again["pgid"] == frontend["pgid"]
                 and again["session"] == frontend["session"], "listener is outside the owned process group")
        _require(os.readlink(entry / "ns/net") == namespace, "listener holder network namespace differs")
        _require(os.readlink(entry / "ns/pid") == domain["pid_namespace"], "listener holder PID namespace differs")
        holders.append({"birth": again, "descriptors": matches})
    _require(holders, "no current-UID holder of the listener was observed")
    for holder in holders:
        expected = holder["birth"]
        again = lifecycle.process_identity(expected["pid"])
        _require(again is not None and again.get("state") != "Z"
                 and all(again.get(key) == expected.get(key) for key in _BIRTH)
                 and os.readlink(f"/proc/{expected['pid']}/ns/net") == namespace
                 and os.readlink(f"/proc/{expected['pid']}/ns/pid") == domain["pid_namespace"]
                 and all(os.readlink(fd) == "socket:[" + inode + "]" for fd in holder["descriptors"]),
                 "listener holder changed during observation")
    _require(_pid_domain() == domain, "observer PID domain changed during listener scan")
    return {"schema": "ft_d12_owned_listener/v2", "pid_domain": domain, "port": port, "socket_inode": inode,
            "network_namespace": namespace, "listener_birth": holders[0]["birth"], "holders": holders,
            "scanned_uid": scanned_uid, "same_uid_listener_exclusivity_verified": True,
            "global_listener_exclusivity_verified": False,
            "scope": "point-in-time current-UID observation within observer PID namespace; no continuous, cross-UID or outer-namespace exclusivity",
            "observed_monotonic_ns": time.monotonic_ns(), "observed_time_ns": time.time_ns()}


def read_wire_response(api_path, *, api_sha256, payload_path, payload_sha256,
                       expected_uid, api_source, ordinary_client, wire_root):
    """Bind v8 API/event clocks to native SSE; preserve the diagnostic timings."""
    api_path, payload_path = Path(api_path).absolute(), Path(payload_path).absolute()
    adapter = load_wire_adapter(wire_root)
    api = json.loads(_read(api_path, api_sha256))
    raw_path, clocks = api_path.with_suffix(".sse"), api_path.with_suffix(".events.jsonl")
    _require(api.get("schema") == "ft_r049_ordinary_sse_stream/v1"
             and api.get("pause_enabled") is False and api.get("ft_dev_ack") is False
             and api.get("uid") == expected_uid and type(api.get("uid")) is int
             and api.get("input_sha256") == payload_sha256
             and api.get("payload_source") == {"path": str(payload_path), "sha256": payload_sha256}
             and api.get("sse") == str(raw_path) and api.get("events") == str(clocks)
             and api.get("raw_sse_sha256") == api.get("sse_sha256"), "API source/UID/path binding differs")
    raw = _read(raw_path, api["sse_sha256"])
    decoded = read_native_sse(raw_path, payload_path, raw_sha=api["sse_sha256"],
        payload_sha=payload_sha256, expected_uid=expected_uid, api_source=api_source, ordinary_client=ordinary_client)
    completion = decoded["completion"]
    _require(api["usage"] == decoded["wire_usage"]
             and api["finish_reason"] == completion["choices"][0]["finish_reason"], "API differs from decoded SSE")
    observed = [json.loads(line) for line in _read(clocks, api["events_sha256"]).splitlines()]
    chunks = [json.loads(line[6:]) for line in raw.splitlines()
              if line.startswith(b"data: ") and line != b"data: [DONE]"]
    _require(observed and [row.get("event") for row in observed] == chunks, "event clocks differ from raw SSE")
    previous = api.get("dispatch_monotonic_ns")
    _require(type(previous) is int and previous > 0 and type(api.get("dispatch_time_ns")) is int
             and api["dispatch_time_ns"] > 0, "dispatch clock missing")
    first = terminal = None
    for row in observed:
        mono, wall = row.get("monotonic_ns"), row.get("time_ns")
        _require(type(mono) is int and mono >= previous and type(wall) is int and wall > 0,
                 "event clock order differs")
        previous = mono
        if first is None and adapter._first_real(row["event"]):
            first = {"monotonic_ns": mono, "time_ns": wall}
        if any(choice.get("finish_reason") is not None for choice in row["event"].get("choices") or []):
            _require(terminal is None, "multiple terminal clocks")
            terminal = {"monotonic_ns": mono, "time_ns": wall}
    _require(terminal is not None and api.get("first_output_event") == first
             and api.get("terminal_event") == terminal, "first-output/terminal clock differs")
    for path, digest in ((api_path, api_sha256), (raw_path, api["sse_sha256"]),
                         (clocks, api["events_sha256"]), (payload_path, payload_sha256)):
        _read(path, digest)
    load_wire_adapter(wire_root)
    return {"api": {"path": str(api_path), "sha256": api_sha256},
            "sse": {"path": str(raw_path), "sha256": api["sse_sha256"]},
            "clocks": {"path": str(clocks), "sha256": api["events_sha256"]},
            "decoded": decoded, "timing_scope": "diagnostic wire clocks; not performance acceptance"}


def observe_live_worker(lifecycle, frontend, capture, *, execution_id, expected_uids):
    """Authenticate admission identity against the owner's live /proc group."""
    domain = _pid_domain()
    current = lifecycle.process_identity(frontend["pid"])
    _require(current is not None and current.get("state") != "Z"
             and all(current.get(key) == frontend.get(key) for key in _BIRTH)
             and frontend["pid"] == frontend["pgid"] == frontend["session"], "owned frontend birth differs")
    paths = sorted((Path(capture) / "admissions").glob("*.json"))
    records = []
    for path in paths:
        raw = _read(path, _sha(path.read_bytes()))
        records.append((path, _sha(raw), json.loads(raw)))
    _require([row["uid"] for _, _, row in records] == expected_uids and expected_uids,
             "actual admission order differs")
    worker = records[0][2]["process_identity"]
    _require(all(row["schema"] == "ft_equiv_service_admission/v1" and row["process_identity"] == worker
                 for _, _, row in records)
             and worker["execution_id"] == execution_id + ":tp0" and worker["pid"] != frontend["pid"],
             "admissions do not name the independent TP1 worker")
    birth = lifecycle.process_identity(worker["pid"])
    _require(birth is not None and birth.get("state") != "Z"
             and birth["start_ticks"] == worker["start_ticks"] and birth["pgid"] == frontend["pgid"]
             and birth["session"] == frontend["session"], "worker birth/group/session differs")
    again = lifecycle.process_identity(frontend["pid"])
    _require(again is not None and again.get("state") != "Z"
             and all(again.get(key) == frontend.get(key) for key in _BIRTH), "frontend changed during worker observation")
    _require(all(os.readlink(f"/proc/{pid}/ns/pid") == domain["pid_namespace"]
                 for pid in (frontend["pid"], worker["pid"])) and _pid_domain() == domain,
             "worker/frontend PID domain differs")
    return {"schema": "ft_d12_live_owned_worker/v2", "pid_domain": domain, "worker_identity": worker,
            "worker_birth": birth, "frontend_birth": current,
            "observed_monotonic_ns": time.monotonic_ns(), "observed_time_ns": time.time_ns(),
            "admission_sha256": {str(path): digest for path, digest, _ in records}}


def collect_requests(owner, *, capture, execution_id, input_root, input_sha256,
                     output, api_source, ordinary_client, wire_root, timeout=1800):
    """Send the frozen three requests through an already running reviewed owner.

    The caller must use health-only readiness. This checks the live owned birth
    before every request and never starts, retries, or stops a model service.
    """
    lifecycle = owner.owned_lifecycle()
    domain = _pid_domain()
    frontend = owner.service_birth
    _require(owner.proc is not None and owner.proc.pid == frontend["pid"]
             and type(owner.port) is int and 1024 <= owner.port < 65535
             and not {owner.port, owner.port + 1} & {8095, 8099}, "owned service/port required")
    endpoint = f"http://127.0.0.1:{owner.port}/v1"
    input_root, output = Path(input_root).absolute(), Path(output).absolute()
    _require(output.resolve() == output, "physical new output required")
    binding = load_replay_binding(input_root, input_sha256)
    index = json.loads(_read(input_root / "binding.json", input_sha256))
    specs = index["selected_history"]
    output.mkdir(parents=True, exist_ok=False)
    _write(output / "owned_frontend.json", frontend)
    responses, worker = {}, None
    for row in specs:
        uid = row["uid"]
        current = lifecycle.process_identity(frontend["pid"])
        _require(owner.proc.poll() is None and current is not None and current.get("state") != "Z"
                 and all(current.get(key) == frontend.get(key) for key in _BIRTH), "frontend changed before request")
        payload = input_root / row["payload_path"]
        raw_payload = _read(payload, row["payload_sha256"])
        # This is the exact serialization in the pinned ordinary wire client;
        # retain both original file SHA and transmitted JSON byte encoding.
        body = json.dumps(json.loads(raw_payload), ensure_ascii=False, separators=(",", ":")).encode()
        body_path = output / f"uid-{uid}.request-body.json"
        with body_path.open("xb") as stream:
            stream.write(body)
        api_path = output / f"uid-{uid}.api.json"
        listener_before = observe_owned_listener(lifecycle, frontend, owner.port)
        before_binding = _write(output / f"uid-{uid}.listener-before.json", listener_before)
        adapter = load_wire_adapter(wire_root)
        adapter.ordinary_stream_request(endpoint, payload, api_path, timeout)
        listener_after = observe_owned_listener(lifecycle, frontend, owner.port)
        _require(listener_before["pid_domain"] == listener_after["pid_domain"] == domain
                 and listener_before["socket_inode"] == listener_after["socket_inode"]
                 and listener_before["network_namespace"] == listener_after["network_namespace"]
                 and [{key: item["birth"][key] for key in _BIRTH} for item in listener_before["holders"]]
                 == [{key: item["birth"][key] for key in _BIRTH} for item in listener_after["holders"]],
                 "listener changed during request")
        response = read_wire_response(api_path, api_sha256=_sha(api_path.read_bytes()), payload_path=payload,
            payload_sha256=row["payload_sha256"], expected_uid=uid, api_source=api_source,
            ordinary_client=ordinary_client, wire_root=wire_root)
        proof = observe_live_worker(lifecycle, frontend, capture, execution_id=execution_id,
                                    expected_uids=list(range(uid + 1)))
        _require(proof["pid_domain"] == domain, "worker observation PID domain changed")
        _require(worker is None or proof["worker_identity"] == worker, "scheduler worker changed between requests")
        worker = proof["worker_identity"]
        response["live_worker"] = _write(output / f"uid-{uid}.live-worker.json", proof)
        response["listener_before"] = before_binding
        response["listener_after"] = _write(output / f"uid-{uid}.listener-after.json", listener_after)
        response["request_body"] = {"path": str(body_path), "sha256": _sha(body)}
        responses[str(uid)] = response
    _require(load_replay_binding(input_root, input_sha256) == binding, "frozen input changed during requests")
    _require(_pid_domain() == domain, "collection PID domain changed")
    result = {"schema": "ft_d12_ordinary_request_collection/v2", "pid_domain": domain, "responses": responses,
              "worker_identity": worker, "frontend_birth": frontend, "bundle_sha256": input_sha256,
              "wire_source_sha256": WIRE_SOURCES, "output_equivalence_verified": False,
              "worker_stopped_verified": False, "performance_eligible": False,
              "listener_observation_scope": "current UID within observer PID namespace, request boundary samples only",
              "global_listener_exclusivity_verified": False}
    _write(output / "collection.json", result)
    return result


def record_stopped_worker(lifecycle, output, *, collection_path, collection_sha256):
    """Persist independent observations after the existing owner's stop returns."""
    collection_path = Path(collection_path).absolute()
    collection = json.loads(_read(collection_path, collection_sha256))
    domain = _pid_domain()
    _require(collection.get("schema") == "ft_d12_ordinary_request_collection/v2"
             and collection.get("pid_domain") == domain
             and set(collection["responses"]) == {"0", "1", "2"}, "three-request collection required")
    proofs = []
    for uid in range(3):
        binding = collection["responses"][str(uid)]["live_worker"]
        expected_path = collection_path.parent / f"uid-{uid}.live-worker.json"
        _require(binding["path"] == str(expected_path), "collection worker proof path differs")
        proof = json.loads(_read(expected_path, binding["sha256"]))
        _require(proof.get("schema") == "ft_d12_live_owned_worker/v2" and proof.get("pid_domain") == domain
                 and proof["worker_identity"] == collection["worker_identity"]
                 and all(proof["frontend_birth"][key] == collection["frontend_birth"][key] for key in _BIRTH),
                 "collection and live worker identities differ")
        proofs.append((expected_path, binding["sha256"], proof))
    live_worker = proofs[-1][2]
    frontend, worker = live_worker["frontend_birth"], live_worker["worker_birth"]
    _require(live_worker.get("schema") == "ft_d12_live_owned_worker/v2"
             and frontend["pid"] == frontend["pgid"] == frontend["session"]
             and worker["pid"] != frontend["pid"] and worker["pgid"] == frontend["pgid"]
             and worker["session"] == frontend["session"]
             and all(type(row.get(key)) is int and row[key] > 0
                     for row in (frontend, worker) for key in _BIRTH), "live owned identities are invalid")
    observations = {}
    for role, expected in (("frontend", frontend), ("worker", worker)):
        current = lifecycle.process_identity(expected["pid"])
        _require(current is None or (all(current.get(key) == expected.get(key) for key in _BIRTH)
                                    and current.get("state") == "Z"), role + " survives or PID was reused")
        observations[role] = current
    _require(lifecycle.owned_group_alive(frontend["pgid"]) is False, "owned service group survives stop")
    _require(_pid_domain() == domain, "stop observer PID domain changed")
    value = {"schema": "ft_d12_owned_worker_stopped/v2", "pid_domain": domain, "live_worker": live_worker,
             "collection": {"path": str(collection_path), "sha256": collection_sha256},
             "live_worker_sources": {str(path): digest for path, digest, _ in proofs},
             "post_stop": observations, "owned_group_alive": False,
             "observed_monotonic_ns": time.monotonic_ns(), "observed_time_ns": time.time_ns(),
             "worker_stopped_verified": True, "output_equivalence_verified": False}
    _require(value["observed_monotonic_ns"] > live_worker["observed_monotonic_ns"], "stop observation precedes live proof")
    _read(collection_path, collection_sha256)
    for path, digest, _ in proofs:
        _read(path, digest)
    _write(output, value)
    return value
