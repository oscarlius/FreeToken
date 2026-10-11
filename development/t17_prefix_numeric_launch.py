"""Reserve one source-bound numeric diagnostic after actual Linux CPU proofs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import t17_matched_launch as shared


def checked_stage(stage, expected):
    if sys.platform!='linux' or stage.is_symlink() or stage.stat().st_mode&0o222:
        raise ValueError('read-only Linux stage required')
    path=stage/'cpu_validation.json'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('CPU receipt changed')
    report=json.loads(path.read_bytes())
    if report.get('schema')!='ft_t17_prefix_numeric_cpu/v1' or report.get('gpu_started') is not False:
        raise ValueError('numeric CPU proof required')
    for name,digest in report['source_files'].items():
        path=stage/name
        if path.is_symlink() or path.stat().st_mode&0o222 or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise ValueError('frozen source differs: '+name)
    for name,step in report['steps'].items():
        if step['returncode']!=0 or hashlib.sha256((stage/(name+'.log')).read_bytes()).hexdigest()!=step['log_sha256']:
            raise ValueError('CPU step differs: '+name)
    proof=report['spawn_proof']
    if (proof['gpu_started'] is not False or proof['worker']['cuda_initialized']
            or proof['worker']['numeric_engine_init']!='init_prefix_numeric'
            or proof['worker']['reply_wrapper']!='reply_prefix_numeric'
            or proof['worker']['exact_endpoint_registered'] is not True):
        raise ValueError('normal-spawn installation proof differs')
    return report


def launch(stage, expected):
    report=checked_stage(stage,expected);sys.path.insert(0,str(stage))
    helper=shared.module(stage/'t17_d14_runner.py','t17_d14_runner')
    protocol=shared.module(stage/helper.T16_LAUNCH_PROTOCOL,'ft_numeric_reservation')
    atomic=protocol.verified_module(shared.ROOT/'runs/plan_batches/e2_launch.py',protocol.HELPER_SHA,'ft_numeric_atomic')
    number,batch=protocol.next_round(shared.ROUNDS),atomic.next_batch(shared.ROUNDS)
    rid=f'E2-R{number:03d}-diagnostic-T17'
    argv=[shared.PY,'-u',str(stage/'t17_prefix_numeric_runner.py'),'--rid',rid,'--batch',str(batch)]
    subprocess.run(argv,check=True,timeout=120)
    if protocol.next_round(shared.ROUNDS)!=number or atomic.next_batch(shared.ROUNDS)!=batch or (shared.ROUNDS/rid).exists():
        raise ValueError('round/batch ledger changed; do not reserve')
    execution=Path(tempfile.mkdtemp(prefix='ft-t17-prefix-numeric-',dir='/tmp'))
    for name,digest in report['source_files'].items():
        data=(stage/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('source changed before freeze')
        path=execution/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as stream:stream.write(data)
        path.chmod(0o444)
    for path in sorted((p for p in execution.rglob('*') if p.is_dir()),reverse=True):path.chmod(0o555)
    execution.chmod(0o555);argv[2]=str(execution/'t17_prefix_numeric_runner.py');argv.append('--run')
    reserved={'schema':'ft_t17_prefix_numeric_launch/v1','state':'reserved','rid':rid,'batch':batch,
              'card':'T17-diagnostic','diagnostic_only':True,'candidate_commit':helper.CANDIDATE,
              'source_stage':str(stage),'frozen_runner':argv[2],'cpu_stage_sha256':expected,
              'source_files':report['source_files'],'FT_LM_CHUNK':4096,
              'baseline_acceptance':'not_granted; R023_not_met_retained'}
    receipt=protocol.reserve_process(atomic,batch,rid,argv,shared.ROOT/'runs/dev_D14'/('launch_'+rid+'.json'),reserved)
    print(json.dumps(receipt),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',type=Path,required=True);parser.add_argument('--report-sha256',required=True)
    options=parser.parse_args();launch(options.stage,options.report_sha256)
