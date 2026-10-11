import importlib.util, json
from pathlib import Path
ROOT=Path(__file__).parents[1]; spec=importlib.util.spec_from_file_location('r',ROOT/'allxy_runner.py'); r=importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
def raw(max_tokens, finish='length', request_id='x'):
 return {"metadata":{"x_request_id":request_id,"was_cancelled":False},"status":200,"payload":{"max_tokens":max_tokens,"temperature":0,"top_p":1,"ignore_eos":False},"responses":[{"packets":[{"name":"data","value":json.dumps({"choices":[{"finish_reason":finish}]})}]}]}
def metrics(max_tokens, request_id='x'):
 return {"metadata":{"x_request_id":request_id},"metrics":{"inter_token_latency":{"value":40,"unit":"ms"},"usage_prompt_tokens":{"value":7800},"usage_completion_tokens":{"value":max_tokens}}}
def test_raw_summary_and_d0_bs2_delta_only(tmp_path):
 p=tmp_path/'profile_export_raw.jsonl';p.write_text('\n'.join(json.dumps(raw(256,request_id=x)) for x in ('a','b')))
 (tmp_path/'profile_export.jsonl').write_text('\n'.join(json.dumps(metrics(256,x)) for x in ('a','b')))
 assert r.raw_summary(p,'X')[0]['per_lane_decode_tps']==25
 d=tmp_path/'d0.jsonl';d.write_text(json.dumps({"bs":1,"missing_total":480})+'\n'+json.dumps({"bs":2,"missing_total":480,"rids":[1,2]})+'\n')
 got=r.d0_delta(d,1); assert got['m_equivalent_shared_batch_per_lane_average']==.5 and got['from_index']==1 and got['to_index']==2
def test_x_rejects_nonlength(tmp_path):
 p=tmp_path/'profile_export_raw.jsonl';p.write_text('\n'.join(json.dumps(raw(256,'stop',x)) for x in ('a','b')))
 (tmp_path/'profile_export.jsonl').write_text('\n'.join(json.dumps(metrics(256,x)) for x in ('a','b')))
 try:r.raw_summary(p,'X')
 except ValueError as e:assert 'length' in str(e)
 else:assert False

def test_actual_r045_raw_and_sibling_metrics_fixture():
 p=Path('freetoken/development/r045_production_aiperf_20261009/raw_retry1/wave1/profile_export_raw.jsonl')
 got=r.raw_summary(p,'Y')
 assert [round(x['per_lane_decode_tps'],7) for x in got] == [22.4249957,22.5311783]
