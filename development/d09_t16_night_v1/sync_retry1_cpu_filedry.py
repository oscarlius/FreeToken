"""Synchronize the D09 retry1 tooling and seal its Linux CPU FILEdry receipt."""
import importlib.util
import posixpath
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMOTE = '/data2/FreeToken/development/d09_t16_night_v1'
NAMES = ('d09_t16_full_runner_retry1.py', 'd09_owned_launch_retry1.py')


def main():
    ops_path = HERE.parent / 'r067c_retry2_production_control_20261009' / 'ssh_ops.py'
    spec = importlib.util.spec_from_file_location('ops', ops_path)
    ops = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(ops)
    client = ops.connect()
    try:
        sftp = client.open_sftp()
        for name in NAMES:
            target = posixpath.join(REMOTE, name)
            payload = (HERE / name).read_bytes()
            try:
                with sftp.open(target, 'rb') as stream:
                    existing = stream.read()
                if existing != payload:
                    sftp.chmod(target, 0o644)
                    with sftp.open(target, 'wb') as stream:
                        stream.write(payload)
            except FileNotFoundError:
                ops.put_new(sftp, target, payload)
            sftp.chmod(target, 0o444)
        sftp.close()
        code = """import hashlib,json,os,subprocess
from pathlib import Path
p=Path('/data2/FreeToken/development/d09_t16_night_v1')
names=%r
assert all((p/n).stat().st_mode & 0o777 == 0o444 for n in names)
env=dict(os.environ,CUDA_VISIBLE_DEVICES='')
test=subprocess.run(['/data2/FreeToken/venv/bin/python',str(p/'d09_t16_full_runner_retry1.py'),'--self-test'],cwd='/data2/FreeToken',text=True,capture_output=True,env=env,timeout=120)
assert test.returncode==0,(test.stdout,test.stderr)
terminal=p/'evidence_cpu_filedry_retry1/terminal.json'
if not terminal.exists():
 run=subprocess.run(['/data2/FreeToken/venv/bin/python',str(p/'d09_owned_launch_retry1.py'),'--filedry','--card','D09'],cwd='/data2/FreeToken',text=True,capture_output=True,env=env,timeout=120)
 assert run.returncode==0,(run.stdout,run.stderr)
doc=json.loads(terminal.read_text())
assert doc['arms']==8 and doc['calls']==96 and all(doc[k] is False for k in ('gpu_started','service_started','http_started','gpu_lock_taken','formal_round_created'))
assert all(doc['source_sha256'].get(n)==hashlib.sha256((p/n).read_bytes()).hexdigest() for n in names)
os.chmod(terminal,0o444)
print(json.dumps({'sha256':hashlib.sha256(terminal.read_bytes()).hexdigest(),'selftest':test.stdout.strip(),'terminal':str(terminal)},sort_keys=True))""" % (NAMES,)
        output = ops.run(client, code)
        sftp = client.open_sftp()
        sftp.get(posixpath.join(REMOTE, 'evidence_cpu_filedry_retry1/terminal.json'),
                 str(HERE / 'LINUX_CPU_FILEDRY_RECEIPT_RETRY1.json'))
        sftp.close()
        print(output)
    finally:
        client.close()


if __name__ == '__main__':
    main()

