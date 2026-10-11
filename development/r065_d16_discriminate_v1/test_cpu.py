"""Actual loopback SSE through official SDK; no GPU/model operations."""
import importlib.util, json, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
import pytest
import sdk_adapter as sdk
HERE=Path(__file__).resolve().parent

@pytest.fixture
def loopback():
    state={'calls':[],'mode':'ok','cached':None,'windows':[]}
    inputs=json.loads((HERE/'inputs.json').read_text(encoding='utf-8'))['items']
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            assert self.path=='/v1/completions'
            req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with guard: index=len(state['calls']); state['calls'].append(req)
            key=next(k for k,v in inputs.items() if v['prompt']==req['prompt']); item=inputs[key]
            if state['mode']=='http_error': self.send_error(503,'fixture unavailable'); return
            count=req['max_tokens']; text=item.get('marker','LONG' if key=='long' else 'Y')
            if state['mode']=='a_text' and index==1: text='DIFFERENT'
            if state['mode']=='b_text' and index==2: text='DIFFERENT'
            if state['mode']=='c_text' and index>=3 and key=='long': text='C DIFFERENCE'
            if state['mode']=='wrong_marker' and key=='alpha': text=inputs['beta']['marker']
            if state['mode']=='missing_marker' and key=='alpha': text='No marker here'
            if state['mode']=='malformed' and key=='alpha': text+='\ufffd'
            if state['mode']=='wrong_budget': count=64 if count==128 else 128
            prompt_tokens=item['prompt_tokens']; usage={'prompt_tokens':prompt_tokens,'completion_tokens':count,'total_tokens':prompt_tokens+count}
            if state['cached'] is not None: usage['prompt_tokens_details']={'cached_tokens':state['cached']}
            if state['mode']=='cache_varies': usage['prompt_tokens_details']={'cached_tokens':7 if index==1 else 0}
            if state['mode']=='c_usage' and index>=3 and key=='long': usage['completion_tokens']=127; usage['total_tokens']-=1
            started=time.monotonic(); time.sleep(.07)
            chunks=[{'id':'fixture-'+str(index),'object':'text_completion','created':0,'model':'fixture','choices':[{'index':0,'text':text,'finish_reason':None}], 'usage':None},
                    {'id':'fixture-'+str(index),'object':'text_completion','created':0,'model':'fixture','choices':[{'index':0,'text':'','finish_reason':'length'}],'usage':None},
                    {'id':'fixture-'+str(index),'object':'text_completion','created':0,'model':'fixture','choices':[],'usage':usage}]
            body=(''.join('data: '+json.dumps(c)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode()
            self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
            with guard: state['windows'].append((started,time.monotonic()))
    guard=threading.Lock(); server=ThreadingHTTPServer(('127.0.0.1',0),Handler); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}',state
    finally: server.shutdown(); thread.join(3); server.server_close()

def run_arms(base,out):
    for arm in ('A','B','C'):
        (out/arm).mkdir(); sdk.run_service(base,'fixture',arm,out)

@pytest.mark.parametrize('cached',[None,7])
def test_seven_calls_official_sdk_positive_and_cache_missing(loopback,tmp_path,cached):
    base,state=loopback; state['cached']=cached; run_arms(base,tmp_path)
    result=json.loads((tmp_path/'criteria_result.json').read_text())
    assert result['handoff_ready'] and result['proposed_verdict']=='passed_R065_criteria'
    assert len(state['calls'])==7 and [x['max_tokens'] for x in state['calls']]==[128]*5+[64]*2
    for req in state['calls']:
        assert req['temperature']==0 and req['top_p']==1 and req['ignore_eos'] is True and req['stream_options']=={'include_usage':True}
    a2=json.loads((tmp_path/'A/calls/A2.json').read_text())
    assert a2['cached_tokens_observation']=={'status':'missing' if cached is None else 'reported','value':cached,'fallback_used':False}
    assert len(a2['chunks'])==3 and a2['projection']['usage']['completion_tokens']==128
    for left,right in ((3,4),(5,6)):
        # The official SDK client request windows overlap independently of handler scheduling order.
        labels=('C_long','C_short') if left==3 else ('C_alpha','C_beta')
        artifacts=[json.loads((tmp_path/'C/calls'/(x+'.json')).read_text()) for x in labels]
        assert max(x['client']['started_seconds'] for x in artifacts)<min(x['client']['completed_seconds'] for x in artifacts)

@pytest.mark.parametrize('mode,expected_calls,failed_arm',[('a_text',2,'A'),('b_text',3,'B'),('wrong_marker',7,'C'),('missing_marker',7,'C'),('malformed',7,'C'),('c_usage',5,'C')])
def test_official_sdk_negative_persists_and_early_stops(loopback,tmp_path,mode,expected_calls,failed_arm):
    base,state=loopback; state['mode']=mode
    with pytest.raises(ValueError): run_arms(base,tmp_path)
    result=json.loads((tmp_path/'criteria_result.json').read_text())
    assert result['proposed_verdict']=='not_met' and result['handoff_ready'] is False and result['failed_service']==failed_arm
    assert len(state['calls'])==expected_calls
    if failed_arm!='C': assert not (tmp_path/'C').exists()

def test_c_text_difference_is_observation(loopback,tmp_path):
    base,state=loopback; state['mode']='c_text'; run_arms(base,tmp_path)
    result=json.loads((tmp_path/'criteria_result.json').read_text())
    assert result['handoff_ready'] and result['batch_invariance_difference_reproduced']

@pytest.mark.parametrize('budget',[64,128])
def test_official_sdk_token_budget_mixing_rejected(loopback,tmp_path,budget):
    base,state=loopback; state['mode']='wrong_budget'; key='alpha' if budget==64 else 'long'
    item=json.loads((HERE/'inputs.json').read_text(encoding='utf-8'))['items'][key]
    with pytest.raises(sdk.CriterionMismatch): sdk.collect_one(base,'fixture','bad',item,tmp_path)
    artifact=json.loads((tmp_path/'bad.json').read_text()); assert artifact['request']['max_tokens']==budget and len(artifact['chunks'])==3

@pytest.mark.parametrize('bad',['OWN\ufffd','OWN\x00','OWN\ud800','OWN\x7f','OTHER','nothing'])
def test_malformed_or_missing_marker_rejected(bad):
    with pytest.raises(ValueError): sdk.discriminate(bad,'OWN','OTHER')

def test_normal_unicode_is_not_malformed():
    sdk.discriminate('\u201cOWN\u201d 中文说明\n','OWN','OTHER')

def test_cache_details_are_observation_not_comparison(loopback,tmp_path):
    base,state=loopback; state['mode']='cache_varies'; run_arms(base,tmp_path)
    a1=json.loads((tmp_path/'A/calls/A1.json').read_text()); a2=json.loads((tmp_path/'A/calls/A2.json').read_text())
    assert a1['projection']['usage']==a2['projection']['usage']
    assert a1['full_usage_observation']!=a2['full_usage_observation']
    assert a2['cached_tokens_observation']['value']==7
    assert json.loads((tmp_path/'criteria_result.json').read_text())['handoff_ready']

def test_http_error_is_failed_harness_not_product_fail(loopback,tmp_path):
    base,state=loopback; state['mode']='http_error'
    with pytest.raises(sdk.frozen.CompletionCollectionError): run_arms(base,tmp_path)
    result=json.loads((tmp_path/'criteria_result.json').read_text())
    assert result['proposed_verdict']=='failed_harness' and not result['handoff_ready'] and len(state['calls'])==1

def runner():
    spec=importlib.util.spec_from_file_location('r065_runner_test',HERE/'r065_runner.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def test_filedry_has_no_launch_lock_batch_or_request(monkeypatch,tmp_path):
    m=runner(); monkeypatch.setattr(m,'DEV',tmp_path); monkeypatch.setattr(m,'plan',lambda:{'candidate':{},'rid':m.RID})
    monkeypatch.setattr(m,'sources',lambda:{'test.py':HERE/'test_cpu.py'})
    pair=SimpleNamespace(dynamic_port=lambda:19001,port_receipt=lambda port:{'api':port,'tcpstore':port+1})
    d07=SimpleNamespace(clean_environment=lambda wt:{'CUDA_VISIBLE_DEVICES':'0','PYTHONPATH':'p','VIRTUAL_ENV':'v'})
    monkeypatch.setattr(m.j,'load',lambda path,name:d07 if path==m.j.D07 else pair)
    monkeypatch.setattr(m.j,'serve_argv',lambda port:['ft','serve'])
    def forbidden(*args,**kwargs): pytest.fail('FILEdry launch operation')
    monkeypatch.setattr(m.subprocess,'Popen',forbidden); monkeypatch.setattr(m.j,'launch',forbidden)
    out=Path(m.filedry()['output']); assert {p.name for p in out.iterdir()}=={'runtime_sources','source_manifest.json','preflight.json','filedry.json','A','B','C'}
    for arm in ('A','B','C'): assert json.loads((out/arm/'no_start.json').read_text())['popen'] is False
    assert json.loads((out/'filedry.json').read_text())['no_formal_rid_batch_lock_popen_or_request']

def test_preserves_frozen_lifecycle_and_new_entry_identity():
    m=runner(); assert m.sha(m.J_PATH)==m.J_SHA
    assert m.j.WT==m.WT and m.j.CANDIDATE==m.CANDIDATE and m.j.RID==m.RID
    assert m.j.start.__code__.co_filename==str(m.J_PATH)
    assert m.j.launch.__code__.co_filename==str(m.J_PATH)
    assert m.child_argv(88,Path('/tmp/receipt'),Path('/tmp/admit'))[1]==str(HERE/'r065_runner.py')
