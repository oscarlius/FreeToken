"""Resume the exact frozen R032 closer, retaining its outer binding receipt."""
import json
from pathlib import Path
import subprocess

PROGRAM = r'''
import hashlib,json,sys
from pathlib import Path
s=Path('/data2/FreeToken/runs/dev_D14/t16_r032_close_e0fb95ce0f87')
sys.path.insert(0,str(s))
import t16_r032_close as c
result=c.close(execute=True,closure_stage=s,audit_receipt=Path('/data2/_shared/runs/ft_rounds/E2-R032-gate-D14/review_batch60.json'))
d=c.ROUNDS/c.RID
binding={
 **result,'round':c.RID,'parent_commit':'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42',
 'candidate_commit':'e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7',
 'gate_sha256':c.sha(d/'gate_batch60.json'),'review_sha256':c.sha(d/'review_batch60.json')}
p=Path('/data2/FreeToken/runs/dev_D14/r032_closure_binding_20261005.json')
with p.open('x') as f:json.dump(binding,f,indent=2);f.write('\n')
p.chmod(0o444)
print(json.dumps({'closure_binding':str(p),'closure_binding_sha256':c.sha(p),**binding}))
'''

if __name__ == '__main__':
    run = subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10','9',
                          'env','CUDA_VISIBLE_DEVICES=','/data2/FreeToken/venv/bin/python','-'],
                         input=PROGRAM.encode(),capture_output=True)
    report={'returncode':run.returncode,'stdout':run.stdout.decode(),'stderr':run.stderr.decode()}
    if not run.returncode:report.update(json.loads(run.stdout.decode().splitlines()[-1]))
    path=Path(__file__).with_name('r032_closure_receipt_20261005.json')
    with path.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2);f.write('\n')
    print(json.dumps(report,ensure_ascii=False))
    raise SystemExit(run.returncode)
