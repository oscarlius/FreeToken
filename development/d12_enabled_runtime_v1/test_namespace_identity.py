"""Linux CPU namespace prototype; synthetic HTTP only, no model launch path."""
from contextlib import contextmanager
import copy
import ctypes
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

if sys.platform != "linux":
    pytest.skip("requires Linux PID/user/mount namespaces", allow_module_level=True)

from namespace_identity import BIRTH, observe_member, observe_namespace_init
from namespace_channel import HostChannel, InitChannel
from test_ordinary_evidence import LIFECYCLE, collect, owned_fixture, record_stopped_worker, sha


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")


def pdeathsig():
    value = ctypes.c_int()
    libc = ctypes.CDLL(None, use_errno=True)
    assert libc.prctl(2, ctypes.byref(value), 0, 0, 0) == 0, ctypes.get_errno()
    return value.value


def inner_controller(root, escaped, start_timeout, control_fd, event_fd, binding):
    assert os.getpid() == 1 and os.getuid() == os.geteuid() == 0
    assert os.environ["CUDA_VISIBLE_DEVICES"] == ""
    subprocess.run(["mount", "--bind", str(root / "private-tmp"), "/tmp"], check=True)
    marker = "ft-d12-namespace-" + root.name
    Path("/tmp", marker).write_text("private namespace marker\n")

    channel = InitChannel(control_fd, event_fd, binding)
    emit = channel.send

    def command(timeout=20):
        try:
            return channel.receive(timeout)["kind"]
        except TimeoutError:
            return "timeout"

    # No model-related process exists before START. PR_GET_PDEATHSIG proves
    # configuration only; the host must also observe the original outer birth.
    emit("ready", pid=os.getpid(), pdeathsig=pdeathsig(), marker=marker)
    action = command(start_timeout)
    if action != "start":
        emit("no-start", reason=action or "eof")
        channel.close_after_cleanup()
        return
    assert pdeathsig() == signal.SIGKILL
    with owned_fixture(root / "owned", escaped=escaped) as owner:
        ready = json.loads((root / "owned/ready.json").read_bytes())
        births = {"frontend": owner.service_birth,
                  "worker": LIFECYCLE.process_identity(ready["worker"]["pid"])}
        if escaped:
            births["escaped"] = json.loads((root / "owned/escaped.json").read_bytes())
        emit("started", births=births, port=owner.port)
        action = command()
        if action == "busy":
            emit("busy")
            # Parent-death test: the main thread cannot observe control EOF.
            # Only the production watchdog can terminate this PID namespace.
            time.sleep(120)
            raise AssertionError("busy fixture was not aborted after parent exit")
        if action == "collect":
            result = collect(owner, root / "owned")
            emit("collected", uids=list(result["responses"]))
            action = command()
        assert action == "stop", action
    collection = root / "owned/wire/collection.json"
    if collection.exists():
        record_stopped_worker(LIFECYCLE, root / "inner-stopped.json",
                              collection_path=collection, collection_sha256=sha(collection))
    emit("stopped")
    assert command() == "exit"
    channel.close_after_cleanup()


def receive(proc, log, expected):
    try:
        row = proc._d12_channel.endpoint.receive(20)
    except BaseException as exc:
        raise AssertionError(f"namespace event failed: {log.read_text()}") from exc
    value = {"event": row["kind"], **row["data"]}
    assert value["event"] == expected, value
    return value


def send(proc, value):
    proc._d12_channel.endpoint.send(value)


@contextmanager
def namespace(root, *, escaped=False, start=True, start_timeout=20):
    root.mkdir()
    (root / "private-tmp").mkdir()
    log = root / "controller.log"
    binding = sha(Path(__file__).resolve())
    channel = HostChannel(binding)
    command = ["unshare", "--user", "--map-root-user", "--mount", "--pid", "--fork",
               "--mount-proc", "--propagation", "private", "--kill-child=KILL",
               sys.executable, "-u", str(Path(__file__).resolve()), str(root),
               str(int(escaped)), str(start_timeout), *map(str, channel.child_fds), binding]
    with log.open("xb") as output:
        try:
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=output,
                                    stderr=output, start_new_session=True, bufsize=0, pass_fds=channel.child_fds,
                                    env={**os.environ, "CUDA_VISIBLE_DEVICES": "",
                                         "PYTHONDONTWRITEBYTECODE": "1"})
        except BaseException:
            channel.close()
            raise
        channel.child_started()
        proc._d12_channel = channel
        original = LIFECYCLE.process_identity(proc.pid)
        try:
            ready = receive(proc, log, "ready")
            assert ready["pid"] == 1 and ready["pdeathsig"] == signal.SIGKILL
            assert not (root / "owned").exists()
            anchor = observe_namespace_init(LIFECYCLE, original)
            write(root / "namespace-anchor.json", anchor)
            assert (root / "private-tmp" / ready["marker"]).read_text() == "private namespace marker\n"
            assert not Path("/tmp", ready["marker"]).exists()
            started = None
            if start:
                # Fresh host validation is the final operation before START.
                fresh = observe_namespace_init(LIFECYCLE, original)
                assert fresh["outer"] == anchor["outer"] and fresh["init"] == anchor["init"]
                send(proc, "start")
                started = receive(proc, log, "started")
            yield proc, log, anchor, started
        finally:
            LIFECYCLE.stop_owned_process(proc, term_timeout=3, kill_timeout=5)
            proc.wait(timeout=5)
            channel.close()


