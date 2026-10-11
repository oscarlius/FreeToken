"""Freeze and execute the D16 spawn startup contract without exposing CUDA."""
from pathlib import Path
import base64
import hashlib
import json
import subprocess

HERE = Path(__file__).resolve().parent
NAMES = ('d16_exact_service_startup.py', 't17_d14_runner.py',
         't17_d14_observe.py', 't17_d14_gpu.py', 't17_d14_artifacts.py',
         't16_full_tail_base_runner.py', 't17_owned_launch_protocol.py',
         'd16_service_workloads.py', 'd16_native_process_collection.py',
         'tests/test_d16_service_startup.py', 'tests/test_d16_service_workloads.py',
         'tests/test_d16_native_process_collection.py', 'tests/test_d16_cpu_network_guard.py',
         'tests/test_d16_source_review.py')

PROGRAM = r'''
import base64, hashlib, json, os, pathlib, re, subprocess, sys
payload = json.loads(sys.stdin.read())
stage = pathlib.Path(payload['stage'])
stage.mkdir(parents=True, exist_ok=False)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def write(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream: stream.write(raw)
tree = pathlib.Path('/data2/FreeToken/wt/e2base1-ordinary-rewind')
details = {}
verdict = 'FAIL'
try:
    for name, item in payload['files'].items():
        raw = base64.b64decode(item['bytes'])
        assert sha(raw) == item['sha256'], name
        write(stage / 'sources' / name, raw)
    head = subprocess.check_output(['git', '-C', str(tree), 'rev-parse', 'HEAD'], text=True).strip()
    assert head == payload['commit']
    assert not subprocess.check_output(['git', '-C', str(tree), 'status', '--porcelain'], text=True).strip()
    env = {key:value for key,value in os.environ.items() if not key.startswith('FT_') and key != 'PYTHONPATH'}
    env.update(CUDA_VISIBLE_DEVICES='', PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='2',
               PYTHONPATH=str(stage/'sources')+':'+str(tree/'scripts')+':'+str(tree/'python'))
    setup = subprocess.run([sys.executable, '-c', "import pathlib,t17_d14_runner as r; pathlib.Path('t17_d14_exact_ids.py').write_text(r.EXACT_ID_PATCH)"],
                           cwd=stage/'sources',env=env,capture_output=True)
    write(stage/'setup.log', setup.stdout+setup.stderr)
    assert setup.returncode == 0
    # Verification reads the exact readonly execution bytes. Temporary test
    # artifacts stay in the separate pytest directory created below.
    for source in (stage/'sources').rglob('*'):
        if source.is_file(): source.chmod(0o444)
    expected = stage/'expected.json'
    write(expected,json.dumps([{'uid':uid,'generation_index':generation,'logical_label':'cpu-slot-'+str(uid)}
                               for uid in (0,1) for generation in range(128)]).encode())
    for name in ('dump', 'observations', 'inputs'):
        (stage/name).mkdir()
    env.update(FT_DEV_STATE_DUMP=str(stage/'dump'), FT_T17_OBSERVATIONS=str(stage/'observations'),
               FT_T17_INPUT_RECEIPTS=str(stage/'inputs'), FT_D16_SERVICE_CAPTURE_DIR=str(stage/'capture'),
               FT_D16_EXECUTION_ID='cpu-spawn-'+head[:12], FT_D16_SERVICE_CAPTURE_EXPECTED_JSON=str(expected),
               FT_D16_SERVICE_CAPTURE_MAX_CAPTURES='512', FT_D16_SERVICE_CAPTURE_MAX_BYTES='1073741824')
    argv = [sys.executable,str(stage/'sources/d16_exact_service_startup.py'),'--cpu-startup-probe']
    probe = subprocess.run(argv,cwd=stage,env=env,capture_output=True,timeout=100)
    write(stage/'spawn.log',probe.stdout+probe.stderr)
    assert probe.returncode == 0, (probe.stdout+probe.stderr).decode(errors='replace')[-6000:]
    proof = json.loads(probe.stdout.decode().splitlines()[-1])
    assert proof['worker']['d16_scheduler_worker_installed'] and not proof['worker']['cuda_initialized']
    tested = subprocess.run([sys.executable,'-m','pytest','-q','-p','no:cacheprovider',
                            'tests/test_d16_service_startup.py','tests/test_d16_service_workloads.py',
                            'tests/test_d16_native_process_collection.py','tests/test_d16_cpu_network_guard.py',
                            'tests/test_d16_source_review.py',
                            '--basetemp',str(stage/'pytest_tmp')],
                           cwd=stage/'sources',env=env,capture_output=True,timeout=120)
    log = tested.stdout+tested.stderr
    write(stage/'pytest.log',log)
    text = log.decode(errors='replace')
    assert tested.returncode == 0 and 'skipped' not in text.lower(),text[-3000:]
    passed = re.search(r'(\d+) passed',text)
    assert passed
    details.update(commit=head, startup_argv=argv, worker=proof['worker'], passed=int(passed.group(1)))
    verdict = 'PASS'
except BaseException as error:
    details['error'] = repr(error)
finally:
    # pytest creates convenience "current" symlinks beside the retained real
    # temp directories. Record those aliases, then remove only aliases whose
    # exact targets stay inside this new stage's pytest directory.
    aliases = {}
    temporary = stage/'pytest_tmp'
    for p in stage.rglob('*'):
        if p.is_symlink():
            target = p.resolve()
            if not p.is_relative_to(temporary) or not target.is_relative_to(temporary):
                raise RuntimeError('unexpected symbolic link in CPU stage')
            aliases[p.relative_to(stage).as_posix()] = target.relative_to(stage).as_posix()
            p.unlink()
    if aliases:
        write(stage/'pytest_temporary_aliases.json',json.dumps(aliases,sort_keys=True).encode())
    files = {p.relative_to(stage).as_posix():sha(p.read_bytes()) for p in stage.rglob('*') if p.is_file()}
    report = dict(schema='ft_d16_exact_startup_cpu/v1', verdict=verdict, fixture_only=True,
                  gpu_started=False, model_admitted=False, service_started=False, details=details, files=files)
    raw = json.dumps(report,sort_keys=True).encode()
    write(stage/'cpu_validation.json',raw)
    for p in sorted(stage.rglob('*'),reverse=True):
        assert not p.is_symlink()
        p.chmod(0o444 if p.is_file() else 0o555)
    stage.chmod(0o555)
    print(json.dumps(dict(stage=str(stage),verdict=verdict,report_sha256=sha(raw),details=details)))
sys.exit(0 if verdict == 'PASS' else 1)
'''

