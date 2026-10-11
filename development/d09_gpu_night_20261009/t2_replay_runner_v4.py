#!/usr/bin/env python3
import argparse,copy,hashlib,importlib.util,json,time,urllib.request
from pathlib import Path
H=Path(__file__).resolve().parent;F=H/'agent_trace_remote_frozen.py';S=H.parent/'d09_prediction_20261009';RID='E2-D09-T2-v3'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def mod():
 q=importlib.util.spec_from_file_location('t2f',F);m=importlib.util.module_from_spec(q);q.loader.exec_module(m);return m
def run_stream(m,op,url,payload,raw):
 def events():
  r=urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  with op.open(r,timeout=1800) as z:
   for line in z:
    raw.append(line.decode(errors='replace'));s=raw[-1].strip()
    if s.startswith('data:') and s[5:].strip()!='[DONE]':yield json.loads(s[5:].strip())
 return m.consume_stream(events(),time.perf_counter())
def main():
 a=argparse.ArgumentParser();a.add_argument('--filedry',action='store_true');a.add_argument('--run',action='store_true');a.add_argument('--admission',type=Path);x=a.parse_args();m=mod();rev=json.loads((S/'source/trace_rev.json').read_text());trace=json.loads((S/'source/trace.json').read_text());edit=json.loads((S/'source/C_edit.json').read_text());pred=json.loads((S/'PREDICTION_MANIFEST_v4.json').read_text());assert len(rev['rounds'])==len(trace['rounds'])==len(edit['rounds'])==12 and len(m.DEFAULT_EDIT_TEXT)==2952
 passes=[('reverse_cold',rev,None),('ascending_warm',trace,None),('edit',trace,10)];assert sum(len(t['rounds']) for _,t,_ in passes)==36
 if x.filedry:
  class R:
   def __enter__(s):return iter([b'data: {"choices":[{"delta":{"reasoning_content":"x"}}]}\n',b'data: {"usage":{"prompt_tokens":3,"completion_tokens":1,"prompt_tokens_details":{"cached_tokens":0}}}\n'])
   def __exit__(s,*z):pass
  class O:
   def open(s,*z,**k):return R()
  raw=[];r=run_stream(m,O(),'http://dry',{},raw);assert r['ttft_any_s'] is not None
  (H/'T2_FILEDRY_v3.json').write_text(json.dumps({'rid':RID,'calls':36,'rounds_per_pass':12,'frozen_client_sha256':sha(F),'trace_rev_sha256':sha(S/'source/trace_rev.json'),'trace_sha256':sha(S/'source/trace.json'),'edit_sha256':sha(S/'source/C_edit.json'),'prediction_sha256':sha(S/'PREDICTION_MANIFEST_v4.json'),'max_tokens':m.REPLAY_MAX_TOKENS,'first_delta':r['ttft_any_s'],'gpu_started':False,'http_started':False},indent=2));return
 if not x.run or not x.admission:raise SystemExit('root SHA admission required')
 ad=json.loads(x.admission.read_text());assert ad.get('root_approved') and ad['runner_sha256']==sha(Path(__file__)) and ad['frozen_client_sha256']==sha(F) and ad['endpoint'].startswith('http://127.0.0.1:') and Path(ad['service_log']).is_file()
 out=Path(ad['output_dir']);out.mkdir(parents=True,exist_ok=False);op=urllib.request.build_opener(urllib.request.ProxyHandler({}));rows=[];pm={z['round']:z for z in pred['eligible_predictions']}
 for name,t,idx in passes:
  for i,row in enumerate(t['rounds']):
   msgs=copy.deepcopy(row['messages']); applied,note=m.apply_edit(msgs,idx,m.DEFAULT_EDIT_TEXT)
   source='C_edit.json' if name=='edit' else ('C_warm.json' if name=='ascending_warm' else 'C_coldfirst.json')
   expected=json.loads((S/'source'/source).read_text())['rounds'][i]
   assert bool(applied)==bool(expected['edit_applied']) and m.messages_digest(msgs)==expected['messages_sha']
   payload=m.build_payload(msgs,t['meta']['params']['model'],t.get('tools') or m.tool_specs(),t['meta']['params']['thinking'],m.REPLAY_MAX_TOKENS);log=Path(ad['service_log']);off=log.stat().st_size;raw=[];r=run_stream(m,op,ad['endpoint'].rstrip('/')+'/v1/chat/completions',payload,raw);u=m.usage_counts(r['usage']);d={'pass':name,'round':i,'request':payload,'sse_raw':raw,'ttft_any_s':r['ttft_any_s'],'usage':{'prompt_tokens':u[0],'cached_tokens':u[1],'completion_tokens':u[2]},'backend_log_window':log.open('rb').read()[off:].decode(errors='replace'),'edit_applied':applied,'edit_note':note}
   if name=='edit' and i in pm:d['prediction']={**pm[i],'actual_ttft':r['ttft_any_s'],'residual':r['ttft_any_s']-pm[i]['predicted_ttft_any_s_target'] if r['ttft_any_s'] is not None else None}
   (out/f'{name}_{i:02d}.json').write_text(json.dumps(d,ensure_ascii=False,indent=2));rows.append(d)
 (out/'terminal.json').write_text(json.dumps({'rid':RID,'calls':36,'rows':rows},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
