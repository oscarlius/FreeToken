"""Exclusive-create sync and CPU-only Linux validation for the retry1 packet."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import posixpath
import shlex

HERE = Path(__file__).resolve().parent
REMOTE = '/data2/FreeToken/development/' + HERE.name


def load_ops():
    path = HERE.parent / 'r067c_retry2_production_control_20261009/ssh_ops.py'
    spec = importlib.util.spec_from_file_location('r067_ssh_ops', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files():
    for path in HERE.rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts or 'evidence_cpu_filedry_' in path.parts:
            continue
        yield path


def ensure_dir(sftp, directory: str) -> None:
    try:
        sftp.mkdir(directory)
    except OSError:
        pass


def sync(sftp) -> None:
    ensure_dir(sftp, REMOTE)
    for source in files():
        relative = source.relative_to(HERE).as_posix()
        parent = REMOTE
        for part in relative.split('/')[:-1]:
            parent = posixpath.join(parent, part)
            ensure_dir(sftp, parent)
        target = posixpath.join(REMOTE, relative)
        try:
            with sftp.open(target, 'rb') as handle:
                existing = handle.read()
            if existing != source.read_bytes():
                # The only mutable state is this agent's not-yet-validated packet.
                # Once a Linux receipt exists the directory is immutable.
                try:
                    sftp.stat(posixpath.join(REMOTE, 'LINUX_CPU_RECEIPT_v1.json'))
                except OSError:
                    with sftp.open(target, 'wb') as handle:
                        handle.write(source.read_bytes())
                else:
                    raise AssertionError(f'remote validated packet differs: {target}')
        except FileNotFoundError:
            with sftp.open(target, 'wx') as handle:
                handle.write(source.read_bytes())


def main() -> None:
    ops = load_ops()
    client = ops.connect()
    try:
        sftp = client.open_sftp()
        sync(sftp)
        sftp.close()
        code = r'''
import hashlib,json,os,subprocess,time
from pathlib import Path
packet=Path('/data2/FreeToken/development/r067d_short_tail_retry1_20261010')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
freeze=json.loads((packet/'RETRY1_SOURCE_FREEZE.json').read_text())
for name,remote in freeze['remote_candidate_paths'].items():
    assert sha(remote)==freeze['files'][name]['sha256'],name
os.environ['FT_R067D_ENGINE_SOURCE']=freeze['remote_candidate_paths']['candidate_engine']
commands=[]
for command in (
    ['/data2/FreeToken/venv/bin/python','prepare_runner_packet.py'],
    ['/data2/FreeToken/venv/bin/python','-m','pytest','tests','/data2/FreeToken/development/r067c_retry2_short_tail_v1/tests','-q'],
    ['/data2/FreeToken/venv/bin/python','run_cpu_filedry.py','--out','evidence_cpu_filedry_remote_v1'],
):
    run=subprocess.run(command,cwd=packet,text=True,capture_output=True,check=True,env=os.environ.copy())
    commands.append({'command':command,'stdout':run.stdout,'stderr':run.stderr,'exit_code':run.returncode})
receipt={'schema':'ft_r067d_retry1_linux_cpu_receipt/v1','rid':'E2-R067d-d20-short-tail-retry1','commands':commands,'sha256':{name:sha(packet/name) for name in ('RETRY1_SOURCE_FREEZE.json','R067D_RETRY1_CONFIG_CPU_ONLY.json','R067D_RETRY1_PREPARED_RUNNER_PACKET.json','evidence_cpu_filedry_remote_v1/receipt.json')},'gpu_started':False,'service_started':False,'http_generation':False,'at_utc':time.time()}
with (packet/'LINUX_CPU_RECEIPT_v1.json').open('x') as handle: json.dump(receipt,handle,indent=2);handle.write('\n')
print(json.dumps({'receipt_sha256':sha(packet/'LINUX_CPU_RECEIPT_v1.json'),'tests':commands[1]['stdout'],'filedry':commands[2]['stdout']}))
'''
        _, out, err = client.exec_command('/data2/FreeToken/venv/bin/python -c ' + shlex.quote(code))
        stdout, stderr = out.read().decode(), err.read().decode()
        status = out.channel.recv_exit_status()
        print(stdout)
        if stderr:
            print(stderr)
        assert status == 0, status
        sftp = client.open_sftp()
        for name in ('LINUX_CPU_RECEIPT_v1.json', 'R067D_RETRY1_CONFIG_CPU_ONLY.json', 'R067D_RETRY1_PREPARED_RUNNER_PACKET.json'):
            sftp.get(posixpath.join(REMOTE, name), str(HERE / name))
        remote_evidence = REMOTE + '/evidence_cpu_filedry_remote_v1'
        (HERE / 'evidence_cpu_filedry_remote_v1').mkdir()
        for name in ('receipt.json', 'prepared_child_cpu_mode.json'):
            sftp.get(posixpath.join(remote_evidence, name), str(HERE / 'evidence_cpu_filedry_remote_v1' / name))
        sftp.close()
    finally:
        client.close()


if __name__ == '__main__':
    main()
