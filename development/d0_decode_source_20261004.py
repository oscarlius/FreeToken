"""Verify D0 source identity and historical protocol differences using CPU-only reads."""
import json
from pathlib import Path
import shlex
import subprocess

PROGRAM = r'''
import collections,hashlib,json,pathlib,subprocess
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
output={'source':{},'protocol':{}}
for wt,commit in [('e2base','23f2e2caa3395837c9474735ffc83321f3b9b5a1'),('e2d14','e4f32022a5aa4d8734d87d9f6eb15e98c1edde42')]:
 data={}
 for file in ['python/freetoken/moe/d0_decode.py','python/freetoken/moe/offload_cache.py']:
  raw=subprocess.check_output(['git','-C','/data2/FreeToken/wt/'+wt,'show',commit+':'+file])
  lines=raw.decode().splitlines()
  data[file]={'sha256':hashlib.sha256(raw).hexdigest(),
   'timeline_settings_present':'FT_DEV_D0_TIMELINE' in raw.decode(),
   'selected_lines':[str(i+1)+':'+line for i,line in enumerate(lines) if any(s in line for s in ['FT_DEV_D0','read_counters','read_missing','end_step','synchronize','cpu()','to("cpu")'])]}
 output['source'][commit]=data
for rid,arms in [('E2-R003',['A_d0on_p1','A_d0on_p2','A_d0on_p3']),('E2-R022-gate-D14',['PARENT_b50','NEW_b50'])]:
 result={}
 for arm in arms:
  base=root/rid/arm
  lines=(base/'ENV.txt').read_text().splitlines()
  rows=[json.loads(line) for line in (base/'d0_decode_steps.jsonl').read_text().splitlines() if line.strip()]
  by=collections.defaultdict(list)
  for row in rows:by[str(row['rids'])].append(row['missing_total'])
  result[arm]={'environment_header':lines[:3],'timeline_files':[p.name for p in base.glob('*timeline*')],
   'requests':{rid:{'steps':len(values),'mean_missing':sum(values)/len(values),'first_missing':values[0]} for rid,values in by.items()}}
 output['protocol'][rid]=result
print(json.dumps(output))
'''

if __name__ == '__main__':
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-c', shlex.quote(PROGRAM)], capture_output=True)
    if process.returncode:
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    value = json.loads(process.stdout)
    Path(__file__).with_suffix('.json').write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(value, ensure_ascii=False, indent=2))
