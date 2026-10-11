"""Create an immutable forensic copy of the stopped E2-R035 failure package."""
from pathlib import Path
import json
import subprocess

PROGRAM = r'''
import datetime, hashlib, json, os, pathlib, shutil, socket, stat
source = pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R035')
parent = pathlib.Path('/data2/FreeToken/runs/dev_D16')

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def inventory(root):
    entries, files, total = [], {}, 0
    for current, dirs, names in os.walk(root, followlinks=False):
        current_path = pathlib.Path(current)
        for name in sorted(dirs + names):
            path = current_path / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise RuntimeError('symlink in source: ' + rel)
            if path.is_dir():
                entries.append({'path': rel, 'type': 'dir'})
            elif path.is_file():
                size = path.stat().st_size
                files[rel] = {'sha256': digest(path), 'size': size}
                total += size
                entries.append({'path': rel, 'type': 'file', 'size': size, 'sha256': files[rel]['sha256']})
            else:
                raise RuntimeError('nonregular source entry: ' + rel)
    return entries, files, total

if os.path.exists('/proc/3468758'):
    raise RuntimeError('R035 controller PID 3468758 is still live')
probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    if probe.connect_ex(('127.0.0.1', 8095)) == 0:
        raise RuntimeError('port 8095 is still listening')
finally:
    probe.close()
failed = source / 'failed_harness.json'
status = source / 'status_batch64.json'
if not source.is_dir() or source.is_symlink() or not failed.is_file() or not status.is_file():
    raise RuntimeError('stopped failed R035 source is unavailable')
if json.loads(failed.read_text()).get('admitted') is not False:
    raise RuntimeError('source failure receipt is not non-admitted')
before_entries, before_files, before_bytes = inventory(source)
stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
root = parent / ('r035_failure_snapshot_' + stamp)
snapshot = root / 'snapshot' / 'E2-R035'
root.mkdir()
snapshot.mkdir(parents=True)
try:
    for index, item in enumerate(before_entries, 1):
        rel = item['path']; src = source / rel; dst = snapshot / rel
        if item['type'] == 'dir':
            dst.mkdir()
            continue
        with src.open('rb') as inp, dst.open('xb') as out:
            shutil.copyfileobj(inp, out, 8 * 1024 * 1024)
        copied = {'sha256': digest(dst), 'size': dst.stat().st_size}
        if copied != before_files[rel] or (src.stat().st_dev, src.stat().st_ino) == (dst.stat().st_dev, dst.stat().st_ino):
            raise RuntimeError('copy verification failed: ' + rel)
        if index % 250 == 0:
            print(json.dumps({'copied_entries': index, 'total_entries': len(before_entries)}), flush=True)
    after_entries, after_files, after_bytes = inventory(source)
    if before_entries != after_entries or before_files != after_files or before_bytes != after_bytes:
        raise RuntimeError('source changed while snapshotting')
    copied_entries, copied_files, copied_bytes = inventory(snapshot)
    if copied_entries != before_entries or copied_files != before_files or copied_bytes != before_bytes:
        raise RuntimeError('snapshot inventory differs from source')
    report = {'schema': 'ft_t17_r035_failure_snapshot/v1', 'verdict': 'PASS', 'source': str(source),
        'snapshot': str(snapshot), 'source_unchanged': True, 'source_entries': before_entries,
        'files': before_files, 'bytes': before_bytes, 'failed_harness_sha256': digest(failed),
        'model_admitted': False, 'd04_closed': False, 'gpu_started': False}
    raw = json.dumps(report, sort_keys=True).encode()
    receipt = root / 'snapshot_receipt.json'
    with receipt.open('xb') as handle: handle.write(raw)
    for path in sorted(snapshot.rglob('*'), reverse=True):
        if path.is_symlink(): raise RuntimeError('snapshot has symlink')
        path.chmod(0o555 if path.is_dir() else 0o444)
    snapshot.chmod(0o555); snapshot.parent.chmod(0o555); receipt.chmod(0o444); root.chmod(0o555)
    print(json.dumps({'verdict': 'PASS', 'snapshot': str(snapshot), 'bytes': before_bytes,
        'files': len(before_files), 'receipt_sha256': digest(receipt), 'source_unchanged': True}), flush=True)
except BaseException as error:
    failure = {'verdict': 'FAIL', 'error': repr(error), 'source': str(source), 'snapshot': str(snapshot)}
    with (root / 'snapshot_failure.json').open('x') as handle: json.dump(failure, handle, sort_keys=True)
    raise
'''

def main():
    result = subprocess.run(['ssh', '-o', 'BatchMode=yes', '9', '/data2/FreeToken/venv/bin/python', '-'],
                            input=PROGRAM, text=True, capture_output=True)
    receipt = Path(__file__).with_name('t17_r035_failure_snapshot_execution.json')
    with receipt.open('x', encoding='utf-8') as handle:
        json.dump({'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}, handle, indent=2)
    print(result.stdout); print(result.stderr)
    raise SystemExit(result.returncode)

if __name__ == '__main__':
    main()
