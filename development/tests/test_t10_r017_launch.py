from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

DEV = Path(__file__).parents[1]


def load():
    path = DEV / 'd03_t10_r017_launch.py'
    spec = importlib.util.spec_from_file_location('r017_launch_test', path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_r017_no_run_or_non_linux_is_inert(monkeypatch):
    module = load()
    called = []
    monkeypatch.setattr(module, 'launch', lambda: called.append('launch'))
    monkeypatch.setattr(sys, 'argv', ['r017'])
    with pytest.raises(SystemExit):
        module.main()
    monkeypatch.setattr(sys, 'argv', ['r017', '--run'])
    monkeypatch.setattr(module.sys, 'platform', 'win32')
    with pytest.raises(SystemExit):
        module.main()
    assert not called


def test_r017_unfrozen_source_fails_before_prerequisite_or_receipt(tmp_path, monkeypatch):
    module = load()
    monkeypatch.setattr(module, 'DEV', tmp_path)
    monkeypatch.setattr(module, 'ROUNDS', tmp_path / 'rounds'); module.ROUNDS.mkdir()
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES', '0')
    called = []
    monkeypatch.setattr(module, 'verify_sources', lambda: (_ for _ in ()).throw(RuntimeError('unfrozen')))
    with pytest.raises(RuntimeError, match='unfrozen'):
        module.launch()
    assert not called and not list(tmp_path.glob('launch_*.json'))


def test_r017_launch_preflights_before_reserve_and_records_exact_receipt(tmp_path, monkeypatch):
    module = load(); dev = tmp_path / 'dev'; dev.mkdir(); rounds = tmp_path / 'rounds'; rounds.mkdir()
    gate = tmp_path / 'gate'; gate.mkdir(); (gate / 'round.json').write_text('{}')
    wrapper, log = tmp_path / 'batch.sh', tmp_path / 'batch.log'; wrapper.write_text('batch')
    order = []
    class Atomic:
        def next_batch(self, _): order.append('next'); return 93
        def reserve_and_launch(self, batch, rid, argv):
            order.append(('reserve', batch, rid, argv)); return SimpleNamespace(pid=902_001), wrapper, log
    monkeypatch.setattr(module, 'DEV', dev); monkeypatch.setattr(module, 'ROUNDS', rounds)
    monkeypatch.setattr(module, 'FROZEN_R017_SHA', 'r' * 64)
    monkeypatch.setattr(module, 'verify_sources', lambda: SimpleNamespace(prerequisite=lambda: (order.append('prerequisite') or gate)))
    monkeypatch.setattr(module, 'preflight', lambda runner, batch: order.append(('preflight', runner, batch)))
    monkeypatch.setattr(module, 'load', lambda *args: Atomic())
    monkeypatch.setattr(module, 'sha', lambda path: 'a' * 64)
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES', '0')
    receipt = module.launch()
    assert order[:4] == ['prerequisite', 'next', ('preflight', module.RUNNER, 93), 'next']
    assert order[4][0:3] == ('reserve', 93, 'E2-R017')
    assert receipt['state'] == 'launched' and receipt['runner_sha256'] == 'a' * 64
    stored = json.loads((dev / 'launch_E2-R017.json').read_text())
    assert stored['state'] == 'launched' and stored['cuda_visible_devices'] == '0'


@pytest.mark.parametrize('fault', ('bad_env', 'preflight', 'ledger_drift'))
def test_r017_failures_never_reserve_or_create_success_receipt(tmp_path, monkeypatch, fault):
    module = load(); dev = tmp_path / 'dev'; dev.mkdir(); rounds = tmp_path / 'rounds'; rounds.mkdir()
    calls = []
    class Atomic:
        def next_batch(self, _):
            calls.append('next')
            return 99 if fault != 'ledger_drift' or calls.count('next') == 1 else 100
        def reserve_and_launch(self, *args):
            calls.append('reserve'); raise AssertionError('reserve must not execute')
    monkeypatch.setattr(module, 'DEV', dev); monkeypatch.setattr(module, 'ROUNDS', rounds)
    monkeypatch.setattr(module, 'verify_sources', lambda: SimpleNamespace(prerequisite=lambda: tmp_path))
    monkeypatch.setattr(module, 'load', lambda *args: Atomic())
    monkeypatch.setattr(module, 'preflight', lambda *args: (_ for _ in ()).throw(ValueError('preflight')) if fault == 'preflight' else None)
    if fault == 'bad_env': monkeypatch.delenv('CUDA_VISIBLE_DEVICES', raising=False)
    else: monkeypatch.setenv('CUDA_VISIBLE_DEVICES', '0')
    with pytest.raises(ValueError):
        module.launch()
    assert 'reserve' not in calls
    receipt = dev / 'launch_E2-R017.json'
    assert not receipt.exists() or json.loads(receipt.read_text())['state'] != 'launched'


def test_r017_launch_failure_preserves_explicit_failed_receipt(tmp_path, monkeypatch):
    module = load(); dev = tmp_path / 'dev'; dev.mkdir(); rounds = tmp_path / 'rounds'; rounds.mkdir(); gate = tmp_path / 'gate'; gate.mkdir(); (gate / 'round.json').write_text('{}')
    class Atomic:
        def next_batch(self, _): return 101
        def reserve_and_launch(self, *args): raise RuntimeError('popen failed')
    monkeypatch.setattr(module, 'DEV', dev); monkeypatch.setattr(module, 'ROUNDS', rounds)
    monkeypatch.setattr(module, 'FROZEN_R017_SHA', 'f' * 64)
    monkeypatch.setattr(module, 'verify_sources', lambda: SimpleNamespace(prerequisite=lambda: gate))
    monkeypatch.setattr(module, 'preflight', lambda *args: None)
    monkeypatch.setattr(module, 'load', lambda *args: Atomic())
    monkeypatch.setattr(module, 'sha', lambda path: 'a' * 64)
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES', '0')
    with pytest.raises(RuntimeError, match='popen failed'):
        module.launch()
    receipt = json.loads((dev / 'launch_E2-R017.json').read_text())
    assert receipt['state'] == 'launch_failed'


def test_r017_verify_sources_requires_readonly_runner_bundle(tmp_path, monkeypatch):
    if os.name != 'posix':
        pytest.skip('POSIX permission contract')
    module = load(); root, dev = tmp_path / 'root', tmp_path / 'dev'
    runner_parent = tmp_path / 'bundle'; runner_parent.mkdir()
    runner = runner_parent / 't10_raw_phase1_r017.py'; runner.write_text('x = 1\n')
    prereq = dev / 'd03_phase2_launch.py'; prereq.parent.mkdir(); prereq.write_text('x = 1\n')
    atomic = root / 'runs/plan_batches/e2_launch.py'; atomic.parent.mkdir(parents=True); atomic.write_text('x = 1\n')
    frozen = dev / 'phase2_tools_c30ae0d_ready/t10_raw_phase1.py'; frozen.parent.mkdir(); frozen.write_text('x = 1\n')
    for path in (runner_parent, runner, prereq, atomic, frozen):
        path.chmod(0o444 if path.is_file() else 0o555)
    expected = {prereq: module.PREREQUISITE_SHA, atomic: module.ATOMIC_SHA,
                frozen: module.FROZEN_PHASE1_SHA, runner: 'f' * 64}
    monkeypatch.setattr(module, 'ROOT', root); monkeypatch.setattr(module, 'DEV', dev)
    monkeypatch.setattr(module, 'RUNNER', runner); monkeypatch.setattr(module, 'FROZEN_R017_SHA', 'f' * 64)
    monkeypatch.setattr(module, 'sha', lambda path: expected[Path(path)])
    sentinel = SimpleNamespace(prerequisite=lambda: None)
    monkeypatch.setattr(module, 'load', lambda path, pin: sentinel)
    assert module.verify_sources() is sentinel
    runner.chmod(0o644)
    with pytest.raises(ValueError, match='read-only'):
        module.verify_sources()
