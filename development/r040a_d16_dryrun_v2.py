"""R040a actual entry's filesystem path without model, lock, or batch."""
from __future__ import annotations

import getpass
import json
import os
from pathlib import Path
import subprocess


def dry_run(directory, *, entry, after, collector_review,
            collector_review_sha256, seed_sha256):
    out = Path(directory)
    formal = entry.ROUNDS / entry.RID
    if (out.exists() or out.is_symlink() or out.parent != entry.ROUNDS
            or not out.name.startswith('.dryrun_R040a_') or formal.exists()
            or any(path.is_symlink() for path in (out, *out.parents))):
        raise RuntimeError('R040a dry run requires a new canonical nonformal sibling')
    base = entry.base_module()
    protocol = base.shared_protocol()
    if protocol.LOCK.exists() or protocol.LOCK.is_symlink():
        raise RuntimeError('foreign GPU lock exists; actual dry precheck remains queued')
    sources = entry.source_bindings()
    base.prepare(entry.HERE)
    entry.predecessor_checks(base, after)
    owner = entry.create_service_owner(0, out, protocol, file_dry_run=True)
    collector = entry.load(entry.HERE / 'r040a_d16_process_collection_v4.py', 'r040a_dry_collection')
    anchor = entry.load(entry.HERE / 'r040a_anchor_four_cell_v2.py', 'r040a_dry_anchor')
    review = {'candidate_commit': entry.CANDIDATE, 'sources': sources,
              'anchor_four_cell': {
                  'state': 'queued_bound_supplement',
                  'probe_path': str(entry.HERE / 'helpers/raw/ft_probe_ckpt_tax.py'),
                  'probe_sha256': anchor.PROBE_SHA,
                  'input_binding': {'path': str(entry.ROOT / 'wt/e1r003/seed_45k.txt'),
                                    'sha256': seed_sha256}}}
    out.mkdir(mode=0o700)
    out.chmod(0o700)
    with (out / '.cpu_write_probe').open('xb') as stream:
        stream.write(b'CPU_FILE_PROBE_ONLY\n')
    # Formal execution also runs this anchor scope first, when the approved
    # source review marks the missing four-cell item as queued.
    anchor_result = anchor.collect_anchor_four_cell(owner, review, file_dry_run=True)
    common = {'wrapper': entry.HERE / 'd16_native_capture_shutdown_v3.py',
              'source_review': Path(collector_review),
              'source_review_sha256': collector_review_sha256,
              'file_dry_run': True}
    # File paths depend on request count/shape, not prior measurement payloads.
    # Old round raw files are not read during this pre-lock dry run.
    short = [[value] * 512 for value in range(1, 5)]
    arms = {
        'batch2': collector.collect_native_processes(owner, short[:2], slots=2, **common),
        'batch4': collector.collect_native_processes(owner, short, slots=4, **common),
        'parking': collector.collect_parking_processes(owner, short[0], **common),
        'cache': collector.collect_cache_processes(owner, short[0], **common),
        'interleave': collector.collect_native_processes(owner, [short[0], [5] * 5000],
                                                         slots=2, interleave=True, **common)}
    count = sum(len(result['arms']) for result in arms.values()) + len(anchor_result['arms'])
    if count != 36 or owner.proc is not None or formal.exists() or protocol.LOCK.exists():
        raise RuntimeError('R040a file dry run coverage or side-effect boundary differs')
    if sources != entry.source_bindings():
        raise RuntimeError('R040a sources changed during actual dry run')
    receipt_path = out / 'dry_run_receipt.json'
    receipt = {'schema': 'ft_r040a_dry_run/v3', 'kind': 'CPU_FILE_PROBE',
               'not_measurement': True, 'rid': entry.RID, 'passed': True,
               'candidate_commit': entry.CANDIDATE, 'worktree': str(entry.WT),
               'script': str(entry.HERE / 'r040a_d16_supplement_prepare_v3.py'),
               'formal_entry': str(entry.HERE / 'r040a_d16_supplement_prepare_v3.py'),
               'dry_runner': str(Path(__file__).resolve()), 'uid': os.getuid(),
               'user': getpass.getuser(), 'cwd': os.getcwd(),
               'time': subprocess.check_output(['date', '+%Y-%m-%d %H:%M'], text=True).strip(),
               'port': owner.port, 'formal_round_path': str(formal),
               'receipt_path': str(receipt_path.resolve()), 'after_round': after,
               'sources': sources, 'collector_review': str(collector_review),
               'collector_review_sha256': collector_review_sha256,
               'seed_sha256': seed_sha256, 'service_file_scopes': count,
               'files': sorted(str(path.relative_to(out)) for path in out.rglob('*') if path.is_file()),
               'arms': arms, 'anchor_pre_popen': anchor_result,
               'service_started': False, 'requests_sent': False, 'gpu_lock_taken': False,
               'batch_allocated': False, 'formal_rid_directory_created': False}
    with receipt_path.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, sort_keys=True, allow_nan=False)
        stream.write('\n')
    receipt_path.chmod(0o444)
    return receipt
