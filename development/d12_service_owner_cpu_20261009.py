"""Bounded CPU-only evidence harness; run on FT Linux venv with a fresh stage."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

stage = Path(sys.argv[1]).resolve()
assert stage.is_relative_to(Path('/data2/FreeToken/runs/dev_D12'))
assert not (stage / 'receipt.json').exists()
source = Path('/data2/FreeToken/wt/e2d12-short-suffix')
prior = json.loads(Path('/data2/FreeToken/runs/dev_D12/arm_plan_v1_cpu_20261008_2330/pytest-artifacts/test_four_arm_native_file_dry_0/file-dry/launch-plan.json').read_bytes())
bundle = Path('/data2/FreeToken/runs/dev_D12/enabled_inputs_v2_20261008_1715/inputs')
env = {**os.environ, 'CUDA_VISIBLE_DEVICES': '', 'PYTHONDONTWRITEBYTECODE': '1',
    'PYTHONPATH': ':'.join(map(str, (stage, source / 'python', source / 'scripts'))),
    'FT_D12_NATIVE_SOURCE': str(source), 'FT_D12_TEST_INPUT_BUNDLE': str(bundle),
    'FT_D12_D16_RUNTIME': prior['d16'], 'FT_D12_D03_ROOT': prior['d03'],
    'FT_D12_WIRE_SOURCE': '/data2/FreeToken/runs/dev_T21/r049a_v8_cpu_20261008_011210/source',
    'FT_D12_GATE_ROOT': '/data2/FreeToken/runs/dev_T16/d12_default_gate_v2_20261008_1638/d12_default_gate_runtime_v2',
    'FT_D12_ORDINARY_CLIENT': '/data2/FreeToken/runs/dev_D12/capture_pair_v2_cpu_20261008_2230/r046e_t06_ordinary_client_v8.py'}
os.environ.update(env)
sys.path.insert(0, str(stage))
import arm_plan
plan = arm_plan.build_plan(candidate=source, runtime=stage, d16=prior['d16'], d03=prior['d03'], inputs=bundle,
    service_root=stage / 'unused-harness-service-root', execution_prefix='d12-owner-cpu-harness', ports=[18100,18102,18104,18106])
old_receipt = json.loads(Path('/data2/FreeToken/runs/dev_D12/namespace_channel_v2_cpu_20261009_0040/receipt.json').read_bytes())
paths = set(Path(p) for p in plan['source_sha256']) | set(stage.glob('*.py'))
paths |= {Path(p) for p in old_receipt['before_sha256'] if '/namespace_channel_v2_cpu_20261009_0040/' not in p}
previous = Path('/data2/FreeToken/runs/dev_D12/service_owner_v1_cpu_20261009_0100')
if stage != previous:
    paths |= {previous / name for name in ('receipt.json', 'pytest.log', 'cpu-abort.json')}
# Bind actual imports of the same extensions the owner will fingerprint.
spec = importlib.util.spec_from_file_location('d12_verify_native', Path(prior['d16']) / 't16_private_port_base_runner.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
from types import SimpleNamespace
extensions = base.Runner.compiled_extensions(SimpleNamespace(environment=lambda _: {
    **plan['arms']['control']['environment'], 'CUDA_VISIBLE_DEVICES': ''}), source)
paths |= {Path(row['path']).resolve() for row in extensions.values()}
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def snapshot(items): return {str(p): sha(p) for p in sorted(items)}
inputs = set(p for p in bundle.rglob('*') if p.is_file())
before, input_before = snapshot(paths), snapshot(inputs)
command = ['unshare', '--user', '--map-root-user', '--pid', '--fork', '--mount-proc', '--propagation', 'private', '--kill-child=KILL',
    '/data2/FreeToken/venv/bin/python', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--tb=short',
    '--basetemp', 'pytest-artifacts', 'test_arm_plan.py', 'test_service_owner.py']
with (stage / 'pytest.log').open('xb') as log:
    run = subprocess.run(command, cwd=stage, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
after, input_after = snapshot(paths), snapshot(inputs)
head = subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
clean = not subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=no'],text=True).strip()
receipt = {'schema': 'ft_d12_service_owner_cpu/v1', 'time': datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
    'command': command, 'returncode': run.returncode, 'before_sha256': before, 'after_sha256': after, 'sources_unchanged': before == after,
    'input_sha256': input_before, 'inputs_unchanged': input_before == input_after,
    'compiled_extensions': extensions, 'candidate_commit': head, 'candidate_tracked_clean': clean,
    'test_log': str(stage / 'pytest.log'), 'test_log_sha256': sha(stage / 'pytest.log'),
    'artifacts': snapshot((stage / 'pytest-artifacts').rglob('*.json')),
    'service_popen_replaced_by_cpu_http_fixture': True, 'gpu_release_readback_stubbed': True,
    'model_service_started': False, 'model_requests_sent': False, 'weights_loaded': False, 'formal_round_created': False,
    'formal_d07_namespace_integration_verified': False, 'model_correctness_verified': False, 'performance_eligible': False}
with (stage / 'receipt.json').open('x') as output: json.dump(receipt, output, indent=2); output.write('\n')
print((stage / 'pytest.log').read_text())
print(json.dumps({'receipt':str(stage/'receipt.json'), 'sha256':sha(stage/'receipt.json'), 'returncode':run.returncode,
    'stable_files':len(before), 'inputs':len(inputs), 'artifacts':len(receipt['artifacts']), 'sources_unchanged':before==after,
    'inputs_unchanged':input_before==input_after, 'candidate_tracked_clean':clean}))
assert run.returncode == 0 and before == after and input_before == input_after and clean and head == arm_plan.CANDIDATE
