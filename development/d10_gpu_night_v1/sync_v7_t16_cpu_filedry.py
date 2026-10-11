"""Upload only the new T16 v7 controller and seal its CPU FILEdry receipt."""
import hashlib
import importlib.util
import posixpath
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMOTE = '/data2/FreeToken/development/d10_gpu_night_v1'
NAME = 'd10_owned_launch_v7.py'


def main():
    ops_path = HERE.parent / 'r067c_retry2_production_control_20261009' / 'ssh_ops.py'
    spec = importlib.util.spec_from_file_location('ops', ops_path)
    ops = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(ops)
    payload = (HERE / NAME).read_bytes()
    client = ops.connect()
    try:
        sftp = client.open_sftp()
        target = posixpath.join(REMOTE, NAME)
        try:
            with sftp.open(target, 'rb') as stream:
                existing = stream.read()
            if existing != payload:
                raise RuntimeError('remote v7 source already exists with different bytes; preserve history')
        except FileNotFoundError:
            ops.put_new(sftp, target, payload)
        sftp.chmod(target, 0o444)
        sftp.close()
        code = """import hashlib,json,os,subprocess
from pathlib import Path
p=Path('/data2/FreeToken/development/d10_gpu_night_v1')
source=p/%r
assert source.stat().st_mode & 0o777 == 0o444
env=dict(os.environ,CUDA_VISIBLE_DEVICES='')
run=subprocess.run(['/data2/FreeToken/venv/bin/python',str(source),'--filedry','--card','D10'],cwd='/data2/FreeToken',text=True,capture_output=True,env=env,timeout=120)
assert run.returncode==0,(run.stdout,run.stderr)
terminal=p/'evidence_cpu_filedry_v7/terminal.json'
doc=json.loads(terminal.read_text())
assert doc['arms']==8 and doc['calls']==100
actual=[json.loads((terminal.parent/f'arm_{i}.json').read_text())['calls'] for i in range(8)]
assert actual==[12]*4+[13]*4,actual
assert doc['call_derivation']['profiles'][0]['calls']==48 and doc['call_derivation']['profiles'][1]['calls']==52
assert all(doc[k] is False for k in ('gpu_started','service_started','http_started','gpu_lock_taken','formal_round_created'))
assert doc['source_sha256'][%r]==hashlib.sha256(source.read_bytes()).hexdigest()
os.chmod(terminal,0o444)
print(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'receipt_sha256':hashlib.sha256(terminal.read_bytes()).hexdigest(),'calls':doc['calls'],'arm_calls':actual,'terminal':str(terminal)},sort_keys=True))""" % (NAME, NAME)
        output = ops.run(client, code)
        sftp = client.open_sftp()
        sftp.get(posixpath.join(REMOTE, 'evidence_cpu_filedry_v7/terminal.json'),
                 str(HERE / 'LINUX_CPU_FILEDRY_RECEIPT_V7_T16.json'))
        sftp.close()
        print(output)
    finally:
        client.close()


if __name__ == '__main__':
    main()
