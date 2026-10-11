"""R040a entry binding the actual private owner and real-path file dry-run."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
RID = 'E2-R040a'
ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
WT = ROOT / 'wt/e2base1-ordinary-rewind'
CANDIDATE = '0aa23431e5b800797543bdecbf35a01045131d7d'
REVIEW_DIR = ROOT / 'runs/dev_D16/r040a_startup_review_v5'
DRY = HERE / 'r040a_d16_dryrun_v3.py'
EXTRA = ('r040a_d16_supplement_prepare_v4.py', 'r040a_d16_dryrun_v3.py',
         'r040a_d16_process_collection_v4.py', 'r040a_private_port_owner_v2.py',
         'r040a_anchor_four_cell_v3.py', 't16_private_port_base_runner.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def base_module():
    base = load(HERE / 'r040a_d16_supplement_prepare.py', 'r040a_retained_prepare')
    base.ROOT, base.WT, base.RUNS = ROOT, WT, ROUNDS
    base.CANDIDATE = base.PARENT = CANDIDATE
    base.REVIEW_DIR = REVIEW_DIR
    return base


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
    base = base_module()
    required = set(EXTRA) | set(base.REQUIRED) | {
        'r040a_d16_supplement_prepare.py', 'd07_g3g4_prepare.py',
        't17_continuation_runner.py', 'd17_frozen_helpers.py',
        'helpers/raw/ft_probe_ckpt_tax.py'}
    if not required <= declared.keys():
        raise RuntimeError('R040a source manifest omits actual dependencies')
    result = {str(HERE / name): digest for name, digest in declared.items()}
    result[str(manifest)] = sha(manifest)
    return result


def predecessor_checks(base, after):
    verdicts = {'E2-R048': 'measured'}
    if after not in verdicts:
        raise RuntimeError('R040a independent insertion must precede T05')
    protocol = base.shared_protocol()
    protocol.require_t20_failed_harness()
    protocol.require_r041_kept(ROOT)
    protocol.require_closed_round(after, verdicts[after])
    protocol.checked_worktree(WT)


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

    private = load(HERE / 'r040a_private_port_owner_v2.py', 'r040a_private_owner')
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
            or not path.parent.name.startswith('.dryrun_R040a_')):
        raise RuntimeError('R040a requires a sealed receipt in its actual dry sibling')
    document = json.loads(path.read_text())
    expected = {'schema': 'ft_r040a_dry_run/v4', 'rid': RID, 'passed': True,
                'candidate_commit': CANDIDATE, 'worktree': str(WT),
                'script': str(Path(__file__).resolve()), 'formal_entry': str(Path(__file__).resolve()),
                'dry_runner': str(DRY), 'uid': os.getuid(), 'user': getpass.getuser(),
                'cwd': os.getcwd(), 'formal_round_path': str(ROUNDS / RID),
                'receipt_path': str(path.resolve()), 'after_round': after,
                'sources': source_bindings()}
    if any(document.get(key) != value for key, value in expected.items()):
        raise RuntimeError('R040a actual dry receipt identity/source/path differs')
    if (type(document.get('port')) is not int or not 1024 <= document['port'] <= 65535
            or document['port'] == 8095 or document.get('service_file_scopes') != 36):
        raise RuntimeError('R040a actual dry receipt port or arm coverage differs')
    if any(document.get(key) is not False for key in (
            'service_started', 'requests_sent', 'gpu_lock_taken', 'batch_allocated',
            'formal_rid_directory_created')):
        raise RuntimeError('R040a dry receipt records prohibited side effects')
    return {'path': str(path), 'sha256': sha(path), 'document': document}


def child_argv(base, batch, receipt, after, dry_receipt):
    return [str(ROOT / 'venv/bin/python'), str(Path(__file__).resolve()), '--run',
            '--owned-child', '--batch', str(batch), '--launch-receipt', str(receipt),
            '--after-round', after, '--dry-receipt', str(dry_receipt)]


def execute(*, dry_receipt, owned_child=False, batch=None, receipt=None,
            after='E2-R048'):
    if after != 'E2-R048':
        raise RuntimeError('R040a section twelve requires E2-R048 measured before execution')
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
        HERE / 'r040a_anchor_four_cell_v3.py' if Path(path).name == 'r040a_anchor_four_cell_v1.py' else path, name)
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
    parser.add_argument('--after-round', default='E2-R048')
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
