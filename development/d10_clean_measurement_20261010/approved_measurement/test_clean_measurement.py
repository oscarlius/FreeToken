import copy,importlib.util,json,sys,time
from pathlib import Path
import pytest
HERE=Path(__file__).parent
sys.path.insert(0,str(HERE))
import d10_clean_consumer as consumer
import d10_clean_owned_parent as owned

def fixture(speed=31,n=288):
    dt=int(1e9/speed);metrics=[];samples=[]
    for step in range(n):
        metrics.append({'step':step,'uids':[7,8],'gpu_completion_ms':1000/speed,'lanes':[{'uid':uid,'lookups':4,'hits':3,'misses':1,'h2d_bytes':32} for uid in [7,8]]})
        samples.append({'step':step,'uids':[7,8],'tokens':[{'uid':uid,'token_id':123} for uid in [7,8]],'completed_monotonic_ns':1000000000+step*dt,'timestamp_source':'after_existing_scheduler_copy_done_and_host_append'})
    return metrics,samples,[{'done':True,'finish_reason':'length','usage':{'completion_tokens':512}} for _ in range(2)]

def test_exact_threshold_and_warm_interval():
    m,s,c=fixture(30);r=consumer.evaluate(m,s,c)
    # Integer nanosecond resolution may move the quotient just above30;
    # enforce exact duration for equality and verify strict comparator.
    s[-1]['completed_monotonic_ns']=s[15]['completed_monotonic_ns']+len(s[16:])*100000000
    r=consumer.evaluate(m,s,c);assert r['verdict']=='valid_negative';assert r['common_actual_tokens']==[272,272];assert r['duration_s']==27.2
    assert r['lane_counters'][0]['h2d_bytes']==272*32
    m,s,c=fixture(31);assert consumer.evaluate(m,s,c)['verdict']=='positive_candidate'

@pytest.mark.parametrize('broken',['chunks_only','missing_metric','uid_change','short','early_eos','nonmonotonic','double_token','gpu_nan','tail_resume'])
def test_invalid_evidence_is_harness_failure(broken):
    m,s,c=fixture()
    if broken=='chunks_only':s[20]['tokens']=[{'uid':7,'text':'piece'},{'uid':8,'text':'piece'}]
    if broken=='missing_metric':m.pop(30)
    if broken=='uid_change':s[20]['uids']=[7,9]
    if broken=='short':s=s[:271]
    if broken=='early_eos':c[0]['finish_reason']='stop';c[0]['usage']['completion_tokens']=45
    if broken=='nonmonotonic':s[25]['completed_monotonic_ns']=s[24]['completed_monotonic_ns']
    if broken=='double_token':s[20]['tokens'].append({'uid':7,'token_id':123})
    if broken=='gpu_nan':m[20]['gpu_completion_ms']=float('nan')
    if broken=='tail_resume':s[20]['tokens']=s[20]['tokens'][:1]
    with pytest.raises(RuntimeError,match='failed_harness'):consumer.evaluate(m,s,c)

def test_frozen_dataset_maps_to_real_chat_body():
    b=consumer.body(consumer.PAYLOADS[0]);assert b['messages'][0]['content']==consumer.PAYLOADS[0]['text'];assert 'text' not in b;assert b['ignore_eos'];assert b['max_tokens']==512

def test_cleanup_wait_rechecks_idle():
    class Gate:
        n=0
        def require_gpu_idle(self):
            self.n+=1
            if self.n==1:raise RuntimeError('owned GPU releasing')
    gate=Gate();owned.wait_cleanup_idle(gate,2);assert gate.n==2

def test_actual_effects_constructor_no_gpu_or_http(monkeypatch):
    marker=object();monkeypatch.setattr(owned,'d07',lambda:marker)
    effects=owned.Effects();assert effects.gate is marker;assert callable(effects.dispatch);assert owned.MAX_CALLS==2


def test_probe_counts_appended_ids_after_existing_drain(monkeypatch,tmp_path):
    import types
    class Number:
        def __init__(self,n):self.n=n
        def item(self):return self.n
    class Tokens:
        def __init__(self):self.values=[Number(1)]
        def numel(self):return len(self.values)
        def __getitem__(self,i):return self.values[i]
    reqs=[types.SimpleNamespace(uid=uid,input_ids=Tokens()) for uid in [7,8]]
    batch=types.SimpleNamespace(reqs=reqs)
    class Engine:
        def __init__(self):self.ctx=types.SimpleNamespace(route_tracer=None);self.collected=[]
        def _can_use_d10_staggered(self,*a):return True
        def _forward_d10_staggered_decode(self,batch):return 'logits'
        def forward_batch(self,batch):self._forward_d10_staggered_decode(batch);return (None,[123,456],None)
        def collect_d10_step_metrics(self,wait):self.collected.append(wait);return [{'step':0,'uids':[7,8]}]
    class Scheduler:
        def __init__(self,engine):self.engine=engine
        def _process_last_data(self,data):
            for r,t in zip(data[0].batch.reqs,data[1][1]):r.input_ids.values.append(Number(t))
    monkeypatch.setitem(sys.modules,'freetoken.engine.engine',types.SimpleNamespace(Engine=Engine))
    monkeypatch.setitem(sys.modules,'freetoken.scheduler.scheduler',types.SimpleNamespace(Scheduler=Scheduler))
    monkeypatch.setenv('FT_D10_BRANCH_EVENT',str(tmp_path/'branch.json'))
    monkeypatch.setenv('FT_D10_METRICS_TRACE',str(tmp_path/'raw_d10_steps.jsonl'))
    monkeypatch.setenv('FT_D10_CANDIDATE',owned.CANDIDATE)
    import d10_branch_probe_v4 as probe
    monkeypatch.setattr(probe,'_birth',lambda:{'pid':1,'start_ticks':2})
    monkeypatch.setattr(probe.os,'getpgid',lambda _:1,raising=False)
    probe.install();engine=Engine();result=engine.forward_batch(batch)
    Scheduler(engine)._process_last_data((types.SimpleNamespace(batch=batch),result))
    sample=json.loads((tmp_path/'raw_d10_samples.jsonl').read_text())
    assert sample['tokens']==[{'uid':7,'token_id':123},{'uid':8,'token_id':456}]
    assert sample['step']==0;assert engine.collected==[False]
    assert sample['timestamp_source']=='after_existing_scheduler_copy_done_and_host_append'
