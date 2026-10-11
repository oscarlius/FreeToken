import importlib.util
from pathlib import Path

PATH = Path(__file__).parents[1] / 'd09_replay_parent.py'
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
    assert (tmp_path / 'FILEDRY_v2' / 'terminal.json').is_file()
