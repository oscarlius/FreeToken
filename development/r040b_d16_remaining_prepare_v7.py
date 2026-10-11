"""R040b CPU/file-dry entry for the remaining D16 arms after R040a closure."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
RID = 'E2-R040b'
ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
WT = ROOT / 'wt/e2base1-ordinary-rewind'
CANDIDATE = '0aa23431e5b800797543bdecbf35a01045131d7d'
REVIEW_DIR = ROOT / 'runs/dev_D16/r040b_startup_review_v1'
DRY = HERE / 'r040b_d16_remaining_dryrun_v7.py'
PINNED_T20_SOURCE = ROOT / 'runs/dev_D16/t20_startup_cpu_5deba0293ed3/source_tools'
EXTRA = ('r040a_d16_supplement_prepare_base_v2.py', 'r040b_d16_remaining_prepare_v7.py', 'r040b_d16_remaining_dryrun_v7.py',
         'r040a_d16_process_collection_v4.py', 'r040a_private_port_owner_v3.py',
         'r040a_anchor_four_cell_v4.py', 't16_private_port_base_runner.py', 'ft_batch_port_pair_v1.py',
         'R040A_D04_FAILED_CLOSURE_20261007.json')

# This is the actual import closure reached by create_service_owner() and the
# retained D16 collector.  The equiv_suite files are copied from the pinned D16
# CPU source package when a new capsule is assembled; they are not replaced by
# a summary-only collector or by placeholders in a launch package.
RUNTIME_CAPSULE_FILES = (
    't17_d14_artifacts.py', 't17_d14_gpu.py', 't17_d14_runner.py',
    't17_d14_exact_ids.py', 't17_d14_observe.py', 't17_d14_startup.py', 't17_operator_observe.py',
    't17_operator_startup.py', 't16_full_tail_base_runner.py',
    't17_owned_launch_protocol.py', 'd16_service_workloads.py', 'd16_exact_service_startup.py',
    'equiv_suite/service_capture.py', 'equiv_suite/service_capture_startup.py',
    'equiv_suite/sampler_capture.py', 'equiv_suite/native_workloads.py',
    'cpu_guard/sitecustomize.py',
    *(f'helpers/{name}' for name in ('cold_eq.py', 'probe_ft_cold32k.py',
                                     'ft_probe_ckpt_tax.py', 'serve_args_diff.py')),
    *(f'helpers/raw/{name}' for name in ('cold_eq.py', 'probe_ft_cold32k.py',
                                         'ft_probe_ckpt_tax.py', 'serve_args_diff.py')),
)


def required_capsule_files() -> set[str]:
    """Exact source files that a sealed R040a CPU/dry package must carry."""
    base = base_module()
    return set(EXTRA) | set(base.REQUIRED) | set(RUNTIME_CAPSULE_FILES) | {
        'r040a_d16_supplement_prepare.py', 'd07_g3g4_prepare.py',
        't17_continuation_runner.py', 'd17_frozen_helpers.py',
    }


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def d04_binding():
    path = HERE / 'R040A_D04_FAILED_CLOSURE_20261007.json'
    document = json.loads(path.read_text())
    report = document['report']
    return {'path': str(path.resolve()), 'sha256': sha(path),
            'round_sha256': report['round_sha256'], 'manifest_sha256': report['manifest_sha256'],
            'independent_review_sha256': report['independent_review_sha256'],
            'receipt_sha256': document['sha256'], 'completed_anchor_arms': report['completed_anchor_arms']}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def base_module():
    base = load(HERE / 'r040a_d16_supplement_prepare_base_v2.py', 'r040a_retained_prepare')
    base.ROOT, base.WT, base.RUNS = ROOT, WT, ROUNDS
    base.CANDIDATE = base.PARENT = CANDIDATE
    base.REVIEW_DIR = REVIEW_DIR
    return base


def capsule_source_origins(*, pinned_source: Path = PINNED_T20_SOURCE) -> dict[str, Path]:
    """Map every sealed capsule file to its reviewed byte origin.

    Current R040a leaf code comes from this directory.  Runtime and helper
    dependencies come from the independently sealed T20 CPU source tree, which
    is the only complete source archive for the retained collector imports.
    """
    pinned_source = Path(pinned_source)
    runtime = set(RUNTIME_CAPSULE_FILES)
    origins = {name: (HERE / 'd16_exact_service_startup_v2.py' if name == 'd16_exact_service_startup.py'
                      else pinned_source / name if name in runtime else HERE / name)
               for name in required_capsule_files()}
    return origins


def prepare_source_capsule(destination: Path, *, pinned_source: Path = PINNED_T20_SOURCE) -> dict:
    """Create the minimal R040a source package without copying raw round data."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise RuntimeError('R040a source capsule destination must be a new regular path')
    records = {}
    try:
        for name, origin in sorted(capsule_source_origins(pinned_source=pinned_source).items()):
            if (origin.is_symlink() or not origin.is_file() or origin.stat().st_mode & 0o222):
                raise RuntimeError('R040a capsule source is absent, symlinked, or writable: ' + str(origin))
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
            target.chmod(0o444)
            digest = sha(target)
            if digest != sha(origin):
                raise RuntimeError('R040a capsule copy SHA differs: ' + name)
            records[name] = {'origin': str(origin.resolve()), 'sha256': digest}
        manifest = destination / 'MANIFEST.sha256'
        manifest.write_text(''.join(f"{records[name]['sha256']}  {name}\n" for name in sorted(records)), encoding='utf-8')
        manifest.chmod(0o444)
        for path in sorted((item for item in destination.rglob('*') if item.is_dir()), reverse=True):
            path.chmod(0o555)
        destination.chmod(0o555)
        return {'schema': 'ft_r040a_source_capsule/v1', 'destination': str(destination),
                'manifest': str(manifest), 'manifest_sha256': sha(manifest), 'files': records}
    except BaseException:
        # Do not silently leave a partially writable source package for review.
        if destination.exists():
            for path in sorted(destination.rglob('*'), reverse=True):
                try: path.chmod(0o700 if path.is_dir() else 0o600)
                except OSError: pass
        raise


