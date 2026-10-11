"""Local CPU orchestration evidence; never a server dry-run or launch review."""
import getpass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import time
from types import ModuleType, SimpleNamespace
import urllib.request

import pytest

HERE = Path(__file__).parents[1]
AFTER = 'E2-R058'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def denied(*_args, **_kwargs):
    pytest.fail('CPU entry validation crossed a process, network, or allocation boundary')


@pytest.fixture(autouse=True)
def cpu_guard(monkeypatch):
    monkeypatch.setenv('CUDA_VISIBLE_DEVICES', '')
    monkeypatch.setattr(os, 'getuid', lambda: 321, raising=False)
    monkeypatch.setattr(subprocess, 'Popen', denied)
    monkeypatch.setattr(urllib.request, 'urlopen', denied)
    monkeypatch.setattr(socket.socket, 'connect', denied)
    monkeypatch.setattr(socket.socket, 'connect_ex', denied)


@pytest.fixture
def capsule(monkeypatch, tmp_path):
    """Freeze a local source inventory; native imports remain explicit stubs."""
    source = tmp_path / 'source_tools'
    source.mkdir()
    original = load(HERE / 'r040a_d16_supplement_prepare_v5.py', 'r040a_v3_inventory_definition')
    retained = original.base_module()
    required = set(original.EXTRA) | set(retained.REQUIRED) | {
        'r040a_d16_supplement_prepare.py', 'd07_g3g4_prepare.py',
        't17_continuation_runner.py', 'd17_frozen_helpers.py',
        'helpers/raw/ft_probe_ckpt_tax.py', 't17_d14_exact_ids.py',
        'd16_native_process_collection_v2.py'}
    inventory = {}
    for name in sorted(required):
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        origin = HERE / name
        raw = ((HERE.parent / 'scripts/ft_probe_ckpt_tax.py').read_bytes()
               if name == 'helpers/raw/ft_probe_ckpt_tax.py'
               else origin.read_bytes() if origin.is_file() else b'# CPU source inventory fixture\n')
        destination.write_bytes(raw)
        destination.chmod(0o444)
        inventory[name] = hashlib.sha256(raw).hexdigest()
    manifest = source / 'MANIFEST.sha256'
    manifest.write_text(''.join(f'{digest}  {name}\n' for name, digest in inventory.items()), encoding='utf-8')
    manifest.chmod(0o444)
    entry = load(source / 'r040a_d16_supplement_prepare_v5.py', 'r040a_v3_entry_cpu')
    monkeypatch.setattr(entry, 'ROOT', tmp_path / 'FreeToken')
    monkeypatch.setattr(entry, 'ROUNDS', tmp_path / 'ft_rounds')
    monkeypatch.setattr(entry, 'WT', entry.ROOT / 'wt/e2base1')
    entry.ROUNDS.mkdir()
    return SimpleNamespace(entry=entry, retained=retained, inventory=inventory, manifest=manifest,
                           source=source, tmp=tmp_path)


def receipt_fixture(capsule):
    entry = capsule.entry
    directory = entry.ROUNDS / '.dryrun_R040a_receipt_cpu'
    directory.mkdir()
    path = directory / 'dry_run_receipt.json'
    document = {'schema': 'ft_r040a_dry_run/v5', 'kind': 'CPU_FILE_PROBE', 'not_measurement': True,
        'rid': entry.RID, 'passed': True, 'candidate_commit': entry.CANDIDATE, 'worktree': str(entry.WT),
        'script': str(Path(entry.__file__).resolve()), 'formal_entry': str(Path(entry.__file__).resolve()),
        'dry_runner': str(entry.DRY), 'uid': os.getuid(), 'user': getpass.getuser(), 'cwd': os.getcwd(),
        'formal_round_path': str(entry.ROUNDS / entry.RID), 'receipt_path': str(path.resolve()),
        'after_round': AFTER, 'sources': entry.source_bindings(), 'port': 43333, 'service_file_scopes': 36,
        'service_started': False, 'requests_sent': False, 'gpu_lock_taken': False,
        'batch_allocated': False, 'formal_rid_directory_created': False}
    path.write_text(json.dumps(document), encoding='utf-8')
    path.chmod(0o444)
    return path, document


