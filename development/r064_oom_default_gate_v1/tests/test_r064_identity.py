import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

PACK = Path(__file__).parents[1]
CANDIDATE = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
BASE = '0aa23431e5b800797543bdecbf35a01045131d7d'


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, PACK / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_r064_prepare_identity_and_four_arm_contract(tmp_path):
    m = load('r064_prepare_identity', 'r064_oom_t16_prepare_v1.py')
    assert m.RID == 'E2-R064-gate-OOM'
    assert (m.BASE, m.CANDIDATE) == (BASE, CANDIDATE)
    assert m.NATIVE_PROVENANCE.name == 'r064_native_provenance_v1.json'
    assert {(x['tree'], x['d0']) for x in m.four_arms()} == {('base', False), ('base', True), ('candidate', False), ('candidate', True)}
    assert m.COLD == {'requested_tokens': 32052, 'expected_input_tokens': 32064, 'completion_tokens': 128, 'temperature': 0}
    wt = tmp_path / 'candidate'; wt.mkdir()
    assert m.candidate_binding(CANDIDATE, wt)['candidate_commit'] == CANDIDATE
    assert m.candidate_binding('4c878f6b3251cca273d8548e7f5cf58a56711d3a', wt)['candidate_commit'].startswith('4c878')


def test_r064_native_proof_requires_new_candidate_binding(tmp_path, monkeypatch):
    if os.name == 'nt':
        pytest.skip('Windows permission bits cannot prove sealed provenance')
    m = load('r064_native_identity', 'r064_oom_t16_prepare_v1.py')
    root = tmp_path / 'FreeToken'; root.mkdir(); proof = tmp_path / 'r064_native_provenance_v1.json'
    monkeypatch.setattr(m, 'ROOT', root); monkeypatch.setattr(m, 'NATIVE_PROVENANCE', proof)
    doc = {'schema': 'ft_r064_oom_native_provenance/v1', 'candidate_commit': CANDIDATE, 'parent_commit': BASE,
           'candidate_worktree': str(root / 'wt/e2oom-protocol-restart'), 'parent_worktree': str(root / 'wt/e2base1-ordinary-rewind'),
           'native_sources_unchanged': True,
           'native': {name: {'regular_copy': True, 'parent_is_symlink': True, 'parent_resolved_path': '/origin/' + name, 'size': 1, 'sha256': 'a' * 64} for name in ('_cpu_moe', '_pinned_tensor')}}
    proof.write_text(json.dumps(doc), encoding='utf-8'); monkeypatch.setattr(m, 'NATIVE_PROVENANCE_SHA256', m.sha(proof)); proof.chmod(0o444)
    assert m.require_r060_native_provenance(proof)['candidate_commit'] == CANDIDATE
    doc['candidate_commit'] = '4c878f6b3251cca273d8548e7f5cf58a56711d3a'
    proof.chmod(0o644); proof.write_text(json.dumps(doc), encoding='utf-8'); proof.chmod(0o444); monkeypatch.setattr(m, 'NATIVE_PROVENANCE_SHA256', m.sha(proof))
    with pytest.raises(RuntimeError, match='identity'):
        m.require_r060_native_provenance(proof)


def test_r064_entry_wraps_exact_owned_v3_chain_without_launching():
    m = load('r064_owned_entry', 'r064_oom_owned_launch_v3.py')
    retained = m.runtime()
    assert retained.RID == 'E2-R064-gate-OOM'
    assert retained.CANDIDATE == CANDIDATE
    assert retained.REVIEW.name == 'E2-R064-gate-OOM-v1'
    assert retained.dry_dir().name == '.dryrun_R060c_v3_E2-R064-gate-OOM'
    assert retained.argv(17, Path('/tmp/receipt'))[:3] == [str(retained.ROOT / 'venv/bin/python'), str(PACK / 'r064_oom_owned_launch_v3.py'), '--run']