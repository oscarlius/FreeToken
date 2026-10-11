"""CPU contract tests exercise official SDK wire streaming and bounded retry."""
import json,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import pytest
import sdk_adapter as a

def chunks(text='SUNSTONE-7319',finish='stop',count=5,prompt=2):
    return [dict(id='c1',choices=[dict(index=0,text=text,finish_reason=None)]),dict(id='c1',choices=[dict(index=0,text='',finish_reason=finish)]),dict(id='c1',choices=[],usage=dict(prompt_tokens=prompt,completion_tokens=count,total_tokens=prompt+count))]

@pytest.mark.parametrize('finish,count',[('stop',0),('stop',5),('stop',32),('length',32)])
def test_finish_budget(finish,count):
    p,c=a.project32(chunks(finish=finish,count=count),2)
    assert p['usage']['completion_tokens']==count and c=={'status':'missing','value':None,'fallback_used':False}

@pytest.mark.parametrize('case',['short_length','over_budget','bool_usage','missing_finish','changed_id','duplicate_usage','after_finish','wrong_index','bad_cache'])
def test_protocol_errors(case):
    rows=chunks()
    if case=='short_length': rows[1]['choices'][0]['finish_reason']='length'
    if case=='over_budget': rows[2]['usage'].update(completion_tokens=33,total_tokens=35)
    if case=='bool_usage': rows[2]['usage'].update(completion_tokens=True,total_tokens=3)
    if case=='missing_finish': rows.pop(1)
    if case=='changed_id': rows[1]['id']='other'
    if case=='duplicate_usage': rows.append(rows[-1])
    if case=='after_finish': rows.append(rows[0])
    if case=='wrong_index': rows[0]['choices'][0]['index']=1
    if case=='bad_cache': rows[-1]['usage']['prompt_tokens_details']={'cached_tokens':-1}
    with pytest.raises(ValueError): a.project32(rows,2)

@pytest.mark.parametrize('text',['GLACIER-4826','\ufffd','x\x01'])
def test_product_failures(text):
    with pytest.raises(a.ProductMismatch): a.assess({'projection':{'text':text}},{'own_marker':'SUNSTONE-7319','other_marker':'GLACIER-4826'})

def test_own_absent_is_invalid():
    assert not a.assess({'projection':{'text':'ordinary response\n\t'}},{'own_marker':'SUNSTONE-7319','other_marker':'GLACIER-4826'})

def fake_inputs():
    return {f'{t}_{p}_{w}':{'own_marker':w,'other_marker':'foreign','prompt':w,'prompt_tokens':2} for t in ('primary','alternative') for p in ('p1','p2') for w in ('sun','ice')}

@pytest.mark.parametrize('missing',[0,1,2,3])
def test_one_global_retry_and_both_base_pairs(tmp_path,missing):
    seen=[]
    def fake(base,items,out,warm,log):
        seen.append([key for key,item in items]); n=len(seen)
        records=[{'projection':{'text':item['own_marker'] if n>missing else ''}} for key,item in items]
        return records,dict(api_windows_overlap=True,first_chunk_order=True,cache_scope_met=True)
    a.run_service('unused',tmp_path,inputs=fake_inputs(),pair_fn=fake)
    r=json.loads((tmp_path/'criteria_result.json').read_text())
    assert len(seen)==(2 if missing==0 else 3) and r['calls'] in (4,6)
    assert any('primary_p2_sun' in row for row in seen)
    assert r['handoff_R063'] and r['c_met']==(missing<=1)

def test_product_failure_stops_before_next_pair(tmp_path):
    seen=[]
    def fake(base,items,out,warm,log):
        seen.append(1)
        return [{'projection':{'text':'foreign'}}]*2,{}
    with pytest.raises(a.ProductMismatch): a.run_service('unused',tmp_path,inputs=fake_inputs(),pair_fn=fake)
    r=json.loads((tmp_path/'criteria_result.json').read_text())
    assert len(seen)==1 and r['proposed_verdict']=='not_met' and not r['handoff_R063']

def test_scheduler_log_chunking():
    rows=a.cached_rows('Prefill batch, #new-seq: 1, #new-token: 512, #cached-token: 0\nPrefill batch, #new-seq: 1, #new-token: 7766, #cached-token: 0\nPrefill batch, #new-seq: 1, #new-token: 22, #cached-token: 8256')
    assert sum(x['new_tokens'] for x in rows)+max(x['cached_tokens'] for x in rows)==16556
    assert a.cache_scope([None,None],rows,16556,True)
    assert not a.cache_scope([0,0],rows,16556,True)
    assert not a.cache_scope([None,None],rows[:-1],16556,True)
    cold=a.cached_rows('Prefill batch, #new-seq: 2, #new-token: 1024, #cached-token: 0\nPrefill batch, #new-seq: 2, #new-token: 15532, #cached-token: 0')
    assert a.cache_scope([None,None],cold,16556,False)
    assert not a.cache_scope([None,None],[],16556,False)

def test_official_sdk_first_chunk_overlap_and_wire(tmp_path):
    requests=[]; first_sent=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length']))); requests.append((time.monotonic(),self.path,body))
            self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Connection','close'); self.end_headers()
            own=body['prompt']
            for i,data in enumerate(chunks(text=own)):
                self.wfile.write(('data: '+json.dumps(data)+'\n\n').encode()); self.wfile.flush()
                if i==0: first_sent.set(); time.sleep(.15)
            self.wfile.write(b'data: [DONE]\n\n'); self.wfile.flush()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try:
        records,coverage=a.pair(f'http://127.0.0.1:{server.server_port}', [('sun',{'prompt':'sun','prompt_tokens':2}),('ice',{'prompt':'ice','prompt_tokens':2})],tmp_path,True)
        assert coverage['api_windows_overlap'] and coverage['first_chunk_order'] and not coverage['cache_scope_met']
        assert len(requests)==2 and all(path=='/v1/completions' and b['max_tokens']==32 and b['ignore_eos'] is False and b['temperature']==0 for _,path,b in requests)
        assert all(r['cached_tokens_observation']['value'] is None for r in records)
    finally: server.shutdown(); server.server_close(); thread.join()

def test_target_tokenizer_binding():
    import os,subprocess
    receipt=json.loads(subprocess.check_output(['/data2/FreeToken/venv/bin/python',str(a.HERE/'prepare_inputs.py'),'--verify'],env={**os.environ,'CUDA_VISIBLE_DEVICES':''},text=True))
    assert receipt['verified'] and receipt['items']==8 and min(receipt['shared_prefix_tokens'].values())>=8192
