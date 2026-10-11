"""Run the retained formal executor with owned CPU fixtures, without model workers."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


DEV = Path(__file__).parents[1]


def load_entry():
    spec = importlib.util.spec_from_file_location('r040b_v8_fixture', DEV / 'r040b_d16_remaining_prepare_v9.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def fixture(tmp_path, monkeypatch):
    entry = load_entry()
    rounds = tmp_path / 'rounds'
    rounds.mkdir()
    old = rounds / 'E2-R040a'
    old.mkdir()
    (old / 'closed.json').write_text('original closed bytes')
    (old / 'closed.json').chmod(0o444)
    root = tmp_path / 'FreeToken'
    monkeypatch.setattr(entry, 'ROUNDS', rounds)
    monkeypatch.setattr(entry, 'ROOT', root)
    monkeypatch.setattr(entry, 'WT', root / 'wt/e2base1-ordinary-rewind')
    monkeypatch.setattr(entry, 'REVIEW_DIR', tmp_path / 'review')
    sources = {'fixture-source': 'current-source-hash'}
    closure = {'round_sha256': 'closed-round', 'completed_anchor_arms': 6}
    monkeypatch.setattr(entry, 'source_bindings', lambda: sources)
    monkeypatch.setattr(entry, 'd04_binding', lambda: closure)
    checked = []
    monkeypatch.setattr(entry, 'predecessor_checks', lambda base, after: checked.append(after))
    realinputs = rounds / 'E2-R040/source_tools/realinput_28.json'
    dump(realinputs, {'cases': [
        {'name': str(i), 'query': [i + 1] * 512, 'input_ids_sha256': str(i)}
        for i in range(4)
    ] + [{'name': 'long', 'query': [9] * 5000, 'input_ids_sha256': 'long'}]})
    dry = {'path': 'fixture-dry', 'sha256': 'fixture-dry-sha', 'document': {
        'collector_review': 'collector-review', 'collector_review_sha256': 'collector-sha'}}
    monkeypatch.setattr(entry, 'require_dry_run_receipt', lambda path, after: dry)
    review = {'rid': entry.RID, 'verdict': 'PASS', 'candidate_commit': entry.CANDIDATE,
              'after_round': 'E2-R040a', 'source_execution_ready': True, 'model_admitted': False,
              'sources': sources, 'dry_run_receipt': dry['path'], 'dry_run_receipt_sha256': dry['sha256'],
              **dry['document'], 'input_binding': {'path': str(realinputs), 'sha256': entry.sha(realinputs)},
              'anchor_four_cell': {'state': 'already_complete_in_R040', 'source_round': 'E2-R040a',
                                   'completed_anchor_arms': 6, 'closed_r040a': closure}}

    def write_review(value):
        entry.REVIEW_DIR.mkdir(exist_ok=True)
        for name in ('review.json', 'pin.json'):
            p = entry.REVIEW_DIR / name
            if p.exists(): p.chmod(0o600)
        dump(entry.REVIEW_DIR / 'review.json', value)
        dump(entry.REVIEW_DIR / 'pin.json', {'rid': entry.RID,
             'review_sha256': entry.sha(entry.REVIEW_DIR / 'review.json'),
             'dry_run_receipt_sha256': dry['sha256']})
        for p in entry.REVIEW_DIR.iterdir(): p.chmod(0o444)
        entry.REVIEW_DIR.chmod(0o555)

    write_review(review)
    calls = []
    lock = tmp_path / 'gpu.lock'
    birth = {'pid': 700, 'start_ticks': 91, 'execution_id': '700:91'}

    class Lifecycle:
        def verified_module(self, *args):
            return SimpleNamespace(next_batch=lambda runs: 77)

        def reserve_process(self, allocator, batch, rid, argv, receipt, reserved):
            calls.append(('reserve', rid, argv))
            return {'batch_pid': 700, 'rid': rid}

        def process_identity(self, pid):
            return birth

    def take(rid, batch):
        assert not lock.exists()
        dump(lock, {'owner': rid, 'batch': batch})
        calls.append(('take', rid))
        return {'lock_token': lock.read_text(), 'lock_inode': lock.stat().st_ino}

    def release(token):
        assert lock.read_text() == token['lock_token'] and lock.stat().st_ino == token['lock_inode']
        lock.unlink()
        calls.append(('release',))

    gate = SimpleNamespace(LOCK=lock, ATOMIC_HELPER_SHA='fixture',
        load_owned_lifecycle=lambda: Lifecycle(), take_d07_gpu_lock=take, release_d07_gpu_lock=release,
        require_gpu_idle=lambda: None, require_child_receipt=lambda *a, **kw: calls.append(('child', kw)),
        argv_sha256=lambda argv: 'fixture-argv', process_birth=lambda: birth,
        publish_child_binding=lambda path, value, child, **kw: {**value, 'child': child})
    base = entry.base_module()
    base.sys = SimpleNamespace(platform='linux')
    base.shared_protocol = lambda: gate
    monkeypatch.setattr(entry, 'base_module', lambda: base)

    class Owner:
        proc = None
        options = SimpleNamespace(rid=entry.RID, batch=77, run=True, gate='T20')

        def set_status(self, **values):
            calls.append(('status', values))

    monkeypatch.setattr(entry, 'create_service_owner', lambda *args: Owner())

    class Collector:
        def collect_native_processes(self, owner, ids, *, slots, interleave=False, **kwargs):
            calls.append(('native', slots, interleave))
            return {'arms': list(range(6 if interleave or slots == 2 else 10))}

        def collect_parking_processes(self, *args, **kwargs):
            calls.append(('parking',))
            return {'arms': list(range(4))}

        def collect_cache_processes(self, *args, **kwargs):
            calls.append(('cache',))
            return {'arms': list(range(4))}

    original_load = entry.load
    monkeypatch.setattr(entry, 'load', lambda path, name:
        Collector() if name == 'r040a_private_collection' else original_load(path, name))

    def retained_load(path, name):
        raise AssertionError('retained anchors must never be collected')

    base.load_source = retained_load
    wrapper = tmp_path / 'batch.sh'
    wrapper.write_text('# CPU fixture wrapper, never executed\n')
    launch = tmp_path / 'launch.json'
    dump(launch, {'wrapper': str(wrapper), 'wrapper_sha256': entry.sha(wrapper)})
    return entry, base, dry, review, write_review, calls, launch, old, checked


def test_base_and_actual_controller_use_new_round_and_actual_child_script(tmp_path, monkeypatch):
    entry, base, _, _, _, calls, _, old, checked = fixture(tmp_path, monkeypatch)
    assert base.RID == 'E2-R040b'
    result = entry.execute(dry_receipt='fixture-dry', after='E2-R040a')
    reserve = next(row for row in calls if row[0] == 'reserve')
    assert reserve[1] == result['rid'] == 'E2-R040b'
    assert reserve[2][1] == str(DEV / 'r040b_d16_remaining_prepare_v9.py')
    assert checked == ['E2-R040a'] and not any(row[0] == 'take' for row in calls)
    assert (old / 'closed.json').read_text() == 'original closed bytes'


def test_actual_retained_child_runs_only_d16_and_preserves_closed_anchors(tmp_path, monkeypatch):
    entry, base, _, _, _, calls, launch, old, checked = fixture(tmp_path, monkeypatch)
    result = entry.execute(dry_receipt='fixture-dry', owned_child=True, batch=77, receipt=launch)
    new = entry.ROUNDS / 'E2-R040b'
    assert sum(len(value['arms']) for value in result['d16'].values()) == 30
    assert result['anchor_four_cell']['source_round'] == 'E2-R040a'
    assert result['rid'] == 'E2-R040b'
    assert not (new / 'r040a_d16_supplement.json').exists()
    assert json.loads((new / 'r040b_d16_supplement.json').read_text())['rid'] == 'E2-R040b'
    assert json.loads((new / 'owned_cleanup.json').read_text())['lock_released'] is True
    assert [row[0] for row in calls].count('take') == [row[0] for row in calls].count('release') == 1
    assert (old / 'closed.json').read_text() == 'original closed bytes'


@pytest.mark.parametrize('change', ['old_rid', 'rerun_anchor', 'wrong_dry'])
def test_current_review_rejects_old_round_rerun_and_stale_dry_before_lock(tmp_path, monkeypatch, change):
    entry, _, _, review, write_review, calls, _, _, _ = fixture(tmp_path, monkeypatch)
    entry.REVIEW_DIR.chmod(0o700)
    if change == 'old_rid': review['rid'] = 'E2-R040a'
    elif change == 'rerun_anchor': review['anchor_four_cell']['state'] = 'queued_bound_supplement'
    else: review['dry_run_receipt_sha256'] = 'stale'
    write_review(review)
    with pytest.raises(RuntimeError): entry.execute(dry_receipt='fixture-dry')
    assert not any(row[0] in ('take', 'reserve') for row in calls)
