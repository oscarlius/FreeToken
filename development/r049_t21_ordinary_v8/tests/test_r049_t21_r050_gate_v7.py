import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

DEV = Path(__file__).parent

def load():
    spec = importlib.util.spec_from_file_location('r049_r050_v8', DEV/'r049_t21_ordinary_prepare_v8.py')
    module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    return module

def closure_fixture(monkeypatch, tmp_path):
    m = load(); m.ROUNDS = tmp_path/'rounds'; m.ROOT = tmp_path/'root'; m.VENV = tmp_path/'venv'
    directory = m.ROUNDS/m.R050_RID; directory.mkdir(parents=True)
    round_json, manifest, checker = directory/'round.json', directory/'MANIFEST.sha256', directory/'round_json_append.py'
    round_json.write_text(json.dumps({'round_id':m.R050_RID, 'verdict':'kept'})); manifest.write_text('manifest\n'); checker.write_text('# checker\n')
    m.R050_ROUND_SHA = hashlib.sha256(round_json.read_bytes()).hexdigest(); m.R050_MANIFEST_SHA = hashlib.sha256(manifest.read_bytes()).hexdigest()
    pin = m.ROOT/'runs/plan_batches/closed_round_pins'/f'{m.R050_RID}.json'; pin.parent.mkdir(parents=True)
    pin.write_text(json.dumps({'rid':m.R050_RID, 'verdict':'kept', 'candidate_commit':m.CANDIDATE, 'round_sha256':m.R050_ROUND_SHA, 'manifest_sha256':m.R050_MANIFEST_SHA}))
    for path in (directory, pin.parent): path.chmod(0o555)
    for path in (round_json, manifest, checker, pin): path.chmod(0o444)
    monkeypatch.setattr(m.subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0))
    return m, pin

def test_r050_kept_gate_accepts_only_exact_readonly_candidate_closure(monkeypatch, tmp_path):
    m, _ = closure_fixture(monkeypatch, tmp_path)
    assert m.require_r050_d15_closure()['round_sha256'] == m.R050_ROUND_SHA

@pytest.mark.parametrize('change,pattern', [('candidate', 'identity differs'), ('verdict', 'identity differs'), ('writable', 'missing, linked, or writable')])
def test_r050_gate_rejects_wrong_candidate_nonkept_or_nonreadonly(monkeypatch, tmp_path, change, pattern):
    m, pin = closure_fixture(monkeypatch, tmp_path)
    if change == 'writable':
        pin.chmod(0o600)
    else:
        pin.chmod(0o600); doc = json.loads(pin.read_text())
        doc['candidate_commit' if change == 'candidate' else 'verdict'] = 'wrong' if change == 'candidate' else 'measured'
        pin.write_text(json.dumps(doc)); pin.chmod(0o444)
    with pytest.raises(RuntimeError, match=pattern): m.require_r050_d15_closure()
