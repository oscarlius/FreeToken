"""Pause-only adapter and real file preparation for the authorized R055b."""
from __future__ import annotations
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
RID = 'E2-R055b-gate-D06'
PARENT_COMMIT = '0aa23431e5b800797543bdecbf35a01045131d7d'
CANDIDATE_COMMIT = 'effb9969706922ddad9e59b96377e46469ebe97f'

def load(name, label):
    spec = importlib.util.spec_from_file_location(label, HERE / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

base = load('r055_gate_d06_prepare.py', 'r055b_retained_private_gate')
base.ASSIGNED_RID = RID
ROOT, ROUNDS, write_new = base.ROOT, base.ROUNDS, base.write_new

class CandidateRunner(base.CandidateRunner):
    def execute(self):
        if self.directory.exists():
            raise RuntimeError('R055b formal round exists; preserve its bytes')
        self.directory.mkdir()
        self.set_status(state='pause_only_preparing', cold_arms_replayed=False)

def dry_run():
    owner = load('r055b_owned_launch.py', 'r055b_final_dry_owner')
    legacy = owner._legacy()
    gate = legacy.d07()
    if gate.LOCK.exists() or gate.LOCK.is_symlink():
        raise RuntimeError('R055b real-path dry run waits for the current GPU batch')
    gate.require_r041_kept(ROOT)
    gate.require_closed_round('E2-R050-gate-D15', 'kept')
    retained = owner.require_retained_cold(legacy)
    candidate = legacy.require_candidate()
    legacy.require_native_reuse()
    tools = gate.verify_d07_tools(candidate)
    sources = owner.source_hashes()
    for name in sources:
        path = HERE / name
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
            raise RuntimeError('R055b actual execution source is not frozen: ' + name)
    formal = ROUNDS / RID
    target = ROUNDS / f'.dryrun_R055b_{RID}'
    if formal.exists() or target.exists() or target.is_symlink():
        raise RuntimeError('R055b formal or dry path already exists')
    target.mkdir(mode=0o700)
    for directory in (ROOT / 'runs/dev_R055', ROOT / 'runs/plan_batches'):
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / '.r055b-file-write-probe'
        with probe.open('x') as stream:
            stream.write('CPU FILE PROBE ONLY\n')
        probe.chmod(0o444)
        probe.chmod(0o600)
        with probe.open('a') as stream:
            stream.write('write permission restored\n')
        probe.unlink()
    pause = owner.pause_smoke(legacy, gate, 1, target / 'PAUSE_ON',
                              file_dry_run=True, worktree_override=candidate)
    if formal.exists() or gate.LOCK.exists():
        raise RuntimeError('R055b dry path crossed a formal round or lock boundary')
    receipt = {
        'schema': 'ft_R055b_dry_run/v2', 'rid': RID,
        'user': {'uid': os.getuid(), 'user': subprocess.check_output(['id', '-un'], text=True).strip()},
        'cwd': str(Path.cwd()), 'owner_path': str((HERE / 'r055b_owned_launch.py').resolve()),
        'adapter_path': str(Path(__file__).resolve()), 'formal_directory': str(formal),
        'worktrees': {'parent': {'head': PARENT_COMMIT}, 'candidate': {'head': CANDIDATE_COMMIT}},
        'source_sha256': sources, 'retained_cold': retained, 'tools': tools,
        'pause_on': pause, 'port': pause['port'], 'arms': ['PAUSE_ON'], 'passed': True,
        'service_started': False, 'requests_sent': False, 'gpu_lock_taken': False,
        'batch_allocated': False, 'formal_rid_directory_created': False,
        'timestamp': subprocess.check_output(['date', '+%Y-%m-%d %H:%M'], text=True).strip(),
    }
    path = target / 'dry_run_receipt.json'
    write_new(path, receipt)
    path.chmod(0o444)
    return {**receipt, 'receipt_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
