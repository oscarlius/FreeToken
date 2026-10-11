"""CPU-only root admission packaging for the 2026-10-11 hybrid verification window.

Runs on the server with the FreeToken venv python. Starts no service, stops nothing,
touches no GPU (CUDA_VISIBLE_DEVICES is emptied for every child). Steps, in order:
freeze the current production owner read-back (must be the -07 approval, argv shape
checked), cross-check the stage-1 payload manifest (production token counts must
match), run the directory's full CPU pytest, dry-run both final service argvs through
the release-e2 parser, then write and seal ROOT_ADMISSION.json (mode 0444).

    cd /data2/FreeToken/development/kimi_phase2_20261011/hybrid_verify
    CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 \
    /data2/FreeToken/venv/bin/python -B prepare_root_admission.py
"""
from pathlib import Path
import datetime
import hashlib
import json
import os
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
VENV_PY = '/data2/FreeToken/venv/bin/python'
EXPECTED_COMMIT = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
EXPECTED_APPROVAL = 'RESTORE481-MORNING-20261011-07'
BASELINE_PYTHONPATH = '/data2/FreeToken/wt/release-e2/python'
CONTROLLER_FILES = ('gpu_window.py', 'hybrid_service.py', 'window_measure.py', 'warmup_client.py')
X_SHA = 'f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162'
OLD_RUNNER = ROOT / 'development/d10_reanalysis_20261010/closed_loop_20261010/allxy_runner.py'
# output_compare.py is a byte-identical vendor copy of
# development/d08_hybrid_review_20261011/output_compare.py (the pre-registered J4
# comparison method), vendored because that review directory exists only on the
# office machine, not on the server. The provenance SHA below is the source file's.
OUTPUT_COMPARE = HERE / 'output_compare.py'
OUTPUT_COMPARE_PROVENANCE_SHA = '8968ca4d2dcb1a5614fc799cb7653984a0a1322810711e6dd8663b3275d36870'
QUALITY60_SCRIPT = ROOT / 'evaluation/quality60/phase3_sdk.py'
QUALITY60_PYTHON = '/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python'
QUALITY60_PROMPTS = '/data2/_shared/test_prompts_60.json'
WARMUP_ADAPTER = ROOT / 'development/r065_d16_discriminate_v1/sdk_adapter.py'
WARMUP_INPUTS = ROOT / 'development/r065_d16_discriminate_v1/inputs.json'
WARMUP_ADAPTER_SHA = '7870d1adab240ea1b0ee05e8035b13d77cd9b414597405a1987d60fea68412cd'
WARMUP_INPUTS_SHA = '18cce7cde13420f793cffd55ff8ce6e542f99b21bb193038912421854156539e'

HOST = '127.0.0.1'
PORT = 8123
WINDOW_LIMIT_SECONDS = 9000
OUTPUT_ROOT = '/data2/FreeToken/runs/dev_hybrid_verify_20261011/window01'

