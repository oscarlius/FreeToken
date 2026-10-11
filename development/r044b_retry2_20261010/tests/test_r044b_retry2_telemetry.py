from __future__ import annotations
import json
import importlib.util
import io
from datetime import datetime
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parents[1]
MODULE = HERE / 'r044b_retry2_telemetry.py'


def telemetry_module():
    spec = importlib.util.spec_from_file_location('r044b_retry2_telemetry', MODULE)
    value = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(value)
    return value


class Handle(io.StringIO):
    pass


class Process:
    def __init__(self, *, timeout_on_wait=False):
        self.alive = True
        self.timeout_on_wait = timeout_on_wait
        self.actions = []
    def poll(self):
        return None if self.alive else 0
    def terminate(self):
        self.actions.append('terminate')
    def wait(self, timeout):
        self.actions.append('wait')
        if self.timeout_on_wait:
            raise __import__('subprocess').TimeoutExpired('sidecar', timeout)
        self.alive = False
        return 0
    def kill(self):
        self.actions.append('kill')


class Thread:
    def __init__(self, alive=False): self.alive = alive; self.joined = False
    def join(self, timeout): self.joined = True
    def is_alive(self): return self.alive


def make_telemetry(tmp_path, *, dmon_timeout=False, vmstat_timeout=False, thread_alive=False):
    value = telemetry_module()
    class Instance(value.ReliableTelemetryStopMixin):
        pass
    instance = Instance()
    instance.stopped = False
    instance.stop_event = type('StopEvent', (), {'set': lambda self: None})()
    instance.thread = Thread(thread_alive)
    instance.raw = tmp_path
    instance.diskstats = tmp_path / 'proc_diskstats.jsonl'; instance.diskstats.write_text('disk')
    instance.bindings = tmp_path / 'service_bindings.jsonl'; instance.bindings.write_text('bindings')
    instance.manifest = tmp_path / 'telemetry_manifest.json'; instance.manifest.write_text('{}')
    instance.terminal = tmp_path / 'telemetry_terminal.json'
    instance._disk_handle = Handle(); instance._bindings_handle = Handle()
    instance._remaining_stop = lambda: 1
    instance._stamp = lambda: datetime(2026, 10, 10).astimezone().isoformat()
    instance._write_manifest = lambda state: None
    dmon = Process(timeout_on_wait=dmon_timeout)
    vmstat = Process(timeout_on_wait=vmstat_timeout)
    dmon_handle, vmstat_handle = Handle(), Handle()
    instance.processes = [
      {'name': 'nvidia_dmon_raw.txt', 'process': dmon, 'handle': dmon_handle},
      {'name': 'vmstat_raw.txt', 'process': vmstat, 'handle': vmstat_handle},
    ]
    for path in (tmp_path / 'nvidia_dmon_raw.txt', tmp_path / 'vmstat_raw.txt'): path.write_text('raw')
    return instance, dmon, vmstat, dmon_handle, vmstat_handle


def test_first_sidecar_timeout_does_not_skip_vmstat_cleanup(tmp_path):
    instance, dmon, vmstat, dmon_handle, vmstat_handle = make_telemetry(tmp_path, dmon_timeout=True)
    with pytest.raises(RuntimeError, match='telemetry cleanup incomplete; preserve GPU lock'):
        instance.stop()
    assert dmon.actions == ['terminate', 'wait', 'kill', 'wait']
    assert vmstat.actions == ['terminate', 'wait']
    assert vmstat.poll() == 0
    assert dmon_handle.closed and vmstat_handle.closed
    assert not instance.terminal.exists()
    assert not instance.stopped


def test_disk_thread_error_still_stops_every_sidecar(tmp_path):
    instance, _dmon, vmstat, _dmon_handle, _vmstat_handle = make_telemetry(tmp_path, thread_alive=True)
    with pytest.raises(RuntimeError, match='proc_diskstats'):
        instance.stop()
    assert vmstat.poll() == 0


def test_all_sidecars_stopped_writes_terminal_and_seals_files(tmp_path):
    instance, dmon, vmstat, _dmon_handle, _vmstat_handle = make_telemetry(tmp_path)
    instance.stop()
    assert dmon.poll() == vmstat.poll() == 0
    assert instance.terminal.is_file()
    assert instance.stopped
    assert (instance.terminal.stat().st_mode & 0o777) == 0o444


FROZEN = HERE.parent / 'r044b_20261010' / 'run_r044b_actual.py'


def test_retry1_mixin_composes_with_the_frozen_ownedtelemetry_class():
    repair = telemetry_module()
    spec = importlib.util.spec_from_file_location('r044b_frozen_for_retry1_composition', FROZEN)
    frozen = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(frozen)
    composed = repair.retry1_telemetry_class(frozen.OwnedTelemetry)
    assert issubclass(composed, frozen.OwnedTelemetry)
    assert composed.stop is repair.ReliableTelemetryStopMixin.stop



def test_cleanup_error_receipt_aggregates_first_and_later_sidecars_without_terminal(tmp_path):
    instance, _dmon, _vmstat, _dmon_handle, _vmstat_handle = make_telemetry(tmp_path, dmon_timeout=True, vmstat_timeout=True)
    with pytest.raises(RuntimeError, match="preserve GPU lock"):
        instance.stop()
    receipt = json.loads((tmp_path / "telemetry_cleanup_errors.json").read_text())
    assert [item["name"] for item in receipt["errors"]] == ["nvidia_dmon_raw.txt", "vmstat_raw.txt"]
    assert receipt["sidecars_stopped"] is False
    assert not instance.terminal.exists()


