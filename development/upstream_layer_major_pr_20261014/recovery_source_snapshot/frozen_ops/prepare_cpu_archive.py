"""Archive CPU preparation via existing SSH configuration; never starts a server."""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import sys

import paramiko

HERE = Path(__file__).resolve().parent
FT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from release_config import environment_projection


def main():
    spec = importlib.util.spec_from_file_location('existing_ssh', FT.parent / '_shared/ssh_upload.py')
    settings = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settings)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('172.16.108.9', username=settings.REMOTE_USER,
                   password=settings.REMOTE_PASS, timeout=20)
    sftp = client.open_sftp()
    remote = '/data2/FreeToken/runs/dev_release/release_e2_ops_v5_20261009_review'
    local_out = HERE / 'evidence_v5'
    local_out.mkdir(exist_ok=False)

    def mkdir(path):
        try:
            sftp.stat(path)
        except FileNotFoundError:
            mkdir(str(Path(path).parent).replace('\\', '/'))
            sftp.mkdir(path)

    def read(path):
        with sftp.open(path, 'rb') as handle:
            return handle.read()

    def save(name, data):
        if isinstance(data, str):
            data = data.encode()
        target = remote + '/evidence/' + name
        with sftp.open(target, 'wx') as handle:
            handle.write(data)
        sftp.chmod(target, 0o444)
        (local_out / name).write_bytes(data)

    try:
        try:
            sftp.stat(remote)
        except FileNotFoundError:
            mkdir(remote)
        else:
            raise RuntimeError('CPU archive already exists; never overwrite')
        mkdir(remote + '/evidence')
        sources = []
        for pattern in ('release_e2_ops_v2/*.py', 'release_e2_ops_v2/binary_manifest.json', 'd07_g3g4_prepare.py',
                        'r066_d16_discriminate_v2/sdk_adapter.py',
                        'r066b_canary_v2/sdk_adapter.py',
                        'r065_d16_discriminate_v1/sdk_adapter.py',
                        'r065_d16_discriminate_v1/inputs.json'):
            sources.extend(FT.joinpath('development').glob(pattern))
        sources.append(FT / 'evaluation/d16_api/sdk_completions.py')
        manifest = {}
        for path in sources:
            relative = path.relative_to(FT).as_posix()
            target = remote + '/source/' + relative
            mkdir(target.rsplit('/', 1)[0])
            blob = path.read_bytes()
            with sftp.open(target, 'wx') as handle:
                handle.write(blob)
            sftp.chmod(target, 0o444)
            manifest[relative] = hashlib.sha256(blob).hexdigest()
        save('source_manifest.json', json.dumps(manifest, indent=2) + '\n')
        r056 = '/data2/_shared/runs/ft_rounds/E2-R056'
        original = read(r056 + '/production/SERVE_CMD.txt')
        listed = read(r056 + '/MANIFEST.sha256').decode()
        assert hashlib.sha256(original).hexdigest() in listed
        save('R056_SERVE_CMD.txt', original)
        original_env_bytes = read(r056 + '/production/ENV.json')
        assert hashlib.sha256(original_env_bytes).hexdigest() in listed
        original_env = environment_projection(json.loads(original_env_bytes))
        save('R056_environment_projection.json', json.dumps(original_env, indent=2) + '\n')
        for mode in ('release', 'rollback'):
            plan_command = ('cd ' + shlex.quote(remote + '/source/development/release_e2_ops_v2') +
                ' && PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python release_control.py --plan --mode ' + mode)
            _, stdout, stderr = client.exec_command(plan_command, timeout=30)
            plan = json.loads(stdout.read())
            assert stdout.channel.recv_exit_status() == 0, stderr.read().decode()
            argv = plan['argv']
            assert not plan['starts_service'] and not any('\\' in item for item in argv)
            save(mode + '_argv.json', json.dumps(argv, indent=2) + '\n')
            command = shlex.join(argv) + '\n'
            save(mode + '_SERVE_CMD.txt', command)
            save(mode + '_vs_R056.diff', ''.join(difflib.unified_diff(
                original.decode().splitlines(True), command.splitlines(True),
                fromfile='sealed_R056/production/SERVE_CMD.txt', tofile=mode + '/SERVE_CMD.txt')))
            save(mode + '_environment.json', json.dumps(plan['environment'], indent=2) + '\n')
            save(mode + '_environment_vs_R056.diff', ''.join(difflib.unified_diff(
                (json.dumps(original_env, indent=2) + '\n').splitlines(True),
                (json.dumps(plan['environment'], indent=2) + '\n').splitlines(True),
                fromfile='R056/operational_environment', tofile=mode + '/operational_environment')))
        r061 = '/data2/_shared/runs/ft_rounds/E2-R061f-OOM'
        runtime = sftp.listdir(r061 + '/runtime')
        r061_result = json.loads(read(r061 + '/result.json'))
        assert r061_result['candidate_commit'] == '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
        assert r061_result['queue_timeout_seconds'] == 900
        defaults = {}
        for candidate in ('/data2/FreeToken/wt/release-e2/python/freetoken/server/api_server.py',
                          '/data2/FreeToken/wt/e2oom-protocol-restart/python/freetoken/server/api_server.py'):
            body = read(candidate).decode()
            defaults[candidate] = [line for line in body.splitlines()
                if line.startswith('RESTART_READY_TIMEOUT_S =') or line.startswith('RESTART_QUEUE_MAX =')]
        save('oom_defaults_readback.json', json.dumps({
            'candidate_defaults': defaults, 'R061f_runtime_entries': runtime,
            'R061f_result_candidate_commit': r061_result['candidate_commit'],
            'R061f_queue_timeout_seconds': r061_result['queue_timeout_seconds'],
            'R061f_single_chat_injection': True,
            'service_started': False}, indent=2) + '\n')
        command = ('cd ' + shlex.quote(remote + '/source/development/release_e2_ops_v2') +
            ' && CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 /data2/FreeToken/venv/bin/python -m pytest -q -p no:cacheprovider test_cpu.py test_worktree_checks.py')
        _, stdout, stderr = client.exec_command(command, timeout=90)
        output = stdout.read() + stderr.read()
        code = stdout.channel.recv_exit_status()
        save('CPU_pytest.txt', output)
        if code:
            raise RuntimeError('Remote CPU tests failed; inspect archived output')
        receipt = {'schema': 'ft_release_ops_cpu_archive/v1', 'remote': remote,
            'CPU_exit_code': code, 'source_files': len(manifest), 'GPU_started': False,
            'service_started': False, 'production_smoke_run': False,
            'CPU_skipped': 0, 'explicit_smoke_missing_env_test': 'fails, never skips',
            'R056_ENV_sha256': hashlib.sha256(original_env_bytes).hexdigest(),
            'R056_SERVE_CMD_sha256': hashlib.sha256(original).hexdigest()}
        save('receipt.json', json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt))
        print(output.decode())
    finally:
        sftp.close()
        client.close()


if __name__ == '__main__':
    main()