def main():
    files = {name: {'bytes':base64.b64encode((HERE/name).read_bytes()).decode(),
                    'sha256':hashlib.sha256((HERE/name).read_bytes()).hexdigest()} for name in NAMES}
    reader_tree = HERE/'e2d16-readers'
    reader_commit = '37d46a078dd458bbe663d8d12dc36bdee6fef600'
    paths = subprocess.check_output(['git','-C',str(reader_tree),'ls-tree','-r','--name-only',
                                     reader_commit,'scripts/equiv_suite'],text=True).splitlines()
    for path in paths:
        if path.endswith('.py'):
            raw = subprocess.check_output(['git','-C',str(reader_tree),'show',reader_commit+':'+path])
            files[path.removeprefix('scripts/')] = {
                'bytes':base64.b64encode(raw).decode(),'sha256':hashlib.sha256(raw).hexdigest()}
    # The actual T20 package retains these local execution bytes (including
    # checkout line endings); test the same digest, not a normalized Git blob.
    native_raw=(reader_tree/'scripts/equiv_suite/native_workloads.py').read_bytes()
    files['equiv_suite/native_workloads.py']={
        'bytes':base64.b64encode(native_raw).decode(),'sha256':hashlib.sha256(native_raw).hexdigest()}
    files['stage_producer.py'] = {'bytes':base64.b64encode(Path(__file__).read_bytes()).decode(),
                                'sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    guard = (HERE/'d16_cpu_sitecustomize.py').read_bytes()
    files['sitecustomize.py'] = {'bytes':base64.b64encode(guard).decode(), 'sha256':hashlib.sha256(guard).hexdigest()}
    fingerprint = hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()[:12]
    payload = dict(files=files,commit='0aa23431e5b800797543bdecbf35a01045131d7d',
                   stage='/data2/FreeToken/runs/dev_D16/exact_startup_cpu_'+fingerprint)
    code = 'import io,sys\nsys.stdin=io.StringIO('+repr(json.dumps(payload))+')\n'+PROGRAM
    result = subprocess.run(['ssh','9','/data2/FreeToken/venv/bin/python','-'],input=code,text=True,capture_output=True)
    receipt = HERE/('d16_exact_startup_cpu_'+fingerprint+'.json')
    with receipt.open('x',encoding='utf-8') as stream:
        json.dump(dict(returncode=result.returncode,stdout=result.stdout,stderr=result.stderr),stream)
    print(result.stdout); print(result.stderr)
    raise SystemExit(result.returncode)

if __name__ == '__main__':
    main()
