"""Launch reviewed T17 bytes only after the exact sealed T16 prerequisite passes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

ROOT=Path('/data2/FreeToken')
ROUNDS=Path('/data2/_shared/runs/ft_rounds')
PY=str(ROOT/'venv/bin/python')


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def preflight(stage):
    if sys.platform!='linux' or stage.is_symlink() or not stage.is_dir() or stage.stat().st_mode & 0o222:
        raise ValueError('Linux owned read-only CPU stage required')
    report_path=stage/'cpu_validation.json';report=json.loads(report_path.read_text())
    if report.get('schema')!='ft_t17_d14_cpu_stage/v1' or report.get('gpu_started') is not False:
        raise ValueError('missing CPU-only T17 report')
    required={'t17_d14_runner.py','t17_d14_gpu.py','t17_d14_launch.py','t17_owned_launch_protocol.py',
              't16_full_tail_base_runner.py','test_t17_d14_runner.py','tests/test_t17_d14_gpu.py',
              't17_d14_observe.py','t17_d14_artifacts.py','test_t17_d14_artifacts.py',
              'stage_source.py','t17_d14_startup.py','t17_d14_exact_ids.py','real_inputs.json'}
    if set(report.get('source_files',{}))!=required:
        raise ValueError('CPU stage source binding incomplete')
    for name,digest in report['source_files'].items():
        path=stage/name
        if (path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222
                or hashlib.sha256(path.read_bytes()).hexdigest()!=digest):
            raise ValueError('frozen CPU source changed: '+name)
    for name in ('helper_tests','gate_tests','raw_tests','byte_comparison','startup_spawn','build_inputs'):
        step=report[name];path=stage/(name+'.log')
        if step.get('returncode')!=0 or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=step.get('log_sha256'):
            raise ValueError('CPU proof log changed: '+name)
    proof=report['spawn_proof']
    if (proof.get('gpu_started') is not False or proof['worker'].get('cuda_initialized') is not False
            or proof['worker'].get('scheduler_wrapper')!='restore_observed'
            or proof['worker'].get('engine_wrapper')!='build_chunks_observed'
            or proof['worker'].get('reply_wrapper')!='reply_observed'
            or proof['worker'].get('input_wrapper')!='process_observed'
            or proof['worker'].get('ids')!=[1469,17,198,248068]
            or set(report['case_lengths'])!={8192,12416,12736,18944}):
        raise ValueError('actual spawn/input CPU proof incomplete')
    sys.path.insert(0,str(stage))
    helper=load(stage/'t17_d14_runner.py','t17_d14_runner')
    helper.verify_t16_lifecycle(stage/'t16_full_tail_base_runner.py',stage/helper.T16_LAUNCH_PROTOCOL)
    prerequisite=helper.t16_prerequisite()
    protocol=load(stage/helper.T16_LAUNCH_PROTOCOL,'ft_t17_owned_launch')
    atomic=protocol.verified_module(ROOT/'runs/plan_batches/e2_launch.py',protocol.HELPER_SHA,'ft_t17_atomic_helper')
    number,batch=protocol.next_round(ROUNDS),atomic.next_batch(ROUNDS)
    rid=f'E2-R{number:03d}-gate-T17'
    argv=[PY,'-u',str(stage/'t17_d14_gpu.py'),'--rid',rid,'--batch',str(batch)]
    subprocess.run(argv,check=True,timeout=120)
    if protocol.next_round(ROUNDS)!=number or atomic.next_batch(ROUNDS)!=batch or (ROUNDS/rid).exists():
        raise ValueError('round/batch ledger changed during T17 preflight')
    return report,helper,protocol,atomic,prerequisite,argv,rid,batch


def launch(stage):
    report,helper,protocol,atomic,prerequisite,argv,rid,batch=preflight(stage)
    parent=Path('/tmp');mode=parent.stat().st_mode
    if parent.is_symlink() or not stat.S_ISDIR(mode) or mode & 0o022 and not mode & stat.S_ISVTX:
        raise ValueError('unsafe execution directory parent')
    execution=Path(tempfile.mkdtemp(prefix='ft-t17-d14-',dir=parent))
    for name,digest in report['source_files'].items():
        data=(stage/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('source changed before T17 freeze')
        path=execution/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(data)
        path.chmod(0o444)
    for directory in sorted((path for path in execution.rglob('*') if path.is_dir()),reverse=True):directory.chmod(0o555)
    execution.chmod(0o555)
    argv[2]=str(execution/'t17_d14_gpu.py');argv.append('--run')
    reserved={'schema':'ft_t17_d14_launch/v1','state':'reserved','rid':rid,'batch':batch,
              'card':'T17','candidate_commit':helper.CANDIDATE,'parent_commit':helper.PARENT,
              'source_stage':str(stage),'frozen_runner':argv[2],
              'runner_sha256':report['source_files']['t17_d14_gpu.py'],
              'cpu_stage_sha256':hashlib.sha256((stage/'cpu_validation.json').read_bytes()).hexdigest(),
              'launcher_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'prerequisite':prerequisite,'source_files':report['source_files']}
    receipt=protocol.reserve_process(atomic,batch,rid,argv,ROOT/'runs/dev_D14'/f'launch_{rid}.json',reserved)
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',type=Path,required=True)
    parser.add_argument('--launch',action='store_true');options=parser.parse_args()
    if options.launch:launch(options.stage)
    else:
        report,_,_,_,prerequisite,argv,rid,batch=preflight(options.stage)
        print(json.dumps({'state':'preflight_only','rid':rid,'batch':batch,'argv':argv,'prerequisite':prerequisite}))
