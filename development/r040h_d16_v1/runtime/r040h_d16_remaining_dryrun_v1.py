"""R040a actual entry's filesystem path without model, lock, or batch."""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import subprocess


def foreign_lock_snapshot(lock, lifecycle):
    if lock.is_symlink():
        raise RuntimeError('foreign GPU lock is symlinked')
    if not lock.exists():
        return {'state': 'absent'}
    raw = lock.read_bytes()
    try:
        pid = json.loads(raw).get('pid')
        birth = lifecycle.process_identity(pid) if type(pid) is int else None
    except (json.JSONDecodeError, AttributeError):
        birth = None
    return {'state': 'held', 'inode': lock.stat().st_ino, 'raw': raw, 'birth': birth}


def foreign_lock_after(lock, before, lifecycle):
    if lock.is_symlink():
        return 'foreign_lock_recheck_required'
    if before['state'] == 'absent':
        return 'unchanged_absent' if not lock.exists() else 'foreign_lock_recheck_required'
    if lock.exists() and lock.stat().st_ino == before['inode'] and lock.read_bytes() == before['raw']:
        return 'preserved'
    if not lock.exists() and before['birth'] is not None:
        current = lifecycle.process_identity(before['birth']['pid'])
        if current is None or current.get('start_ticks') != before['birth']['start_ticks']:
            return 'foreign_owner_finished'
    return 'foreign_lock_recheck_required'


def dry_run(directory, *, entry, after, collector_review,
            collector_review_sha256, seed_sha256):
    out = Path(directory)
    formal = entry.ROUNDS / entry.RID
    if (out.exists() or out.is_symlink() or out.parent != entry.ROUNDS
            or not out.name.startswith('.dryrun_r040h_') or formal.exists()
            or any(path.is_symlink() for path in (out, *out.parents))):
        raise RuntimeError('r040h dry run requires a new canonical nonformal sibling')
    base = entry.base_module()
    protocol = base.shared_protocol()
    lifecycle = protocol.load_owned_lifecycle()
    foreign_before = foreign_lock_snapshot(protocol.LOCK, lifecycle)
    sources = entry.source_bindings()
    base.prepare(entry.HERE)
    entry.predecessor_checks(base, after)
    owner = entry.create_service_owner(0, out, protocol, file_dry_run=True)
    owner._r040a_file_probe_foreign_lock = foreign_before
    collector = entry.load(entry.HERE / 'r040f_d16_process_collection_v2.py', 'r040a_dry_collection')
    # R040a already completed the six anchor arms.  Bind their closed metadata
    # and deliberately do not fabricate an anchor_result or repeat the arms.
    review = {'candidate_commit': entry.CANDIDATE, 'sources': sources,
              'anchor_four_cell': {'state': 'already_complete_in_R040',
                                   'source_round': 'E2-R040a', 'completed_anchor_arms': 6,
                                   'closed_r040a': entry.d04_binding()}}
    out.mkdir(mode=0o700)
    out.chmod(0o700)
    with (out / '.cpu_write_probe').open('xb') as stream:
        stream.write(b'CPU_FILE_PROBE_ONLY\n')
    common = {'wrapper': entry.HERE / 'd16_native_capture_shutdown_v3.py',
              'source_review': Path(collector_review),
              'source_review_sha256': collector_review_sha256,
              'file_dry_run': True}
    # File paths depend on request count/shape, not prior measurement payloads.
    # Old round raw files are not read during this pre-lock dry run.
    short = [[value] * 512 for value in range(1, 5)]
    arms = {
        'cache': collector.collect_cache_processes(owner, short[0], **common),
        'interleave': collector.collect_native_processes(owner, [short[0], [5] * 5000],
                                                         slots=2, interleave=True, **common)}
    count = sum(len(result['arms']) for result in arms.values())
    if count != 8 or owner.proc is not None or formal.exists():
        raise RuntimeError('r040h remaining-arm file dry run coverage or side-effect boundary differs')
    if sources != entry.source_bindings():
        raise RuntimeError('r040h sources changed during actual dry run')
    foreign_after = foreign_lock_after(protocol.LOCK, foreign_before, lifecycle)
    receipt_path = out / 'dry_run_receipt.json'
    receipt = {'schema': 'ft_r040h_dry_run/v1', 'kind': 'CPU_FILE_PROBE',
               'not_measurement': True, 'rid': entry.RID, 'passed': True,
               'candidate_commit': entry.CANDIDATE, 'worktree': str(entry.WT),
               'script': str(entry.HERE / 'r040h_d16_remaining_prepare_v1.py'),
               'formal_entry': str(entry.HERE / 'r040h_d16_remaining_prepare_v1.py'),
               'dry_runner': str(Path(__file__).resolve()), 'uid': os.getuid(),
               'user': getpass.getuser(), 'cwd': os.getcwd(),
               'time': subprocess.check_output(['date', '+%Y-%m-%d %H:%M'], text=True).strip(),
               'port': owner.port, 'formal_round_path': str(formal),
               'receipt_path': str(receipt_path.resolve()), 'after_round': after,
               'sources': sources, 'collector_review': str(collector_review),
               'collector_review_sha256': collector_review_sha256,
               'seed_sha256': seed_sha256,
               'input_binding': entry.metadata_input_binding(entry.ROUNDS),
               'retained_r040e_slots4': entry.retained_r040e_slots4_binding(protocol),
               'retained_r040g_partial': entry.retained_r040g_partial_binding(protocol),
               'maximum_generation_calls': 10,
               'r055_section10_basis': entry.r055_section10_basis(protocol),
               'service_file_scopes': count,
               'files': sorted(str(path.relative_to(out)) for path in out.rglob('*') if path.is_file()),
               'arms': arms, 'anchor_pre_popen': None,
               'service_started': False, 'requests_sent': False, 'gpu_lock_taken': False,
               'batch_allocated': False, 'formal_rid_directory_created': False,
               'foreign_lock_before': foreign_before['state'], 'foreign_lock_after': foreign_after}
    with receipt_path.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, sort_keys=True, allow_nan=False)
        stream.write('\n')
    receipt_path.chmod(0o444)
    return receipt