def source_bindings():
    """Bind this actual source capsule, including its retained helper archive."""
    manifest = HERE / 'MANIFEST.sha256'
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_mode & 0o222:
        raise RuntimeError('R040a source capsule requires its frozen manifest')
    declared = {}
    for line in manifest.read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        name = name.removeprefix('./')
        path = HERE / name
        if (len(digest) != 64 or Path(name).is_absolute() or '..' in Path(name).parts
                or name in declared or any(p.is_symlink() for p in (path, *path.parents))
                or not path.is_file() or path.stat().st_mode & 0o222 or sha(path) != digest):
            raise RuntimeError('R040a source inventory differs: ' + name)
        declared[name] = digest
    required = required_capsule_files()
    if not required <= declared.keys():
        missing = sorted(required - declared.keys())
        raise RuntimeError('R040a source manifest omits actual dependencies: ' + ', '.join(missing))
    result = {str(HERE / name): digest for name, digest in declared.items()}
    result[str(manifest)] = sha(manifest)
    return result


def predecessor_checks(base, after):
    verdicts = {'E2-R040a': 'failed_harness'}
    if after not in verdicts:
        raise RuntimeError('R040b requires the closed R040a failed-harness metadata')
    protocol = base.shared_protocol()
    protocol.require_closed_round(after, verdicts[after])
    protocol.checked_worktree(WT)
    closure = json.loads((HERE / 'R040A_D04_FAILED_CLOSURE_20261007.json').read_text())
    report = closure.get('report', {})
    if (report.get('rid') != 'E2-R040a' or report.get('verdict') != 'failed_harness'
            or report.get('candidate_commit') != CANDIDATE or not report.get('readonly')
            or report.get('completed_anchor_arms') != 6):
        raise RuntimeError('R040b D04 closed-R040a binding differs')