def rewrite(path, document):
    path.chmod(0o644)
    path.write_text(json.dumps(document), encoding='utf-8')
    path.chmod(0o444)


def test_receipt_accepts_complete_actual_capsule_identity(capsule):
    path, document = receipt_fixture(capsule)
    value = capsule.entry.require_dry_run_receipt(path, AFTER)
    assert value['document'] == document and value['sha256'] == capsule.entry.sha(path)
    assert len(document['sources']) == len(capsule.inventory) + 1
    assert document['sources'][str(capsule.manifest)] == capsule.entry.sha(capsule.manifest)
    assert not (capsule.entry.ROUNDS / capsule.entry.RID).exists()


@pytest.mark.parametrize('field', ['uid', 'user', 'cwd', 'candidate_commit', 'worktree', 'script',
    'formal_entry', 'dry_runner', 'formal_round_path', 'receipt_path', 'after_round', 'schema', 'rid', 'passed'])
def test_receipt_rejects_identity_and_after_tampering(capsule, field):
    path, document = receipt_fixture(capsule)
    document[field] = False if field == 'passed' else 999 if field == 'uid' else 'foreign'
    rewrite(path, document)
    with pytest.raises(RuntimeError, match='identity/source/path'):
        capsule.entry.require_dry_run_receipt(path, AFTER)


@pytest.mark.parametrize('change', ['missing', 'wrong_hash', 'extra', 'manifest'])
def test_receipt_requires_exact_full_source_binding(capsule, change):
    path, document = receipt_fixture(capsule)
    key = next(iter(document['sources']))
    if change == 'missing':
        del document['sources'][key]
    elif change == 'wrong_hash':
        document['sources'][key] = '0' * 64
    elif change == 'extra':
        document['sources']['/foreign/source.py'] = 'a' * 64
    else:
        document['sources'][str(capsule.manifest)] = '0' * 64
    rewrite(path, document)
    with pytest.raises(RuntimeError, match='identity/source/path'):
        capsule.entry.require_dry_run_receipt(path, AFTER)


@pytest.mark.parametrize('field', ['service_started', 'requests_sent', 'gpu_lock_taken',
                                  'batch_allocated', 'formal_rid_directory_created'])
@pytest.mark.parametrize('value', [True, 0, None, 'false'])
def test_receipt_requires_each_prohibited_flag_to_be_literal_false(capsule, field, value):
    path, document = receipt_fixture(capsule)
    document[field] = value
    rewrite(path, document)
    with pytest.raises(RuntimeError, match='prohibited side effects'):
        capsule.entry.require_dry_run_receipt(path, AFTER)


@pytest.mark.parametrize('field,value', [('port', 8095), ('port', 0), ('port', 65536),
                                       ('port', True), ('port', '43333'),
                                       ('service_file_scopes', 35), ('service_file_scopes', 37)])
def test_receipt_rejects_shared_endpoint_or_incomplete_service_coverage(capsule, field, value):
    path, document = receipt_fixture(capsule)
    document[field] = value
    rewrite(path, document)
    with pytest.raises(RuntimeError, match='port or arm coverage'):
        capsule.entry.require_dry_run_receipt(path, AFTER)


@pytest.mark.parametrize('change', ['writable', 'foreign_parent', 'formal', 'wrong_prefix'])
def test_receipt_rejects_unsealed_or_noncanonical_location(capsule, change):
    path, document = receipt_fixture(capsule)
    if change == 'writable':
        path.chmod(0o644)
    else:
        directory = (capsule.tmp / '.dryrun_R040a_foreign' if change == 'foreign_parent'
                     else capsule.entry.ROUNDS / capsule.entry.RID if change == 'formal'
                     else capsule.entry.ROUNDS / 'dryrun_R040a_wrong')
        directory.mkdir()
        destination = directory / path.name
        destination.write_bytes(path.read_bytes())
        destination.chmod(0o444)
        path = destination
    with pytest.raises(RuntimeError, match='sealed receipt'):
        capsule.entry.require_dry_run_receipt(path, AFTER)


