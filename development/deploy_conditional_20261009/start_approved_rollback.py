"""One user-authorized rollback start; the existing supervisor owns service and GPU lock."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    approval = json.loads((HERE / 'DEPLOYMENT_APPROVAL.json').read_text())
    assert 'failure stop and rollback184' in approval['scope']
    approval['approval_id'] = approval['rollback_approval']
    approval['run_dir'] = '/data2/FreeToken/runs/production/' + approval['approval_id']
    failed = Path('/data2/FreeToken/runs/production/DEPLOY-E2-20261009-COND-01')
    assert (failed / 'stopped.json').is_file()
    assert json.loads((failed / 'smoke_execution_result.json').read_text())['classification'] == 'failed'
    ops = Path(approval['ops'])
    archive = ops.parents[2]
    assert sha(ops / 'binary_manifest.json') == approval['binary_manifest_sha256']
    sources = json.loads((archive / 'evidence/source_manifest.json').read_text())
    assert all(sha(archive / 'source' / name) == digest for name, digest in sources.items())
    spec = importlib.util.spec_from_file_location('deployment_checks', ops / 'worktree_checks.py')
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    manifest = json.loads((ops / 'binary_manifest.json').read_text())
    receipts = {mode: checks.validate_worktree(item['path'], item['commit'], manifest, mode)
                for mode, item in manifest['worktrees'].items()}
    for mode in ('release', 'r067_cold'):
        tree = Path(manifest['worktrees'][mode]['path'])
        assert not list((tree / 'python/freetoken/kernel').glob('_row_store*.so'))
        for item in manifest['worktrees'][mode]['extensions']:
            assert (tree / item['path']).read_bytes() == (Path('/data2/FreeToken/wt/e2oom-protocol-restart') / item['path']).read_bytes()
    compute = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True)
    memory = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], text=True)
    ports = subprocess.check_output(['ss', '-H', '-ltn', '( sport = :8095 or sport = :8096 )'], text=True)
    assert not compute.strip() and not ports.strip() and all(int(row) < 1000 for row in memory.splitlines())
    for path in ('/data2/_shared/gpu.lock', '/data2/FreeToken/run/production.active.json', '/data2/FreeToken/run/production.cleanup_failed.json'):
        assert not Path(path).exists() and not Path(path).is_symlink()
    run = Path(approval['run_dir'])
    assert not run.exists()
    run.parent.mkdir(parents=True, exist_ok=True)
    Path('/data2/FreeToken/run').mkdir(exist_ok=True)
    proof = {'schema': 'ft_conditional_deploy_execution_preflight/v1', 'approval_id': approval['approval_id'],
             'conditions_met': True, 'worktrees': receipts, 'compute_pids': compute, 'GPU_memory_mib': memory,
             'production_listeners': ports, 'source_manifest_matches': True, 'at': time.time()}
    with (HERE / 'ROLLBACK_EXECUTION_PREFLIGHT.json').open('x') as handle:
        json.dump(proof, handle, indent=2)
        handle.write('\n')
    argv = ['setsid', '-f', '/data2/FreeToken/venv/bin/python', str(ops / 'release_control.py'),
            '--start', '--mode', 'rollback', '--approval-id', approval['approval_id'], '--run-dir', str(run)]
    log = run.parent / (approval['approval_id'] + '.supervisor.log')
    with log.open('xb') as handle:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=handle, stderr=subprocess.STDOUT,
                                   env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        assert process.wait(timeout=10) == 0
    deadline = time.monotonic() + 20
    while not (run / 'owner.json').exists():
        if time.monotonic() > deadline:
            raise RuntimeError('Supervisor owner not published: ' + log.read_text()[-5000:])
        time.sleep(.2)
    owner = json.loads((run / 'owner.json').read_text())
    assert owner['approval_id'] == approval['approval_id'] and owner['mode'] == 'rollback'
    for source, name in ((HERE / 'DEPLOYMENT_APPROVAL.json', 'deployment_approval.json'),
                         (HERE / 'INDEPENDENT_PREFLIGHT_REVIEW.json', 'independent_preflight_review.json'),
                         (HERE / 'ROLLBACK_EXECUTION_PREFLIGHT.json', 'execution_preflight.json'),
                         (ops / 'binary_manifest.json', 'binary_manifest.json')):
        with (run / name).open('xb') as handle:
            handle.write(source.read_bytes())
    with (run / 'exposure.json').open('x') as handle:
        json.dump({'phase': 'exclusive_smoke_only', 'business_release': False,
                   'approval_id': approval['approval_id'], 'at': time.time()}, handle)
        handle.write('\n')
    result = {'status': 'rollback_started_waiting_serving', 'approval_id': approval['approval_id'], 'run_dir': str(run),
              'supervisor': owner['supervisor'], 'service': owner['service'], 'gpu_owner': owner['gpu_owner'],
              'supervisor_log': str(log)}
    with (run.parent / 'coordination.jsonl').open('a') as handle:
        handle.write(json.dumps(result) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