def stopped(birth):
    current = LIFECYCLE.process_identity(birth["pid"])
    assert current is None or (current["state"] == "Z" and
                              all(current[k] == birth[k] for k in BIRTH)), current
    return current


def test_actual_mapping_three_requests_and_owned_stop(tmp_path):
    root = tmp_path / "normal"
    with namespace(root) as (proc, log, anchor, started):
        mappings = {role: observe_member(LIFECYCLE, anchor, birth)
                    for role, birth in started["births"].items()}
        for role, row in mappings.items():
            assert row["inner_birth"]["pid"] != row["outer_process"]["birth"]["pid"]
            assert row["pid_namespace_mapping_verified"] is True
            assert row["formal_launch_authorized"] is row["model_worker_verified"] is False
        write(root / "mapped-before.json", mappings)
        with urlopen(f"http://127.0.0.1:{started['port']}/health", timeout=5) as response:
            assert response.status == 200
        for field in BIRTH:
            changed = dict(started["births"]["worker"])
            changed[field] += 1000000
            with pytest.raises(ValueError):
                observe_member(LIFECYCLE, anchor, changed)
        for field in ("boot_id", "observer_uid", "init", "outer"):
            changed = copy.deepcopy(anchor)
            if field in ("outer", "init"):
                changed[field]["birth"]["start_ticks"] += 1
            else:
                changed[field] = "different"
            with pytest.raises(ValueError):
                observe_member(LIFECYCLE, changed, started["births"]["worker"])
        with pytest.raises(ValueError):
            observe_member(LIFECYCLE, anchor, mappings["worker"]["outer_process"]["birth"])
        send(proc, "collect")
        assert receive(proc, log, "collected")["uids"] == ["0", "1", "2"]
        fresh = {role: observe_member(LIFECYCLE, anchor, birth)
                 for role, birth in started["births"].items()}
        assert all(fresh[r]["outer_process"] == mappings[r]["outer_process"] for r in mappings)
        write(root / "mapped-after.json", fresh)
        send(proc, "stop")
        receive(proc, log, "stopped")
        # Inner process IDs must never be interpreted as host process IDs,
        # including after the same collection has valid inner stop evidence.
        collection = root / "owned/wire/collection.json"
        with pytest.raises(ValueError, match="three-request collection"):
            record_stopped_worker(LIFECYCLE, root / "wrong-domain-stop.json",
                                  collection_path=collection, collection_sha256=sha(collection))
        assert not (root / "wrong-domain-stop.json").exists()
        post = {r: stopped(row["outer_process"]["birth"]) for r, row in mappings.items()}
        assert LIFECYCLE.owned_group_alive(mappings["frontend"]["outer_process"]["birth"]["pgid"]) is False
        write(root / "host-stopped.json", {"post_stop": post, "formal_launch_authorized": False})
        send(proc, "exit")
        assert proc.wait(timeout=5) == 0


def test_outer_death_kills_separate_group_and_session(tmp_path):
    root = tmp_path / "forced"
    with namespace(root, escaped=True) as (proc, log, anchor, started):
        mappings = {r: observe_member(LIFECYCLE, anchor, b) for r, b in started["births"].items()}
        assert mappings["frontend"]["outer_process"]["birth"]["pgid"] != mappings["escaped"]["outer_process"]["birth"]["pgid"]
        write(root / "mapped-before.json", mappings)
        LIFECYCLE.stop_owned_process(proc, term_timeout=3, kill_timeout=5)
        proc.wait(timeout=5)
        expected = [anchor["init"]["birth"], *[r["outer_process"]["birth"] for r in mappings.values()]]
        deadline = time.monotonic() + 5
        while any((row := LIFECYCLE.process_identity(b["pid"])) is not None and row["state"] != "Z" for b in expected):
            assert time.monotonic() < deadline
            time.sleep(.02)
        post = {str(b["pid"]): stopped(b) for b in expected}
        assert all(not LIFECYCLE.owned_group_alive(mappings[r]["outer_process"]["birth"]["pgid"])
                   for r in ("frontend", "escaped"))
        write(root / "host-forced-stopped.json", {"post_stop": post, "formal_launch_authorized": False})


