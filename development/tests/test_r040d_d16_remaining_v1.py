"""Run the retained formal executor with owned CPU fixtures, without model workers."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


DEV = Path(__file__).parents[1]


def load_entry():
    spec = importlib.util.spec_from_file_location('R040d_v1_fixture', DEV / 'r040d_d16_remaining_prepare_v1.py')
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
    retained = {'source_round': 'E2-R040c', 'group': 'S-batch-slots2',
                'case_count': 6, 'state': 'already_reviewed_PASS', 'metadata': {}}
    monkeypatch.setattr(entry, 'retained_slots2_binding', lambda protocol: retained)
    checked = []
    monkeypatch.setattr(entry, 'predecessor_checks', lambda base, after: checked.append(after))
    realinputs = rounds / 'E2-R040/source_tools/realinput_28.json'
    dump(realinputs, {'cases': [
        {'name': str(i), 'query': [i + 1] * 512, 'input_ids_sha256': str(i)}
        for i in range(4)
    ] + [{'name': 'long', 'query': [9] * 5000, 'input_ids_sha256': 'long'}]})
    # The payload fixture exercises the retained base byte check.  The
    # production metadata parser itself is covered separately with its fixed
    # closed-manifest digest; this synthetic payload cannot reproduce it.
    binding = {'path': str(realinputs), 'sha256': entry.sha(realinputs),
               'manifest': 'fixture-manifest', 'manifest_sha256': 'fixture-manifest-sha',
               'seed_45k_historical_only': True}
    monkeypatch.setattr(entry, 'metadata_input_binding', lambda rounds: binding)
    dry = {'path': 'fixture-dry', 'sha256': 'fixture-dry-sha', 'document': {
        'collector_review': 'collector-review', 'collector_review_sha256': 'collector-sha'}}
    monkeypatch.setattr(entry, 'require_dry_run_receipt', lambda path, after: dry)
    review = {'rid': entry.RID, 'verdict': 'PASS', 'candidate_commit': entry.CANDIDATE,
              'after_round': 'E2-R040a', 'source_execution_ready': True, 'model_admitted': False,
              'sources': sources, 'dry_run_receipt': dry['path'], 'dry_run_receipt_sha256': dry['sha256'],
              **dry['document'], 'input_binding': binding, 'retained_slots2': retained,
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
    assert base.RID == 'E2-R040d'
    result = entry.execute(dry_receipt='fixture-dry', after='E2-R040a')
    reserve = next(row for row in calls if row[0] == 'reserve')
    assert reserve[1] == result['rid'] == 'E2-R040d'
    assert reserve[2][1] == str(DEV / 'r040d_d16_remaining_prepare_v1.py')
    assert checked == ['E2-R040a'] and not any(row[0] == 'take' for row in calls)
    assert (old / 'closed.json').read_text() == 'original closed bytes'


def test_actual_retained_child_runs_only_d16_and_preserves_closed_anchors(tmp_path, monkeypatch):
    entry, base, _, _, _, calls, launch, old, checked = fixture(tmp_path, monkeypatch)
    result = entry.execute(dry_receipt='fixture-dry', owned_child=True, batch=77, receipt=launch)
    new = entry.ROUNDS / 'E2-R040d'
    assert sum(len(value['arms']) for value in result['d16'].values()) == 24
    assert result['anchor_four_cell']['source_round'] == 'E2-R040a'
    assert result['rid'] == 'E2-R040d'
    assert not (new / 'r040a_d16_supplement.json').exists()
    assert json.loads((new / 'r040d_d16_supplement.json').read_text())['rid'] == 'E2-R040d'
    assert result['retained_slots2']['source_round'] == 'E2-R040c'
    assert result['retained_slots2']['case_count'] == 6
    assert not any(row[:3] == ('native', 2, False) for row in calls)
    assert json.loads((new / 'owned_cleanup.json').read_text())['lock_released'] is True
    assert [row[0] for row in calls].count('take') == [row[0] for row in calls].count('release') == 1
    assert (old / 'closed.json').read_text() == 'original closed bytes'


@pytest.mark.parametrize('change', ['old_rid', 'rerun_anchor', 'wrong_dry', 'wrong_slots2'])
def test_current_review_rejects_old_round_rerun_and_stale_dry_before_lock(tmp_path, monkeypatch, change):
    entry, _, _, review, write_review, calls, _, _, _ = fixture(tmp_path, monkeypatch)
    entry.REVIEW_DIR.chmod(0o700)
    if change == 'old_rid': review['rid'] = 'E2-R040a'
    elif change == 'rerun_anchor': review['anchor_four_cell']['state'] = 'queued_bound_supplement'
    elif change == 'wrong_dry': review['dry_run_receipt_sha256'] = 'stale'
    else: review['retained_slots2'] = {'source_round': 'E2-R040c', 'case_count': 30}
    write_review(review)
    with pytest.raises(RuntimeError): entry.execute(dry_receipt='fixture-dry')
    assert not any(row[0] in ('take', 'reserve') for row in calls)


def test_closed_manifest_is_the_only_authority_for_the_d16_input_digest(tmp_path):
    entry = load_entry()
    manifest = tmp_path / 'E2-R040' / 'MANIFEST.sha256'
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        '90015a737cdc53f9c71e1f32cf1856bd0de0560362a31b2c91cac36d57806be0'
        '  ./source_tools/realinput_28.json\n', encoding='utf-8')
    manifest.chmod(0o444)
    binding = entry.metadata_input_binding(tmp_path)
    assert binding['sha256'] == entry.INPUT_MANIFEST_SHA256
    assert binding['seed_45k_historical_only'] is True
    manifest.chmod(0o600)
    manifest.write_text('499c000000000000000000000000000000000000000000000000000000000000'
                        '  ./source_tools/realinput_28.json\n', encoding='utf-8')
    manifest.chmod(0o444)
    with pytest.raises(RuntimeError, match='manifest binding differs'):
        entry.metadata_input_binding(tmp_path)


def test_v1_closure_and_dry_entry_bind_the_new_round_identity():
    entry = load_entry()
    assert entry.RID == 'E2-R040d'
    assert entry.DRY == DEV / 'r040d_d16_remaining_dryrun_v1.py'
    assert {'r040d_d16_remaining_prepare_v1.py',
            'r040d_d16_remaining_dryrun_v1.py'} <= set(entry.EXTRA)
    assert entry.REVIEW_DIR.name == 'R040d_startup_review_v1'


def test_actual_base_payload_check_rejects_seed_hash_and_changed_bytes(tmp_path, monkeypatch):
    entry, _, _, review, write_review, calls, launch, _, _ = fixture(tmp_path, monkeypatch)
    entry.REVIEW_DIR.chmod(0o700)
    review['input_binding'] = {**review['input_binding'], 'sha256': '499c' + '0' * 60}
    write_review(review)
    with pytest.raises(RuntimeError, match='authoritative D16 input metadata'):
        entry.execute(dry_receipt='fixture-dry', owned_child=True, batch=77, receipt=launch)
    assert not any(row[0] == 'take' for row in calls)

    changed = tmp_path / 'changed'
    changed.mkdir()
    entry, _, _, _, _, calls, launch, _, _ = fixture(changed, monkeypatch)
    payload = entry.ROUNDS / 'E2-R040' / 'source_tools' / 'realinput_28.json'
    payload.write_text('{"cases":[]}', encoding='utf-8')
    with pytest.raises(RuntimeError, match='actual input bytes differ'):
        entry.execute(dry_receipt='fixture-dry', owned_child=True, batch=77, receipt=launch)
    assert [row[0] for row in calls].count('take') == [row[0] for row in calls].count('release') == 1



def retained_metadata_fixture(tmp_path, monkeypatch):
    entry = load_entry()
    monkeypatch.setattr(entry, "ROUNDS", tmp_path)
    directory = tmp_path / "E2-R040c"
    values = {
        "round.json": {"base": {"commit": entry.CANDIDATE}, "verdict": "failed_harness"},
        "metadata/slots2_group_review.json": {"rid": "E2-R040c", "verdict": "PASS", "case_count": 6, "case_names": [str(x) for x in range(6)], "recomputation": {"independent_review_verified": True}},
        "metadata/slots2_group_pin.json": {"rid": "E2-R040c", "verdict": "PASS", "case_count": 6},
    }
    for name, value in values.items(): dump(directory / name, value)
    pin = values["metadata/slots2_group_pin.json"]
    pin["review_sha256"] = entry.sha(directory / "metadata/slots2_group_review.json")
    dump(directory / "metadata/slots2_group_pin.json", pin)
    (directory / "MANIFEST.sha256").write_text("closed fixture manifest", encoding="utf-8")
    expected = {name: entry.sha(directory / name) for name in entry.RETAINED_R040C_METADATA}
    monkeypatch.setattr(entry, "RETAINED_R040C_METADATA", expected)
    for name in expected: (directory / name).chmod(0o444)
    calls = []
    def require_closed(rid, verdict):
        calls.append((rid, verdict))
        return directory / "round.json"
    protocol = SimpleNamespace(require_closed_round=require_closed)
    return entry, directory, values, protocol, calls


def test_retained_slots2_reads_only_metadata_after_d04_validation(tmp_path, monkeypatch):
    entry, directory, _, protocol, calls = retained_metadata_fixture(tmp_path, monkeypatch)
    # No raw measurement or evidence directory exists in this fixture.
    result = entry.retained_slots2_binding(protocol)
    assert result["case_count"] == 6 and result["state"] == "already_reviewed_PASS"
    assert calls == [("E2-R040c", "failed_harness")]
    assert set(result["metadata"]) == set(entry.RETAINED_R040C_METADATA)
    assert not (directory / "dev_D16").exists()


@pytest.mark.parametrize("name", ["round.json", "MANIFEST.sha256", "metadata/slots2_group_review.json", "metadata/slots2_group_pin.json"])
def test_retained_slots2_rejects_metadata_sha_drift(tmp_path, monkeypatch, name):
    entry, directory, _, protocol, _ = retained_metadata_fixture(tmp_path, monkeypatch)
    p = directory / name; p.chmod(0o600); p.write_bytes(p.read_bytes() + b" "); p.chmod(0o444)
    with pytest.raises(RuntimeError, match="sealed metadata differs"):
        entry.retained_slots2_binding(protocol)


@pytest.mark.parametrize("change", ["candidate", "review_verdict", "case_count", "independent_review", "pin_review_sha"])
def test_retained_slots2_rejects_wrong_group_despite_self_consistent_current_sha(tmp_path, monkeypatch, change):
    entry, directory, values, protocol, _ = retained_metadata_fixture(tmp_path, monkeypatch)
    review_name = "metadata/slots2_group_review.json"; pin_name = "metadata/slots2_group_pin.json"
    if change == "candidate": values["round.json"]["base"]["commit"] = "wrong-candidate"
    elif change == "review_verdict": values[review_name]["verdict"] = "pending"
    elif change == "case_count": values[review_name]["case_count"] = 5
    elif change == "independent_review": values[review_name]["recomputation"]["independent_review_verified"] = False
    else: values[pin_name]["review_sha256"] = "wrong-review-sha"
    for name, value in values.items():
        p = directory / name; p.chmod(0o600); dump(p, value); p.chmod(0o444)
    if change != "pin_review_sha":
        values[pin_name]["review_sha256"] = entry.sha(directory / review_name)
        p = directory / pin_name; p.chmod(0o600); dump(p, values[pin_name]); p.chmod(0o444)
    monkeypatch.setattr(entry, "RETAINED_R040C_METADATA", {name: entry.sha(directory / name) for name in entry.RETAINED_R040C_METADATA})
    with pytest.raises(RuntimeError, match="independent review identity differs"):
        entry.retained_slots2_binding(protocol)


def test_new_capsule_maps_only_reviewed_new_leaves_and_complete_capture_origins(tmp_path):
    entry = load_entry()
    frozen = tmp_path / "frozen_r040c_source"
    origins = entry.capsule_source_origins(pinned_source=frozen)
    assert origins["equiv_suite/sampler_capture.py"] == DEV / "r040d_capture_v3/equiv_suite/sampler_capture.py"
    assert origins["d16_native_capture_shutdown_v3.py"] == DEV / "r040d_capture_v3/d16_native_capture_shutdown_v4.py"
    assert origins["d16_exact_service_startup_v4.py"] == DEV / "r040d_capture_v3/d16_exact_service_startup_v5.py"
    assert origins["r040d_d16_remaining_prepare_v1.py"] == DEV / "r040d_d16_remaining_prepare_v1.py"
    assert origins["d16_native_process_collection_v2.py"] == frozen / "d16_native_process_collection_v2.py"
    assert origins["equiv_suite/native_workloads.py"] == frozen / "equiv_suite/native_workloads.py"
    assert set(origins) == entry.required_capsule_files()
