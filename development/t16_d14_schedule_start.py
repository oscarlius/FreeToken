"""Launch the reviewed schedule T16 stage once and retain its process receipt."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
STAGE = '/data2/FreeToken/runs/dev_D14/t16_schedule_a9eaf6c40ec8'
CPU_SHA = '458553a9db361c00ff4f1056604fc6c8807c086f27b66a1b363122c1b542736c'


def main():
    transport = json.loads((HERE/'t16_d14_schedule_stage_a9eaf6c40ec8.json').read_bytes())
    result = transport['remote_result']
    if (transport['returncode'] != 0 or result.get('verdict') != 'PASS'
            or result['stage'] != STAGE or result['receipt_sha256'] != CPU_SHA):
        raise ValueError('exact successful CPU stage required')
    spec = importlib.util.spec_from_file_location('schedule_source_manifest', HERE/'t16_d14_schedule_stage.py')
    controller = importlib.util.module_from_spec(spec); spec.loader.exec_module(controller)
    _, files = controller.source_manifest()
    if {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()} != transport['source_sha256']:
        raise ValueError('local CPU-tested source changed')
    review = json.loads((HERE/'t16_d14_schedule_a9eaf6c40ec8_independent_review.json').read_bytes())
    if review.get('scope') != 'CPU_PRELAUNCH' or review.get('verdict') != 'PASS' or review.get('report_sha256') != CPU_SHA:
        raise ValueError('independent exact-stage review missing')
    if list(HERE.glob('t16_d14_schedule_E2-R*-gate-D14_launch_receipt.json')):
        raise ValueError('schedule launch already recorded; inspect the owned process')
    run = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                          '/data2/FreeToken/venv/bin/python', STAGE+'/t16_d14_schedule_launch.py',
                          '--stage', STAGE, '--launch'], capture_output=True, timeout=220)
    stdout = run.stdout.decode(errors='replace')
    with (HERE/'t16_d14_schedule_a9eaf6c40ec8_launch_transport.json').open('x', encoding='utf-8') as stream:
        json.dump({'cpu_sha256': CPU_SHA, 'returncode': run.returncode,
                   'stdout': stdout, 'stderr': run.stderr.decode(errors='replace')}, stream, indent=2)
        stream.write('\n')
    if run.returncode:
        raise RuntimeError('launch failed; inspect the retained transport and exact server receipt')
    receipt = json.loads(stdout.splitlines()[-1])
    if (receipt.get('state') != 'launched' or type(receipt.get('batch_pid')) is not int
            or receipt.get('source_stage') != STAGE or receipt.get('cpu_stage_sha256') != CPU_SHA):
        raise ValueError('response does not bind the launched process to the reviewed stage')
    with (HERE/('t16_d14_schedule_'+receipt['rid']+'_launch_receipt.json')).open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2); stream.write('\n')
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__': main()
