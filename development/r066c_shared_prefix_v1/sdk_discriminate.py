"""R066c arm observations, reusing the frozen R066b official SDK transport."""
from __future__ import annotations
import hashlib,importlib.util,json,re
from criteria import grammar
from pathlib import Path
HERE=Path(__file__).resolve().parent; OLD=HERE.parent/'r066b_canary_v2/sdk_adapter.py'
spec=importlib.util.spec_from_file_location('r066c_frozen_sdk',OLD); sdk=importlib.util.module_from_spec(spec); spec.loader.exec_module(sdk)
ProductMismatch=sdk.ProductMismatch
def write(p,v):
 with Path(p).open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')
def lines(text,item=None):
 raw=text.splitlines()[:3]; norm=[x.strip().removeprefix('CODE:').strip() for x in raw]; own=item['own_marker'] if item else ''
 return {'raw':raw,'normalized':norm,'line_equals_own_marker':[x==own for x in norm],'all_first_three_equal_own_marker':len(norm)==3 and all(x==own for x in norm),'literal_line_equals_own_marker':[x==own for x in raw],'fulltext_sha256':hashlib.sha256(text.encode()).hexdigest()}
def rows(log,offset):
 if not log:return [],None
 with Path(log).open('rb') as f:f.seek(offset);x=f.read();end=f.tell()
 return sdk.cached_rows(x.decode('utf-8',errors='replace')),end
def observe(rec,item,log,offset):
 sdk.assess(rec,item); r,end=rows(log,offset); c=rec['cached_tokens_observation']['value']; return {'projection':rec['projection'],'cache_api':c,'cache_rows':r,'backend_log':str(log) if log else None,'cache_log_start':offset,'cache_log_end':end,'line_observation':lines(rec['projection']['text'],item),'own_marker_present':item['own_marker'] in rec['projection']['text'],'grammar':grammar(rec['projection']['text'],item['own_marker'])}
def cache_proof(obs,prompt,warm):
 rows=obs['cache_rows']; api=obs['cache_api']; total=obs['projection']['usage']['prompt_tokens']
 if total!=prompt['prompt_tokens']: return {'met':False,'backend_rows':rows,'api_cached_tokens':api,'fallback_used':False,'log_start_byte':obs['cache_log_start'],'log_end_byte':obs['cache_log_end']}
 if warm:
  positive=[r for r in rows if r['cached_tokens']>0]; ok=bool(rows) and len(positive)==1 and positive[0]['cached_tokens']==8256 and sum(r['new_tokens'] for r in rows)==30 and sum(r['cached_tokens'] for r in rows)==8256 and total==8286 and (api is None or api==8256)
 else:
  ok=(bool(rows) and all(r['cached_tokens']==0 for r in rows) and sum(r['new_tokens'] for r in rows)==total and api in (None,0)) or (not rows and api==0)
 return {'met':ok,'backend_rows':rows,'api_cached_tokens':api,'fallback_used':False,'log_start_byte':obs['cache_log_start'],'log_end_byte':obs['cache_log_end']}
def run_arm(base,arm,out,inputs_path,log=None):
 data=json.loads(Path(inputs_path).read_text())['items']; out=Path(out); out.mkdir(parents=True,exist_ok=True); result={'arm':arm,'calls':0,'observations':[]}
 try:
  if arm=='X':
   off=Path(log).stat().st_size if log else 0; result['calls']+=1; a=sdk.collect(base,'X_sun_cold',data['primary_p1_sun'],out); oa=observe(a,data['primary_p1_sun'],log,off); result['observations'].append(oa); pa=cache_proof(oa,data['primary_p1_sun'],False)
   result['cache_proof']={'cold':pa}
   if not pa['met']: raise RuntimeError('X cold cache coverage differs')
   off=Path(log).stat().st_size if log else 0; result['calls']+=1; b=sdk.collect(base,'X_ice_warm',data['primary_p1_ice'],out); ob=observe(b,data['primary_p1_ice'],log,off); result['observations'].append(ob); pb=cache_proof(ob,data['primary_p1_ice'],True)
   result['cache_proof']['warm']=pb; result['actualtail30']=pb['met']
   if not pb['met']: raise RuntimeError('X warm cache coverage differs')
  elif arm=='Y':
   off=Path(log).stat().st_size if log else 0; result['calls']=1; a=sdk.collect(base,'Y_ice_cold',data['primary_p1_ice'],out); oy=observe(a,data['primary_p1_ice'],log,off); result['observations'].append(oy); result['cache_proof']=cache_proof(oy,data['primary_p1_ice'],False)
   if not result['cache_proof']['met']: raise RuntimeError('Y cold cache coverage differs')
  elif arm=='Z':
   result['calls']=2; rec,cov=sdk.pair(base,[('Z_sun',data['primary_p1_sun']),('Z_ice',data['primary_p1_ice'])],out,True,log); result['pair_coverage']=cov; result['observations']=[observe(r,data[k],None,0) for r,k in zip(rec,('primary_p1_sun','primary_p1_ice'))]
   if not all(cov.get(k) is True for k in ('api_windows_overlap','first_chunk_order','cache_scope_met')): raise RuntimeError('Z pair coverage differs')
  else:raise ValueError('arm must be X,Y,Z')
  result['status']='observed'
 except ProductMismatch as e:result.update(status='not_met',reason=str(e));raise
 except BaseException as e:result.update(status='failed_harness',reason=str(e));raise
 finally:write(out/'result.json',result)
