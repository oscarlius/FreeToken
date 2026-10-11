import importlib.util
import json
from pathlib import Path

import pytest

DEV = Path(__file__).parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, DEV / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def births():
    return {"pid": 17, "start_ticks": 23, "execution_id": "17:23", "pgid": 17, "session": 17}


def test_v4_accepts_service_created_empty_directory_and_writes_exclusive_receipts(monkeypatch, tmp_path):
    startup = load("ordinary_v4", "r046c_t06_ordinary_startup_v4.py")
    worker = {"pid": 19, "start_ticks": 29, "execution_id": "19:29", "pgid": 19, "session": 19}
    monkeypatch.setattr(startup, "birth", lambda: worker)
    directory = tmp_path / "ordinary"; directory.mkdir()
    observer = startup.WorkerObserver(directory, births())
    observer.record_input(type("User", (), {"uid": 7, "input_ids": [11, 12]})())
    observer.record_token(type("Token", (), {"uid": 7, "next_token": 22, "finished": True, "finish_reason": "stop"})())
    observer.flush(); observer.flush()
    inputs = [json.loads(line) for line in (directory / "inputs.jsonl").read_text().splitlines()]
    tokens = [json.loads(line) for line in (directory / "tokens.jsonl").read_text().splitlines()]
    shutdown = json.loads((directory / "shutdown.json").read_text())
    assert inputs[0]["uid"] == tokens[0]["uid"] == 7
    assert inputs[0]["service_birth"] == births() and inputs[0]["worker_birth"] == worker
    assert tokens[0]["completion_tokens_delta"] == 1 and shutdown["terminal_uids"] == [7]


@pytest.mark.parametrize("artifact", ["inputs.jsonl", "tokens.jsonl", "shutdown.json", "input-7.json"])
def test_v4_rejects_nonempty_service_observer_directory(monkeypatch, tmp_path, artifact):
    startup = load("ordinary_v4_busy", "r046c_t06_ordinary_startup_v4.py")
    monkeypatch.setattr(startup, "birth", births)
    directory = tmp_path / "ordinary"; directory.mkdir(); (directory / artifact).write_text("old")
    with pytest.raises(RuntimeError, match="not empty"):
        startup.WorkerObserver(directory, births())


def test_v4_rejects_symlink_observer_directory(monkeypatch, tmp_path):
    startup = load("ordinary_v4_link", "r046c_t06_ordinary_startup_v4.py")
    monkeypatch.setattr(startup, "birth", births)
    target = tmp_path / "target"; target.mkdir(); link = tmp_path / "ordinary"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(RuntimeError, match="symlink"):
        startup.WorkerObserver(link, births())


def test_r046d_binds_new_rid_and_v4_composition():
    source = (DEV / "r046d_d07_t06_prepare.py").read_text(encoding="utf-8")
    memory = (DEV / "r046c_ordinary_memory_startup_v2.py").read_text(encoding="utf-8")
    assert 'RID = "E2-R046d"' in source
    assert 'r046c_t06_ordinary_startup_v4.py' in source
    assert 'r046c_ordinary_memory_startup_v2.py' in source
    assert 'r046c_t06_ordinary_startup_v4.py' in memory


def test_r046d_keeps_metadata_only_predecessors_and_v4_in_packet_source():
    prepare = load("r046d_prepare", "r046d_d07_t06_prepare.py")
    calls = []
    class Gate:
        def require_closed_round(self, rid, verdict):
            calls.append((rid, verdict)); return Path('/sealed') / rid
    closures = prepare.require_predecessors(Gate())
    assert set(closures) == {'E2-R059-gate-D07', 'E2-R058', 'E2-R041-gate-D17'}
    assert calls == [('E2-R059-gate-D07', 'kept'), ('E2-R058', 'measured'), ('E2-R041-gate-D17', 'kept')]
    assert prepare.RID == 'E2-R046d'
    assert prepare.STARTUP_V3.name == 'r046c_t06_ordinary_startup_v4.py'
    assert prepare.MEMORY_STARTUP.name == 'r046c_ordinary_memory_startup_v2.py'
