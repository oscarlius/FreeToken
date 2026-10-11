"""Read selected D0 protocol evidence; exclude environment secrets and full prompts."""
import json
from pathlib import Path
import shlex
import subprocess

PROGRAM = r'''
import collections,hashlib,json,pathlib,re
root=pathlib.Path('/data2/_shared/runs/ft_rounds')
output={}
for rid,arms in [('E2-R003',['A_d0on_p1','B_d0off_p1','A_d0on_p2','B_d0off_p2','A_d0on_p3','B_d0off_p3']),
                 ('E2-R022-gate-D14',['PARENT_b50','NEW_b50','PARENT_P_b50','NEW_P_b50'])]:
 directory=root/rid
 record={'arms':{},'source_lines':{}}
 for arm in arms:
  base=directory/arm
  data={'files':{},'env':{},'command_settings':{},'step_summary':None}
  data['formal_samples']={}
  for path in sorted(base.glob('c_*_r*.json')):
   raw=path.read_bytes();value=json.loads(raw)
   data['formal_samples'][path.name]={'record':value['record'],'text_sha256':hashlib.sha256(value['text'].encode()).hexdigest(),
     'file_sha256':hashlib.sha256(raw).hexdigest()}
  for name in ['ENV.txt','SERVE_CMD.txt','serve_args.txt','first_shot.json','c_32052_r1.json','det.json','tax.json','d0_decode.json']:
   path=base/name
   if not path.exists():continue
   raw=path.read_bytes();text=raw.decode();data['files'][name]=hashlib.sha256(raw).hexdigest()
   if name=='ENV.txt':
    data['env']={key:value for key,value in re.findall(r'^(FT_[A-Z0-9_]+)=(.*)$',text,re.M)}
   elif name=='SERVE_CMD.txt':
    data['command_settings']={key:value for key,value in re.findall(r'(FT_[A-Z0-9_]+)=([^\s]+)',text)}
    data['serve_command_flags']=re.findall(r'--[a-z][a-z0-9_-]*(?:[ =][^\s]+)?',text)
   elif name=='serve_args.txt':data['serve_args']=text
   elif name=='d0_decode.json':
    value=json.loads(text);data['decode_profile_keys']=list(value)
    data['decode_profile']=value
   else:data[name]=json.loads(text)
  path=base/'d0_decode_steps.jsonl'
  if path.exists():
   rows=[json.loads(line) for line in path.read_bytes().splitlines() if line.strip()]
   data['files'][path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
   data['step_summary']={'rows':len(rows),'first':rows[0] if rows else None,'last':rows[-1] if rows else None,
      'keys':sorted({key for row in rows for key in row}),
      'kind_counts':dict(collections.Counter(str(row.get('kind')) for row in rows)),
      'uid_counts':dict(collections.Counter(str(row.get('uid',row.get('uids'))) for row in rows))}
  record['arms'][arm]=data
 for name in ['t07_runner.py','t00_runner.py','e2_runtime.py','base_runner_batch50.py','runner_batch50.py']:
  path=directory/name
  if path.exists():
   lines=path.read_text().splitlines()
   hits=set()
   for i,line in enumerate(lines):
    if any(term in line for term in ['TIMELINE','first_shot','warmup','decode_tps','max_tokens','D0_DECODE','D0_TIMELINE','FT_DEV_D0','cold_id','--count']):
     hits.update(range(max(0,i-2),min(len(lines),i+3)))
   record['source_lines'][name]={'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
     'lines':[str(i+1)+':'+lines[i] for i in sorted(hits)]}
 output[rid]=record
print(json.dumps(output,ensure_ascii=False))
'''

if __name__ == '__main__':
    process = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10', '9',
                              '/data2/FreeToken/venv/bin/python', '-c', shlex.quote(PROGRAM)], capture_output=True)
    if process.returncode:
        print(process.stderr.decode())
        raise SystemExit(process.returncode)
    value = json.loads(process.stdout)
    target = Path(__file__).with_suffix('.json')
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for rid, record in value.items():
        print(rid)
        for arm, data in record['arms'].items():
            print(json.dumps({'arm':arm,'env':data['env'],'command_settings':data['command_settings'],
                              'step_summary':data['step_summary'],
                              'sample_keys':{name:list(data[name]) for name in ['det.json','tax.json','c_32052_r1.json'] if name in data}},ensure_ascii=False))
        print(json.dumps(record['source_lines'],ensure_ascii=False))