def test_receipt_rejects_symlinked_dry_directory_ancestor(monkeypatch, capsule):
    path, _ = receipt_fixture(capsule)
    alias = capsule.entry.ROUNDS / '.dryrun_R040a_alias'
    try:
        alias.symlink_to(path.parent, target_is_directory=True)
        candidate = alias / path.name
    except OSError as error:
        if os.name != 'nt':
            raise
        # Windows may deny symlink creation. Keep the ancestor check covered;
        # Linux validation exercises the actual directory symlink above.
        candidate = path
        original = Path.is_symlink
        monkeypatch.setattr(Path, 'is_symlink', lambda current: current == path.parent or original(current))
    with pytest.raises(RuntimeError, match='sealed receipt'):
        capsule.entry.require_dry_run_receipt(candidate, AFTER)


def test_receipt_rejects_noncanonical_filename_even_with_matching_identity(capsule):
    path, document = receipt_fixture(capsule)
    other = path.with_name('renamed_receipt.json')
    document['receipt_path'] = str(other.resolve())
    other.write_text(json.dumps(document), encoding='utf-8')
    other.chmod(0o444)
    with pytest.raises(RuntimeError, match='sealed receipt'):
        capsule.entry.require_dry_run_receipt(other, AFTER)


@pytest.mark.parametrize('change', ['writable_manifest', 'writable_source', 'changed_source',
                                  'missing_dependency', 'duplicate', 'traversal'])
def test_manifest_binds_frozen_dependency_inventory(capsule, change):
    if change == 'writable_manifest':
        capsule.manifest.chmod(0o644)
    elif change in ('writable_source', 'changed_source'):
        path = capsule.source / 'r040a_anchor_four_cell_v3.py'
        path.chmod(0o644)
        if change == 'changed_source':
            path.write_bytes(path.read_bytes() + b'\n# drift\n')
            path.chmod(0o444)
    else:
        capsule.manifest.chmod(0o644)
        rows = capsule.manifest.read_text().splitlines()
        if change == 'missing_dependency':
            rows = [row for row in rows if not row.endswith('r040a_private_port_owner_v2.py')]
        elif change == 'duplicate':
            rows.append(rows[0])
        else:
            rows.append('0' * 64 + '  ../foreign.py')
        capsule.manifest.write_text('\n'.join(rows) + '\n')
        capsule.manifest.chmod(0o444)
    with pytest.raises(RuntimeError, match='manifest|inventory'):
        capsule.entry.source_bindings()


def test_child_argv_uses_v3_entry_and_exact_dry_receipt(capsule):
    entry = capsule.entry
    launch, dry = capsule.tmp / 'launch.json', capsule.tmp / 'dry.json'
    argv = entry.child_argv(SimpleNamespace(), 71, launch, AFTER, dry)
    assert argv == [str(entry.ROOT / 'venv/bin/python'), str(Path(entry.__file__).resolve()),
        '--run', '--owned-child', '--batch', '71', '--launch-receipt', str(launch),
        '--after-round', AFTER, '--dry-receipt', str(dry)]
    assert 'supplement_prepare_v2.py' not in ' '.join(argv)


