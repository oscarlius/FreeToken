"""Run the retained formal executor with owned CPU fixtures, without model workers."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


DEV = Path(__file__).parents[1]


def load_entry():
    spec = importlib.util.spec_from_file_location('R040f_v1_fixture', DEV / 'r040f_d16_remaining_prepare_v5.py')
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
    retained = {'source_round': 'E2-R040e', 'state': 'sealed_completed_slots4_not_rerun',
                'round_sha256': 'closed-round', 'manifest_sha256': 'closed-manifest',
                'd04_review': {'path': 'fixture-d04', 'sha256': 'd04'},
                'batch_envelope': {'path': 'fixture-envelope', 'sha256': 'envelope'},
                'scope_count': 9, 'raw_not_copied': True}
    monkeypatch.setattr(entry, 'retained_r040e_slots4_binding', lambda protocol: retained)
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
              'after_round': 'E2-R040e', 'source_execution_ready': True, 'model_admitted': False,
              'sources': sources, 'dry_run_receipt': dry['path'], 'dry_run_receipt_sha256': dry['sha256'],
              **dry['document'], 'input_binding': binding, 'retained_r040e_slots4': retained,
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
            return {'arms': list(range(6 if interleave or slots == 2 else 9))}

        def collect_parking_processes(self, *args, **kwargs):
            calls.append(('parking',))
            return {'arms': list(range(4))}

        def collect_cache_processes(self, *args, **kwargs):
            calls.append(('cache',))
            return {'arms': list(range(4))}

    original_load = entry.load
    monkeypatch.setattr(entry, 'load', lambda path, name:
        Collector() if name == 'r040f_private_collection' else original_load(path, name))

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
    assert base.RID == 'E2-R040f'
    result = entry.execute(dry_receipt='fixture-dry', after='E2-R040e')
    reserve = next(row for row in calls if row[0] == 'reserve')
    assert reserve[1] == result['rid'] == 'E2-R040f'
    assert reserve[2][1] == str(DEV / 'r040f_d16_remaining_prepare_v5.py')
    assert checked == ['E2-R040e'] and not any(row[0] == 'take' for row in calls)
    assert (old / 'closed.json').read_text() == 'original closed bytes'


def test_actual_retained_child_runs_only_d16_and_preserves_closed_anchors(tmp_path, monkeypatch):
    entry, base, _, _, _, calls, launch, old, checked = fixture(tmp_path, monkeypatch)
    result = entry.execute(dry_receipt='fixture-dry', owned_child=True, batch=77, receipt=launch)
    new = entry.ROUNDS / 'E2-R040f'
    assert sum(len(value['arms']) for value in result['d16'].values()) == 14
    assert result['anchor_four_cell']['source_round'] == 'E2-R040a'
    assert result['rid'] == 'E2-R040f'
    assert not (new / 'r040a_d16_supplement.json').exists()
    assert json.loads((new / 'r040f_d16_supplement.json').read_text())['rid'] == 'E2-R040f'
    assert result['retained_r040e_slots4']['source_round'] == 'E2-R040e'
    assert result['retained_r040e_slots4']['scope_count'] == 9
    assert not any(row[:3] == ('native', 4, False) for row in calls)
    assert json.loads((new / 'owned_cleanup.json').read_text())['lock_released'] is True
    assert [row[0] for row in calls].count('take') == [row[0] for row in calls].count('release') == 1
    assert (old / 'closed.json').read_text() == 'original closed bytes'


@pytest.mark.parametrize('change', ['old_rid', 'rerun_anchor', 'wrong_dry', 'wrong_r040e_binding'])
def test_current_review_rejects_old_round_rerun_and_stale_dry_before_lock(tmp_path, monkeypatch, change):
    entry, _, _, review, write_review, calls, _, _, _ = fixture(tmp_path, monkeypatch)
    entry.REVIEW_DIR.chmod(0o700)
    if change == 'old_rid': review['rid'] = 'E2-R040a'
    elif change == 'rerun_anchor': review['anchor_four_cell']['state'] = 'queued_bound_supplement'
    elif change == 'wrong_dry': review['dry_run_receipt_sha256'] = 'stale'
    else: review['retained_r040e_slots4'] = {'source_round': 'E2-R040e', 'scope_count': 23}
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
    assert entry.RID == 'E2-R040f'
    assert entry.DRY == DEV / 'r040f_d16_remaining_dryrun_v5.py'
    assert {'r040f_d16_remaining_prepare_v5.py',
            'r040f_d16_remaining_dryrun_v5.py'} <= set(entry.EXTRA)
    assert entry.REVIEW_DIR.name == 'R040f_startup_review_v1'


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



def test_r040f_closed_round_leaf_uses_same_dir_canonical_checker_for_r040e(tmp_path, monkeypatch):
    """R040e has no checker in its old closure; reject before a substitute runs."""
    import shutil
    package = tmp_path / 'package'; package.mkdir()
    leaf_path = package / 'r040f_d07_g3g4_prepare_v2.py'
    writer = package / 'r040f_round_json_append_v1.py'
    shutil.copyfile(DEV / 'r040f_d07_g3g4_prepare_v2.py', leaf_path)
    shutil.copyfile(DEV / 'r040f_round_json_append_v1.py', writer)
    writer.chmod(0o444)
    spec = importlib.util.spec_from_file_location('r040f_closed_round_leaf', leaf_path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    rounds = tmp_path / 'rounds'; root = tmp_path / 'root'; rid = 'E2-R040e'
    directory = rounds / rid; directory.mkdir(parents=True)
    round_path = directory / 'round.json'; dump(round_path, {'round_id': rid, 'verdict': 'failed_harness'})
    manifest = directory / 'MANIFEST.sha256'; manifest.write_text('manifest')
    # A round-local substitute must be ignored for R040e.
    substitute = directory / 'round_json_append.py'; substitute.write_text('raise RuntimeError("substitute executed")')
    pin = root / 'runs/plan_batches/closed_round_pins' / f'{rid}.json'; pin.parent.mkdir(parents=True)
    dump(pin, {'rid': rid, 'round_json_sha256': module.sha256(round_path),
               'manifest_sha256': module.sha256(manifest)})
    for path in (round_path, manifest, substitute, pin): path.chmod(0o444)
    directory.chmod(0o555)
    monkeypatch.setattr(module, 'ROOT', root); monkeypatch.setattr(module, 'ROUNDS', rounds)
    ran = []
    monkeypatch.setattr(module.subprocess, 'run', lambda args, **kwargs: ran.append(args) or SimpleNamespace(returncode=0))
    assert module.require_closed_round(rid, 'failed_harness') == round_path
    assert ran[0][1] == str(writer)

    writer.chmod(0o644)
    with pytest.raises(RuntimeError, match='same-directory history checker differs'):
        module.require_closed_round(rid, 'failed_harness')
    writer.chmod(0o644)
    writer.write_text('replacement')
    writer.chmod(0o444)
    with pytest.raises(RuntimeError, match='same-directory history checker differs'):
        module.require_closed_round(rid, 'failed_harness')


def test_r040f_closed_round_leaf_rejects_ambiguous_aliases(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('r040f_closed_round_leaf_aliases', DEV / 'r040f_d07_g3g4_prepare_v2.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    rounds = tmp_path / 'rounds'; root = tmp_path / 'root'; rid = 'E2-R040x'
    directory = rounds / rid; directory.mkdir(parents=True)
    round_path = directory / 'round.json'; dump(round_path, {'round_id': rid, 'verdict': 'failed_harness'})
    manifest = directory / 'MANIFEST.sha256'; manifest.write_text('manifest')
    checker = directory / 'round_json_append.py'; checker.write_text('# checked externally')
    pin = root / 'runs/plan_batches/closed_round_pins' / f'{rid}.json'; pin.parent.mkdir(parents=True)
    for path in (round_path, manifest, checker): path.chmod(0o444)
    directory.chmod(0o555)
    monkeypatch.setattr(module, 'ROOT', root); monkeypatch.setattr(module, 'ROUNDS', rounds)
    monkeypatch.setattr(module.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=0))
    def write_pin(**extra):
        if pin.exists(): pin.chmod(0o600)
        dump(pin, {'rid': rid, 'round_json_sha256': module.sha256(round_path),
                   'manifest_sha256': module.sha256(manifest), **extra})
        pin.chmod(0o444)
    write_pin()
    assert module.require_closed_round(rid, 'failed_harness') == round_path
    write_pin(round_sha256='f' * 64)
    with pytest.raises(RuntimeError, match='aliases differ'):
        module.require_closed_round(rid, 'failed_harness')
    write_pin(round_json_sha256='not-a-sha')
    with pytest.raises(RuntimeError, match='malformed'):
        module.require_closed_round(rid, 'failed_harness')

def test_r040e_completed_slots4_binding_requires_closed_round_candidate_and_envelope(tmp_path, monkeypatch):
    entry = load_entry()
    rounds = tmp_path / 'rounds'; directory = rounds / 'E2-R040e'; directory.mkdir(parents=True)
    round_path = directory / 'round.json'
    dump(round_path, {'base': {'commit': entry.CANDIDATE}, 'verdict': 'failed_harness',
                      'independent_review_sha256': 'd04-sha'})
    manifest = directory / 'MANIFEST.sha256'; manifest.write_text('sealed manifest')
    d04 = tmp_path / 'd04-review.json'; dump(d04, {'rid': 'E2-R040e'})
    envelope = tmp_path / 'slots4-envelope.json'; dump(envelope, {
        'schema': 'ft_r040e_slots4_batch_envelope_report/v1', 'rid': 'E2-R040e',
        'result': {'generation_tokens_per_case': 128, 'first_divergence_generation_index': None}})
    d04_sha = entry.sha(d04)
    round_path.chmod(0o600)
    dump(round_path, {'base': {'commit': entry.CANDIDATE}, 'verdict': 'failed_harness',
                      'independent_review_sha256': d04_sha})
    for path in (round_path, manifest, d04, envelope): path.chmod(0o444)
    monkeypatch.setattr(entry, 'ROUNDS', rounds)
    monkeypatch.setattr(entry, 'R040E_CLOSED_METADATA', {'round.json': entry.sha(round_path),
                       'MANIFEST.sha256': entry.sha(manifest)})
    monkeypatch.setattr(entry, 'R040E_D04_REVIEW', d04)
    monkeypatch.setattr(entry, 'R040E_D04_REVIEW_SHA256', d04_sha)
    monkeypatch.setattr(entry, 'R040E_ENVELOPE', envelope)
    monkeypatch.setattr(entry, 'R040E_ENVELOPE_SHA256', entry.sha(envelope))
    protocol = SimpleNamespace(require_closed_round=lambda rid, verdict: round_path)
    binding = entry.retained_r040e_slots4_binding(protocol)
    assert binding['source_round'] == 'E2-R040e' and binding['scope_count'] == 9
    round_path.chmod(0o600)
    dump(round_path, {'base': {'commit': '0' * 40}, 'verdict': 'failed_harness',
                      'independent_review_sha256': 'd04-sha'})
    round_path.chmod(0o444)
    monkeypatch.setattr(entry, 'R040E_CLOSED_METADATA', {'round.json': entry.sha(round_path),
                       'MANIFEST.sha256': entry.sha(manifest)})
    with pytest.raises(RuntimeError, match='slots4 evidence identity differs'):
        entry.retained_r040e_slots4_binding(protocol)


def test_r040e_completed_slots4_binding_rejects_old_or_unsealed_predecessor(tmp_path, monkeypatch):
    entry = load_entry()
    protocol = SimpleNamespace(require_closed_round=lambda rid, verdict: tmp_path / 'E2-R040e' / 'round.json')
    monkeypatch.setattr(entry, 'ROUNDS', tmp_path)
    with pytest.raises(RuntimeError, match='metadata differs'):
        entry.retained_r040e_slots4_binding(protocol)


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
    if (DEV / "MANIFEST.sha256").is_file():
        # A reviewed archive must repackage its pinned flattened leaves.
        assert all(path == DEV / name for name, path in origins.items())
    else:
        # Development assembly has no sealed self-inventory and uses origins.
        assert origins["equiv_suite/sampler_capture.py"] == DEV / "r040d_capture_v5/equiv_suite/sampler_capture.py"
        assert origins["d16_native_capture_shutdown_v3.py"] == DEV / "r040d_capture_v5/d16_native_capture_shutdown_v4.py"
        assert origins["d16_exact_service_startup_v4.py"] == DEV / "r040d_capture_v5/d16_exact_service_startup_v5.py"
    if not (DEV / "MANIFEST.sha256").is_file():
        assert origins["r040f_d16_remaining_prepare_v5.py"] == DEV / "r040f_d16_remaining_prepare_v5.py"
        assert origins["d16_native_process_collection_v4.py"] == DEV / "d16_native_process_collection_v4.py"
        assert origins["d16_native_process_collection_v5.py"] == DEV / "d16_native_process_collection_v5.py"
        assert origins["multisession_probe.py"] == DEV / "multisession_probe.py"
        assert origins["d16_native_process_collection_v2.py"] == frozen / "d16_native_process_collection_v2.py"
        assert origins["equiv_suite/native_workloads.py"] == frozen / "equiv_suite/native_workloads.py"
    assert set(origins) == entry.required_capsule_files()


def first_batch_fixture(tmp_path, monkeypatch):
    import hashlib
    entry = load_entry()
    monkeypatch.setattr(entry, 'ROUNDS', tmp_path / 'rounds')
    monkeypatch.setattr(entry, 'HERE', tmp_path / 'source')
    directory = entry.ROUNDS / 'E2-R040d'
    review_name = 'metadata/slots4_batch0_partial_review.json'
    pin_name = 'metadata/slots4_batch0_partial_pin.json'
    values = {
        'round.json': {'base': {'commit': entry.CANDIDATE}, 'verdict': 'failed_harness'},
        review_name: {'rid': 'E2-R040d', 'admitted': False,
                     'verdict': 'complete_case_evidence_preserved_not_group_accepted'},
        pin_name: {'rid': 'E2-R040d', 'immutable': True},
    }
    for name, value in values.items(): dump(directory / name, value)
    values[pin_name]['review_sha256'] = entry.sha(directory / review_name)
    dump(directory / pin_name, values[pin_name])
    prefix = 'dev_D16/native_slots_4/dev_D16_4_batch_0_None/'
    ledger = {prefix + 'collection/collection.json': 'a' * 64,
              prefix + 'capture/service_delivery.json': 'b' * 64}
    (directory / 'MANIFEST.sha256').write_text(''.join(
        digest + '  ' + name + '\n' for name, digest in ledger.items()), encoding='utf-8')
    expected = {name: entry.sha(directory / name) for name in entry.RETAINED_R040D_METADATA}
    monkeypatch.setattr(entry, 'RETAINED_R040D_METADATA', expected)
    for name in expected: (directory / name).chmod(0o444)
    body = {'schema': 'ft_r040d_retained_batch0/v1', 'round': 'E2-R040d',
            'candidate_commit': entry.CANDIDATE, 'case': 'dev_D16_4_batch_0_None',
            'round_sha256': expected['round.json'], 'manifest_sha256': expected['MANIFEST.sha256'],
            'review_sha256': expected[review_name], 'pin_sha256': expected[pin_name],
            'source_round': str(directory), 'case_root': str(directory / prefix),
            'accepted_group': False, 'raw_not_copied': True, 'case_metadata_files': ledger}
    binding = entry.HERE / 'R040D_RETAINED_BATCH0_BINDING_20261008.json'
    def seal_body():
        body.pop('metadata_sha256', None)
        body['metadata_sha256'] = hashlib.sha256(json.dumps(
            body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if binding.exists(): binding.chmod(0o600)
        dump(binding, body); binding.chmod(0o444)
    seal_body()
    calls = []
    def require_closed(rid, verdict):
        calls.append((rid, verdict)); return directory / 'round.json'
    return entry, directory, binding, body, seal_body, SimpleNamespace(require_closed_round=require_closed), calls


def test_retained_first_batch_reads_metadata_without_raw_and_cannot_accept_group(tmp_path, monkeypatch):
    entry, directory, binding, _, _, protocol, calls = first_batch_fixture(tmp_path, monkeypatch)
    result = entry.retained_slots4_batch0_binding(protocol)
    assert result['state'] == 'complete_case_pending_group_combination'
    assert result['accepted_group'] is False and result['raw_not_copied'] is True
    assert result['binding_file_sha256'] == entry.sha(binding)
    assert calls == [('E2-R040d', 'failed_harness')]
    assert not (directory / 'dev_D16').exists()


@pytest.mark.parametrize('change', ['candidate', 'group', 'file_sha', 'wrong_case_path'])
def test_retained_first_batch_rejects_identity_or_manifest_drift_even_with_self_sha(tmp_path, monkeypatch, change):
    entry, _, _, body, seal_body, protocol, _ = first_batch_fixture(tmp_path, monkeypatch)
    if change == 'candidate': body['candidate_commit'] = '0' * 40
    elif change == 'group': body['accepted_group'] = True
    elif change == 'wrong_case_path': body['case_root'] += '/other'
    else: body['case_metadata_files'] = {next(iter(body['case_metadata_files'])): '0' * 64}
    seal_body()
    with pytest.raises(RuntimeError, match='identity differs|manifest binding differs'):
        entry.retained_slots4_batch0_binding(protocol)


@pytest.mark.parametrize('name', ['round.json', 'MANIFEST.sha256',
                                'metadata/slots4_batch0_partial_review.json',
                                'metadata/slots4_batch0_partial_pin.json'])
def test_retained_first_batch_rejects_closed_metadata_sha_drift(tmp_path, monkeypatch, name):
    entry, directory, _, _, _, protocol, _ = first_batch_fixture(tmp_path, monkeypatch)
    path = directory / name; path.chmod(0o600); path.write_bytes(path.read_bytes() + b' '); path.chmod(0o444)
    with pytest.raises(RuntimeError, match='metadata differs'):
        entry.retained_slots4_batch0_binding(protocol)


def test_r040f_v4_uses_actual_sealed_r040e_review_location():
    entry = load_entry()
    assert entry.R040E_D04_REVIEW.as_posix() == '/data2/FreeToken/runs/dev_D16/reviews/E2-R040e_failed_harness_review_v1/review.json'
    assert entry.R040E_D04_REVIEW_SHA256 == '1928ac64c8bee653b0c8e290cc1dcf4bdc91c7b03adb12d552ac1857d25a98c1'
