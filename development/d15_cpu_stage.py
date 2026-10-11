"""Freeze isolated D15 CPU validation in the FreeToken server environment."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess

PROGRAM = r'''
import base64, hashlib, json, os, pathlib, subprocess, sys
payload = json.loads(sys.stdin.read())
wt = pathlib.Path('/data2/FreeToken/wt/e2d15')
out = pathlib.Path(payload['stage'])
def digest(raw): return hashlib.sha256(raw).hexdigest()
def git(*args): return subprocess.check_output(['git', '-C', str(wt), *args], text=True).strip()
assert git('rev-parse', 'HEAD') == payload['candidate']
assert not git('status', '--porcelain')
tests = ['tests/moe/test_adaptation_boundary.py', 'tests/moe/test_expert_profile.py',
         'tests/moe/test_expert_profile_format.py']
sources = [*tests, 'tests/conftest.py', 'python/freetoken/moe/adaptation_boundary.py',
           'python/freetoken/moe/offload_cache.py', 'python/freetoken/moe/offload_kernels.py',
           'python/freetoken/moe/expert_profile.py', 'python/freetoken/scheduler/scheduler.py']
source_sha = {}
for name in sources:
    path = wt / name
    assert path.is_file() and not path.is_symlink(), name
    raw = path.read_bytes()
    blob = subprocess.check_output(['git', '-C', str(wt), 'show', 'HEAD:' + name])
    assert raw == blob, name
    source_sha[name] = digest(raw)
out.mkdir(exist_ok=False)
(out / 'stage_source.py').write_bytes(base64.b64decode(payload['source']))
env = dict(os.environ, CUDA_VISIBLE_DEVICES='', PYTHONPATH=str(wt / 'python'),
           PYTHONDONTWRITEBYTECODE='1')
python = '/data2/FreeToken/venv/bin/python'
probe = [python, '-c', "import json,pathlib,torch,freetoken; "
         "p=pathlib.Path(freetoken.__file__).resolve(); "
         "assert p.is_relative_to(pathlib.Path('/data2/FreeToken/wt/e2d15/python')); "
         "assert not torch.cuda.is_initialized(); "
         "print(json.dumps({'import':str(p),'cuda_initialized':torch.cuda.is_initialized()}))"]
binding = subprocess.run(probe, cwd=wt, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
(out / 'binding.log').write_bytes(binding.stdout)
argv = [python, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *tests]
result = subprocess.run(argv, cwd=wt, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) if binding.returncode == 0 else binding
(out / 'cpu_tests.log').write_bytes(result.stdout)
report = {'schema': 'ft_d15_cpu_validation/v1', 'candidate_commit': git('rev-parse', 'HEAD'),
          'worktree': str(wt), 'clean': not git('status', '--porcelain'),
          'source_sha256': source_sha, 'stage_source_sha256': digest((out / 'stage_source.py').read_bytes()),
          'argv': argv, 'returncode': result.returncode, 'log_sha256': digest(result.stdout),
          'binding_argv': probe, 'binding_returncode': binding.returncode,
          'binding_log_sha256': digest(binding.stdout),
          'gpu_started': False, 'requests_sent': False,
          'verdict': 'PASS' if binding.returncode == result.returncode == 0 else 'FAIL'}
raw = json.dumps(report, sort_keys=True).encode()
(out / 'cpu_validation.json').write_bytes(raw)
for file in out.iterdir(): file.chmod(0o444)
out.chmod(0o555)
print(json.dumps({'stage': str(out), 'report_sha256': digest(raw),
                 'verdict': report['verdict'], 'output': result.stdout.decode(errors='replace')}))
sys.exit(0 if report['verdict'] == 'PASS' else 1)
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.candidate):
        parser.error("a full committed D15 candidate SHA is required")
    source = Path(__file__).read_bytes()
    identity = hashlib.sha256(source).hexdigest()[:12]
    payload = {"candidate": args.candidate, "source": base64.b64encode(source).decode(),
               "stage": f"/data2/FreeToken/runs/dev_D15/cpu_{args.candidate[:7]}_verified_{identity}"}
    code = "import io,sys\nsys.stdin=io.StringIO(" + repr(json.dumps(payload)) + ")\n" + PROGRAM
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "9", "/data2/FreeToken/venv/bin/python", "-"],
                            input=code, text=True, capture_output=True)
    receipt = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    output = Path(__file__).with_name(f"d15_cpu_{args.candidate[:7]}_{identity}.json")
    if not output.exists():
        output.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
