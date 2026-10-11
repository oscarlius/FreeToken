"""Launch one assigned D03 consumer after its actual prerequisite gates close."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/data2/FreeToken')
DEV = ROOT / 'runs/dev_D03'
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
TOOLS = DEV / 'phase2_tools_c30ae0d_ready'
PARENT = '23f2e2caa3395837c9474735ffc83321f3b9b5a1'
CANDIDATE = 'c30ae0d7003c3bbbf56867ce74da797332fa7ed5'
HASHES = {
    'd03_gpu_selfcheck.py': '4cf751a93457ef28a88fc175004c86d12130b84943193cb43c55254c2e0fb453',
    't04_logits_phase2.py': 'd7226c466e5922ecc4e80d80dc2b634592e1449538587d3232d4f3b9176723eb',
    't10_raw_phase1.py': 'b86900137665b97817d1a8e5620c2e250ef1cf61bc11698e432b6a9f75d07d52',
    't10_logits_stage2.py': 'd6e01dee6fd39e59976f5b9f90b798b27dded4a7e516bb97debe10e237c2e2e9',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prerequisite():
    for name, expected in HASHES.items():
        if sha(TOOLS / name) != expected:
            raise ValueError(f'frozen helper changed: {name}')
    if sha(DEV / 'd03_gpu_selfcheck.py') != HASHES['d03_gpu_selfcheck.py']:
        raise ValueError('shared lifecycle differs from reviewed version')
    gate_dir = ROUNDS / 'E2-R002-gate-D03'
    subprocess.run([sys.executable, str(ROOT / 'scripts/round_json_append.py'), str(gate_dir), 'check'], check=True)
    gate_round = json.loads((gate_dir / 'round.json').read_text())
    if (gate_round.get('round_id') != gate_dir.name or gate_round.get('card') != 'T16'
            or gate_round.get('base', {}).get('commit') != PARENT
            or gate_round.get('experimental', {}).get('candidate_commit') != CANDIDATE
            or not gate_round.get('closed_at')):
        raise ValueError('closed T16 round does not bind this candidate')
    batch = gate_round['design']['batch']
    gate = json.loads((gate_dir / f'gate_batch{batch}.json').read_text())
    review_path = gate_dir / f'review_batch{batch}.json'
    review = json.loads(review_path.read_text())
    if (gate.get('proposed_verdict') != 'kept' or gate.get('parent_commit') != PARENT
            or gate.get('new_commit') != CANDIDATE or review.get('verdict') != 'PASS'
            or review.get('rid') != gate_dir.name or review.get('batch') != batch
            or gate_round.get('independent_review_sha256') != sha(review_path)):
        raise ValueError('T16 measurement/independent review did not pass')
    manifest = gate_dir / 'MANIFEST.sha256'
    required = {f'gate_batch{batch}.json', review_path.name, 'batch.sh'}
    declared = set()
    for line in manifest.read_text().splitlines():
        expected, relative = line.split('  ', 1)
        path = (gate_dir / relative).resolve()
        if gate_dir.resolve() not in path.parents or not path.is_file() or sha(path) != expected:
            raise ValueError(f'T16 sealed manifest mismatch: {relative}')
        declared.add(path.relative_to(gate_dir.resolve()).as_posix())
    if not required <= declared:
        raise ValueError('T16 manifest lacks gate, review, or actual batch wrapper')
    if any(path.is_symlink() or path.stat().st_mode & 0o222 for path in [gate_dir, *gate_dir.rglob('*')]):
        raise ValueError('T16 evidence tree is not sealed read-only')
    return gate_dir


def arguments(card, batch):
    candidate_args = ['--batch', str(batch), '--candidate-commit', CANDIDATE]
    if card == 'T04':
        check = DEV / 'gpu_selfcheck_c30ae0d_urlfix'
        report = json.loads((check / 'selfcheck.json').read_text())
        return 'E2-R014', 't04_logits_phase2.py', [
            '--rid', 'E2-R014', *candidate_args,
            '--g4-token-file', report['g4_terminal_binding']['path'],
            '--raw-binding-manifest', str(DEV / 'historical_raw_ids_c30ae0d.json'),
            '--trace', '/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json', '--k', '32',
        ]
    if card == 'T10-P1':
        return 'E2-R012', 't10_raw_phase1.py', [
            '--rid', 'E2-R012', *candidate_args,
            '--reverse-trace', '/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json',
            '--forward-trace', '/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json',
            '--frontend-manifest', str(DEV / 't10_frontend_tokens_c30ae0d.json'),
            '--agent-trace-md5', 'f81acb79c3dbc89999f5f76de4c9a070',
        ]
    return 'E2-R013', 't10_logits_stage2.py', [
        *candidate_args, '--phase1-manifest', str(ROUNDS / 'E2-R012/phase1_manifest.json'),
        '--phase1-round-json', str(ROUNDS / 'E2-R012/round.json'),
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--card', required=True, choices=['T04', 'T10-P1', 'T10-P2'])
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if not args.run or sys.platform != 'linux':
        parser.error('--run and the Linux test host are required')
    gate_dir = prerequisite()
    launcher_path = ROOT / 'runs/plan_batches/e2_launch.py'
    if sha(launcher_path) != 'a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf':
        raise ValueError('atomic batch launcher changed')
    launcher = load(launcher_path, 'e2_launcher')
    batch = launcher.next_batch(ROUNDS)
    rid, filename, extra = arguments(args.card, batch)
    if (ROUNDS / rid).exists() or (DEV / f'launch_{rid}.json').exists():
        raise FileExistsError(f'assigned measurement already exists: {rid}')
    subprocess.run([sys.executable, str(TOOLS / filename), '--self-test'], check=True)
    module = load(TOOLS / filename, 'selected_consumer')
    if args.card == 'T04':
        ns = argparse.Namespace(rid=rid, batch=batch, candidate_commit=CANDIDATE,
                                g4_token_file=Path(extra[extra.index('--g4-token-file') + 1]),
                                raw_binding_manifest=DEV / 'historical_raw_ids_c30ae0d.json',
                                trace=Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json'), k=32)
        run = module.Phase2(ns)
        module.verify_g4_source(run.sc, ns.g4_token_file, ns.raw_binding_manifest, ns.trace, CANDIDATE)
        run.gate()
    elif args.card == 'T10-P1':
        ns = argparse.Namespace(rid=rid, batch=batch, candidate_commit=CANDIDATE,
                                reverse_trace=Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace_rev.json'),
                                forward_trace=Path('/data2/_shared/runs/ft_rounds/E1-R003-v2/trace.json'),
                                frontend_manifest=DEV / 't10_frontend_tokens_c30ae0d.json',
                                agent_trace_md5='f81acb79c3dbc89999f5f76de4c9a070')
        run = module.Run(ns)
        frontend, _ = module.frontend(ns.frontend_manifest, CANDIDATE, sha(ns.reverse_trace), sha(ns.forward_trace),
                                      ns.reverse_trace, ns.forward_trace)
        model = ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay'
        for name, expected in frontend['tokenizer_files_sha256'].items():
            if sha(model / name) != expected:
                raise ValueError(f'frontend tokenizer changed: {name}')
        run.gate()
    else:
        ns = argparse.Namespace(batch=batch, candidate_commit=CANDIDATE,
                                phase1_manifest=ROUNDS / 'E2-R012/phase1_manifest.json',
                                phase1_round_json=ROUNDS / 'E2-R012/round.json')
        run = module.Run(ns)
        phase1_dir, manifest, _ = run.sealed_phase1()
        forks = run.recompute_forks(phase1_dir, manifest)
        if not forks:
            proof = {'rid': rid, 'state': 'not_applicable_no_actual_fork',
                     'phase1_manifest_sha256': sha(ns.phase1_manifest), 'gpu_started': False}
            with (DEV / 't10_stage2_no_fork.json').open('x') as stream:
                json.dump(proof, stream, indent=2)
            print(json.dumps(proof), flush=True)
            return
        run.gate()
    if launcher.next_batch(ROUNDS) != batch:
        raise ValueError('batch ledger changed during preflight')
    argv = [sys.executable, '-u', str(TOOLS / filename), *extra]
    process, wrapper, log = launcher.reserve_and_launch(batch, rid, argv)
    record = {'rid': rid, 'card': args.card, 'batch': batch, 'batch_pid': process.pid, 'pgid': process.pid,
              'candidate_commit': CANDIDATE, 'runner_sha256': sha(TOOLS / filename),
              'wrapper': str(wrapper), 'wrapper_sha256': sha(wrapper), 'batch_log': str(log),
              'prerequisite_round': str(gate_dir), 'prerequisite_round_sha256': sha(gate_dir / 'round.json')}
    with (DEV / f'launch_{rid}.json').open('x') as stream:
        json.dump(record, stream, indent=2)
    print('D03_CONSUMER_LAUNCHED', json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