def dry_runtime(monkeypatch, capsule):
    """Use real anchor/collector/native writers with explicit CPU dependency stubs."""
    entry = capsule.entry
    events = []
    lock = capsule.tmp / 'gpu.lock'
    protocol = SimpleNamespace(LOCK=lock, load_owned_lifecycle=lambda: SimpleNamespace(),
        require_t20_failed_harness=lambda: events.append('t20_metadata'),
        require_r041_kept=lambda root: events.append(('r041_metadata', root)),
        require_closed_round=lambda rid, verdict: events.append(('preceding_metadata', rid, verdict)),
        checked_worktree=lambda wt: events.append(('worktree', wt)),
        take_d07_gpu_lock=denied, release_d07_gpu_lock=denied)

    class ProtocolRunner:
        @staticmethod
        def environment(_owner, wt, arm=None, d0=False):
            return {'PYTHONPATH': str(wt / 'python'), 'PYTHONUNBUFFERED': '1',
                    'VIRTUAL_ENV': '/CPU/venv', 'PATH': '/CPU/bin', 'LD_LIBRARY_PATH': '/CPU/lib',
                    'CUDA_VISIBLE_DEVICES': '0', 'FT_DEV_D0': 'must-be-removed'}

        set_status = staticmethod(denied)

    class Run:
        def __init__(self, options):
            self.options = options
            self.proc = None

        def compiled_extensions(self, wt):
            events.append(('native_binding', wt, self.environment(wt)['CUDA_VISIBLE_DEVICES']))
            return {'native': {'path': 'CPU_IMPORT_FIXTURE', 'sha256': 'a' * 64}}

        def startup_wrapper(self):
            return entry.HERE / 'd16_native_capture_shutdown_v3.py'

        parser = staticmethod(denied)

    Run.__module__ = 'r040a_cpu_native_run'

    def query(argv, **kwargs):
        events.append(('read_only_query', tuple(argv)))
        if argv[0] == 'date':
            return '2026-10-07 00:00 CPU_FIXTURE_ONLY'
        if argv[0] == 'nvidia-smi':
            return '4'
        if argv[0] == 'git':
            return 'E2-base.1@0aa23431'
        if argv[0] in ('numactl', 'free', 'ps'):
            return 'CPU_FIXTURE_ONLY'
        pytest.fail('unexpected external command: ' + repr(argv))

    monkeypatch.setattr(subprocess, 'check_output', query)
    gpu = SimpleNamespace(__name__=Run.__module__, Run=Run, ROOT=entry.ROOT, HERE=entry.HERE,
        PY='/CPU/venv/python', helper=SimpleNamespace(CANDIDATE=entry.CANDIDATE), shlex=shlex,
        time=time, subprocess=subprocess, urllib=SimpleNamespace(request=urllib.request),
        protocol={'Runner': ProtocolRunner, 'command': query},
        put=lambda path, value: Path(path).write_text(json.dumps(value), encoding='utf-8'))
    helper = SimpleNamespace(bind_protocol=lambda actual, folder: events.append(('bind_helpers', folder)))

    def configure(old, candidate):
        assert candidate == {'worktree': str(entry.WT), 'candidate_commit': entry.CANDIDATE,
                             'parent_commit': entry.CANDIDATE}
        events.append(('configure', candidate))
        return gpu, object()

    base = SimpleNamespace(prepare=capsule.retained.prepare, shared_protocol=lambda: protocol,
        configure_candidate_runtime=configure,
        load_source=lambda path, name: helper if Path(path).name == 'd17_frozen_helpers.py' else SimpleNamespace(),
        REQUIRED=capsule.retained.REQUIRED)
    monkeypatch.setattr(entry, 'base_module', lambda: base)
    private = load(entry.HERE / 'r040a_private_port_owner_v2.py', 'r040a_v3_private_cpu')

    def source_gate(owner, wt, candidate):
        assert candidate == entry.CANDIDATE
        environment = owner.environment(wt)
        assert environment['CUDA_VISIBLE_DEVICES'] == '' and not any(k.startswith('FT_') for k in environment)
        events.append(('source_gate', wt))
        return str(wt / 'python/freetoken/__init__.py')

    monkeypatch.setattr(private, '_private_gate', source_gate)
    anchor = load(entry.HERE / 'r040a_anchor_four_cell_v3.py', 'r040a_v3_actual_anchor_cpu')
    for name, value in [('ROOT', entry.ROOT), ('ROUNDS', entry.ROUNDS), ('LOCK', lock),
                        ('FT', str(entry.ROOT / 'venv/bin/ft'))]:
        monkeypatch.setattr(anchor, name, value)
    collector = load(entry.HERE / 'r040a_d16_process_collection_v4.py', 'r040a_v3_actual_collector_cpu')
    for name in ('d16_service_workloads', 't17_d14_runner', 'd16_native_capture_shutdown_v3'):
        module = ModuleType(name)
        module.collect = denied
        module.exact_id_request = denied
        module.read_sealed_service_delivery = denied
        monkeypatch.setitem(sys.modules, name, module)
    native = load(entry.HERE / 'd16_native_process_collection_v2.py', 'r040a_v3_native_file_loops_cpu')
    review = capsule.tmp / 'collector_review.json'
    report = capsule.tmp / 'collector_cpu_report.json'
    for path in (review, report):
        path.write_text('{"scope":"CPU_DEPENDENCY_FIXTURE_ONLY"}')
        path.chmod(0o444)

    def verify(wrapper, path, digest):
        assert path == review and digest == entry.sha(review)
        return {'source_files': {'startup': {'path': str(wrapper), 'sha256': entry.sha(wrapper)}},
                'review': str(review), 'cpu_report': str(report), 'model_admitted': False}

    monkeypatch.setattr(native, 'verify_source_review', verify)
    monkeypatch.setattr(collector, '_frozen', lambda: native)
    calls = []
    for function in ('collect_native_processes', 'collect_parking_processes', 'collect_cache_processes'):
        actual = getattr(collector, function)

        def observed(owner, inputs, _actual=actual, _name=function, **kwargs):
            calls.append((_name, inputs, dict(kwargs)))
            return _actual(owner, inputs, **kwargs)

        monkeypatch.setattr(collector, function, observed)
    modules = {'r040a_private_port_owner_v2.py': private,
               'r040a_anchor_four_cell_v3.py': anchor, 'r040a_d16_process_collection_v4.py': collector}
    original_load = entry.load
    monkeypatch.setattr(entry, 'load', lambda path, name: modules.get(Path(path).name) or original_load(path, name))
    seed = entry.ROOT / 'wt/e1r003/seed_45k.txt'
    seed.parent.mkdir(parents=True)
    seed.write_bytes(('CPU anchor business seed ' * 5000).encode())
    seed.chmod(0o444)
    dry = load(entry.DRY, 'r040a_v3_actual_dry_cpu')
    return SimpleNamespace(entry=entry, dry=dry, protocol=protocol, base=base, review=review,
                           seed=seed, events=events, calls=calls, owner=None)


