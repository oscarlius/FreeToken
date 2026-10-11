"""Actual AIPerf 0.11 parser: output count and decode speed are separate gates."""
from __future__ import annotations
import json
from pathlib import Path
def metric(metrics,name):
 v=metrics.get(name)
 if not isinstance(v,dict) or not isinstance(v.get('value'),(int,float)):raise RuntimeError('missing raw metric '+name)
 return v['value']
def parse_profile(directory:Path):
 rows=[]
 for file in directory.rglob('profile_export.jsonl'):
  for line in file.read_text(encoding='utf-8').splitlines():
   x=json.loads(line);meta=x.get('metadata');metrics=x.get('metrics')
   if not isinstance(meta,dict) or not isinstance(metrics,dict) or not isinstance(meta.get('x_request_id'),str):raise RuntimeError('invalid AIPerf 0.11 raw record')
   out=metric(metrics,'usage_completion_tokens');out2=metric(metrics,'output_token_count');speed=metric(metrics,'output_token_throughput_per_user')
   if int(out)!=out or out!=out2 or out<=0 or speed<=0:raise RuntimeError('invalid output count or decode speed')
   rows.append({'request_id':meta['x_request_id'],'completion_tokens':int(out),'ttft_ms':float(metric(metrics,'time_to_first_token')),'decode_tokens_per_second':float(speed)})
 if len({x['request_id'] for x in rows})!=len(rows):raise RuntimeError('duplicate request IDs')
 return rows
def original_gate(directory:Path):
 rows=parse_profile(directory)
 if len(rows)!=2:raise RuntimeError('original group needs two records')
 if any(x['decode_tokens_per_second']<=30 for x in rows):raise RuntimeError('original per-request decode speed must be > 30')
 return rows
def fixed_gate(directory:Path):
 rows=parse_profile(directory)
 if len(rows)!=2 or [x['completion_tokens'] for x in rows] != [256,256]:raise RuntimeError('fixed group must be exactly [256, 256]')
 return rows
