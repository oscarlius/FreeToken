"""Transport the frozen T17 launcher invocation; default remains preflight-only."""
import argparse
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
STAGE = '/data2/FreeToken/runs/dev_D16/continuation_cpu_a914a2a85e0d'
REVIEW = '/data2/FreeToken/runs/dev_D16/continuation_a914a2a85e0d_independent_review.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--stage', default=STAGE)
    parser.add_argument('--review', default=REVIEW)
    parser.add_argument('--rid', choices=('E2-R033', 'E2-R034','E2-R034a'), default='E2-R033')
    args = parser.parse_args()
    prefix = 't17_' + args.rid.removeprefix('E2-').lower() + '_dispatch_'
    target = HERE / (prefix + ('launch.json' if args.launch else 'preflight.json'))
    if target.exists():
        raise FileExistsError('dispatch receipt already exists; inspect it before another invocation')
    program = """import os,runpy,sys
stage=%r
os.environ.update(FT_T17_BATCH_TEMPLATE=stage+'/batchNN_T17.sh',
 FT_T17_INPUTS='/data2/FreeToken/runs/dev_D16/inputs_cpu_fd6362813705/real_inputs.json',
 FT_T17_CLOSURE_BINDING='/data2/FreeToken/runs/dev_D14/r032_closure_binding_20261005.json',
 PYTHONDONTWRITEBYTECODE='1')
sys.path.insert(0,stage)
import t17_owned_launch_protocol as protocol
sys.argv=['t17_continuation_launch.py','--stage',stage,'--review',%r]+%r+%r
runpy.run_path(stage+'/t17_continuation_launch.py',run_name='__main__')
""" % (args.stage, args.review, ['--rid',args.rid] if args.rid=='E2-R034a' else [], ['--launch'] if args.launch else [])
    completed = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
                                '9', '/data2/FreeToken/venv/bin/python', '-'],
                               input=program.encode(), capture_output=True)
    receipt = {'returncode': completed.returncode, 'stdout': completed.stdout.decode(),
               'stderr': completed.stderr.decode(), 'stage': args.stage, 'launch_requested': args.launch}
    with target.open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, indent=2); stream.write('\n')
    print(json.dumps(receipt))
    raise SystemExit(completed.returncode)


if __name__ == '__main__':
    main()