def run_dry(runtime, output):
    return runtime.dry.dry_run(output, entry=runtime.entry, after=AFTER,
        collector_review=runtime.review, collector_review_sha256=runtime.entry.sha(runtime.review),
        seed_sha256=runtime.entry.sha(runtime.seed))


def test_actual_entry_dry_runs_36_writer_scopes_without_old_raw_or_side_effects(monkeypatch, capsule):
    runtime = dry_runtime(monkeypatch, capsule)
    previous = runtime.entry.ROUNDS / 'E2-R040/source_tools/realinput_28.json'
    previous.parent.mkdir(parents=True)
    previous.write_text('OLD_MEASUREMENT_MUST_NOT_BE_READ')
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if 'E2-R040' in path.parts:
            pytest.fail('dry-run read a previous round raw payload')
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', guarded_open)
    created = []
    original_factory = runtime.entry.create_service_owner

    def factory(batch, directory, protocol, *, file_dry_run=False):
        assert batch == 0 and file_dry_run is True
        owner = original_factory(batch, directory, protocol, file_dry_run=file_dry_run)
        created.append(owner)
        return owner

    monkeypatch.setattr(runtime.entry, 'create_service_owner', factory)
    out = runtime.entry.ROUNDS / '.dryrun_R040a_actual_cpu'
    receipt = run_dry(runtime, out)
    assert receipt['kind'] == 'CPU_FILE_PROBE' and receipt['not_measurement'] is True
    assert receipt['service_file_scopes'] == 36
    assert [len(receipt['arms'][name]['arms']) for name in ('batch2', 'batch4', 'parking', 'cache', 'interleave')] == [6, 10, 4, 4, 6]
    assert len(receipt['anchor_pre_popen']['arms']) == 6
    assert len(list(out.rglob('SERVE_CMD.txt'))) == 36
    assert len(list(out.glob('*/requests/*.json'))) == 60
    assert len(list(out.rglob('expected_capture.json'))) == 30
    assert len(list(out.rglob('file_permission_probe.json'))) == 30
    assert all(not receipt[key] for key in ('service_started', 'requests_sent', 'gpu_lock_taken',
                                           'batch_allocated', 'formal_rid_directory_created'))
    assert len(created) == 1 and created[0].options.batch == 0 and created[0].proc is None
    assert created[0].token is None and created[0].lock_inode is None
    assert not runtime.protocol.LOCK.exists() and not (runtime.entry.ROUNDS / runtime.entry.RID).exists()
    assert out.stat().st_mode & 0o200 and not (out / 'dry_run_receipt.json').stat().st_mode & 0o222
    assert runtime.entry.require_dry_run_receipt(out / 'dry_run_receipt.json', AFTER)['document'] == receipt
    assert runtime.calls[0][1] == [[1] * 512, [2] * 512]
    assert runtime.calls[1][1] == [[value] * 512 for value in range(1, 5)]
    assert runtime.calls[2][1] == runtime.calls[3][1] == [1] * 512
    assert runtime.calls[4][1] == [[1] * 512, [5] * 5000]
    assert [call[0] for call in runtime.calls] == ['collect_native_processes', 'collect_native_processes',
        'collect_parking_processes', 'collect_cache_processes', 'collect_native_processes']
    assert all(call[2]['file_dry_run'] is True for call in runtime.calls)
    assert runtime.calls[4][2]['interleave'] is True
    assert len([event for event in runtime.events if isinstance(event, tuple) and event[0] == 'source_gate']) == 36
    assert 't20_metadata' in runtime.events and ('preceding_metadata', AFTER, 'measured') in runtime.events


