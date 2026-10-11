import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).parents[1] / "t16_private_port_base_runner.py"
spec = importlib.util.spec_from_file_location("t16_private_port_base", SOURCE)
runner_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner_module)


def bare_runner(*, port=48123):
    runner = object.__new__(runner_module.Runner)
    runner.port = port
    runner.options = SimpleNamespace(gate="D01", rid="E2-R999", batch=999)
    runner.token = None
    runner.lock_inode = None
    runner.proc = None
    return runner


class SocketGuard:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def connect_ex(self, address):
        self.calls.append(address)
        if address[1] == 8095:
            raise AssertionError("CPU gate must never probe 8095")
        return 1


def test_gate_accepts_owned_lock_and_never_contacts_8095(monkeypatch, tmp_path):
    runner = bare_runner()
    lock = tmp_path / "gpu.lock"
    lock.write_text("owned-token")
    runner.token = "owned-token"
    runner.lock_inode = lock.stat().st_ino
    guard = SocketGuard()

    def command(argv, **_):
        if argv[0] == "nvidia-smi":
            return "4"
        if argv[0] == "ps":
            return "PID COMMAND\n"
        if argv[0] == "git" and "rev-parse" in argv:
            return "abcdef1"
        if argv[0] == "git":
            return ""
        assert argv[:2] == [runner_module.PY, "-c"]
        return str(tmp_path / "wt/python/freetoken/__init__.py")

    monkeypatch.setattr(runner_module, "LOCK", lock)
    monkeypatch.setattr(runner_module, "command", command)
    monkeypatch.setattr(runner_module.socket, "socket", lambda: guard)
    monkeypatch.setattr(runner, "environment", lambda _: {})

    assert runner.gate(tmp_path / "wt", "abcdef1") == str(tmp_path / "wt/python/freetoken/__init__.py")
    assert guard.calls == []


def test_gate_rejects_foreign_lock_before_resource_commands(monkeypatch, tmp_path):
    runner = bare_runner()
    lock = tmp_path / "gpu.lock"
    lock.write_text("foreign")
    monkeypatch.setattr(runner_module, "LOCK", lock)
    monkeypatch.setattr(runner_module, "command", lambda *_args, **_kwargs: pytest.fail("foreign lock must fail first"))

    with pytest.raises(RuntimeError, match="foreign GPU lock"):
        runner.gate(tmp_path / "wt", "abcdef1")


@pytest.mark.parametrize("client_name", ["cold_eq.py", "ft_probe_ckpt_tax.py"])
def test_private_probe_bootstrap_rebinds_only_url_preserves_argv_and_calls_main_once(monkeypatch, tmp_path, client_name):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    probe = scripts / "probe_ft_cold32k.py"
    probe.write_text("URL = 'http://127.0.0.1:8095/v1/chat/completions'\n")
    client = scripts / client_name
    output = tmp_path / (client_name + ".json")
    client.write_text(
        "import json, sys\n"
        "import probe_ft_cold32k\n"
        "URL = 'http://127.0.0.1:8095/v1/chat/completions'\n"
        "def main():\n"
        "    assert URL == probe_ft_cold32k.URL\n"
        "    assert URL == 'http://127.0.0.1:48123/v1/chat/completions'\n"
        "    assert sys.argv == [__file__, 'alpha', 'beta']\n"
        "    json.dump({'calls': 1, 'argv': sys.argv, 'url': URL}, open(sys.argv[-1] + '.result', 'w'))\n"
    )
    runner = bare_runner()
    monkeypatch.setattr(runner_module, "SCR", scripts)

    completed = subprocess.run(
        [sys.executable, "-c", runner.private_probe_bootstrap(client_name), "alpha", "beta"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stderr == ""
    result = json.loads(Path("beta.result").read_text())
    assert result == {"calls": 1, "argv": [str(client), "alpha", "beta"], "url": "http://127.0.0.1:48123/v1/chat/completions"}
    Path("beta.result").unlink()


class Process:
    pid = 7123


def lifecycle(*, birth=None, alive=False, stop_error=None):
    expected = birth or {"pid": 7123, "start_ticks": 11, "pgid": 7123, "session": 7123}

    def stop(_proc):
        if stop_error:
            raise stop_error

    return SimpleNamespace(process_identity=lambda _pid: expected, stop_owned_process=stop,
                           owned_group_alive=lambda _pid: alive)


def configured_stop(monkeypatch, *, active_lifecycle):
    runner = bare_runner()
    runner.proc = Process()
    runner.service_birth = {"pid": 7123, "start_ticks": 11, "pgid": 7123, "session": 7123}
    monkeypatch.setattr(runner, "owned_lifecycle", lambda: active_lifecycle)
    monkeypatch.setattr(runner_module, "command", lambda argv, **_: "4" if argv[0] == "nvidia-smi" else pytest.fail(str(argv)))
    return runner


def test_stop_rejects_birth_drift_without_clearing_process(monkeypatch):
    changed = {"pid": 7123, "start_ticks": 12, "pgid": 7123, "session": 7123}
    runner = configured_stop(monkeypatch, active_lifecycle=lifecycle(birth=changed))
    with pytest.raises(RuntimeError, match="birth changed"):
        runner.stop()
    assert runner.proc is not None


def test_stop_rejects_live_owned_group_without_clearing_process(monkeypatch):
    runner = configured_stop(monkeypatch, active_lifecycle=lifecycle(alive=True))
    with pytest.raises(RuntimeError, match="group remains"):
        runner.stop()
    assert runner.proc is not None


def test_stop_cleanup_error_preserves_process_and_success_clears_it(monkeypatch):
    runner = configured_stop(monkeypatch, active_lifecycle=lifecycle(stop_error=RuntimeError("stop failed")))
    with pytest.raises(RuntimeError, match="stop failed"):
        runner.stop()
    assert runner.proc is not None

    runner = configured_stop(monkeypatch, active_lifecycle=lifecycle())
    runner.stop()
    assert runner.proc is None
