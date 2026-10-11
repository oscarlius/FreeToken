import importlib.util
import json
from pathlib import Path

import pytest


def load():
    path = Path(__file__).parents[1] / 'r061b_oom_owned_launch_v2.py'
    spec = importlib.util.spec_from_file_location('r061b_kept_v2', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def closed_gate(tmp_path, monkeypatch, *, verdict='kept', commit=None):
    module = load()
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module, 'ROUNDS', tmp_path / 'rounds')
    rid = 'E2-R060c-gate-OOM'
    directory = module.ROUNDS / rid
    directory.mkdir(parents=True)
    document = {'round_id': rid, 'verdict': verdict, 'base': {
        'commit': commit or module.CANDIDATE, 'parent_commit': module.BASE}}
    round_path = directory / 'round.json'
    round_path.write_text(json.dumps(document))
    manifest = directory / 'MANIFEST.sha256'
    manifest.write_text(module.sha(round_path) + '  ./round.json\n')
    pin = tmp_path / 'runs/plan_batches/closed_round_pins' / (rid + '.json')
    pin.parent.mkdir(parents=True)
    pin.write_text(json.dumps({'schema': 'ft_closed_round_pin/v1', 'rid': rid,
        'verdict': verdict, 'candidate_commit': commit or module.CANDIDATE,
        'round_sha256': module.sha(round_path), 'manifest_sha256': module.sha(manifest),
        'independent_review_sha256': 'a' * 64}))
    for path in (round_path, manifest, pin):
        path.chmod(0o444)
    return module, round_path


def test_real_closed_gate_is_bound_by_metadata_hashes(tmp_path, monkeypatch):
    module, round_path = closed_gate(tmp_path, monkeypatch)
    proof = module.require_r060c_kept()
    assert proof['candidate_commit'] == module.CANDIDATE
    assert proof['round_sha256'] == module.sha(round_path)
    assert proof['independent_review_sha256'] == 'a' * 64


@pytest.mark.parametrize('verdict,commit', [('pending_review', None), ('kept', 'b' * 40)])
def test_unaccepted_or_other_candidate_gate_blocks_before_filedry_writes(tmp_path, monkeypatch, verdict, commit):
    module, _ = closed_gate(tmp_path, monkeypatch, verdict=verdict, commit=commit)
    monkeypatch.setattr(module.sys, 'platform', 'linux')
    output = tmp_path / 'new_filedry'
    with pytest.raises(RuntimeError, match='current candidate R060c kept closure'):
        module.file_dry(output, tmp_path, 'reference', 'affected', 'queued')
    assert not output.exists()


def test_changed_closed_round_is_rejected_before_candidate_admission(tmp_path, monkeypatch):
    module, round_path = closed_gate(tmp_path, monkeypatch)
    round_path.chmod(0o600)
    round_path.write_text(round_path.read_text() + ' ')
    round_path.chmod(0o444)
    with pytest.raises(RuntimeError, match='closed metadata SHA differs'):
        module.require_admission(tmp_path, 'r', 'a', 'q', 'dry', 'review', 'pin')
