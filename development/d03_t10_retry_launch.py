"""Launch the assigned R016 retry after complete frozen-source preflight."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
DEV = ROOT / 'runs/dev_D03'
RID = 'E2-R016'
CANDIDATE = 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
PARENT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
RUNNER = Path(__file__).with_name('t10_raw_phase1_retry.py')
ATOMIC_SHA = 'a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf'
PREREQUISITE_SHA = '6c403cc8ea2c8719c22c8a6be86de23ad266d138d31e5af63fcb02dcb2a588fe'
FROZEN_PHASE1_SHA = 'b86900137665b97817d1a8e5620c2e250ef1cf61bc11698e432b6a9f75d07d52'
RETRY_SHA = 'eda681d434ed01fa36fe58b6d049e2912895045406fdb5afff5fb9ebb02361c2'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, expected=None):
    spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    module = importlib.util.module_from_spec(spec)
    if expected is None:
        spec.loader.exec_module(module)
    else:
        source = Path(path).read_bytes()
        if hashlib.sha256(source).hexdigest() != expected:
            raise ValueError(f'frozen import source changed: {Path(path).name}')
        exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def arguments(batch):
    return ['--rid', RID, '--batch', str(batch), '--candidate-commit', CANDIDATE,
            '--reverse-trace', '/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json',
            '--forward-trace', '/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json',
            '--frontend-manifest', str(DEV / 't10_frontend_tokens_c30ae0d.json'),
            '--agent-trace-md5', 'f81acb79c3dbc89999f5f76de4c9a070']


def verify_sources():
    sources = {
        DEV / 'd03_phase2_launch.py': PREREQUISITE_SHA,
        ROOT / 'runs/plan_batches/e2_launch.py': ATOMIC_SHA,
        DEV / 'phase2_tools_c30ae0d_ready/t10_raw_phase1.py': FROZEN_PHASE1_SHA,
        RUNNER: RETRY_SHA,
    }
    for path, expected in sources.items():
        if sha(path) != expected:
            raise ValueError(f'frozen launch source changed: {path.name}')
    if RUNNER.stat().st_mode & 0o222 or RUNNER.parent.stat().st_mode & 0o222:
        raise ValueError('retry runner bundle must be frozen read-only')
    return load(DEV / 'd03_phase2_launch.py', PREREQUISITE_SHA)


def preflight(runner, batch):
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '0':
        raise ValueError('CUDA_VISIBLE_DEVICES must be exactly 0')
    if (ROUNDS / RID).exists() or (DEV / f'launch_{RID}.json').exists():
        raise FileExistsError('assigned retry round or receipt already exists')
    module = load(runner, RETRY_SHA)
    argv = arguments(batch)
    ns = argparse.Namespace(rid=RID, batch=batch, candidate_commit=CANDIDATE,
        reverse_trace=Path(argv[argv.index('--reverse-trace') + 1]),
        forward_trace=Path(argv[argv.index('--forward-trace') + 1]),
        frontend_manifest=DEV / 't10_frontend_tokens_c30ae0d.json',
        agent_trace_md5='f81acb79c3dbc89999f5f76de4c9a070')
    frontend, _ = module.frontend(ns.frontend_manifest, CANDIDATE, sha(ns.reverse_trace),
                                  sha(ns.forward_trace), ns.reverse_trace, ns.forward_trace)
    model = ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'
    for name, expected in frontend['tokenizer_files_sha256'].items():
        if sha(model / name) != expected:
            raise ValueError(f'frontend tokenizer changed: {name}')
    module.Run(ns).gate()
    module.self_test()
    return ns


def launch():
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '0':
        raise ValueError('CUDA_VISIBLE_DEVICES must be exactly 0')
    inherited = verify_sources()
    gate = inherited.prerequisite()
    atomic = load(ROOT / 'runs/plan_batches/e2_launch.py', ATOMIC_SHA)
    batch = atomic.next_batch(ROUNDS)
    preflight(RUNNER, batch)
    if atomic.next_batch(ROUNDS) != batch:
        raise ValueError('batch changed during preflight')
    receipt_path = DEV / f'launch_{RID}.json'
    reserved = {'rid': RID, 'card': 'T10-P1', 'batch': batch, 'state': 'reserved',
                'runner': str(RUNNER), 'runner_sha256': RETRY_SHA,
                'cuda_visible_devices': os.environ['CUDA_VISIBLE_DEVICES']}
    with receipt_path.open('x', encoding='utf-8') as stream:
        json.dump(reserved, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    receipt_identity = (receipt_path.stat().st_dev, receipt_path.stat().st_ino)
    try:
        process, wrapper, log = atomic.reserve_and_launch(batch, RID,
            [str(ROOT / 'venv/bin/python'), '-u', str(RUNNER), *arguments(batch)])
    except BaseException as exc:
        publish_receipt(receipt_path, receipt_identity, {**reserved, 'state': 'launch_failed', 'error': repr(exc)})
        raise
    receipt = {'rid': RID, 'card': 'T10-P1', 'batch': batch, 'batch_pid': process.pid,
        'pgid': process.pid, 'runner_sha256': sha(RUNNER), 'launcher_sha256': sha(Path(__file__)),
        'wrapper': str(wrapper), 'wrapper_sha256': sha(wrapper), 'batch_log': str(log),
        'parent_commit': PARENT, 'candidate_commit': CANDIDATE,
        'cuda_visible_devices': os.environ['CUDA_VISIBLE_DEVICES'], 'atomic_launcher_sha256': ATOMIC_SHA,
        'prerequisite_round': str(gate), 'prerequisite_round_sha256': sha(gate / 'round.json'),
        'state': 'launched', 'runner': str(RUNNER)}
    publish_receipt(receipt_path, receipt_identity, receipt)
    print('T10_RETRY_LAUNCHED', json.dumps(receipt), flush=True)
    return receipt


def publish_receipt(path, identity, value):
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        current = path.stat()
        if path.is_symlink() or (current.st_dev, current.st_ino) != identity:
            raise ValueError('exclusive launch receipt identity changed')
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run or sys.platform != 'linux':
        parser.error('--run on Linux required')
    launch()


if __name__ == '__main__':
    main()
