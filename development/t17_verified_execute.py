"""Execute the exact CPU-verified T17 stage after the sealed R022 prerequisite."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
PROGRAM = r'''
import hashlib,json,pathlib,subprocess,sys
data=json.load(sys.stdin);stage=pathlib.Path(data['stage']);report=stage/'cpu_validation.json'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if sha(report)!=data['report_sha256'] or json.loads(report.read_text())!=data['report']:raise ValueError('frozen CPU evidence changed')
for name,wanted in data['report']['source_files'].items():
 path=stage/name
 if path.is_symlink() or path.stat().st_mode&0o222 or sha(path)!=wanted:raise ValueError('frozen T17 source changed: '+name)
launcher=stage/'t17_d14_launch.py'
argv=[sys.executable,str(launcher),'--stage',str(stage)]
preflight=subprocess.run(argv,capture_output=True,text=True,timeout=150)
if preflight.returncode:raise RuntimeError(preflight.stderr[-8000:])
checked=json.loads(preflight.stdout.splitlines()[-1])
if checked['state']!='preflight_only':raise ValueError('T17 preflight missing')
if data['launch']:
 launched=subprocess.run([*argv,'--launch'],capture_output=True,text=True,timeout=180)
 if launched.returncode:raise RuntimeError(launched.stderr[-8000:])
 result=json.loads(launched.stdout.splitlines()[-1])
 if result['state']!='launched' or result['source_stage']!=str(stage):raise ValueError('owned launch receipt differs')
else:result=checked
print(json.dumps(result))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launch', action='store_true')
    args = parser.parse_args()
    receipt = json.loads((HERE / 't17_d14_cpu_receipt.json').read_text(encoding='utf-8'))
    for name, wanted in receipt['report']['source_files'].items():
        if name in ('real_inputs.json', 't17_d14_exact_ids.py', 't17_d14_startup.py'):
            continue
        source = HERE / ('t17_d14_stage.py' if name == 'stage_source.py' else name)
        if hashlib.sha256(source.read_bytes()).hexdigest() != wanted:
            raise ValueError('current reviewed source differs from frozen stage: ' + name)
    payload = {**receipt, 'launch': args.launch}
    result = subprocess.run([
        'ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
        '/data2/FreeToken/venv/bin/python', '-c', shlex.quote(PROGRAM),
    ], input=json.dumps(payload).encode(), capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-8000:])
    report = json.loads(result.stdout)
    prefix = 't17_launch_' if args.launch else 't17_preflight_'
    target = HERE / (prefix + report['rid'] + '.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
