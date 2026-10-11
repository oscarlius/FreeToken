"""Assign and atomically launch a candidate gate after fresh resource preflight."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from types import ModuleType

ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
STAGE = ROOT / 'runs/dev_D06/t16_full_tail_d29f639'
PY = str(ROOT / 'venv/bin/python')
RUNNER_SHA = 'd29f639ea1559dff92588d8d8da25190a32ebf77f44f5cfd9618d302145f57f1'
BASE_SHA = '66f0dce3c5bdcc885f2e19267110e7a3a74798e7e87936b27faa122a28ae2125'
HELPER_SHA = 'a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf'
CPU_LOG_SHA = '3ac07ec5ad32a0821a6a27758b48743c5e9f8d078ddcbde288da668b7ca31612'
CANDIDATES = {
    'D06': ('D06', '03692633df48456fb0baa78de7b64e5628a12ab1'),
    'D07': ('D07', 'fefb19cbac6bb1cb08835c411c895310600b3677'),
}


def read_pinned(path, digest):
    source = path.read_bytes()
    if path.is_symlink() or hashlib.sha256(source).hexdigest() != digest:
        raise ValueError('frozen launch dependency changed: ' + str(path))
    return source


def verified_module(path, digest, name):
    source = read_pinned(path, digest)
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module


def verify_execution_directory(directory):
    parent = directory.parent
    parent_mode = parent.stat().st_mode
    if (parent.is_symlink() or not stat.S_ISDIR(parent_mode)
            or parent_mode & 0o022 and not parent_mode & stat.S_ISVTX):
        raise ValueError('execution copy parent permits unprotected replacement')
    if directory.is_symlink() or directory.stat().st_uid != os.geteuid() or directory.stat().st_mode & 0o222:
        raise ValueError('execution copy directory must be owned and read-only')
    for name,digest in (('t16_candidate_runner_full_tail.py', RUNNER_SHA), ('t16_full_tail_base_runner.py', BASE_SHA)):
        path = directory / name
        if (path.is_symlink() or not path.is_file() or path.stat().st_uid != os.geteuid()
                or path.stat().st_mode & 0o222):
            raise ValueError('execution copy source must be owned and read-only')
        read_pinned(path,digest)


def freeze_execution_copy(parent=Path('/tmp')):
    # A private owned directory under sticky /tmp prevents other users from
    # replacing the read-only source path after its approved bytes are copied.
    mode = parent.stat().st_mode
    if parent.is_symlink() or not stat.S_ISDIR(mode) or mode & 0o022 and not mode & stat.S_ISVTX:
        raise ValueError('unsafe execution copy parent')
    payloads = {'t16_candidate_runner_full_tail.py':read_pinned(STAGE/'t16_candidate_runner_full_tail.py',RUNNER_SHA),
                't16_full_tail_base_runner.py':read_pinned(STAGE/'t16_full_tail_base_runner.py',BASE_SHA)}
    directory = Path(tempfile.mkdtemp(prefix='ft-t16-source-',dir=parent))
    for name,data in payloads.items():
        with (directory/name).open('xb') as stream:
            stream.write(data)
        (directory/name).chmod(0o444)
    directory.chmod(0o555)
    verify_execution_directory(directory)
    return directory


def write_exclusive(path,value):
    with path.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(value,indent=2)+'\n')
        stream.flush(); os.fsync(stream.fileno())


def publish_receipt(path,identity,value):
    temporary = path.with_name(path.name+f'.{os.getpid()}.tmp')
    try:
        write_exclusive(temporary,value)
        current = path.stat()
        if path.is_symlink() or (current.st_dev,current.st_ino) != identity:
            raise ValueError('exclusive launch receipt identity changed')
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def owned_group_alive(pgid):
    try:
        os.killpg(pgid,0)
    except ProcessLookupError:
        return False
    alive = False
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            fields = (entry/'stat').read_text().rpartition(') ')[2].split()
        except FileNotFoundError:
            continue
        if int(fields[2]) != pgid:
            continue
        if int(fields[3]) != pgid:
            raise RuntimeError('process group no longer belongs to the reserved session')
        alive |= fields[0] != 'Z'
    return alive


def stop_owned_process(process,term_timeout=120,kill_timeout=30):
    # The leader can exit while descendants still hold the owned session.
    for signum,timeout in ((signal.SIGTERM,term_timeout),(signal.SIGKILL,kill_timeout)):
        process.poll()
        if not owned_group_alive(process.pid):
            return
        if process.poll() is None:
            try:
                group = os.getpgid(process.pid)
            except ProcessLookupError:
                if not owned_group_alive(process.pid):
                    return
            else:
                if group != process.pid:
                    raise RuntimeError('owned batch no longer has its expected process group')
        try:
            os.killpg(process.pid,signum)
        except ProcessLookupError:
            if not owned_group_alive(process.pid):
                return
            raise RuntimeError('owned group identity changed during cleanup')
        deadline = time.monotonic()+timeout
        while True:
            process.poll()
            if not owned_group_alive(process.pid):
                return
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.1,remaining))
    raise RuntimeError('owned process group remains after KILL deadline')


def reserve_process(helper,batch,rid,argv,receipt_path,reserved):
    write_exclusive(receipt_path,reserved)
    current = receipt_path.stat()
    identity = (current.st_dev,current.st_ino)
    try:
        process,wrapper,log = helper.reserve_and_launch(batch,rid,argv)
    except BaseException as exc:
        publish_receipt(receipt_path,identity,{**reserved,'state':'launch_failed','error':repr(exc)})
        raise
    receipt = {**reserved,'state':'launched','batch_pid':process.pid,'batch_pgid':process.pid,
        'wrapper':str(wrapper),'wrapper_sha256':hashlib.sha256(wrapper.read_bytes()).hexdigest(),'batch_log':str(log)}
    try:
        publish_receipt(receipt_path,identity,receipt)
    except BaseException as publish_error:
        cleanup_error = None
        try:
            stop_owned_process(process)
        except BaseException as exc:
            cleanup_error = repr(exc)
        recovery = {**receipt,'state':'cleanup_failure' if cleanup_error else 'receipt_publish_failed_stopped',
                    'receipt_error':repr(publish_error),'cleanup_error':cleanup_error}
        print(json.dumps(recovery),file=sys.stderr,flush=True)
        write_exclusive(receipt_path.with_name(receipt_path.name+f'.cleanup_{process.pid}.json'),recovery)
        if cleanup_error:
            raise RuntimeError('launch receipt failed and owned process cleanup failed: '+cleanup_error) from publish_error
        raise
    return receipt


def next_round(root):
    numbers = []
    for path in root.iterdir():
        match = re.fullmatch(r'E2-R([0-9]{3})(?:-[A-Za-z0-9-]+)?', path.name)
        if match:
            if path.is_symlink() or not path.is_dir():
                raise ValueError('round ledger has an invalid matching entry')
            numbers.append(int(match.group(1)))
    if not numbers or max(numbers) >= 999:
        raise ValueError('usable E2 round ledger required')
    return max(numbers) + 1


def launch(case):
    if sys.platform != 'linux':
        raise ValueError('candidate launch requires the Linux test host')
    helper = verified_module(ROOT / 'runs/plan_batches/e2_launch.py', HELPER_SHA, 'ft_atomic_launcher')
    if not isinstance(CPU_LOG_SHA,str) or not re.fullmatch(r'[0-9a-f]{64}',CPU_LOG_SHA):
        raise ValueError('root must freeze the new exact-source Linux CPU proof before launch')
    report = json.loads((STAGE / 'cpu_validation.json').read_text())
    if (len(report.get('steps', [])) != 3 or any(s.get('returncode') != 0 for s in report['steps'])
            or report.get('files', {}).get('t16_candidate_runner_full_tail.py') != RUNNER_SHA
            or report.get('files', {}).get('t16_full_tail_base_runner.py') != BASE_SHA
            or report.get('log_sha256') != CPU_LOG_SHA
            or hashlib.sha256((STAGE / 'cpu_validation.log').read_bytes()).hexdigest() != CPU_LOG_SHA):
        raise ValueError('exact candidate gate CPU proof is missing or changed')
    execution = freeze_execution_copy()
    candidate = verified_module(execution/'t16_candidate_runner_full_tail.py',RUNNER_SHA,'ft_candidate_gate')
    card, commit = CANDIDATES[case]
    if candidate.CASES[case]['new_commit'] != commit:
        raise ValueError('launcher and reviewed runner candidate binding differ')
    number = next_round(ROUNDS)
    rid = f'E2-R{number:03d}-gate-{card}'
    batch = helper.next_batch(ROUNDS)
    argv = [PY, '-u', str(execution / 't16_candidate_runner_full_tail.py'), '--case', case,
            '--rid', rid, '--batch', str(batch), '--candidate-commit', commit]
    subprocess.run(argv, check=True, timeout=120)
    if next_round(ROUNDS) != number or helper.next_batch(ROUNDS) != batch or (ROUNDS / rid).exists():
        raise ValueError('assigned ledger identity changed during preflight')
    verify_execution_directory(execution)
    receipt_path = ROOT/f'runs/dev_{card}'/f'launch_{rid}.json'
    reserved = {'schema': 'ft_candidate_gate_launch/v1', 'case': case, 'card': card,
        'state':'reserved','rid':rid,'batch':batch,
        'runner': str(execution / 't16_candidate_runner_full_tail.py'), 'runner_sha256': RUNNER_SHA,
        'source_stage':str(STAGE),'base_runner_sha256':BASE_SHA,
        'launcher_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'atomic_helper_sha256': HELPER_SHA, 'candidate_commit': commit,
        'parent_commit': candidate.CASES[case]['parent_commit'],
        'cpu_validation_log_sha256': CPU_LOG_SHA}
    receipt = reserve_process(helper,batch,rid,argv,receipt_path,reserved)
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CANDIDATES, required=True)
    launch(parser.parse_args().case)