@pytest.mark.parametrize('change', ['existing', 'foreign_parent', 'wrong_prefix', 'formal_exists', 'foreign_lock', 'bad_after'])
def test_actual_dry_rejects_path_lock_and_after_before_services(monkeypatch, capsule, change):
    runtime = dry_runtime(monkeypatch, capsule)
    out = runtime.entry.ROUNDS / '.dryrun_R040a_invalid_cpu'
    if change == 'existing':
        out.mkdir()
    elif change == 'foreign_parent':
        out = capsule.tmp / '.dryrun_R040a_foreign'
    elif change == 'wrong_prefix':
        out = runtime.entry.ROUNDS / 'dryrun_R040a_wrong'
    elif change == 'formal_exists':
        (runtime.entry.ROUNDS / runtime.entry.RID).mkdir()
    elif change == 'foreign_lock':
        runtime.protocol.LOCK.write_text('foreign owner')
    with pytest.raises(RuntimeError, match='sibling|foreign GPU lock|insertion'):
        runtime.dry.dry_run(out, entry=runtime.entry, after='E2-R045' if change == 'bad_after' else AFTER,
            collector_review=runtime.review, collector_review_sha256=runtime.entry.sha(runtime.review),
            seed_sha256=runtime.entry.sha(runtime.seed))
    assert not runtime.calls and not list(out.glob('OFF_*'))


@pytest.mark.parametrize('args', [[], ['--run', '--dry-run'], ['--run'], ['--dry-run']])
def test_main_requires_one_mode_and_complete_receipt_inputs(capsule, args):
    with pytest.raises(SystemExit) as failure:
        capsule.entry.main(args)
    assert failure.value.code == 2


def test_execute_adapts_actual_child_entry_and_source_review_before_dispatch(monkeypatch, capsule):
    entry = capsule.entry
    path, document = receipt_fixture(capsule)
    sources = entry.source_bindings()
    observed = []
    review = {'sources': sources, 'dry_run_receipt': str(path), 'dry_run_receipt_sha256': entry.sha(path)}
    base = SimpleNamespace(require_review=lambda after: review,
                           run_supplement_body=lambda *args, **kwargs: ('body', kwargs),
                           load_source=lambda path, name: (Path(path), name),
                           write_new=lambda path, value: observed.append((path, value)))

    def execute(**kwargs):
        assert base.require_review(kwargs['after']) == review
        argv = base.child_argv(71, capsule.tmp / 'launch.json', kwargs['after'])
        assert argv[1] == str(Path(entry.__file__).resolve()) and argv[-2:] == ['--dry-receipt', str(path)]
        assert base.create_service_owner is entry.create_service_owner
        assert base.load_source(entry.HERE / 'r040a_anchor_four_cell_v1.py', 'anchor')[0].name == 'r040a_anchor_four_cell_v3.py'
        assert base.run_supplement_body()[1]['native_module'] is collector
        return kwargs

    collector = object()
    base.execute = execute
    monkeypatch.setattr(entry, 'base_module', lambda: base)
    monkeypatch.setattr(entry, 'load', lambda path, name: collector)
    monkeypatch.setattr(entry, 'source_bindings', lambda: sources)
    result = entry.execute(dry_receipt=path, owned_child=True, batch=71,
                           receipt=capsule.tmp / 'launch.json', after=AFTER)
    assert result == {'owned_child': True, 'batch': 71, 'receipt': capsule.tmp / 'launch.json', 'after': AFTER}


