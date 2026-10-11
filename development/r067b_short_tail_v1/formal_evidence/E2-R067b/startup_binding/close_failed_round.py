"""Freeze failed batch134 and append its verdict using the existing D04 tools."""
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import socket
import subprocess

HERE = Path(__file__).resolve().parent
RID = 'E2-R067b'
RAW = Path('/data2/FreeToken/runs/dev_R067') / RID
ROOT = Path('/data2/_shared/runs/ft_rounds') / RID
PY = '/data2/FreeToken/venv/bin/python'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    terminal = json.loads((RAW / 'terminal.json').read_text())
    assert terminal['verdict'] == 'failed_harness'
    assert terminal['actual_services'] == 1 and terminal['actual_generation_calls'] == 0
    assert not terminal['cleanup_errors'] and terminal['GPU_lock_released']
    assert not terminal['cells'] and not terminal['requests']
    assert not Path('/proc/2796853').exists() and not Path('/proc/2797014').exists()
    assert not Path('/data2/_shared/gpu.lock').exists()
    assert not Path('/data2/_shared/gpu.lock').is_symlink()
    assert not subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
    memory = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'], text=True)
    assert all(int(row) < 1000 for row in memory.splitlines())
    for port in (28390, 28391, 8095, 8096):
        with socket.socket() as handle:
            handle.bind(('0.0.0.0', port))
    assert not ROOT.exists()
    review = json.loads((HERE / 'R067B_INDEPENDENT_TERMINAL_REVIEW.json').read_text())
    assert review['verdict'] == 'failed_harness' and review['actual_generation_calls'] == 0
    for relative, digest in json.loads((HERE / 'R067B_ROOT_TERMINAL_HASH_CHECK.json').read_text())['files'].items():
        source = RAW / relative
        if relative in ('launch_receipt.json', 'batch.sh', 'batch134.log'):
            continue  # These three were downloaded from their separately bound locations.
        assert sha(source) == digest, relative
    ROOT.mkdir()
    for path in RAW.iterdir():
        if path.is_file():
            shutil.copy2(path, ROOT / path.name)
    arms = {}
    for service in (RAW / 'services').iterdir():
        assert service.is_dir() and not service.is_symlink()
        dest = ROOT / service.name
        shutil.copytree(service, dest)
        argv = json.loads((dest / 'argv.json').read_text())
        env = json.loads((dest / 'environment.json').read_text())
        (dest / 'SERVE_CMD.txt').write_text(shlex.join(argv) + '\n')
        (dest / 'ENV.txt').write_text(json.dumps(env, indent=2) + '\n')
        lines = [line for line in (dest / 'serve.log').read_text().splitlines() if line.startswith('ServerArgs(')]
        assert len(lines) == 1
        (dest / 'serve_args.txt').write_text(lines[0] + '\n')
        arms[service.name] = {'raw_source': str(service), 'actual_argv_sha256': hashlib.sha256(json.dumps(argv, separators=(',', ':')).encode()).hexdigest()}
    launch = Path('/data2/FreeToken/runs/dev_R067/launch_E2-R067b_batch134.json')
    receipt = json.loads(launch.read_text())
    for source, name in ((launch, 'launch_receipt.json'), (receipt['wrapper'], 'batch.sh'), (receipt['batch_log'], 'batch134.log')):
        shutil.copy2(source, ROOT / name)
    binding = ROOT / 'startup_binding'
    binding.mkdir()
    names = ['R067B_CONFIG.json', 'R067B_ROOT_BINDINGS.json', 'R067B_COMMAND_TEMPLATE.json',
             'R067B_CONTROLLER.diff', 'prepare_bound_command.py',
             'R067B_INDEPENDENT_STARTUP_REVIEW.json', 'R067B_ROOT_STARTUP_ADMISSION.json',
             'R067B_ROOT_EXECUTION_COMMAND_CONFIG.json', 'R067B_ROOT_STOP_READBACK.json',
             'R067B_INDEPENDENT_TERMINAL_REVIEW.json', 'R067B_ROOT_TERMINAL_HASH_CHECK.json',
             'R067B_COMMAND_TEMPLATE_V2_CPU_ONLY.json', 'R067B_CONTROLLER_FIX.diff',
             'prepare_bound_command_v2.py', 'close_failed_round.py']
    sources = {}
    for name in names:
        shutil.copy2(HERE / name, binding / name)
        sources[name] = sha(binding / name)
    for name in ('evidence_cpu_v1', 'evidence_cpu_v2', 'tooling', 'tests'):
        shutil.copytree(HERE / name, binding / name, ignore=shutil.ignore_patterns('__pycache__'))
    manifest = Path(json.loads((HERE / 'R067B_CONFIG.json').read_text())['binary_manifest']['path'])
    shutil.copy2(manifest, binding / 'binary_manifest.json')
    sources['binary_manifest.json'] = sha(binding / 'binary_manifest.json')
    shutil.copy2(HERE / 'R067B_INDEPENDENT_TERMINAL_REVIEW.json', ROOT / 'independent_review.json')
    shutil.copy2(HERE / 'R067B_ROOT_STOP_READBACK.json', ROOT / 'cleanup_readback.json')
    document = {'schema': 'ft_round/v2', 'round_id': RID, 'card': 'R067', 'batch': 134,
                'retry_of': 'E2-R067a-d20-short-tail', 'retry_index': 2,
                'verdict': 'pending_review', 'proposed_verdict': 'failed_harness',
                'verdict_history': [], 'retractions': [], 'serve': {'arms': arms},
                'base': {'commit': '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'},
                'experimental': {'candidate_commit': 'd50be0f8f84ab1105f788be8f1354773ad539b63'},
                'batch_logs': [{'path': receipt['batch_log'], 'sha256': sha(receipt['batch_log'])}],
                'raw_run': str(RAW), 'source_binding': sources,
                'result_binding': {name: {'path': name, 'sha256': sha(ROOT / name)} for name in ('terminal.json', 'cleanup_readback.json')},
                'independent_review': {'path': 'independent_review.json', 'sha256': sha(ROOT / 'independent_review.json')},
                'retry_policy': {'maximum_retries': 2, 'used_retries': 2, 'remaining_retry_not_started': 'New user authority required for another complete matrix.'},
                'actual_services': 1, 'actual_generation_calls': 0, 'cells_comparable': 0,
                'product_acceptance': False, 'CPU_only_repair': review['CPU_only_repair']}
    (ROOT / 'round.json').write_text(json.dumps(document, indent=2) + '\n')
    closer = Path('/data2/FreeToken/runs/dev_D16/r041_accept_final_20261005_2012/d04_server_round_close_db7b2787.py')
    assert sha(closer) == 'db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
    result = subprocess.run([PY, str(closer), RID, '--round-root', str(ROOT.parent)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    append = subprocess.run([PY, '/data2/FreeToken/scripts/round_json_append.py', str(ROOT), 'verdict',
                             '--new', 'failed_harness', '--reason',
                             'Independent review confirms controller service-name shadowing. Root stopped owned batch before generation. CPU-only repair passes five tests; no product conclusion or new GPU authority.',
                             '--evidence', str(ROOT / 'terminal.json'), str(ROOT / 'independent_review.json'), str(ROOT / 'cleanup_readback.json'), '--by', 'root'], capture_output=True, text=True)
    assert append.returncode == 0, append.stderr
    check = subprocess.run([PY, '/data2/FreeToken/scripts/round_json_append.py', str(ROOT), 'check'], capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    for line in (ROOT / 'MANIFEST.sha256').read_text().splitlines():
        digest, name = line.split('  ', 1)
        assert sha(ROOT / name) == digest, name
    assert all(not path.stat().st_mode & 0o222 for path in [ROOT, *ROOT.rglob('*')])
    print(json.dumps({'formal_round': str(ROOT), 'D04': json.loads(result.stdout),
                      'append': json.loads(append.stdout), 'history_check': json.loads(check.stdout),
                      'manifest_sha256': sha(ROOT / 'MANIFEST.sha256'), 'round_sha256': sha(ROOT / 'round.json'),
                      'all_manifest_hashes_match': True, 'all_read_only': True,
                      'source_raw_preserved': True, 'verdict': 'failed_harness'}))


if __name__ == '__main__':
    main()
