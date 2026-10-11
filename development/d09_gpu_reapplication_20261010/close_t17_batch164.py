"""Archive completed batch164 without changing any original result bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess

ROOT = Path('/data2/FreeToken')
HERE = Path(__file__).resolve().parent
RID = 'E2-D09-T17-reapply-bd57-20261010'
RAW = HERE / 'protocol_t17/runs' / (RID + '_batch164') / RID
DEST = Path('/data2/_shared/runs/ft_rounds') / RID
WRITER = ROOT / 'scripts/round_json_append.py'
CLOSER = ROOT / 'scripts/round_close.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write('\n')


def close(review_path, verdict):
    assert not review_path.is_symlink() and review_path.is_file() and not review_path.stat().st_mode & 0o222
    review = json.loads(review_path.read_text())
    assert sha(review_path) == 'd8028c279bb06e78b6ada600f2cc1a2ea9a998f1a30d855d0b2a801d986e9eb6'
    assert sha(RAW / 'terminal.json') == '63a27ab3fbc95471cea02c270a437bb584027f0bd1892d99efb57ac7de570d2d'
    terminal = json.loads((RAW / 'terminal.json').read_text())
    assert terminal['rid'] == RID and terminal['calls'] == 4
    assert terminal['post_cleanup_closed'] and terminal['gpu_lock_released']
    assert not DEST.exists() and not Path('/data2/_shared/gpu.lock').exists()
    for name, digest in terminal['artifact_sha256'].items():
        assert not (RAW / name).is_symlink() and sha(RAW / name) == digest, name
    assert sha(WRITER) == '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
    assert sha(CLOSER) == 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5'
    assert not subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'], text=True).strip()
    assert all(int(x) < 1000 for x in subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], text=True).splitlines())
    config = json.loads((RAW / 'config.json').read_text())
    services = [x for x in config['services'] if x['name'] in terminal['services_cleaned']]
    assert len(services) == 3
    for service in services:
        for port in service['ports']:
            with socket.socket() as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(('127.0.0.1', port))
    # Hardlinks preserve the original large tensor bytes. The completed source
    # evidence becomes read-only together with the canonical archive.
    shutil.copytree(RAW, DEST, copy_function=os.link)
    evidence = DEST / 'closure_evidence'; evidence.mkdir()
    shutil.copyfile(review_path, evidence / 'independent_review.json')
    shutil.copyfile(Path(__file__), evidence / 'close_t17_batch164.py')
    launch = HERE / 'protocol_t17/runs' / ('launch_' + RID + '_batch164.json')
    shutil.copyfile(launch, evidence / 'launch_receipt.json')
    launch_doc = json.loads(launch.read_text())
    argv = launch_doc.get('argv')
    (DEST / 'batch.sh').write_text('# Archived controller command; do not execute.\n' + (shlex.join(argv) if isinstance(argv, list) else '# See immutable closure_evidence/launch_receipt.json') + '\n')
    arms = {}
    for service in services:
        name = service['name']; arm = DEST / name; arm.mkdir()
        birth = json.loads((RAW / 'services' / name / 'pid_birth.json').read_text())
        assert birth['argv'] == service['argv']
        (arm / 'SERVE_CMD.txt').write_text(shlex.join(birth['argv']) + '\n')
        os.link(RAW / 'services' / name / 'serve.log', arm / 'serve.log')
        (arm / 'serve_args.txt').write_text('Reconstruction from exact recorded launched argv; not a new live argument dump.\n' + json.dumps(birth['argv']) + '\n')
        (arm / 'ENV.txt').write_text('Task environment from original config.json; not reconstructed inherited host state.\n' + json.dumps(service.get('env', {}), sort_keys=True) + '\n')
        arms[name] = {'source': 'services/' + name, 'launched_argv_sha256': sha(RAW / 'services' / name / 'pid_birth.json')}
    doc = {'schema': 'ft_round/v2', 'round_id': RID, 'card': 'D09-T17', 'batch': 164,
           'experimental': {'candidate_commit': config['candidate']},
           'actual_services': 3, 'actual_generation_calls': 4,
           'verdict': 'pending_review', 'proposed_verdict': verdict,
           'original_runner_terminal': terminal['proposed_verdict'],
           'product_acceptance': False, 'verdict_history': [], 'retractions': [],
           'serve': {'arms': arms},
           'batch_logs': [{'path': '/data2/_shared/runs/ft_rounds/batch164.log', 'sha256': sha('/data2/_shared/runs/ft_rounds/batch164.log')}],
           'original_terminal_sha256': sha(RAW / 'terminal.json'),
           'independent_review_sha256': sha(review_path),
           'observed_failure': 'hot exact-ID target cached_tokens=20160; configured P=20282; equivalence gate did not finish',
           'conclusion_scope': 'Enabled T17 not accepted; preserve runner result and independent causal review. No retry authorized by closure.'}
    put(DEST / 'round.json', doc)
    python = str(ROOT / 'venv/bin/python')
    subprocess.run([python, str(CLOSER), RID, '--round-root', str(DEST.parent)], check=True)
    subprocess.run([python, str(WRITER), str(DEST), 'verdict', '--new', verdict,
                    '--reason', 'Independent completed-batch review; enabled equivalence not accepted',
                    '--evidence', 'closure_evidence/independent_review.json', 'terminal.json', '--by', 'root'], check=True)
    subprocess.run([python, str(WRITER), str(DEST), 'check'], check=True)
    pin = ROOT / 'runs/plan_batches/closed_round_pins' / (RID + '.json')
    put(pin, {'rid': RID, 'round_sha256': sha(DEST / 'round.json'), 'manifest_sha256': sha(DEST / 'MANIFEST.sha256')})
    pin.chmod(0o444)
    print(json.dumps({'rid': RID, 'verdict': verdict, 'round_sha256': sha(DEST / 'round.json'), 'manifest_sha256': sha(DEST / 'MANIFEST.sha256')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--independent-review', type=Path, required=True)
    parser.add_argument('--verdict', choices=['failed_harness', 'not_met'], required=True)
    args=parser.parse_args()
    close(args.independent_review, args.verdict)