def create_service_owner(batch, directory, protocol, *, file_dry_run=False):
    base = base_module()
    old = base.load_source(HERE / 't17_continuation_runner.py', 'r040a_native_runtime')
    gpu, _ = base.configure_candidate_runtime(old, {
        'worktree': str(WT), 'candidate_commit': CANDIDATE, 'parent_commit': CANDIDATE})
    helpers = base.load_source(HERE / 'd17_frozen_helpers.py', 'r040a_bound_helpers')
    helpers.bind_protocol(gpu.protocol, HERE / 'helpers')
    lifecycle = protocol.load_owned_lifecycle()
    native = next(cls for cls in gpu.Run.__mro__
                  if cls.__module__ == gpu.__name__ and cls.__name__ == 'Run')

    class SupplementOwner(native):
        def set_status(self, **values):
            if file_dry_run:
                raise RuntimeError('file dry-run cannot publish formal status')
            return gpu.protocol['Runner'].set_status(self, rid=RID, card='T20', **values)

        def environment(self, wt, arm=None, d0=False):
            env = gpu.protocol['Runner'].environment(self, wt, arm, d0)
            for key in list(env):
                if key.startswith('FT_'):
                    env.pop(key)
            if file_dry_run:
                env['CUDA_VISIBLE_DEVICES'] = ''
                env['PYTHONPATH'] = str(HERE / 'cpu_guard') + ':' + env['PYTHONPATH']
            return env

    private = load(HERE / 'r040a_private_port_owner_v3.py', 'r040a_private_owner')
    owner = private.make_owner(gpu, SupplementOwner, lifecycle,
        SimpleNamespace(rid=RID, batch=batch, run=True, gate='T20'),
        directory=directory, file_dry_run=file_dry_run)
    owner.worktree = WT
    owner.status = Path(directory) / f'status_batch{batch}.json'
    owner.token = None if file_dry_run else protocol.LOCK.read_text()
    owner.lock_inode = None if file_dry_run else protocol.LOCK.stat().st_ino
    return owner


def require_dry_run_receipt(path, after):
    path = Path(path)
    if (any(parent.is_symlink() for parent in (path, *path.parents))
            or not path.is_file() or path.stat().st_mode & 0o222
            or path.parent.parent != ROUNDS or path.resolve().parent.parent != ROUNDS.resolve()
            or path.name != 'dry_run_receipt.json'
            or not path.parent.name.startswith('.dryrun_R040b_')):
        raise RuntimeError('R040b requires a sealed receipt in its actual dry sibling')
    document = json.loads(path.read_text())
    expected = {'schema': 'ft_r040b_dry_run/v7', 'rid': RID, 'passed': True,
                'candidate_commit': CANDIDATE, 'worktree': str(WT),
                'script': str(Path(__file__).resolve()), 'formal_entry': str(Path(__file__).resolve()),
                'dry_runner': str(DRY), 'uid': os.getuid(), 'user': getpass.getuser(),
                'cwd': os.getcwd(), 'formal_round_path': str(ROUNDS / RID),
                'receipt_path': str(path.resolve()), 'after_round': after,
                'sources': source_bindings()}
    if any(document.get(key) != value for key, value in expected.items()):
        raise RuntimeError('R040b actual dry receipt identity/source/path differs')
    if (type(document.get('port')) is not int or not 1024 <= document['port'] <= 65535
            or document['port'] == 8095 or document.get('service_file_scopes') != 30):
        raise RuntimeError('R040b actual dry receipt port or arm coverage differs')
    if any(document.get(key) is not False for key in (
            'service_started', 'requests_sent', 'gpu_lock_taken', 'batch_allocated',
            'formal_rid_directory_created')):
        raise RuntimeError('R040b dry receipt records prohibited side effects')
    if document.get('foreign_lock_after') not in ('unchanged_absent', 'preserved', 'foreign_owner_finished'):
        raise RuntimeError('R040a foreign lock proof requires a new dry review')
    return {'path': str(path), 'sha256': sha(path), 'document': document}


