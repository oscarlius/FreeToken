"""Inert root-only formal closure for R067e batch166; never starts inference."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import socket
import subprocess

ROOT = Path('/data2/FreeToken')
RID = 'E2-R067e-20261010-retry2'
BATCH = 166
CANDIDATE = 'b86190d78be3b1b4b55f989c98ce963630e425dd'
RAW = ROOT / 'runs/dev_R067/E2-R067e-20261010-retry2_batch166_3625535_173386153'
DEST = Path('/data2/_shared/runs/ft_rounds') / RID
LAUNCH = ROOT / 'runs/dev_R067/launch_E2-R067e-20261010-retry2_batch166.json'
ADMISSION = ROOT / 'development/r067e_20261010/retry2_2045/ROOT_ADMISSION_BATCH166.json'
CLOSER = ROOT / 'scripts/round_close.py'
WRITER = ROOT / 'scripts/round_json_append.py'
CLOSER_SHA = 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5'
WRITER_SHA = '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f'expected regular file: {path}')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise RuntimeError(f'expected JSON object: {path}')
    return value


def put(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def process_alive(pid: int) -> bool:
    try:
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rpartition(') ')[2].split()
    except FileNotFoundError:
        return False
    return fields[0] != 'Z'


def group_alive(pgid: int) -> bool:
    for item in Path('/proc').iterdir():
        if not item.name.isdigit():
            continue
        try:
            fields = (item / 'stat').read_text().rpartition(') ')[2].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if fields[0] != 'Z' and int(fields[2]) == pgid:
            return True
    return False


def validate(review_path: Path) -> tuple[dict, dict, dict, list[Path]]:
    if review_path.is_symlink() or not review_path.is_file() or review_path.stat().st_mode & 0o222:
        raise RuntimeError('independent review must be a read-only regular file')
    review, terminal, launch = read(review_path), read(RAW / 'terminal.json'), read(LAUNCH)
    raw_files = {str(path.relative_to(RAW)): sha(path) for path in RAW.rglob('*') if path.is_file()}
    if any(path.is_symlink() for path in RAW.rglob('*')) or review.get('raw_artifact_sha256') != raw_files:
        raise RuntimeError('independent review raw artifact inventory differs')
    # The inherited parent runner emits its static parent RID.  It is accepted only
    # for this already-failed batch; launch/admission/budget bind the retry2 RID.
    if (terminal.get('schema') != 'ft_r067e_actual_terminal/v1'
            or terminal.get('rid') != 'E2-R067e-20261010'
            or terminal.get('batch') != BATCH):
        raise RuntimeError('raw terminal identity/schema differs')
    if launch.get('rid') != RID or launch.get('batch') != BATCH or launch.get('candidate_commit') != CANDIDATE:
        raise RuntimeError('launch receipt identity differs')
    child = launch.get('child', {})
    if child.get('pid') != 3625535 or child.get('start_ticks') != 173386153 or process_alive(child['pid']) or group_alive(child['pid']):
        raise RuntimeError('controller child is not cleanly finished')
    verdict = terminal.get('verdict')
    formal = review.get('formal_verdict')
    base = {'rid': RID, 'batch': BATCH, 'candidate_commit': CANDIDATE,
            'terminal_sha256': sha(RAW / 'terminal.json'),
            'actual_services': terminal.get('actual_services'), 'actual_generation_calls': terminal.get('actual_generation_calls')}
    if any(review.get(key) != value for key, value in base.items()):
        raise RuntimeError('independent review/terminal binding differs')
    if verdict in {'failed_harness', 'not_met'}:
        if formal != verdict:
            raise RuntimeError('failure carrier must be preserved by formal closure')
    elif verdict == 'PASS':
        if (formal != 'kept' or review.get('recommendation') != 'APPROVE_KEPT' or review.get('all_comparison_gates_passing') is not True
                or terminal.get('actual_services') != 10 or terminal.get('actual_generation_calls') != 14):
            raise RuntimeError('PASS requires explicit independent APPROVE_KEPT plus all-comparison proof')
    else:
        raise RuntimeError('raw terminal verdict is not closeable')
    budget_rows = [json.loads(line) for line in (RAW / 'budget.jsonl').read_text(encoding='utf-8').splitlines() if line]
    dispatched = sum(row.get('event') == 'generation_call' for row in budget_rows)
    completed = len(terminal.get('requests', {}))
    if verdict == 'PASS' and (dispatched != completed or terminal.get('actual_generation_calls') != completed):
        raise RuntimeError('PASS request accounting differs')
    if verdict in {'failed_harness', 'not_met'} and (terminal.get('actual_generation_calls') != dispatched or completed > dispatched):
        raise RuntimeError('failed-round dispatch accounting differs')
    arms = sorted(path for path in (RAW / 'services').iterdir() if path.is_dir() and (path / 'owner.json').is_file())
    if terminal.get('actual_services') != len(arms):
        raise RuntimeError('terminal service count differs')
    packet = read(Path(read(ADMISSION)['execution_packet_path']))
    by_name = {service['name']: service for service in packet.get('services', [])}
    for arm in arms:
        owner, cleanup, service = read(arm / 'owner.json'), read(arm / 'cleanup.json'), by_name.get(arm.name)
        if service is None or owner.get('service') != arm.name or owner.get('batch') != BATCH or cleanup.get('group_alive') is not False:
            raise RuntimeError('service ownership/cleanup differs: ' + arm.name)
        if process_alive(owner['pid']) or group_alive(owner['pid']):
            raise RuntimeError('service group is still live: ' + arm.name)
        for port in (service['port_pair']['api'], service['port_pair']['tcpstore']):
            with socket.socket() as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('127.0.0.1', port))
    if Path('/data2/_shared/gpu.lock').exists():
        raise RuntimeError('GPU lock remains')
    gpu = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'], text=True).strip()
    if gpu:
        raise RuntimeError('GPU compute process remains')
    for tool, digest in ((CLOSER, CLOSER_SHA), (WRITER, WRITER_SHA)):
        if tool.is_symlink() or sha(tool) != digest:
            raise RuntimeError('formal closure tool pin differs')
    return review, terminal, launch, arms


def execute(review_path: Path) -> None:
    if DEST.exists() or (RAW / 'round.json').exists() or (RAW / 'MANIFEST.sha256').exists():
        raise RuntimeError('round already closed or source changed')
    review, terminal, launch, arms = validate(review_path)
    shutil.copytree(RAW, DEST, copy_function=os.link)
    evidence = DEST / 'closure_evidence'; evidence.mkdir()
    for source, name in ((review_path, 'independent_review.json'), (LAUNCH, 'launch_receipt.json'), (ADMISSION, 'admission.json'), (Path(__file__), 'close_batch166.py')):
        shutil.copyfile(source, evidence / name)
    wrapper = Path(launch.get('wrapper', ''))
    (DEST / 'batch.sh').write_text('# Archived controller wrapper; do not execute.\n' + (wrapper.read_text() if wrapper.is_file() and not wrapper.is_symlink() else '# see launch_receipt.json\n'), encoding='utf-8')
    formal_arms = {}
    for source_arm in arms:
        arm = DEST / source_arm.name; arm.mkdir()
        owner, service = read(source_arm / 'owner.json'), next(x for x in read(Path(read(ADMISSION)['execution_packet_path']))['services'] if x['name'] == source_arm.name)
        (arm / 'SERVE_CMD.txt').write_text(shlex.join(owner['argv']) + '\n', encoding='utf-8')
        os.link(source_arm / 'serve.log', arm / 'serve.log')
        (arm / 'serve_args.txt').write_text(json.dumps(owner['argv']) + '\n', encoding='utf-8')
        (arm / 'ENV.txt').write_text('Reconstructed from sealed execution packet; not a live environment readback.\n' + json.dumps(service['env'], sort_keys=True) + '\n', encoding='utf-8')
        formal_arms[source_arm.name] = {'source': 'services/' + source_arm.name, 'owner_sha256': sha(source_arm / 'owner.json')}
    put(DEST / 'round.json', {'schema': 'ft_round/v2', 'round_id': RID, 'card': 'R067e-retry2', 'batch': BATCH,
        'experimental': {'candidate_commit': CANDIDATE}, 'actual_services': terminal['actual_services'], 'actual_generation_calls': terminal['actual_generation_calls'],
        'verdict': 'pending_review', 'proposed_verdict': review['formal_verdict'], 'original_runner_terminal': terminal['verdict'], 'original_terminal_sha256': sha(RAW / 'terminal.json'),
        'product_acceptance': False, 'production_activated': False, 'gate_acceptance': 'formalkept' if review['formal_verdict'] == 'kept' else None, 'verdict_history': [], 'retractions': [], 'serve': {'arms': formal_arms},
        'batch_logs': [{'path': '/data2/_shared/runs/ft_rounds/batch166.log', 'sha256': sha(Path('/data2/_shared/runs/ft_rounds/batch166.log'))}],
        'independent_review_sha256': sha(review_path), 'result_binding': {'launch': {'path': 'closure_evidence/launch_receipt.json', 'sha256': sha(evidence / 'launch_receipt.json')}, 'admission': {'path': 'closure_evidence/admission.json', 'sha256': sha(evidence / 'admission.json')}},
        'raw_terminal_rid': terminal['rid'], 'retry2_rid_binding': {'launch_rid': launch['rid'], 'admission_rid': read(ADMISSION)['rid'], 'budget_path': str(RAW / 'budget.jsonl')},
        'conclusion_scope': 'Carrier-preserving closure of final R067e retry; GPU/product outcome is established only by raw terminal and independent review.'})
    subprocess.run([str(ROOT / 'venv/bin/python'), str(CLOSER), RID, '--round-root', str(DEST.parent)], check=True)
    subprocess.run([str(ROOT / 'venv/bin/python'), str(WRITER), str(DEST), 'verdict', '--new', review['formal_verdict'], '--reason', 'Independent terminal review; carrier preserved', '--evidence', 'closure_evidence/independent_review.json', 'terminal.json', '--by', 'root'], check=True)
    subprocess.run([str(ROOT / 'venv/bin/python'), str(WRITER), str(DEST), 'check'], check=True)
    pin = ROOT / 'runs/plan_batches/closed_round_pins' / (RID + '.json')
    if pin.exists() or pin.is_symlink():
        raise RuntimeError('closed round pin already exists')
    put(pin, {'rid': RID, 'round_sha256': sha(DEST / 'round.json'), 'manifest_sha256': sha(DEST / 'MANIFEST.sha256')})
    pin.chmod(0o444)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--execute', action='store_true'); parser.add_argument('--independent-review', type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode': 'inert', 'rid': RID, 'batch': BATCH, 'requires': 'completed terminal plus sealed independent review'}))
    elif args.independent_review is None:
        parser.error('--execute requires --independent-review')
    else:
        execute(args.independent_review)




