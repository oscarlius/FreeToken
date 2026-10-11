"""Reserve a gemm diagnostic only after its exact Linux CPU stage passes."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
PY = str(ROOT / 'venv/bin/python')


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def checked_stage(stage, expected):
    if sys.platform != 'linux' or stage.is_symlink() or stage.stat().st_mode & 0o222:
        raise ValueError('owned read-only Linux stage required')
    path = stage / 'cpu_validation.json'
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('exact CPU report changed')
    report = json.loads(path.read_text())
    if report.get('schema') != 'ft_t17_gemm_cpu/v1' or report.get('gpu_started') is not False:
        raise ValueError('actual CPU-only report required')
    for name, digest in report['source_files'].items():
        path = stage / name
        if path.is_symlink() or path.stat().st_mode & 0o222 or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('frozen source changed: ' + name)
    for name, step in report['steps'].items():
        path = stage / (name + '.log')
        if step.get('returncode') != 0 or hashlib.sha256(path.read_bytes()).hexdigest() != step['log_sha256']:
            raise ValueError('actual Linux CPU proof changed: ' + name)
    proof = report['preparation']
    plan = proof['plan']
    if (proof.get('gpu_started') is not False or proof.get('schema') != 'ft_t17_gemm_preparation/v1'
            or plan.get('operator') != 'gdn' or plan.get('source_round', {}).get('round_sha256') != 'fc683f998652b3db5682aa9912d7eed469d257e0ea6e11387c1d91be6a6f798c'
            or report['source_files'].get('plan.json') != hashlib.sha256((stage / 'plan.json').read_bytes()).hexdigest()):
        raise ValueError('actual CPU-only GDN preparation proof differs')
    return report


def launch(stage, expected):
    report = checked_stage(stage, expected)
    sys.path.insert(0, str(stage))
    helper = module(stage / 't17_d14_runner.py', 't17_d14_runner')
    protocol = module(stage / helper.T16_LAUNCH_PROTOCOL, 'ft_gemm_reservation')
    atomic = protocol.verified_module(ROOT / 'runs/plan_batches/e2_launch.py', protocol.HELPER_SHA, 'ft_gemm_atomic')
    number, batch = protocol.next_round(ROUNDS), atomic.next_batch(ROUNDS)
    rid = f'E2-R{number:03d}-diagnostic-T17'
    argv = [PY, '-u', str(stage / 't17_gemm_runner.py'), '--rid', rid, '--batch', str(batch)]
    subprocess.run(argv, check=True, timeout=120)
    if protocol.next_round(ROUNDS) != number or atomic.next_batch(ROUNDS) != batch or (ROUNDS / rid).exists():
        raise ValueError('round/batch ledger changed during resource preflight')
    execution = Path(tempfile.mkdtemp(prefix='ft-t17-gemm-', dir='/tmp'))
    for name, digest in report['source_files'].items():
        data = (stage / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('source changed before immutable freeze')
        path = execution / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
        path.chmod(0o444)
    for path in sorted((p for p in execution.rglob('*') if p.is_dir()), reverse=True):
        path.chmod(0o555)
    execution.chmod(0o555)
    argv[2] = str(execution / 't17_gemm_runner.py')
    argv.append('--run')
    reserved = {'schema': 'ft_t17_gemm_launch/v1', 'state': 'reserved', 'rid': rid, 'batch': batch,
                'card': 'T17-diagnostic', 'diagnostic_only': True, 'candidate_commit': helper.CANDIDATE,
                'source_stage': str(stage), 'frozen_runner': argv[2], 'cpu_stage_sha256': expected,
                'source_files': report['source_files'], 'operator_only': True, 'operator': 'gdn',
                'baseline_acceptance': 'not_granted; R023_not_met_retained'}
    receipt = protocol.reserve_process(atomic, batch, rid, argv, ROOT / 'runs/dev_D14' / ('launch_' + rid + '.json'), reserved)
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--report-sha256', required=True)
    options = parser.parse_args()
    launch(options.stage, options.report_sha256)