DRYRUN_SNIPPET = (
    'import sys;'
    'from freetoken.server.args import parse_args;'
    'parsed, run_shell = parse_args(sys.argv[1:], prog="ft serve");'
    'print("PARSE_OK", type(parsed).__name__)'
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def cpu_env(pythonpath=None):
    env = {'PATH': os.environ.get('PATH', ''), 'HOME': os.environ.get('HOME', '/root'),
           'CUDA_VISIBLE_DEVICES': '', 'PYTHONDONTWRITEBYTECODE': '1'}
    if pythonpath:
        env['PYTHONPATH'] = pythonpath
    return env


def freeze_baseline_owner():
    active = json.loads((ROOT / 'run/production.active.json').read_text())
    if active.get('approval_id') != EXPECTED_APPROVAL:
        raise RuntimeError(f"production approval is {active.get('approval_id')}, expected {EXPECTED_APPROVAL}")
    if active.get('commit') != EXPECTED_COMMIT:
        raise RuntimeError('production commit differs from 481d3a7')
    argv = active.get('argv') or []
    if argv[:3] != ['taskset', '-c', '1,3-47'] or '--moe-strategy' not in argv:
        raise RuntimeError('production argv shape unexpected')
    if argv[argv.index('--moe-strategy') + 1] != 'offload':
        raise RuntimeError('production is not running offload')
    target = HERE / 'BASELINE_OWNER_FREEZE.json'
    data = json.dumps(active, indent=2) + '\n'
    if not target.exists() or target.read_text() != data:
        with target.open('w', encoding='utf8') as handle:
            handle.write(data)
    return active


def load_payload_manifest():
    manifest = json.loads((HERE / 'payloads/PAYLOADS.json').read_text())
    for name in ('LC1', 'LC2_lane1'):
        entry = manifest['payloads'][name]
        if not entry.get('production_count_match'):
            raise RuntimeError(f'{name} rendered token count does not match production')
    if manifest['payloads']['X']['sha256'] != X_SHA:
        raise RuntimeError('X manifest pin differs')
    return manifest


def run_pytest():
    completed = subprocess.run([VENV_PY, '-B', '-m', 'pytest', str(HERE), '-q'],
                               env=cpu_env(), capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError('CPU pytest failed:\n' + completed.stdout + completed.stderr)
    return {'argv': completed.args, 'stdout': completed.stdout, 'stderr': completed.stderr,
            'exit_code': completed.returncode}


def parser_dry_run(argv):
    args = argv[argv.index('serve') + 1:]
    completed = subprocess.run([VENV_PY, '-B', '-c', DRYRUN_SNIPPET, *args],
                               env=cpu_env(BASELINE_PYTHONPATH), capture_output=True, text=True)
    if completed.returncode or 'PARSE_OK' not in completed.stdout:
        raise RuntimeError('release-e2 parser rejected an approved argv:\n'
                           + completed.stdout + completed.stderr)
    return {'argv_tail': args, 'stdout': completed.stdout.strip(), 'exit_code': completed.returncode}


def main():
    baseline = freeze_baseline_owner()
    manifest = load_payload_manifest()
    sys.path.insert(0, str(HERE))
    from hybrid_service import expected_argv
    offload_argv = expected_argv(baseline['argv'], 'offload', HOST, PORT)
    hybrid_argv = expected_argv(baseline['argv'], 'hybrid', HOST, PORT)
    pytest_receipt = run_pytest()
    dry_runs = {'offload': parser_dry_run(offload_argv), 'hybrid': parser_dry_run(hybrid_argv)}

    inputs = {
        'X': {'path': str(ROOT / 'development/d10_reanalysis_20261010/closed_loop_20261010/inputs_X.jsonl'),
              'sha256': X_SHA},
        'LC1': {'path': str(HERE / 'payloads/inputs_LC1.jsonl'),
                'sha256': manifest['payloads']['LC1']['aiperf_input_sha256']},
    }
    lc2_status = 'excluded_pending_main_session_adjudication'
    lane2 = manifest['payloads']['LC2_lane2']
    if lane2.get('feasible') and lane2.get('aiperf_input'):
        inputs['LC2'] = {'path': str(HERE / 'payloads/inputs_LC2.jsonl'),
                         'sha256': lane2['aiperf_input_sha256']}
        lc2_status = 'frozen_per_runbook_rule'

    full_matrix = [['x_single', 2], ['x_two', 2], ['lc1_single', 2]]
    if 'LC2' in inputs:
        full_matrix.append(['lc2_two', 2])
    services = {
        'O1': {'mode': 'offload', 'warmup': True, 'matrix': [list(x) for x in full_matrix], 'quality60': True},
        'H1': {'mode': 'hybrid', 'warmup': True, 'matrix': [list(x) for x in full_matrix], 'quality60': True},
        'H2': {'mode': 'hybrid', 'warmup': False, 'matrix': [['x_single', 1]], 'quality60': False},
        'O2': {'mode': 'offload', 'warmup': True, 'matrix': [list(x) for x in full_matrix], 'quality60': False},
    }
    for path, pinned in ((WARMUP_ADAPTER, WARMUP_ADAPTER_SHA), (WARMUP_INPUTS, WARMUP_INPUTS_SHA),
                         (OUTPUT_COMPARE, OUTPUT_COMPARE_PROVENANCE_SHA)):
        if sha(path) != pinned:
            raise RuntimeError(f'source pin differs: {path}')

    doc = {
        'schema': 'ft_hybrid_verify_20261011/v1',
        'admit': True,
        'recorded_at': now(),
        'runbook_ref': 'plan/KIMI_RUNBOOK_PHASE2_20261011.md section 2.4 (stage-2 entry pending main-session review)',
        'baseline_owner': baseline,
        'baseline_owner_freeze_sha256': sha(HERE / 'BASELINE_OWNER_FREEZE.json'),
        'commit': EXPECTED_COMMIT,
        'baseline_pythonpath': BASELINE_PYTHONPATH,
        'output_root': OUTPUT_ROOT,
        'window_limit_seconds': WINDOW_LIMIT_SECONDS,
        'host': HOST,
        'port': PORT,
        'services': services,
        'service_order': ['O1', 'H1', 'H2', 'O2'],
        'offload_argv': offload_argv,
        'hybrid_argv': hybrid_argv,
        'inputs': inputs,
        'lc2_status': lc2_status,
        'max_fetch': -1,
        'max_fetch_semantics': 'per-layer/step PCIe fetch cap; -1 auto profile fraction, else fixed cap1; remainder executes on CPU',
        'warmup_adapter_path': str(WARMUP_ADAPTER),
        'warmup_adapter_sha256': WARMUP_ADAPTER_SHA,
        'warmup_inputs_path': str(WARMUP_INPUTS),
        'warmup_inputs_sha256': WARMUP_INPUTS_SHA,
        'quality60': {'python': QUALITY60_PYTHON, 'script': str(QUALITY60_SCRIPT),
                      'script_sha256': sha(QUALITY60_SCRIPT), 'prompts': QUALITY60_PROMPTS,
                      'prompts_sha256': sha(QUALITY60_PROMPTS), 'model': 'Qwen3.8-Flash-Next-NVFP4'},
        'controller_source_pins': {str(HERE / name): sha(HERE / name) for name in CONTROLLER_FILES},
        'measure_sha256': sha(HERE / 'window_measure.py'),
        'hybrid_controller_sha256': sha(HERE / 'hybrid_service.py'),
        'old_runner_path': str(OLD_RUNNER),
        'old_runner_sha256': sha(OLD_RUNNER),
        'output_compare_path': str(OUTPUT_COMPARE),
        'output_compare_sha256': sha(OUTPUT_COMPARE),
        'payload_manifest_sha256': sha(HERE / 'payloads/PAYLOADS.json'),
        'push_approved': False,
    }
    admission = HERE / 'ROOT_ADMISSION.json'
    with admission.open('x', encoding='utf8') as handle:
        json.dump(doc, handle, indent=2)
        handle.write('\n')
    admission.chmod(0o444)
    receipt = {'at': now(), 'pytest': pytest_receipt, 'parser_dry_runs': dry_runs,
               'admission_sha256': sha(admission), 'lc2_status': lc2_status,
               'baseline_owner_freeze_sha256': doc['baseline_owner_freeze_sha256'],
               'controller_source_pins': doc['controller_source_pins']}
    with (HERE / 'ADMISSION_BUILD.json').open('x', encoding='utf8') as handle:
        json.dump(receipt, handle, indent=2)
        handle.write('\n')
    print(json.dumps({'admission_sha256': receipt['admission_sha256'], 'lc2_status': lc2_status,
                      'pytest': pytest_receipt['stdout'].strip().splitlines()[-1]}, indent=2))


if __name__ == '__main__':
    main()
