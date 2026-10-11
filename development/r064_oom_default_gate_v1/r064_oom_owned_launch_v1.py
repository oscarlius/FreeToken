#!/usr/bin/env python3
"""Owned R060 controller/child and the real CPU-only file-dry rehearsal.

The dry sibling is deliberately non-RID.  It exercises the same source-copy,
writer and arm-output paths that the child will use, but stops before Popen.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

RID = 'E2-R064-gate-OOM'
BASE = '0aa23431e5b800797543bdecbf35a01045131d7d'
CANDIDATE = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
HERE = Path(__file__).resolve().parent
R060 = HERE / 'r064_oom_t16_prepare_v1.py'
PAIR = HERE / 'ft_batch_port_pair_v1.py'
CPU_GUARD = HERE / 'cpu_guard/sitecustomize.py'
CPU_GUARD_SHA256 = '887fe6dd9943f6359b09ee37d41089033f9d6e1e654c43f51e3a64158423637d'
NATIVE = ROOT / 'runs/dev_OOM/r064_native_provenance_v1.json'
REVIEW_DIR = ROOT / 'runs/dev_OOM/reviews/E2-R064-gate-OOM-v1'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_r060():
    spec = importlib.util.spec_from_file_location('r060_owned_runtime', R060)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_d07():
    return load_r060().load_d07(CANDIDATE, ROOT / 'wt/e2oom-protocol-restart')


def source_hashes() -> dict[str, str]:
    r060 = load_r060()
    sources = {str(HERE / 'r064_oom_owned_launch_v1.py'): sha(Path(__file__).resolve()), **r060.source_hashes()}
    sources[str(CPU_GUARD)] = CPU_GUARD_SHA256
    return sources


def dry_dir() -> Path:
    return ROUNDS / '.dryrun_R060c_v1_E2-R064-gate-OOM'


def dry_receipt() -> Path:
    return dry_dir() / 'dry_run_receipt.json'


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def check_source(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError(f'R060 source is not sealed: {path}')


def candidate_binding() -> Path:
    r060 = load_r060()
    worktree = ROOT / 'wt/e2oom-protocol-restart'
    r060.candidate_binding(CANDIDATE, worktree)
    for tree, commit in ((ROOT / 'wt/e2base1-ordinary-rewind', BASE), (worktree, CANDIDATE)):
        if tree.is_symlink():
            raise RuntimeError('R060 worktree is symlinked')
        head = subprocess.check_output(['git', '-C', str(tree), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', '-C', str(tree), 'status', '--porcelain', '--untracked-files=no'], text=True)
        if head != commit or dirty:
            raise RuntimeError('R060 worktree identity or cleanliness differs')
    return worktree


def copy_runtime_sources(target: Path) -> list[dict]:
    target.mkdir(mode=0o700, parents=True, exist_ok=False)
    rows = []
    for source_name in source_hashes():
        source = Path(source_name)
        if source == CPU_GUARD:
            continue
        check_source(source)
        copied = target / source.name
        shutil.copyfile(source, copied)
        copied.chmod(0o600)
        if sha(source) != sha(copied):
            raise RuntimeError('R060 runtime source copy SHA differs')
        rows.append({'source': str(source), 'copy': str(copied), 'sha256': sha(copied),
                     'md5': hashlib.md5(copied.read_bytes()).hexdigest(), 'mode': oct(copied.stat().st_mode & 0o777)})
    return rows


def port_pair():
    spec = importlib.util.spec_from_file_location('r060_pair', PAIR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    port = module.dynamic_port()
    pair = module.port_receipt(port)
    if pair.get('api') != port or pair.get('tcpstore') != port + 1:
        raise RuntimeError('R060 adjacent API/TCPStore pair differs')
    return pair


def output_probe(arm: Path, d0: bool, pair: dict) -> list[str]:
    """The production arm names, all written before the Popen boundary."""
    names = ['SERVE_CMD.txt', 'ENV.txt', 'serve.log', 'serve_args.txt', 'owned_process.json',
             'health.json', 'ready_sayok.json', 'args_checked.json', 'markers.json', 'det.json',
             'det.stdout', 'det.err', 'tax.log', 'tax.json', 'business_prefill_events.json',
             'prefill_seq.txt', 'result.json', 'failed_harness.json', 'owned_cleanup.json']
    if d0:
        names += ['d0_prefill.jsonl', 'prefill_while_alive.json']
    write_new(arm / 'port_pair.json', pair)
    for name in names:
        path = arm / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as stream:
            stream.write('R060 FILE-DRY OUTPUT PROBE ONLY\n')
        with path.open('a', encoding='utf-8') as stream:
            stream.write('append verified\n')
    return names


def file_dry_run() -> dict:
    if sys.platform != 'linux':
        raise RuntimeError('R060 real file-dry requires the Linux measurement user')
    target = dry_dir()
    if target.exists() or target.is_symlink() or (ROUNDS / RID).exists() or (ROUNDS / RID).is_symlink():
        raise RuntimeError('R060 dry sibling or formal RID already exists')
    r060, worktree, d07 = load_r060(), candidate_binding(), load_d07()
    for path in (Path(__file__).resolve(), R060, PAIR, CPU_GUARD):
        check_source(path)
    r060.require_r060_native_provenance(NATIVE)
    target.mkdir(mode=0o700)
    copies = copy_runtime_sources(target / 'runtime_sources')
    env = d07.clean_environment(worktree)
    env['CUDA_VISIBLE_DEVICES'] = ''
    # Guard must be first: it rejects both connect and listen before imports.
    env['PYTHONPATH'] = str(CPU_GUARD.parent) + ':' + str(worktree / 'python')
    env.pop('FT_DEV_ROUTE_TRACE', None); env.pop('FT_DEV_PAUSE_ENDPOINT', None)
    imported = subprocess.check_output([str(ROOT / 'venv/bin/python'), '-c',
        'import freetoken,freetoken.kernel._cpu_moe,freetoken.kernel._pinned_tensor;print(freetoken.__file__)'],
        text=True, cwd=worktree, env=env).strip()
    if imported != str(worktree / 'python/freetoken/__init__.py'):
        raise RuntimeError('R060 file-dry imported a non-candidate package')
    arms = []
    for spec in r060.four_arms():
        arm = target / spec['name']; arm.mkdir(mode=0o700)
        pair = port_pair()
        argv = r060.arm_argv(d07, pair['api'])
        selected = {'CUDA_VISIBLE_DEVICES': '', 'PYTHONPATH': env['PYTHONPATH'],
                    'FT_DEV_D0': '1' if spec['d0'] else '0', 'FT_DEV_ROUTE_TRACE': '0',
                    'FT_DEV_PAUSE_ENDPOINT': '0'}
        write_new(arm / 'service_plan.json', {'arm': spec, 'argv': argv, 'environment': selected,
                                                'port_pair': pair, 'popen_reached': False})
        arms.append({'name': spec['name'], 'd0': spec['d0'], 'port_pair': pair,
                     'outputs': output_probe(arm, spec['d0'], pair)})
    receipt = {'schema': 'ft_r064_file_dry/v1', 'rid': RID, 'candidate_commit': CANDIDATE,
               'parent_commit': BASE, 'script': str(Path(__file__).resolve()), 'cwd': os.getcwd(),
               'uid': os.getuid(), 'passed': True, 'source_sha256': source_hashes(),
               'native_provenance': {'path': str(NATIVE), 'sha256': sha(NATIVE)},
               'runtime_source_copies': copies, 'actual_import': imported, 'arms': arms,
               'formal_rid_directory_created': False, 'service_started': False, 'requests_sent': False,
               'gpu_lock_taken': False, 'batch_allocated': False, 'popen_reached': False}
    write_new(dry_receipt(), receipt)
    dry_receipt().chmod(0o444)
    return receipt


def require_admission() -> dict:
    receipt = dry_receipt(); review = REVIEW_DIR / 'review.json'; pin = REVIEW_DIR / 'pin.json'
    for path in (receipt, review, pin):
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
            raise RuntimeError('R060 sealed FILEDRY/R review/pin is absent or writable')
    dry = json.loads(receipt.read_text(encoding='utf-8'))
    expected = {'schema': 'ft_r064_file_dry/v1', 'rid': RID, 'candidate_commit': CANDIDATE,
                'parent_commit': BASE, 'script': str(Path(__file__).resolve()), 'cwd': os.getcwd(),
                'uid': os.getuid(), 'source_sha256': source_hashes(), 'passed': True}
    if any(dry.get(key) != value for key, value in expected.items()) or any(dry.get(key) is not False for key in
            ('formal_rid_directory_created', 'service_started', 'requests_sent', 'gpu_lock_taken', 'batch_allocated', 'popen_reached')):
        raise RuntimeError('R060 FILEDRY identity, closure, or no-effect proof differs')
    review_doc, pin_doc = json.loads(review.read_text()), json.loads(pin.read_text())
    if (review_doc.get('schema') != 'ft_r060_startup_review/v1' or review_doc.get('rid') != RID
            or review_doc.get('candidate_commit') != CANDIDATE or review_doc.get('parent_commit') != BASE
            or review_doc.get('approved') is not True or review_doc.get('verdict') != 'PASS'
            or review_doc.get('source_sha256') != source_hashes() or review_doc.get('file_dry_sha256') != sha(receipt)
            or pin_doc.get('schema') != 'ft_r060_startup_review_pin/v1' or pin_doc.get('rid') != RID
            or pin_doc.get('review_sha256') != sha(review)):
        raise RuntimeError('R060 independent review/pin binding differs')
    return {'file_dry_receipt': str(receipt), 'file_dry_sha256': sha(receipt),
            'review': str(review), 'review_sha256': sha(review)}


def child_argv(batch: int, receipt: Path) -> list[str]:
    return [str(ROOT / 'venv/bin/python'), str(Path(__file__).resolve()), '--run', '--owned-child',
            '--batch', str(batch), '--launch-receipt', str(receipt)]


def controller() -> dict:
    if sys.platform != 'linux': raise RuntimeError('R060 controller requires Linux')
    proof, d07 = require_admission(), load_d07()
    candidate_binding(); load_r060().require_r060_native_provenance(NATIVE)
    if d07.LOCK.exists() or d07.LOCK.is_symlink(): raise RuntimeError('foreign GPU lock exists; R060 remains queued')
    owned = d07.load_owned_lifecycle(); helper = owned.verified_module(ROOT/'runs/plan_batches/e2_launch.py', d07.ATOMIC_HELPER_SHA, 'r060_atomic')
    batch = helper.next_batch(ROUNDS); receipt = ROOT/'runs/dev_OOM'/f'launch_{RID}_batch{batch}.json'; receipt.parent.mkdir(parents=True, exist_ok=True)
    argv = child_argv(batch, receipt)
    reserved = {'schema':'ft_r064_owned_launch/v1','state':'reserved','rid':RID,'batch':batch,'candidate_commit':CANDIDATE,
                'parent_commit':BASE,'argv_sha256':d07.argv_sha256(argv),'startup_proof':proof,'controller':d07.process_birth()}
    launched = owned.reserve_process(helper, batch, RID, argv, receipt, reserved); birth = owned.process_identity(launched['batch_pid'])
    if birth is None: raise RuntimeError('R060 reserved child birth is absent')
    return d07.publish_child_binding(receipt, launched, {key: birth[key] for key in ('pid','start_ticks','execution_id')}, lifecycle=owned)


def child(batch: int, receipt: Path) -> dict:
    if sys.platform != 'linux': raise RuntimeError('R060 child requires Linux')
    require_admission(); d07 = load_d07(); worktree = candidate_binding()
    d07.require_child_receipt(receipt, batch, worktree, ROUNDS, rid=RID, expected_argv=child_argv(batch, receipt), schema='ft_r064_owned_launch/v1')
    owner = d07.take_d07_gpu_lock(RID, batch); runner = None
    try:
        d07.require_gpu_idle()
        runner = load_r060().build_r059_oom_runner(CANDIDATE, worktree, batch, lambda: load_r060().require_r060_native_provenance(NATIVE))
        runner.token, runner.lock_inode = owner['lock_token'], owner['lock_inode']
        runner.execute()
        return {'rid': RID, 'batch': batch, 'proposed_verdict': 'kept', 'startup_proof': require_admission()}
    finally:
        if runner is None or runner.proc is None:
            d07.release_d07_gpu_lock(owner)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument('--file-dry-run', action='store_true'); parser.add_argument('--run', action='store_true')
    parser.add_argument('--owned-child', action='store_true'); parser.add_argument('--batch', type=int); parser.add_argument('--launch-receipt', type=Path)
    args = parser.parse_args(argv)
    if args.file_dry_run:
        if args.run or args.owned_child or args.batch or args.launch_receipt: parser.error('file-dry accepts no launch arguments')
        print(json.dumps(file_dry_run(), sort_keys=True)); return 0
    if not args.run: print(json.dumps({'rid':RID,'state':'prepared','default_recovery_enabled':True,'fault_injection_enabled':False})); return 0
    print(json.dumps(child(args.batch,args.launch_receipt) if args.owned_child else controller(), sort_keys=True)); return 0


if __name__ == '__main__': raise SystemExit(main())
