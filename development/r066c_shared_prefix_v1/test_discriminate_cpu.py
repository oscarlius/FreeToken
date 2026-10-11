import json
from pathlib import Path
import pytest
import sdk_discriminate as m

def data(tmp):
 d=json.loads((Path(__file__).parents[1]/'r066b_canary_v2/inputs.json').read_text()); p=tmp/'inputs.json';p.write_text(json.dumps(d));return d['items'],p
def record(item,cache=0,text=None):
 t=item['own_marker']+'\nCODE: one\nCODE: two' if text is None else text
 return {'projection':{'text':t,'finish_reason':'length','usage':{'prompt_tokens':item['prompt_tokens'],'completion_tokens':32,'total_tokens':item['prompt_tokens']+32}},'cached_tokens_observation':{'status':'reported','value':cache,'fallback_used':False}}
def patch_ok(monkeypatch,items,calls):
 def collect(base,label,item,out):calls.append(label);return record(item,8256 if 'warm' in label else 0)
 def pair(base,rows,out,warm,log):calls.extend(x[0] for x in rows);return [record(i,0) for _,i in rows],{'api_windows_overlap':True,'first_chunk_order':True,'cache_scope_met':True}
 monkeypatch.setattr(m.sdk,'collect',collect);monkeypatch.setattr(m.sdk,'pair',pair)
 seq=[]
 def backend(log,off):
  seq.append(1)
  return ([{'new_sequences':1,'new_tokens':30,'cached_tokens':8256}] if len(seq)==2 else [{'new_sequences':1,'new_tokens':items['primary_p1_sun']['prompt_tokens'],'cached_tokens':0}]),len(seq)
 monkeypatch.setattr(m,'rows',backend)
@pytest.mark.parametrize('arm,n',[('X',2),('Y',1),('Z',2)])
def test_budget(monkeypatch,tmp_path,arm,n):
 items,p=data(tmp_path);calls=[];patch_ok(monkeypatch,items,calls)
 if arm=='Y':monkeypatch.setattr(m,'rows',lambda log,off:([{'new_sequences':1,'new_tokens':items['primary_p1_ice']['prompt_tokens'],'cached_tokens':0}],1))
 m.run_arm('x',arm,tmp_path/arm,p);assert len(calls)==n
def test_x_order_and_lines(monkeypatch,tmp_path):
 items,p=data(tmp_path);calls=[];patch_ok(monkeypatch,items,calls);m.run_arm('x','X',tmp_path,p);r=json.loads((tmp_path/'result.json').read_text());assert calls==['X_sun_cold','X_ice_warm'] and r['observations'][0]['line_observation']['raw']
@pytest.mark.parametrize('kind',[m.ProductMismatch('bad'),RuntimeError('bad')])
def test_first_x_failure_stops_second(monkeypatch,tmp_path,kind):
 items,p=data(tmp_path);calls=[]
 def collect(*a):calls.append(a[1]);raise kind
 monkeypatch.setattr(m.sdk,'collect',collect)
 with pytest.raises(type(kind)):m.run_arm('x','X',tmp_path,p)
 assert calls==['X_sun_cold'] and json.loads((tmp_path/'result.json').read_text())['calls']==1
def test_missing_api_with_backend_positive(monkeypatch,tmp_path):
 items,p=data(tmp_path);calls=[]
 def collect(base,label,item,out):calls.append(label);return record(item,None)
 monkeypatch.setattr(m.sdk,'collect',collect)
 monkeypatch.setattr(m,'rows',lambda log,off:([{'new_sequences':1,'new_tokens':items['primary_p1_ice']['prompt_tokens'],'cached_tokens':0}],1))
 m.run_arm('x','Y',tmp_path,p);assert json.loads((tmp_path/'result.json').read_text())['cache_proof']['met']
@pytest.mark.parametrize('arm',[ 'Y','X'])
def test_missing_both_cache_rejected(monkeypatch,tmp_path,arm):
 items,p=data(tmp_path);calls=[]
 def collect(base,label,item,out):calls.append(label);return record(item,None)
 monkeypatch.setattr(m.sdk,'collect',collect)
 with pytest.raises(RuntimeError):m.run_arm('x',arm,tmp_path,p)
