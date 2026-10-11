import importlib.util
import json
import os
import stat
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / 'd09_replay_parent_v4.py'
spec = importlib.util.spec_from_file_location('parent', PATH)
parent = importlib.util.module_from_spec(spec); spec.loader.exec_module(parent)


def test_plan_sets_preserve_36_hot_and_two_descending_edited_cold_sets():
    client = parent.load(parent.local_client_path(), 't2')
    _, hot, (cold_a, cold_b), _ = parent.plan_sets(client)
    assert len(hot) == 36 and len(cold_a) == len(cold_b) == 12
    assert [x['round'] for x in cold_a] == list(range(11, -1, -1))
    assert {x['mode'] for x in cold_a} == {'edit_cold_A'}
    assert {x['mode'] for x in cold_b} == {'edit_cold_B'}


def test_filedry_exercises_60_call_topology(monkeypatch, tmp_path):
    monkeypatch.setattr(parent, 'HERE', tmp_path)
    receipt = parent.filedry()
    assert receipt['actual_mock_calls'] == 60
    assert receipt['planned_services'] == 3
    assert receipt['comparison_verdict'] == 'measured_pending_independent_review'
    assert (tmp_path / 'FILEDRY_v4' / 'terminal.json').is_file()
    assert (tmp_path / 'FILEDRY_v4' / 'services' / 'fresh_on' / 'port_pair_reservation.json').is_file()


def test_compare_cold_prefix_difference_is_not_met(tmp_path, monkeypatch):
    monkeypatch.setattr(parent, 'output_bytes', lambda row: row['result'])
    def row(value): return {'result': value}
    hot = {0: row(b'a')}
    cold_a = {0: row(b'ab')}
    cold_b = {0: row(b'ab')}
    rows, verdict = parent.compare_cold(hot, cold_a, cold_b, tmp_path)
    assert verdict == 'not_met'
    assert rows[0]['prefix_difference'] is True
    assert rows[0]['first_differing_output_byte'] == min(rows[0]['hot_length'], rows[0]['cold_length'])


def test_compare_cold_ab_unstable_fails_harness(tmp_path):
    hot = {0: {'result': {'text': 'same'}}}
    cold_a = {0: {'result': {'text': 'a'}}}
    cold_b = {0: {'result': {'text': 'b'}}}
    rows, verdict = parent.compare_cold(hot, cold_a, cold_b, tmp_path)
    assert verdict == 'failed_harness'
    assert rows[0]['reason'] == 'cold_A_B_output_unstable'


def test_actual_gate_rejects_source_gate_mismatch(tmp_path):
    round_json = tmp_path / 'round.json'; manifest = tmp_path / 'MANIFEST.sha256'
    round_json.write_text(json.dumps({'round_id': parent.T16_RID, 'verdict': 'kept'}))
    manifest.write_text('round.json\n')
    class D07:
        def require_closed_round(self, rid, verdict):
            assert (rid, verdict) == (parent.T16_RID, 'kept')
            return round_json
    binding = {'rid': parent.T16_RID, 'actual_verdict': 'kept',
               'round_json_sha256': parent.sha(round_json), 'manifest_sha256': '0' * 64}
    with pytest.raises(RuntimeError, match='sealed round or manifest hash differs'):
        parent.require_actual_gate(D07(), binding, parent.T16_RID, {'kept'})


def test_actual_source_rejects_native_provenance_mismatch(tmp_path, monkeypatch):
    worktree = tmp_path / 'wt'; kernel = worktree / 'python' / 'freetoken' / 'kernel'
    kernel.mkdir(parents=True)
    native_file = kernel / '_cpu_moe.cpython-310-x86_64-linux-gnu.so'
    native_file.write_bytes(b'actual-native-bytes')
    provenance = tmp_path / 'd09_t16_night_v1' / 'd09_native_provenance_v1.json'
    provenance.parent.mkdir()
    provenance.write_text(json.dumps({'candidate_commit': parent.CANDIDATE, 'candidate_worktree': str(worktree),
        'regular_extensions': {'candidate': {'sha256': {'_cpu_moe': '0' * 64},
                                              'size': {'_cpu_moe': len(native_file.read_bytes())}}}}))
    os.chmod(provenance, stat.S_IREAD)
    class D07:
        def checked_worktree(self, value):
            assert value == worktree
            return {'worktree': str(value), 'commit': parent.CANDIDATE, 'tracked_clean': True}
    monkeypatch.setattr(parent, 'WORKTREE', worktree)
    monkeypatch.setattr(parent, 'T16_DEV', provenance.parent)
    with pytest.raises(RuntimeError, match='native provenance actual source differs'):
        parent.require_actual_source(D07())
