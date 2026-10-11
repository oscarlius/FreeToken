"""Root operator transport; credentials remain in the existing shared config."""
import importlib.util
from pathlib import Path
import shlex
import paramiko

HERE = Path(__file__).resolve().parent

def connect():
    spec = importlib.util.spec_from_file_location('ssh_config', HERE.parents[2] / '_shared/ssh_upload.py')
    config = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(config)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(config.REMOTE_HOST, username=config.REMOTE_USER, password=config.REMOTE_PASS)
    return client

def run(client, code):
    _, out, err = client.exec_command('/data2/FreeToken/venv/bin/python -c ' + shlex.quote(code))
    output, error = out.read().decode(), err.read().decode()
    status = out.channel.recv_exit_status()
    print(output)
    if error:
        print(error)
    assert status == 0, status
    return output

def put_new(sftp, path, data):
    if isinstance(data, str):
        data = data.encode()
    with sftp.open(path, 'wx') as handle:
        handle.write(data)
