#!/usr/bin/env python3
"""D09 T2 replay: actual frozen 12-round client protocol; CPU FILEdry injects transport."""
import argparse,copy,hashlib,json,time,urllib.request
from pathlib import Path
HERE=Path(__file__).resolve().parent; SRC=HERE.parent/'d09_prediction_20261009'/'source'; RID='E2-D09-T2-replay-v1'; MODEL='Qwen3.8-Flash-Next-NVFP4'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load():
 t=json.loads((SRC/'trace_rev.json').read_text()); assert len(t['rounds'])==12; return t
def payload(row): return {'model':MODEL,'messages':row['messages'],'max_tokens':512,'temperature':0,'top_p':1,'stream':True,'stream_options':{'include_usage':True},'chat_template_kwargs':{'enable_thinking':True}}
def parse(lines):
 ev=[]; first=None; usage={}
 for raw in lines:
  s=raw.decode() if isinstance(raw,bytes) else raw
  if not s.startswith('data:'):continue
  x=s[5:].strip()
  if x=='[DONE]':break
  v=json.loads(x);ev.append(v);usage=v.get('usage') or usage
  for c in v.get('choices',[]):
   d=c.get('delta') or {}; z=d.get('reasoning_content') or d.get('content') or (d.get('tool_calls') or '')
   if z and first is None:first=len(ev)
 return {'events':ev,'usage':usage,'first_nonempty_delta_event':first}
def request(opener,url,row):
 p=payload(row); r=urllib.request.Request(url,data=json.dumps(p).encode(),headers={'Content-Type':'application/json'}); t=time.perf_counter(); raw=list(opener.open(r,timeout=1800)); v=parse(raw);v['ttft_first_nonempty_s']=time.perf_counter()-t if v['first_nonempty_delta_event'] is not None else None; return p,raw,v
def plan(trace):
 # reverse cold = round 11..0 each isolated; ascending warm = 0..11; edit = trace's edited messages in ascending order.
 return [(mode,i) for mode,order in [('reverse_cold',range(11,-1,-1)),('ascending_warm',range(12)),('edit',range(12))] for i in order]
def main():
 a=argparse.ArgumentParser();a.add_argument('--filedry',action='store_true');a.add_argument('--run',action='store_true');a.add_argument('--admission',type=Path);o=a.parse_args();t=load(); rows=plan(t); assert len(rows)==36
 if o.filedry:
  class Fake:
   def open(self,r,timeout):return [b'data: {"choices":[{"delta":{"reasoning_content":"x"}}]}\n',b'data: {"usage":{"prompt_tokens":1,"completion_tokens":1}}\n',b'data: [DONE]\n']
  p,raw,v=request(Fake(),'http://filedry/v1/chat/completions',t['rounds'][0]); out={'rid':RID,'rounds_per_pass':12,'passes':3,'calls':36,'source_sha256':sha(SRC/'trace_rev.json'),'first_nonempty_delta':v['first_nonempty_delta_event'],'payload_max_tokens':p['max_tokens'],'gpu_started':False,'http_started':False};(HERE/'T2_FILEDRY.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out));return
 if not o.run or not o.admission:raise SystemExit('root SHA admission required')
 ad=json.loads(o.admission.read_text());assert ad.get('root_approved') and ad.get('runner_sha256')==sha(Path(__file__))
 out=Path(ad['output_dir']);out.mkdir(parents=True,exist_ok=False); opener=urllib.request.build_opener(urllib.request.ProxyHandler({})); url=ad['endpoint'].rstrip('/')+'/v1/chat/completions'; results=[]
 for mode,i in rows:
  p,raw,v=request(opener,url,t['rounds'][i]); d=out/f'{mode}_{i:02d}.json'; d.write_text(json.dumps({'request':p,'sse_raw':[x.decode(errors='replace') if isinstance(x,bytes) else x for x in raw],'result':v,'round':i},ensure_ascii=False,indent=2)); results.append({'mode':mode,'round':i,'first_nonempty_delta':v['first_nonempty_delta_event'],'usage':v['usage']})
 pred=json.loads((SRC.parent/'PREDICTION_MANIFEST_v4.json').read_text())['eligible_predictions'];(out/'terminal.json').write_text(json.dumps({'rid':RID,'calls':len(results),'results':results,'prediction_rounds':pred},indent=2))
if __name__=='__main__':main()
