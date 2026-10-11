import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
R045 = ROOT / 'r045_section14_draft_v17/source/r045_d06_t05_prepare.py'
R044 = ROOT / 'r044_runtime_v7/r044_prepare_v6.py'
R047 = ROOT / 'r047_runtime_v12/r047_prepare_v11.py'
EFFB = 'effb9969706922ddad9e59b96377e46469ebe97f'
OLD = '0aa23431e5b800797543bdecbf35a01045131d7d'


def load(path):
    spec = importlib.util.spec_from_file_location('future_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def closure(tmp_path, *, base=EFFB, candidate=EFFB):
    path = tmp_path / 'r040g_round.json'
    path.write_text(json.dumps({'base': {'commit': base}, 'experimental': {'candidate_commit': candidate}}))
    return path


@pytest.mark.parametrize('path', [R045, R044, R047])
def test_r040g_rejects_noncanonical_measurement(path, tmp_path):
    module = load(path)
    good = closure(tmp_path)
    assert module.require_r040g_measurement(good) == good
    for base, candidate in ((OLD, EFFB), (EFFB, OLD), (None, None)):
        with pytest.raises(RuntimeError, match='effb996'):
            module.require_r040g_measurement(closure(tmp_path, base=base, candidate=candidate))


def test_r044_queue_consumes_r040f_failed_and_r040g_measurement(tmp_path):
    module = load(R044)
    calls = []
    good = closure(tmp_path)

    class Gate:
        LOCK = tmp_path / 'gpu.lock'
        def require_t20_failed_harness(self):
            calls.append(('E2-R040', 'failed_harness'))
            return tmp_path / 't20.json'
        def require_closed_round(self, rid, verdict):
            calls.append((rid, verdict))
            return good if rid == 'E2-R040g' else tmp_path / (rid + '.json')

    assert module.require_queue(Gate()) == tmp_path / 't20.json'
    assert calls == [('E2-R040', 'failed_harness'), ('E2-R052', 'failed_harness'),
                     ('E2-R052a', 'measured'), ('E2-R040f', 'failed_harness'),
                     ('E2-R040g', 'measured')]


@pytest.mark.parametrize('failure', ['missing_r040g', 'wrongverdict_r040g', 'wrongbase_r040g', 'wrongcandidate_r040g', 'r040f_nonfailed'])
def test_r044_queue_rejects_predecessor_before_launch(tmp_path, failure):
    module = load(R044)
    good = closure(tmp_path)

    class Gate:
        LOCK = tmp_path / 'gpu.lock'
        def require_t20_failed_harness(self): return tmp_path / 't20.json'
        def require_closed_round(self, rid, verdict):
            if failure == 'missing_r040g' and rid == 'E2-R040g':
                raise RuntimeError('missing E2-R040g')
            if failure == 'wrongverdict_r040g' and rid == 'E2-R040g':
                raise RuntimeError('E2-R040g formal D04 verdict is not measured')
            if failure == 'r040f_nonfailed' and rid == 'E2-R040f':
                raise RuntimeError('E2-R040f formal D04 verdict is not failed_harness')
            if rid == 'E2-R040g' and failure == 'wrongbase_r040g':
                return closure(tmp_path, base=OLD)
            if rid == 'E2-R040g' and failure == 'wrongcandidate_r040g':
                return closure(tmp_path, candidate=OLD)
            return good if rid == 'E2-R040g' else tmp_path / (rid + '.json')

    with pytest.raises(RuntimeError):
        module.require_queue(Gate())


def test_r047_predecessors_bind_both_r040_closures(tmp_path):
    module = load(R047)
    good = closure(tmp_path)
    calls = []
    def require_round(rid, verdict):
        calls.append((rid, verdict))
        return good if rid == 'E2-R040g' else tmp_path / (rid + '.json')
    admitted = module.require_predecessors(require_round)
    assert admitted['historical_t20_commit'] == OLD
    assert calls == list(module.FORMAL_PREDECESSORS)
    assert ('E2-R040f', 'failed_harness') in calls
    assert ('E2-R040g', 'measured') in calls


def test_r045_prepare_reaches_later_gate_after_real_r040_consumption(monkeypatch, tmp_path):
    module = load(R045)
    good = closure(tmp_path)
    proof = tmp_path / 'proof.json'; proof.write_text('{}')
    calls = []
    def require_round(rid, verdict):
        calls.append((rid, verdict))
        return good if rid == 'E2-R040g' else proof
    helper = SimpleNamespace(require_t20_failed_harness=lambda: proof,
                             require_closed_round=require_round)
    monkeypatch.setattr(module, 'd07_helpers', lambda: helper)
    monkeypatch.setattr(module, 'git_checked', lambda: {'commit': module.CANDIDATE})
    monkeypatch.setattr(module, 'verify_pause_helpers', lambda: None)
    monkeypatch.setattr(module, 'require_dry_run_receipt', lambda: {'path': 'dry', 'sha256': 'd'})
    monkeypatch.setattr(module, 'require_startup_review', lambda _: {'path': 'review', 'sha256': 'r'})
    monkeypatch.setattr(module, 'require_kept', lambda _: proof)
    monkeypatch.setattr(module, 'd16_failed_metadata', lambda: {'metadata_only': True})
    monkeypatch.setattr(module, 'r055_failed_metadata', lambda: {'r055_gate_ended': True})
    monkeypatch.setattr(module, 'require_t05_ordinary_capability',
                        lambda: (_ for _ in ()).throw(RuntimeError('later admission reached')))
    with pytest.raises(RuntimeError, match='later admission reached'):
        module.run()
    assert calls == [('E2-R040f', 'failed_harness'), ('E2-R040g', 'measured')]
