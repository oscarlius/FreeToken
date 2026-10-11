"""Copy one production run read-only; live logs are explicitly snapshots."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import time

import paramiko

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('approval_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', args.approval_id):
        raise ValueError('Invalid production run identity')
    target = HERE / ('evidence_' + args.approval_id)
    target.mkdir(exist_ok=False)
    spec = importlib.util.spec_from_file_location('existing_ssh', HERE.parents[2] / '_shared/ssh_upload.py')
    settings = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settings)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(settings.REMOTE_HOST, username=settings.REMOTE_USER,
                   password=settings.REMOTE_PASS, timeout=15)
    started = time.time()
    entries = []
    root = '/data2/FreeToken/runs/production/' + args.approval_id
    try:
        with client.open_sftp() as sftp:
            def copy(remote, local):
                for item in sftp.listdir_attr(remote):
                    source = remote + '/' + item.filename
                    output = local / item.filename
                    if stat.S_ISDIR(item.st_mode):
                        output.mkdir()
                        copy(source, output)
                    else:
                        if not stat.S_ISREG(item.st_mode):
                            raise ValueError('Non-regular evidence file: ' + source)
                        with sftp.open(source, 'rb') as handle:
                            data = handle.read()
                        output.write_bytes(data)
                        entries.append({'path': output.relative_to(target).as_posix(),
                                        'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                                        'remote': source})

            copy(root, target)
            source = root + '.supervisor.log'
            with sftp.open(source, 'rb') as handle:
                data = handle.read()
            output = target / (args.approval_id + '.supervisor.log')
            output.write_bytes(data)
            entries.append({'path': output.name, 'bytes': len(data),
                            'sha256': hashlib.sha256(data).hexdigest(), 'remote': source})
    finally:
        client.close()
    manifest = {'schema': 'ft_production_evidence_snapshot/v1',
                'approval_id': args.approval_id, 'capture_started_at': started,
                'capture_ended_at': time.time(), 'read_only_capture': True,
                'live_logs_are_snapshots': True, 'files': entries}
    path = HERE / (args.approval_id + '.EVIDENCE_MANIFEST.json')
    with path.open('x', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'files': len(entries), 'bytes': sum(row['bytes'] for row in entries),
                      'manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'manifest': str(path)}))


if __name__ == '__main__':
    main()
