"""Launch the independently reviewed S2 retry after exact D09 owner cleanup."""
import datetime
import hashlib
import importlib.util
import json
import os
import socket
import stat
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
PACKET = Path('/data2/Strata/r002-prep/s2_retry1_v2_20261010')
ROUND = Path('/data2/_shared/runs/ft_rounds/E2-D09-T16-night-20261009')
PY = ROOT / 'venv/bin/python'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.flush(); os.fsync(stream.fileno())
    path.chmod(0o444)


def absent(pid, birth):
    try:
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
        return fields[0] == 'Z' or int(fields[19]) != birth
    except FileNotFoundError:
        return True


def require_regular(path):
    assert path.is_file() and not path.is_symlink() and stat.S_ISREG(path.stat().st_mode), str(path)


def assert_no_listener(port):
    found = {}
    for name in ('/proc/net/tcp', '/proc/net/tcp6'):
        rows = []
        for line in Path(name).read_text().splitlines()[1:]:
            fields = line.split()
            if int(fields[1].rsplit(':', 1)[1], 16) == port:
                rows.append({'address': fields[1], 'state': fields[3]})
        assert all(row['state'] != '0A' for row in rows), 'LISTEN remains: ' + name
        found[name] = rows
    return found


def main():
    launch = ROOT / 'runs/dev_T16/launch_E2-D09-T16-night-20261009_batch142.json'
    require_regular(launch)
    binding = json.loads(launch.read_text())
    child = binding['child']
    assert child == {'pid': 199552, 'start_ticks': 165838035, 'execution_id': '199552:165838035'}
    while not absent(child['pid'], child['start_ticks']):
        time.sleep(30)
    # No round verdict is invented. Only the actual owned resources are checked.
    assert not Path('/data2/_shared/gpu.lock').exists() and not Path('/data2/_shared/gpu.lock').is_symlink()
    assert not (ROOT / 'run/production.active.json').exists() and not (ROOT / 'run/production.active.json').is_symlink()
    assert not (ROOT / 'run/production.cleanup_failed.json').exists() and not (ROOT / 'run/production.cleanup_failed.json').is_symlink()
    assert not subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
    owners = []
    for path in ROUND.glob('*/owned_process.json'):
        require_regular(path)
        owner = json.loads(path.read_text())
        birth = owner.get('birth', owner)
        assert absent(birth['pid'], birth['start_ticks'])
        pgid = birth.get('pgid', owner.get('pgid', birth['pid']))
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
                assert fields[0] == 'Z' or int(fields[2]) != pgid
            except (FileNotFoundError, ProcessLookupError):
                pass
        port = owner.get('port')
        assert isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65534, 'malformed owner port'
        listen_proof = {}
        for value in (port, port + 1):
            listen_proof[str(value)] = assert_no_listener(value)
        if port is not None:
            sockets = []
            try:
                for value in (port, port + 1):
                    sock = socket.socket(); sockets.append(sock)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(('0.0.0.0', value))
            finally:
                for sock in sockets:
                    sock.close()
        owners.append({'path': str(path), 'sha256': sha(path), 'pid': birth['pid'], 'start_ticks': birth['start_ticks'], 'pgid': pgid, 'port': port, 'tcpstore_port': port + 1 if port is not None else None, 'group_absent': True, 'all_interface_listen_states': listen_proof, 'ports_rebound': True, 'absent': True})
    assert owners, 'expected actual D09 service owners are missing'
    status_path = ROUND / 'status_batch142.json'
    require_regular(status_path)
    status = json.loads(status_path.read_text())
    assert status['rid'] == ROUND.name and status['batch'] == 142 and status['batch_pid'] == 199552
    assert status['state'] in ('complete_measurements_pending_review', 'failed')
    cleanup_path = HERE / 'D09_T16_OWNED_CLEANUP_READBACK.json'
    put(cleanup_path, {'at': datetime.datetime.now().astimezone().isoformat(), 'cleanup_ok': True,
        'rid': ROUND.name, 'launch_receipt_sha256': sha(launch), 'actual_status': status,
        'status_sha256': sha(status_path), 'child_absent': child, 'service_owners': owners,
        'gpu_compute_absent': True, 'gpu_lock_absent': True, 'product_acceptance': False})
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    assert now.hour < 6 or (now.hour == 6 and now.minute < 45), 'cutoff: do not start a new bounded round'
    script = PACKET / 'run_s2_retry1_v2.py'
    review = PACKET / 'INDEPENDENT_STARTUP_REVIEW.json'
    approval = json.loads(review.read_text())
    assert approval['verdict'] == 'CPU_ADMISSION_READY_CONDITIONAL'
    assert sha(script) == approval['immutable_bindings']['runner_sha256']
    assert sha(PACKET / 'FILE_DRY_S2_RETRY1_V2_R2.json') == approval['immutable_bindings']['file_dry_r2_sha256']
    spec = importlib.util.spec_from_file_location('root_strata_retry1', script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    dry = module.file_dry()
    assert dry == json.loads((PACKET / 'FILE_DRY_S2_RETRY1_V2_R2.json').read_text())
    preflight = module.port_preflight('S2')
    preflight_path = PACKET / 'PORT_PREFLIGHT_S2.json'; preflight_path.chmod(0o444)
    with preflight_path.open('rb') as handle: os.fsync(handle.fileno())
    assert preflight['listen_absent']
    admission_path = PACKET / 'ROOT_ADMISSION_S2.json'
    put(admission_path, {'admit': True, 'arm': 'S2', 'bindings': dry['bindings'], 'config': dry['configs']['S2'],
        'generation_calls_max': 11, 'services_max': 3,
        'predecessor_cleanup': {'path': str(cleanup_path), 'sha256': sha(cleanup_path)},
        'port_preflight': {'path': str(preflight_path), 'sha256': sha(preflight_path)},
        'independent_review': {'path': str(review), 'sha256': sha(review)},
        'at': now.isoformat(), 'authority': 'NIGHT_SUPPLEMENT_20261010_0035', 'no_push': True})
    argv = [str(PY), '-B', '-u', str(script), '--run', 'S2']
    receipt = HERE / 'STRATA_S2_RETRY1_DRIVER_RECEIPT.json'
    assert not receipt.exists()
    with (HERE / 'STRATA_S2_RETRY1_DRIVER.log').open('xb') as log:
        process = subprocess.Popen(argv, cwd='/data2/Strata/wt/r002-v0141', stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
    fields = Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()
    value = {'at': datetime.datetime.now().astimezone().isoformat(), 'pid': process.pid,
        'start_ticks': int(fields[19]), 'argv': argv, 'source_sha256': sha(script),
        'admission_sha256': sha(admission_path), 'review_sha256': sha(review)}
    put(receipt, value)
    with (HERE / 'COORDINATION_LOG.jsonl').open('a') as stream:
        stream.write(json.dumps(value | {'event': 'STRATA_S2_RETRY1_STARTED_AFTER_D09_OWNED_CLEANUP'}) + '\n')
        stream.flush(); os.fsync(stream.fileno())
    print(json.dumps(value), flush=True)


if __name__ == '__main__':
    main()