@pytest.mark.parametrize("action", ["eof", "timeout"])
def test_no_start_creates_no_frontend_or_worker(tmp_path, action):
    root = tmp_path / action
    with namespace(root, start=False, start_timeout=3 if action == "timeout" else 20) as (proc, log, anchor, _):
        if action == "eof":
            proc._d12_channel.close_control()
            assert proc.wait(timeout=5) == 125
        else:
            assert receive(proc, log, "no-start")["reason"] == action
            assert proc.wait(timeout=5) == 0
        assert not (root / "owned").exists()
        stopped(anchor["init"]["birth"])


def host_proxy(root):
    with namespace(root, escaped=True) as (proc, log, anchor, started):
        mappings = {r: observe_member(LIFECYCLE, anchor, b) for r, b in started["births"].items()}
        send(proc, "busy")
        receive(proc, log, "busy")
        print(json.dumps({"anchor": anchor, "mappings": mappings}), flush=True)
        assert sys.stdin.readline().strip() == "die"
        os._exit(37)


def test_host_death_aborts_busy_pid1_and_all_descendants(tmp_path):
    root = tmp_path / "host-death"
    with (tmp_path / "proxy.log").open("x") as log:
        proxy = subprocess.Popen([sys.executable, "-u", str(Path(__file__).resolve()), "--host-proxy", str(root)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, start_new_session=True)
        expected = []
        try:
            assert select.select([proxy.stdout], [], [], 20)[0]
            ready = json.loads(proxy.stdout.readline())
            anchor, mappings = ready["anchor"], ready["mappings"]
            expected = [anchor["outer"]["birth"], anchor["init"]["birth"],
                        *[row["outer_process"]["birth"] for row in mappings.values()]]
            write(tmp_path / "host-death-before.json", ready)
            # Main controller thread is sleeping for 120 s. Abrupt host death
            # closes the sole control writer; no orderly context-manager stop.
            proxy.stdin.write(b"die\n")
            proxy.stdin.flush()
            assert proxy.wait(timeout=5) == 37
            deadline = time.monotonic() + 5
            while any((row := LIFECYCLE.process_identity(b["pid"])) is not None and row["state"] != "Z" for b in expected):
                assert time.monotonic() < deadline, "control EOF did not terminate busy PID 1"
                time.sleep(.02)
            write(tmp_path / "host-death-after.json", {str(b["pid"]): stopped(b) for b in expected})
        finally:
            LIFECYCLE.stop_owned_process(proxy, term_timeout=3, kill_timeout=5)
            proxy.wait(timeout=5)
            proxy.stdin.close()
            proxy.stdout.close()
            if expected:
                birth = expected[0]

                def poll_outer():
                    current = LIFECYCLE.process_identity(birth["pid"])
                    assert current is None or all(current[k] == birth[k] for k in BIRTH)
                    return 0 if current is None or current["state"] == "Z" else None

                if poll_outer() is None:
                    from types import SimpleNamespace
                    LIFECYCLE.stop_owned_process(SimpleNamespace(pid=birth["pid"], poll=poll_outer), term_timeout=3, kill_timeout=5)


@pytest.mark.parametrize("fault", ["binding", "sequence", "json", "oversized"])
def test_invalid_control_frame_aborts_before_start(tmp_path, fault):
    root = tmp_path / fault
    with namespace(root, start=False) as (proc, log, anchor, _):
        endpoint = proc._d12_channel.endpoint
        if fault == "binding":
            endpoint.binding = "0" * 64
            endpoint.send("start")
        elif fault == "sequence":
            endpoint.next_out = 2
            endpoint.send("start")
        else:
            os.write(endpoint.write_fd, b"bad-json\n" if fault == "json" else b"x" * 4097)
        assert proc.wait(timeout=5) == 125
        assert not (root / "owned").exists()
        stopped(anchor["init"]["birth"])


def test_control_queue_overflow_aborts_busy_namespace(tmp_path):
    root = tmp_path / "queue-overflow"
    with namespace(root, escaped=True) as (proc, log, anchor, started):
        mappings = {r: observe_member(LIFECYCLE, anchor, b) for r, b in started["births"].items()}
        write(root / "mapped-before.json", mappings)
        send(proc, "busy")
        receive(proc, log, "busy")
        for _ in range(5):
            send(proc, "stop")
        assert proc.wait(timeout=5) == 125
        expected = [anchor["init"]["birth"], *[row["outer_process"]["birth"] for row in mappings.values()]]
        write(root / "queue-overflow-stopped.json", {str(b["pid"]): stopped(b) for b in expected})


if __name__ == "__main__":
    if sys.argv[1] == "--host-proxy":
        host_proxy(Path(sys.argv[2]))
    else:
        inner_controller(Path(sys.argv[1]), bool(int(sys.argv[2])), float(sys.argv[3]),
                         int(sys.argv[4]), int(sys.argv[5]), sys.argv[6])
