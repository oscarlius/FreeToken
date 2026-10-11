"""CPU-only provenance for the committed D08 capture-safe observer candidate."""
from pathlib import Path
import hashlib
import json
import os
import subprocess

ROOT = Path('/data2/FreeToken')
WT = ROOT / 'wt/e2d08-capture-trace'
COMMIT = '76af7584d7595d9cc52dcd60deff3aacdae1d9d6'
ORIGIN = '8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8'
PRIOR = ROOT / 'runs/dev_T16/d08_8bf_native_cpu_v1/v5/provenance_v5.json'
PRIOR_SHA = '14b1d96e58522179e02dc13cf20d76e8d2157c559007b69bf4e97e005dddd9ec'
OUT = ROOT / 'runs/dev_T16/r051a_capture_trace_cpu_v1'
RECEIPT = ROOT / 'runs/dev_T16/r051a_capture_trace_native_provenance_v1.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(WT), *args], text=True).strip()


def save(path, data):
    with path.open('x') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(0o444)


def main():
    assert not Path('/data2/_shared/gpu.lock').exists()
    assert git('rev-parse', 'HEAD') == COMMIT and not git('status', '--porcelain', '--untracked-files=no')
    assert not git('diff', ORIGIN, 'HEAD', '--', 'python/freetoken/kernel/csrc')
    assert sha(PRIOR) == PRIOR_SHA
    prior = json.loads(PRIOR.read_text())
    assert prior['candidate_commit'] == ORIGIN
    OUT.mkdir(exist_ok=False)
    env = {**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'PYTHONDONTWRITEBYTECODE': '1',
           'PYTHONPATH': str(ROOT / 'runs/dev_R046/r046b_section12_source_v4/cpu_guard') + ':' + str(WT / 'python')}
    test = subprocess.run([str(ROOT / 'venv/bin/python'), '-m', 'pytest', '--noconftest', '-q', '-p', 'no:cacheprovider', 'tests/moe/test_hyb_trace_guard.py'], cwd=WT, env=env, capture_output=True, text=True)
    save(OUT / 'pytest.log', test.stdout + test.stderr)
    assert test.returncode == 0 and '17 passed' in test.stdout and 'skipped' not in test.stdout
    code = '''import importlib,json,torch
def deny(*a,**k): raise RuntimeError('CPU import check forbids CUDA initialization')
torch.cuda._lazy_init=deny
names=['freetoken.kernel._cpu_moe','freetoken.kernel._pinned_tensor','freetoken.layers.moe','freetoken.moe.cpu_executor','freetoken.engine.engine','freetoken.engine.graph']
modules={name:importlib.import_module(name).__file__ for name in names}
assert not torch.cuda.is_initialized()
print(json.dumps({'modules':modules,'torch':torch.__version__,'cuda_initialized':False}))
'''
    imported = subprocess.run([str(ROOT / 'venv/bin/python'), '-c', code], cwd=WT, env=env, capture_output=True, text=True)
    save(OUT / 'import.log', imported.stdout + imported.stderr)
    assert imported.returncode == 0, imported.stderr
    info = json.loads(imported.stdout.strip().splitlines()[-1])
    assert all(str(WT / 'python') in path for path in info['modules'].values())
    cpu = WT / 'python/freetoken/kernel/_cpu_moe.cpython-310-x86_64-linux-gnu.so'
    pinned = WT / 'python/freetoken/kernel/_pinned_tensor.cpython-310-x86_64-linux-gnu.so'
    csrc = WT / 'python/freetoken/kernel/csrc/cpu_moe/cpu_moe_ext.cpp'
    assert not cpu.is_symlink() and not pinned.is_symlink()
    assert sha(cpu) == prior['so_sha256'] and sha(pinned) == prior['pinned_sha256'] and sha(csrc) == prior['csrc_sha256']
    value = {'schema': 'ft_d08_capture_trace_cpu_provenance/v1', 'candidate_commit': COMMIT,
             'parent_commit': prior['parent_commit'], 'native_reused_from_commit': ORIGIN,
             'native_source_diff_empty': True, 'prior_native_proof_sha256': PRIOR_SHA,
             'csrc_sha256': sha(csrc), 'so_sha256': sha(cpu), 'so_size': cpu.stat().st_size,
             'pinned_sha256': sha(pinned), 'pinned_size': pinned.stat().st_size,
             'python_pytest': '17 passed', 'python_skip': 0, 'import': info, 'uid': os.geteuid(),
             'cpu_only': True, 'gpu_validation_performed': False,
             'proof_files': {str(path): sha(path) for path in [OUT/'pytest.log', OUT/'import.log', Path(__file__)]}}
    save(RECEIPT, json.dumps(value, indent=2) + '\n')
    print(json.dumps({'receipt': str(RECEIPT), 'sha256': sha(RECEIPT), 'python_pytest': value['python_pytest'], 'cpu_only': True}))


if __name__ == '__main__':
    main()
