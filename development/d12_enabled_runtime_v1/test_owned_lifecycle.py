"""Deterministic /proc exit races; no process creation or signalling."""
import errno
from pathlib import Path
from types import SimpleNamespace

import pytest

from test_ordinary_evidence import LIFECYCLE


def scan(monkeypatch, *, state="S", session=70001, pgid=70001, failure=None, stop=False):
    entries = [Path("/proc/70002"), Path("/proc/70003")]
    fields = f"70003 (fixture) {state} 1 {pgid} {session} 0 0 0\n"
    monkeypatch.setattr(Path, "iterdir", lambda self: iter(entries))

    def read(self, *args, **kwargs):
        if str(self) == "/proc/70002/stat":
            raise failure
        assert str(self) == "/proc/70003/stat"
        return fields

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(LIFECYCLE.os, "killpg", lambda pgid, sig: None)
    if stop:
        return LIFECYCLE.stop_owned_process(SimpleNamespace(pid=70001, poll=lambda: 0))
    return LIFECYCLE.owned_group_alive(70001)


@pytest.mark.parametrize("failure", [FileNotFoundError(errno.ENOENT, "gone"), ProcessLookupError(errno.ESRCH, "gone")])
@pytest.mark.parametrize("state,expected", [("S", True), ("Z", False)])
def test_exited_unrelated_process_does_not_abort_owned_scan(monkeypatch, failure, state, expected):
    assert scan(monkeypatch, state=state, failure=failure) is expected


def test_unreadable_process_still_fails_closed(monkeypatch):
    with pytest.raises(PermissionError):
        scan(monkeypatch, failure=PermissionError(errno.EACCES, "denied"))


def test_foreign_session_still_rejected(monkeypatch):
    with pytest.raises(RuntimeError, match="reserved session"):
        scan(monkeypatch, session=70009, failure=FileNotFoundError(errno.ENOENT, "gone"))


def test_foreign_group_not_counted_alive(monkeypatch):
    assert scan(monkeypatch, pgid=70009, failure=FileNotFoundError(errno.ENOENT, "gone")) is False


def test_native_stop_uses_repaired_observer(monkeypatch):
    from owned_lifecycle import owned_group_alive
    assert LIFECYCLE.stop_owned_process.__globals__["owned_group_alive"] is owned_group_alive
    assert scan(monkeypatch, state="Z", failure=ProcessLookupError(errno.ESRCH, "gone"), stop=True) is None
