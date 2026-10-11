"""Build an actual V10 admission after the final preceding GPU cleanup.

CPU evidence only: this entry never launches a service or reserves a batch.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import socket
import subprocess
from pathlib import Path

ROOT = Path('/data2/FreeToken')
NIGHT = ROOT / 'development/night_execution_20261009'
PACKET = ROOT / 'development/d10_gpu_night_v1'
OPS = ROOT / 'runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded/source/development/release_e2_ops_v2/release_config.py'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frozen(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o222:
        raise RuntimeError('frozen regular evidence required: ' + str(path))
    return path


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--predecessor-cleanup', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    os.chdir(ROOT)
    cleanup = frozen(args.predecessor_cleanup)
    if cleanup.parent != NIGHT:
        raise RuntimeError('predecessor cleanup outside night scope')
    facts = json.loads(cleanup.read_text())
    if not all(facts.get(key) is True for key in ('cleanup_ok', 'gpu_compute_absent', 'gpu_lock_absent')):
        raise RuntimeError('predecessor cleanup incomplete')
    for path in (Path('/data2/_shared/gpu.lock'), ROOT / 'run/production.active.json', ROOT / 'run/production.cleanup_failed.json'):
        if path.exists() or path.is_symlink():
            raise RuntimeError('GPU or production ownership still present')
    if subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip():
        raise RuntimeError('GPU not idle')
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    if now.hour > 6 or now.hour == 6 and now.minute >= 45 or (now.replace(hour=7, minute=30, second=0, microsecond=0) - now).total_seconds() < 75 * 60:
        raise RuntimeError('insufficient time before restore deadline')
    if not 1024 <= args.port <= 65534:
        raise RuntimeError('invalid private port pair')
    held = []
    try:
        for port in (args.port, args.port + 1):
            for family, address in ((socket.AF_INET, ('0.0.0.0', port)), (socket.AF_INET6, ('::', port))):
                sock = socket.socket(family)
                held.append(sock)
                if family == socket.AF_INET6:
                    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(address)
    finally:
        for sock in held:
            sock.close()
    a = load(frozen(PACKET / 'd10_prototype_owned_parent_v10.py'), 'night_d10_v10')
    recipe = load(frozen(OPS), 'night_frozen_release_recipe')
    original = recipe.serve_argv('release')
    if original[:3] != ['taskset', '-c', '1,3-47'] or original[4] != 'serve':
        raise RuntimeError('frozen R045 production recipe prefix differs')
    argv = ['ft', *original[4:]]
    argv[argv.index('--host') + 1] = '127.0.0.1'
    argv[argv.index('--port') + 1] = str(args.port)
    argv.append(a.b.FLAG)
    d09_cleanup = frozen(NIGHT / 'D09_T16_RETRY1_OWNED_CLEANUP_READBACK.json')
    native = frozen(PACKET / 'd10_native_provenance_v2.json')
    admission = {
        'schema': 'ft_d10_prototype_v10_admission/v1', 'admit': True,
        'rid': a.RID, 'candidate': a.b.CANDIDATE, 'parent': a.b.PARENT,
        'flag': a.b.FLAG, 'calls_max': 8, 'services_max': 1,
        'source_sha256': a.sources(), 'runner_source_sha256': a.b.runner().source_hashes(),
        't16': a.formal(a.b.T16_RID)[1], 'd09': a.formal(a.b.D09_RID)[1],
        'd09_cleanup': {'path': str(d09_cleanup), 'sha256': sha(d09_cleanup)},
        'native_provenance': {'path': str(native), 'sha256': sha(native)},
        'actual_predecessor_cleanup': {'path': str(cleanup), 'sha256': sha(cleanup)},
        'frozen_recipe': {'path': str(OPS), 'sha256': sha(OPS), 'original_argv': original},
        'required_controller_cpu_affinity': '1,3-47',
        'service': {'argv': argv, 'api_port': args.port, 'tcpstore_port': args.port + 1,
                    'endpoint': f'http://127.0.0.1:{args.port}', 'cwd': str(a.b.WT)},
        'prototype_output': str(a.b.RUNS / a.RID), 'at': now.isoformat(),
        'authority': 'NIGHT_SUPPLEMENT_20261010_0035',
        'builder': {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)},
    }
    if args.output.parent != NIGHT or args.output.exists() or args.output.is_symlink():
        raise RuntimeError('fresh night admission output required')
    with args.output.open('x') as handle:
        json.dump(admission, handle, indent=2, sort_keys=True)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())
    args.output.chmod(0o444)
    a.admission(args.output)
    print(json.dumps({'admission': str(args.output), 'sha256': sha(args.output), 'actual_consumer_pass': True, 'service_started': False}))


if __name__ == '__main__':
    main()
