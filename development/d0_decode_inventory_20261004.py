"""Read historical D0 measurement artifacts on SSH9 without allocating a GPU."""
import json
from pathlib import Path
import shlex
import subprocess

PROGRAM = r'''
import hashlib,json,pathlib
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
output={}
for rid,arms in [('E2-R003',['A_d0on_p1','B_d0off_p1','A_d0on_p2','B_d0off_p2','A_d0on_p3','B_d0off_p3']),
                 ('E2-R022-gate-D14',['PARENT_b50','NEW_b50','PARENT_P_b50','NEW_P_b50'])]:
 directory=root/rid
 record={'arms':{},'top':{}}
 for arm in arms:
  base=directory/arm
  files=[]
  for path in sorted(base.rglob('*')):
   if path.is_file() and len(path.relative_to(base).parts)<=2:
    files.append({'path':str(path.relative_to(base)),'size':path.stat().st_size})
  record['arms'][arm]=files
 for name in ['round.json','measurement_summary.json','gate_batch50.json']:
  path=directory/name
  if path.exists():
   raw=path.read_bytes()
   record['top'][name]={'sha256':hashlib.sha256(raw).hexdigest(),'value':json.loads(raw)}
 output[rid]=record
print(json.dumps(output,ensure_ascii=False))
'''

if __name__ == '__main__':
    process = subprocess.run(
        ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
         '/data2/FreeToken/venv/bin/python', '-c', shlex.quote(PROGRAM)],
        capture_output=True,
    )
    if process.returncode:
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    value = json.loads(process.stdout)
    target = Path(__file__).with_suffix('.json')
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'inventory': str(target), 'rounds': {
        rid: {'arms': {arm: [row['path'] for row in rows] for arm, rows in data['arms'].items()},
              'top_sha256': {name: record['sha256'] for name, record in data['top'].items()}}
        for rid, data in value.items()}}, ensure_ascii=False))
