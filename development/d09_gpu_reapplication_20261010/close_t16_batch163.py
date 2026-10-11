"""Root-only closure of the completed bd57 T16 round; never starts a service."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess

ROOT = Path('/data2/FreeToken')
HERE = Path(__file__).resolve().parent
RID = 'E2-D09-T16-reapply-bd57-20261010'
BATCH = 163
CANDIDATE = 'bd57cfdccc2a935d46cb0a89b8b36be7a18706de'
PARENT = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
RUN = Path('/data2/_shared/runs/ft_rounds') / RID
PYTHON = ROOT / 'venv/bin/python'
WRITER = ROOT / 'scripts/round_json_append.py'
CLOSER = ROOT / 'scripts/round_close.py'
CLOSER_SHA = 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5'
WRITER_SHA = '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
ARMS = tuple(n + '_b163' for n in (
    'PARENT', 'NEW', 'PARENT_P', 'NEW_P',
    'CHUNK_PARENT', 'CHUNK_NEW', 'CHUNK_PARENT_P', 'CHUNK_NEW_P'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def put(path, data):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(data, handle, sort_keys=True, indent=2)
        handle.write('\n')


def alive(identity):
    try:
        fields = Path(f"/proc/{identity['pid']}/stat").read_text().rsplit(')', 1)[1].split()
    except FileNotFoundError:
        return False
    return fields[0] != 'Z' and int(fields[19]) == identity['start_ticks']


def group_live(pgid):
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if fields[0] != 'Z' and int(fields[2]) == pgid:
            return True
    return False


def validate(review_path):
    if review_path.is_symlink() or review_path.stat().st_mode & 0o222:
        raise RuntimeError('independent review must be a sealed regular file')
    review = read(review_path)
    expected = {'rid': RID, 'batch': BATCH, 'candidate_commit': CANDIDATE,
                'verdict': 'PASS', 'actual_services': 8, 'actual_generation_calls': 100}
    if any(review.get(key) != value for key, value in expected.items()):
        raise RuntimeError('completed-round independent review binding differs')
    status = read(RUN / 'status_batch163.json')
    gate = read(RUN / 'gate_batch163.json')
    binding = read(RUN / 'candidate_binding.json')
    if (status.get('state') != 'complete_measurements_pending_review'
            or status.get('batch') != BATCH or status.get('rid') != RID
            or gate.get('proposed_verdict') != 'kept' or tuple(gate.get('arms', [])) != ARMS
            or gate.get('parent_commit') != PARENT or gate.get('new_commit') != CANDIDATE
            or binding.get('new_commit') != CANDIDATE
            or binding.get('parent_commit') != PARENT
            or binding.get('default_off_public_flag') != {'enable_message_boundary_ckpt': False}):
        raise RuntimeError('actual T16 measurements are not a kept proposal for this candidate')
    # Review commits every original raw file before any closure additions.
    current = {str(p.relative_to(RUN)): sha(p) for p in RUN.rglob('*') if p.is_file()}
    if current != review.get('original_raw_files_sha256'):
        raise RuntimeError('original raw evidence changed after independent review')
    launch_path = ROOT / 'runs/dev_T16' / f'launch_{RID}_batch163.json'
    launch = read(launch_path)
    if (launch.get('rid') != RID or launch.get('batch') != BATCH
            or launch.get('candidate_commit') != CANDIDATE or alive(launch['child'])
            or group_live(launch['batch_pgid'])):
        raise RuntimeError('controller child has not finished with the expected identity')
    owners, counts = [], {}
    for name in ARMS:
        arm = RUN / name
        owner = read(arm / 'owned_process.json')
        birth = owner['birth']
        if (birth['pid'] != birth['pgid'] or birth['pid'] != birth['session']
                or alive(birth) or group_live(birth['pgid'])):
            raise RuntimeError('service ownership cleanup is incomplete: ' + name)
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('127.0.0.1', owner['port']))
        count = len(re.findall(r'POST /v1/chat/completions HTTP/1\.1', (arm / 'serve.log').read_text()))
        if count != (13 if name.startswith('CHUNK_') else 12):
            raise RuntimeError('actual generation call count differs: ' + name)
        counts[name] = count
        owners.append({'arm': name, 'birth': birth, 'port': owner['port'],
                       'owner_sha256': sha(arm / 'owned_process.json'), 'group_absent': True,
                       'api_port_rebind': True})
    if sum(counts.values()) != 100:
        raise RuntimeError('full 100-call protocol was not completed')
    gpu = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,used_memory',
                                   '--format=csv,noheader'], text=True).strip()
    memory = [int(value.strip()) for value in subprocess.check_output(
        ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
        text=True).splitlines()]
    if gpu or not memory or any(value > 8 for value in memory) or Path('/data2/_shared/gpu.lock').exists():
        raise RuntimeError('GPU or lock not idle; do not close this round')
    for path, digest in ((WRITER, WRITER_SHA), (CLOSER, CLOSER_SHA)):
        if path.is_symlink() or sha(path) != digest:
            raise RuntimeError('canonical formal closure tool changed')
    return launch_path, {'at': datetime.now().astimezone().isoformat(), 'rid': RID,
                         'cleanup_ok': True, 'child': launch['child'], 'owners': owners,
                         'actual_generation_calls_by_arm': counts, 'gpu_idle': True, 'gpu_memory_mib': memory,
                         'lock_absent': True, 'product_acceptance': False}


def execute(review_path):
    if (RUN / 'round.json').exists() or (RUN / 'MANIFEST.sha256').exists():
        raise RuntimeError('formal closure already exists; use its append-only history')
    launch, cleanup = validate(review_path)
    evidence = RUN / 'closure_evidence'
    evidence.mkdir()
    for source, name in ((review_path, 'independent_review.json'), (launch, 'launch_receipt.json'),
                         (Path(__file__), 'close_t16_batch163.py')):
        shutil.copy2(source, evidence / name)
    shutil.copy2(WRITER, RUN / 'round_json_append.py')
    put(evidence / 'owned_cleanup_revalidation.json', cleanup)
    result_names = ['status_batch163.json', 'gate_batch163.json', 'candidate_binding.json',
                    'tools_batch163.json', *[str(p.relative_to(RUN)) for p in evidence.iterdir()]]
    doc = {'schema': 'ft_round/v2', 'round_id': RID, 'card': 'D09-T16', 'batch': BATCH,
           'base': {'commit': PARENT}, 'experimental': {'candidate_commit': CANDIDATE},
           'actual_services': 8, 'actual_generation_calls': 100, 'product_acceptance': False,
           'verdict': 'pending_review', 'proposed_verdict': 'kept', 'verdict_history': [],
           'retractions': [], 'serve': {'arms': {name: {} for name in ARMS}},
           'batch_logs': [{'path': '/data2/_shared/runs/ft_rounds/batch163.log',
                           'sha256': sha('/data2/_shared/runs/ft_rounds/batch163.log')}],
           'result_binding': {name: {'path': name, 'sha256': sha(RUN / name)} for name in result_names},
           'conclusion_scope': 'full default-off identity gate only; enabled T17 and performance remain pending'}
    put(RUN / 'round.json', doc)
    subprocess.run([str(PYTHON), str(CLOSER), RID, '--round-root', str(RUN.parent)], check=True)
    subprocess.run([str(PYTHON), str(WRITER), str(RUN), 'verdict', '--new', 'kept',
                    '--reason', 'Independent full 8-service/100-call bd57 default-off T16 gate passed',
                    '--evidence', 'closure_evidence/independent_review.json', 'gate_batch163.json',
                    'closure_evidence/owned_cleanup_revalidation.json', '--by', 'root'], check=True)
    subprocess.run([str(PYTHON), str(WRITER), str(RUN), 'check'], check=True)
    pin = ROOT / 'runs/plan_batches/closed_round_pins' / (RID + '.json')
    put(pin, {'rid': RID, 'round_sha256': sha(RUN / 'round.json'),
              'manifest_sha256': sha(RUN / 'MANIFEST.sha256')})
    pin.chmod(0o444)
    spec = importlib.util.spec_from_file_location('root_closed_d09_d07', HERE / 'protocol_t16/d07_g3g4_prepare.py')
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    gate.require_closed_round(RID, 'kept')
    print(json.dumps({'rid': RID, 'verdict': 'kept', 'round_json_sha256': sha(RUN / 'round.json'),
                      'manifest_sha256': sha(RUN / 'MANIFEST.sha256')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--independent-review', type=Path)
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'rid': RID, 'batch': BATCH, 'candidate_commit': CANDIDATE,
                          'mode': 'inert; requires completed actual evidence and sealed independent PASS'}))
        return
    if args.independent_review is None:
        parser.error('--execute requires --independent-review')
    execute(args.independent_review)


if __name__ == '__main__':
    main()
