"""Exercise inherited service dispatch without starting any process or GPU."""
import importlib.util
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('t17_matched_service_test', HERE / 't17_matched_runner.py')
matched = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matched)


def test_inherited_service_executes_matched_startup_and_preserves_callback(monkeypatch, tmp_path):
    for name in ('t17_matched_startup.py', 't17_d14_exact_ids.py'):
        path = tmp_path / name
        path.write_text('frozen test-only entry\n')
        path.chmod(0o444)
    monkeypatch.setattr(matched, 'HERE', tmp_path)
    monkeypatch.setattr(matched.original, 'HERE', tmp_path)
    run = object.__new__(matched.Run)
    run.directory = tmp_path / 'round'
    run.directory.mkdir()
    monkeypatch.setattr(run, 'gate', lambda *_: 'bound source')
    monkeypatch.setattr(run, 'compiled_extensions', lambda *_: {'binding': 'same'})
    monkeypatch.setattr(run, 'ready', lambda *_: None)
    monkeypatch.setattr(run, 'set_status', lambda **_: None)
    monkeypatch.setattr(run, 'stop', lambda: setattr(run, 'proc', None))
    run.parser = lambda _: {'_unique_suffix': repr('.pid=4242'), 'mamba_host_slots': '0'}
    captured = []
    class Process:
        pid = 4242
    def start(argv, **kwargs):
        captured.append((argv, kwargs))
        return Process()
    monkeypatch.setattr(matched.original.subprocess, 'Popen', start)
    monkeypatch.setitem(matched.original.protocol, 'command', lambda *_: 'GPU read-only receipt')
    result = matched.original.Run.service(run, 'owned_arm', lambda arm: ('callback', arm.name))
    assert result == ('callback', 'owned_arm')
    assert len(captured) == 1
    argv, options = captured[0]
    assert str(tmp_path / 't17_matched_startup.py') in argv
    assert str(tmp_path / 't17_d14_startup.py') not in argv
    assert options['start_new_session'] is True
    assert options['env']['FT_LM_CHUNK'] == '7680'
    assert options['env']['FT_T17_MATCHED'] == str(run.directory / 'owned_arm/matched')
