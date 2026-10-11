"""Preflight and launch the exact CPU-validated schedule T16 declaration."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
PY = str(ROOT/'venv/bin/python')
CASE = 'D14-schedule'
PARENT = 'e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7'
CANDIDATE = 'a9dca443cd07e1f60d1533e0a678935a09d21636'
PINNED = {
    't16_candidate_runner_full_tail.py':'0451e41128b4d1e0c73f892b375b9fbe70b30a9fbac46bc022500bd3c1b6d8b8',
    't16_full_tail_base_runner.py':'379948776d42d5429304afb11dafb0d316e641638caf7cad15fb5b5e6be7340f',
    't16_process_lifecycle.py':'472a80e65c776803978ff668701c9d40d1f0c895d840e12278c1437862dd02d4',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def frozen_regular(path):
    return (not path.is_symlink() and path.is_file()
            and path.stat().st_uid == os.geteuid() and not path.stat().st_mode & 0o222)


def read_stage(stage):
    if (sys.platform != 'linux' or stage.is_symlink() or stage.stat().st_uid != os.geteuid()
            or stage.stat().st_mode & 0o222):
        raise ValueError('owned immutable Linux stage required')
    proof_file = stage/'cpu_validation.json'
    if not frozen_regular(proof_file):
        raise ValueError('CPU receipt must be frozen and owned')
    report = json.loads(proof_file.read_bytes())
    if (report.get('schema') != 'ft_t16_d14_schedule_stage/v1'
            or report.get('gpu_started') is not False or report.get('requests_sent') is not False
            or report.get('verdict') != 'PASS' or type(report.get('passed')) is not int):
        raise ValueError('schedule T16 CPU proof missing')
    from t16_d14_schedule_stage import SOURCE_NAMES, TESTS
    if set(report.get('files', {})) != set(SOURCE_NAMES) or report.get('tests') != list(TESTS):
        raise ValueError('CPU source/suite binding incomplete')
    for name, digest in report['files'].items():
        relative = Path(name)
        path = stage/name
        if (relative.is_absolute() or '..' in relative.parts or not frozen_regular(path)
                or sha(path) != digest):
            raise ValueError('frozen source differs: '+name)
    if any(report['files'].get(name) != digest for name, digest in PINNED.items()):
        raise ValueError('retained common lifecycle differs')
    if sha(__file__) != report['files'].get(Path(__file__).name) or HERE != stage:
        raise ValueError('execute the launcher from its CPU-tested frozen stage')
    for name in ('regression', 'd18_binding'):
        step = report['steps'][name]
        path = stage/(name+'.log')
        if step['returncode'] != 0 or not frozen_regular(path) or sha(path) != step['log_sha256']:
            raise ValueError('CPU log differs: '+name)
    log = (stage/'regression.log').read_text()
    if re.findall(r'(\d+) passed', log) != [str(report['passed'])] or report['passed'] < 50 or re.search(r'\d+ (failed|skipped|error)', log):
        raise ValueError('CPU regression incomplete')
    cpu = json.loads((stage/'d14_schedule_cpu_receipt.json').read_bytes())
    proof = Path(cpu['stage'])/'cpu_validation.json'
    if not frozen_regular(proof) or sha(proof) != cpu['report_sha256']:
        raise ValueError('engine CPU proof differs')
    if json.loads(proof.read_bytes()) != cpu['report']:
        raise ValueError('embedded engine CPU proof differs from the actual frozen report')
    if cpu['report']['candidate_commit'] != CANDIDATE or cpu['report']['verdict'] != 'PASS':
        raise ValueError('engine candidate CPU binding differs')
    for name, digest in cpu['report']['source_files'].items():
        source = ROOT/'wt/e2d14-ordinary-rewind'/name
        if source.is_symlink() or sha(source) != digest:
            raise ValueError('CPU-tested candidate source changed: '+name)
    return report


def preflight(stage):
    report = read_stage(stage)
    life = load(stage/'t16_process_lifecycle.py', 't16_schedule_lifecycle')
    helper = life.verified_module(ROOT/'runs/plan_batches/e2_launch.py',
                                 'a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf', 't16_schedule_atomic')
    number, batch = life.next_round(ROUNDS), helper.next_batch(ROUNDS)
    if not 32 <= number <= 39:
        raise ValueError('D14 reserved round range exhausted; register a new assignment')
    rid = f'E2-R{number:03d}-gate-D14'
    argv = [PY, '-u', str(stage/'t16_d14_schedule_runner.py'), '--case', CASE,
            '--rid', rid, '--batch', str(batch), '--candidate-commit', CANDIDATE]
    subprocess.run(argv, check=True, timeout=180)
    if life.next_round(ROUNDS) != number or helper.next_batch(ROUNDS) != batch or (ROUNDS/rid).exists():
        raise ValueError('ledger changed during source/resource preflight')
    return report, life, helper, argv, rid, batch


def launch(stage):
    report, life, helper, argv, rid, batch = preflight(stage)
    common = load(stage/'t16_candidate_launch_shared.py', 't16_schedule_freezer')
    execution = common.freeze(stage, report)
    argv[2] = str(execution/'t16_d14_schedule_runner.py')
    # reserve_and_launch owns the --run transition in the retained atomic helper.
    reserved = {'schema':'ft_t16_d14_schedule_launch/v1', 'state':'reserved', 'rid':rid, 'batch':batch,
                'card':'D14', 'case':CASE, 'candidate_commit':CANDIDATE, 'parent_commit':PARENT,
                'source_stage':str(stage), 'cpu_stage_sha256':sha(stage/'cpu_validation.json'),
                'source_files':report['files'], 'frozen_runner':argv[2],
                'runner_sha256':report['files']['t16_d14_schedule_runner.py'],
                'launcher_sha256':sha(__file__)}
    return life.reserve_process(helper, batch, rid, argv, ROOT/'runs/dev_D14'/('launch_'+rid+'.json'), reserved)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    if args.launch:
        print(json.dumps(launch(args.stage)), flush=True)
    else:
        data = preflight(args.stage)
        print(json.dumps({'state':'preflight_only','rid':data[4],'batch':data[5]}), flush=True)