def child_argv(base, batch, receipt, after, dry_receipt):
    return [str(ROOT / 'venv/bin/python'), str(Path(__file__).resolve()), '--run',
            '--owned-child', '--batch', str(batch), '--launch-receipt', str(receipt),
            '--after-round', after, '--dry-receipt', str(dry_receipt)]


def execute(*, dry_receipt, owned_child=False, batch=None, receipt=None,
            after='E2-R040a'):
    if after != 'E2-R040a':
        raise RuntimeError('R040b requires closed R040a metadata before execution')
    dry = require_dry_run_receipt(dry_receipt, after)
    base = base_module()
    original_review = base.require_review

    def reviewed(round_after):
        document = original_review(round_after)
        expected = source_bindings()
        if (any(document.get('sources', {}).get(path) != digest for path, digest in expected.items())
                or document.get('dry_run_receipt') != dry['path']
                or document.get('dry_run_receipt_sha256') != dry['sha256']):
            raise RuntimeError('R040a R startup review omits actual sources or dry receipt')
        if (document.get('collector_review') != dry['document'].get('collector_review')
                or document.get('collector_review_sha256') != dry['document'].get('collector_review_sha256')
                or document.get('anchor_four_cell', {}).get('input_binding', {}).get('sha256')
                   != dry['document'].get('seed_sha256')):
            raise RuntimeError('R040a source review or anchor input differs from actual dry run')
        return document

    base.require_review = reviewed
    base.child_argv = lambda number, launch, previous: child_argv(base, number, launch, previous, dry_receipt)
    base.create_service_owner = create_service_owner
    collector = load(HERE / 'r040a_d16_process_collection_v4.py', 'r040a_private_collection')
    original_body = base.run_supplement_body
    base.run_supplement_body = lambda *args, **kwargs: original_body(*args, native_module=collector, **kwargs)
    original_load = base.load_source
    base.load_source = lambda path, name: original_load(
        HERE / 'r040a_anchor_four_cell_v4.py' if Path(path).name == 'r040a_anchor_four_cell_v1.py' else path, name)
    original_write = base.write_new

    def write(path, value):
        original_write(path, value)
        if Path(path).name == 'admission.json':
            launch = json.loads(Path(receipt).read_text())
            wrapper = Path(launch['wrapper'])
            raw = wrapper.read_bytes()
            if wrapper.is_symlink() or hashlib.sha256(raw).hexdigest() != launch['wrapper_sha256']:
                raise RuntimeError('R040a actual batch wrapper binding differs')
            with (Path(path).parent / 'batch.sh').open('xb') as stream:
                stream.write(raw)

    base.write_new = write
    return base.execute(owned_child=owned_child, batch=batch, receipt=receipt, after=after)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--owned-child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--batch', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--launch-receipt', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--after-round', default='E2-R040a')
    parser.add_argument('--dry-receipt', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--dry-run-dir', type=Path)
    parser.add_argument('--collector-review', type=Path)
    parser.add_argument('--collector-review-sha256')
    parser.add_argument('--anchor-seed-sha256')
    args = parser.parse_args(argv)
    if args.run == args.dry_run:
        parser.error('choose exactly one of --dry-run or --run')
    if args.dry_run:
        if not all((args.dry_run_dir, args.collector_review,
                    args.collector_review_sha256, args.anchor_seed_sha256)):
            parser.error('dry-run requires directory, collector review/SHA and bound seed SHA')
        dry = load(DRY, 'r040a_actual_file_dry')
        return dry.dry_run(args.dry_run_dir, entry=load(Path(__file__), 'r040a_dry_entry'),
                          after=args.after_round, collector_review=args.collector_review,
                          collector_review_sha256=args.collector_review_sha256,
                          seed_sha256=args.anchor_seed_sha256)
    if args.dry_receipt is None:
        parser.error('--run requires --dry-receipt')
    return execute(dry_receipt=args.dry_receipt, owned_child=args.owned_child,
                   batch=args.batch, receipt=args.launch_receipt, after=args.after_round)


if __name__ == '__main__':
    main()