@pytest.mark.parametrize('change', ['source', 'receipt_path', 'receipt_hash'])
def test_execute_rejects_startup_review_tampering_before_dispatch(monkeypatch, capsule, change):
    entry = capsule.entry
    path, _ = receipt_fixture(capsule)
    sources = entry.source_bindings()
    review = {'sources': dict(sources), 'dry_run_receipt': str(path), 'dry_run_receipt_sha256': entry.sha(path)}
    if change == 'source':
        review['sources'][next(iter(sources))] = '0' * 64
    else:
        review['dry_run_receipt' if change == 'receipt_path' else 'dry_run_receipt_sha256'] = 'foreign'
    base = SimpleNamespace(require_review=lambda after: review, run_supplement_body=denied,
        load_source=denied, write_new=denied)
    base.execute = lambda **kwargs: base.require_review(kwargs['after'])
    monkeypatch.setattr(entry, 'base_module', lambda: base)
    monkeypatch.setattr(entry, 'source_bindings', lambda: sources)
    monkeypatch.setattr(entry, 'load', lambda *_: object())
    with pytest.raises(RuntimeError, match='startup review'):
        entry.execute(dry_receipt=path, after=AFTER)


@pytest.mark.parametrize('after', ['E2-R048', 'E2-R057', 'E2-R051-gate-D08', 'E2-R050-gate-D15', 'E2-R046b', 'E2-R045'])
def test_section13_rejects_queue_bypass_before_old_base_or_file_receipt(monkeypatch, after):
    entry = load(HERE / 'r040a_d16_supplement_prepare_v5.py', 'r040a_v4_queue_guard')
    monkeypatch.setattr(entry, 'require_dry_run_receipt', lambda *_: pytest.fail('queue bypass reached files'))
    with pytest.raises(RuntimeError, match='section thirteen requires E2-R058'):
        entry.execute(dry_receipt=Path('unused'), after=after)


def test_section13_actual_predecessor_checks_use_only_R058_measured(monkeypatch):
    entry = load(HERE / 'r040a_d16_supplement_prepare_v5.py', 'r040a_v5_actual_queue')
    calls = []
    protocol = SimpleNamespace(
        require_t20_failed_harness=lambda: calls.append(('T20', 'failed_harness')),
        require_r041_kept=lambda root: calls.append(('R041', 'kept')),
        require_closed_round=lambda rid, verdict: calls.append((rid, verdict)),
        checked_worktree=lambda wt: calls.append(('candidate', str(wt))))
    entry.predecessor_checks(SimpleNamespace(shared_protocol=lambda: protocol), 'E2-R058')
    assert ('E2-R058', 'measured') in calls
    assert not any(rid == 'E2-R048' for rid, _ in calls)
    with pytest.raises(RuntimeError):
        entry.predecessor_checks(SimpleNamespace(shared_protocol=lambda: protocol), 'E2-R048')


def test_section13_retained_core_accepts_R058_then_rejects_missing_review(monkeypatch):
    entry = load(HERE / 'r040a_d16_supplement_prepare_v5.py', 'r040a_v5_retained_core_queue')
    base = entry.base_module()
    calls = []
    protocol = SimpleNamespace(
        require_t20_failed_harness=lambda: None,
        require_r041_kept=lambda root: None,
        require_closed_round=lambda rid, verdict: calls.append((rid, verdict)),
        checked_worktree=lambda wt: None)
    monkeypatch.setattr(base, 'shared_protocol', lambda: protocol)
    monkeypatch.setattr(base, 'REVIEW_DIR', Path('this_r040a_v5_review_does_not_exist'))
    with pytest.raises(base.R040aPreparationError, match='sealed startup review'):
        base.require_review('E2-R058')
    assert calls == [('E2-R058', 'measured')]