@pytest.mark.parametrize('key',['api_windows_overlap','first_chunk_order','cache_scope_met'])
def test_z_coverage_rejected(monkeypatch,tmp_path,key):
 items,p=data(tmp_path);calls=[];patch_ok(monkeypatch,items,calls)
 def pair(base,rows,out,warm,log):return [record(i,0) for _,i in rows],{x:x!=key for x in ('api_windows_overlap','first_chunk_order','cache_scope_met')}
 monkeypatch.setattr(m.sdk,'pair',pair)
 with pytest.raises(RuntimeError):m.run_arm('x','Z',tmp_path,p)
@pytest.mark.parametrize('text,error',[('GLACION-4826\nCODE:x\nCODE:y',None),('GLACIER-4826\x00',m.ProductMismatch),('SUNSTONE-7319',m.ProductMismatch)])
def test_marker_observation_and_product(monkeypatch,tmp_path,text,error):
 items,p=data(tmp_path);calls=[]
 monkeypatch.setattr(m.sdk,'collect',lambda b,l,i,o:record(i,0,text))
 if error:
  with pytest.raises(error):m.run_arm('x','Y',tmp_path,p)
 else:m.run_arm('x','Y',tmp_path,p);assert json.loads((tmp_path/'result.json').read_text())['observations'][0]['own_marker_present'] is False
def test_cache_proof_rejects_api_contradiction_and_extra_warm_rows(tmp_path):
 items,_=data(tmp_path); cold=record(items['primary_p1_sun'],8256); o=m.observe(cold,items['primary_p1_sun'],None,0); assert not m.cache_proof(o,items['primary_p1_sun'],False)['met']
 warm=record(items['primary_p1_ice'],8256); warm['projection']['usage']['prompt_tokens']=8286; o=m.observe(warm,items['primary_p1_ice'],None,0); o['cache_rows']=[{'new_tokens':30,'cached_tokens':8256},{'new_tokens':1,'cached_tokens':0}]; assert not m.cache_proof(o,items['primary_p1_ice'],True)['met']
def test_line_observation_known_hash_and_glacion_not_product(tmp_path):
 items,_=data(tmp_path); text='GLACION-4826\nCODE: one\nCODE: two'; x=m.lines(text,items['primary_p1_ice']); assert x['all_first_three_equal_own_marker'] is False and x['fulltext_sha256']=='4f8b599cabf5d156c41b912ece91325ae1d2afb71f1a6524f4a0bac766229b95'

def test_lines_use_equality_instead_of_substring(tmp_path):
 items,_=data(tmp_path); item=items['primary_p1_ice']; own=item['own_marker']
 x=m.lines(own+' extra\nCODE: '+own+'\nCODE: '+own,item)
 assert x['line_equals_own_marker']==[False,True,True]
 assert not x['all_first_three_equal_own_marker']
 assert x['literal_line_equals_own_marker']==[False,False,False]

@pytest.mark.parametrize('new,cached',[(29,8256),(30,8192),(31,8256)])
def test_warm_exact_tail_and_cache_rejects_drift(tmp_path,new,cached):
 items,_=data(tmp_path);item=items['primary_p1_ice'];obs=m.observe(record(item,8256),item,None,0)
 obs['cache_rows']=[{'new_sequences':1,'new_tokens':new,'cached_tokens':cached}]
 assert not m.cache_proof(obs,item,True)['met']

def test_cold_chunked_log_with_missing_api_is_proven(tmp_path):
 items,_=data(tmp_path);item=items['primary_p1_sun'];obs=m.observe(record(item,None),item,None,20)
 obs['cache_rows']=[{'new_sequences':1,'new_tokens':4096,'cached_tokens':0},{'new_sequences':0,'new_tokens':4096,'cached_tokens':0},{'new_sequences':0,'new_tokens':92,'cached_tokens':0}]
 obs['cache_log_end']=400
 proof=m.cache_proof(obs,item,False)
 assert proof['met'] and proof['api_cached_tokens'] is None and proof['fallback_used'] is False
 assert proof['log_start_byte']==20 and proof['log_end_byte']==400
