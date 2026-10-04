import importlib.util, json
import numpy as np
import pytest
spec=importlib.util.spec_from_file_location("route_analyze","scripts/route_analyze.py"); route_analyze=importlib.util.module_from_spec(spec); spec.loader.exec_module(route_analyze)

def record(d, seq, phase, reqs, values):
    np.savez_compressed(d/f"route-{seq:08d}.npz",expert_ids=values)
    (d/f"route-{seq:08d}.json").write_text(json.dumps({"seq":seq,"phase":phase,"t":sum(x["n_tokens"] for x in reqs),"layer_count":1,"layer_ids":[7],"reqs":reqs,"file":f"route-{seq:08d}.npz"}))
def ids(n, start=0): return np.arange(start,start+n*10,dtype=np.int16).reshape(1,n,10)

def test_prefill_chunks_union_and_decode_exclusion(tmp_path):
    record(tmp_path,0,"prefill",[{"rid":1,"n_tokens":1}],ids(1))
    record(tmp_path,1,"prefill",[{"rid":1,"n_tokens":2}],ids(2,10))
    record(tmp_path,2,"decode",[{"rid":1,"n_tokens":1},{"rid":2,"n_tokens":1}],ids(2,40))
    got=route_analyze.analyze(tmp_path)
    assert got["raw_suffix_tokens"]=={"1":3}
    assert got["f_measured"]["3"]["7"]==pytest.approx(30/512)
    assert got["R_B"]=={} and got["R_B_pending"] is True

@pytest.mark.parametrize("bad",[np.full((1,1,10),512,dtype=np.int16),np.zeros((1,1,10),dtype=np.int16)])
def test_bad_or_duplicate_token_expert_is_rejected(tmp_path,bad):
    record(tmp_path,0,"prefill",[{"rid":1,"n_tokens":1}],bad)
    with pytest.raises(ValueError): route_analyze.analyze(tmp_path)

def test_missing_prefill_duplicate_uid_and_missing_npz_fail(tmp_path):
    record(tmp_path,0,"decode",[{"rid":1,"n_tokens":1},{"rid":2,"n_tokens":1}],ids(2))
    with pytest.raises(ValueError,match="no prefill"): route_analyze.analyze(tmp_path)
    record(tmp_path,1,"prefill",[{"rid":1,"n_tokens":1},{"rid":1,"n_tokens":1}],ids(2,30))
    with pytest.raises(ValueError,match="duplicate"): route_analyze.analyze(tmp_path)

def test_trace_and_per_uid_log_evidence(tmp_path):
    record(tmp_path,0,"prefill",[{"rid":9,"n_tokens":2}],ids(2))
    trace=tmp_path/"trace.json"; trace.write_text(json.dumps({"rounds":[{"record":{"ack_schema":"ft_route_ack/v1","uid":9,"max_tokens":2048,"completion_tokens":2,"finish_reason":"stop","token_events":[{"request_seq":1,"completion_tokens_delta":1,"completion_tokens_cumulative":1},{"request_seq":2,"completion_tokens_delta":1,"completion_tokens_cumulative":2}]}}]}))
    log=tmp_path/"serve.log"; log.write_text("Prefill #new-token: 2, #route-reqs: 9:2,\n")
    assert route_analyze.analyze(tmp_path,[trace],log)["completions"][9]["completion_tokens"]==2
    log.write_text("#new-token: 2\n")
    with pytest.raises(ValueError,match="route-reqs"): route_analyze.analyze(tmp_path,[],log)
    log.write_text("#new-token: 3, #route-reqs: 9:2,\n")
    with pytest.raises(ValueError,match="new-token"): route_analyze.analyze(tmp_path,[],log)


def two_decode_proof(directory, uids=(11,12), hashes=('a'*64,'b'*64)):
    path=directory/'two_decode.json'
    ways=[]
    for index,uid in enumerate(uids):
        sidecar=directory/f'two_decode.rep0.way{index}.tokens.json'
        sidecar.write_text(json.dumps({'uid':uid,'token_events':[{
            'uid':uid,'request_seq':1,'completion_tokens_delta':1,
            'completion_tokens_cumulative':1,'t_s':0.1}]}))
        ways.append({'uid':uid,'completion_tokens':1,'token_timestamps':str(sidecar)})
    path.write_text(json.dumps({'schema':'multisession_probe/v1','command':'two-decode',
        'same_prompt':False,'reps':[{'rep':0,'prompt_sha256':list(hashes),
        'frontend_token_counts':[8000,8000],'per_way':ways}]}))
    return path


def test_rb_requires_declared_distinct_content_pair(tmp_path):
    record(tmp_path,0,'prefill',[{'rid':11,'n_tokens':1},{'rid':12,'n_tokens':1}],ids(2))
    record(tmp_path,1,'decode',[{'rid':12,'n_tokens':1},{'rid':11,'n_tokens':1}],ids(2))
    proof=two_decode_proof(tmp_path)
    got=route_analyze.analyze(tmp_path,two_decode=proof)
    assert got['R_B']=={'7':1.0} and got['decode_B2_steps']==1
    assert got['R_B_pending'] is False and got['two_decode_pairs'][0]['uids']==[11,12]
    two_decode_proof(tmp_path,hashes=('a'*64,'a'*64))
    with pytest.raises(ValueError,match='distinct'):
        route_analyze.analyze(tmp_path,two_decode=proof)


def test_unrelated_b2_record_is_rejected_when_pair_evidence_is_supplied(tmp_path):
    record(tmp_path,0,'prefill',[{'rid':11,'n_tokens':1},{'rid':12,'n_tokens':1}],ids(2))
    record(tmp_path,1,'decode',[{'rid':11,'n_tokens':1},{'rid':99,'n_tokens':1}],ids(2))
    with pytest.raises(ValueError,match='undeclared B=2'):
        route_analyze.analyze(tmp_path,two_decode=two_decode_proof(tmp_path))


def test_pair_sidecar_uid_disagreement_is_rejected(tmp_path):
    record(tmp_path,0,'prefill',[{'rid':11,'n_tokens':1},{'rid':12,'n_tokens':1}],ids(2))
    proof=two_decode_proof(tmp_path)
    sidecar=tmp_path/'two_decode.rep0.way0.tokens.json'
    data=json.loads(sidecar.read_text());data['uid']=99;sidecar.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='sidecar UID'):
        route_analyze.analyze(tmp_path,two_decode=proof)


def test_zero_delta_ack_and_complete_output_cap_are_checked(tmp_path):
    events=[{'request_seq':1,'completion_tokens_delta':0,'completion_tokens_cumulative':0}]
    events += [{'request_seq':n+1,'completion_tokens_delta':1,
        'completion_tokens_cumulative':n} for n in range(1,2049)]
    row={'ack_schema':'ft_route_ack/v1','uid':9,'max_tokens':2048,
        'completion_tokens':2048,'finish_reason':'length','token_events':events}
    path=tmp_path/'trace.json';path.write_text(json.dumps({'rounds':[{'record':row}]}))
    got=route_analyze.load_trace(path)[9]
    assert got['completion_tokens']==2048 and got['finish_reason']=='length'
    row['token_events'].append({'request_seq':2050,'completion_tokens_delta':1,
        'completion_tokens_cumulative':2049})
    row['completion_tokens']=2049
    path.write_text(json.dumps({'rounds':[{'record':row}]}))
    with pytest.raises(ValueError,match='budget'):
        route_analyze.load_trace(path)


def test_business_summary_excludes_readiness_and_checks_suffix_counts(tmp_path):
    record(tmp_path,0,'prefill',[{'rid':1,'n_tokens':1}],ids(1))
    record(tmp_path,1,'prefill',[{'rid':9,'n_tokens':2}],ids(2,10))
    row={'ack_schema':'ft_route_ack/v1','uid':9,'max_tokens':2048,
        'completion_tokens':1,'recomputed_tokens':2,'finish_reason':'stop',
        'token_events':[{'request_seq':1,'completion_tokens_delta':1,'completion_tokens_cumulative':1}]}
    path=tmp_path/'trace.json';path.write_text(json.dumps({'rounds':[{'record':row}]}))
    got=route_analyze.analyze(tmp_path,[path])
    assert got['business_uids']==[9]
    assert got['suffix_distribution']['median']==2 and got['suffix_le_64_fraction']==1
    assert got['completion_distribution']['median']==1 and got['completion_gt_233_fraction']==0
    assert got['suffix_tokens'][0]['uid']==9 and got['suffix_tokens'][0]['n']==2
    row['recomputed_tokens']=3;path.write_text(json.dumps({'rounds':[{'record':row}]}))
    with pytest.raises(ValueError,match='recomputed_tokens'):
        route_analyze.analyze(tmp_path,[path])


def test_real_generate_schema_with_zero_ack_passes_offline_analyzer(monkeypatch,tmp_path):
    spec=importlib.util.spec_from_file_location('d07_trace_integration','scripts/agent_trace.py')
    wrapper=importlib.util.module_from_spec(spec);spec.loader.exec_module(wrapper)
    monkeypatch.delenv('FT_DEV_ROUTE_TRACE',raising=False)
    uids=iter((11,12))
    def stream(*_):
        uid=next(uids)
        return iter([
            {'ft_dev':{'schema':'ft_dev_stream/v1','uid':uid,'request_seq':1,
                'completion_tokens_delta':0,'completion_tokens_cumulative':0},
             'choices':[{'delta':{},'finish_reason':None}]},
            {'ft_dev':{'schema':'ft_dev_stream/v1','uid':uid,'request_seq':2,
                'completion_tokens_delta':1,'completion_tokens_cumulative':1},
             'choices':[{'delta':{'content':'response'},'finish_reason':'stop'}]},
            {'choices':[],'usage':{'completion_tokens':1,'prompt_tokens':200,
                'prompt_tokens_details':{'cached_tokens':198}}},
        ])
    wrapper._ns['post_events']=stream
    out=tmp_path/'actual_trace.json'
    import sys
    monkeypatch.setattr(sys,'argv',['agent_trace.py','--route-evidence','generate','--rounds','2',
        '--max-tokens','2048','--out',str(out)])
    assert wrapper.main()==0
    record(tmp_path,0,'prefill',[{'rid':1,'n_tokens':1}],ids(1))
    record(tmp_path,1,'prefill',[{'rid':11,'n_tokens':2}],ids(2,10))
    record(tmp_path,2,'prefill',[{'rid':12,'n_tokens':2}],ids(2,30))
    got=route_analyze.analyze(tmp_path,[out])
    assert got['business_uids']==[11,12] and got['completion_count']==2
    assert [row['n'] for row in got['suffix_tokens']]==[2,2]
    saved=json.loads(out.read_text())['rounds'][0]['record']
    assert saved['token_events'][0]['completion_tokens_delta']==0
    assert saved['max_tokens']==2048


def test_actual_two_decode_cli_output_and_sidecars_bind_rb(monkeypatch,tmp_path):
    spec=importlib.util.spec_from_file_location('d07_pair_integration','scripts/multisession_probe.py')
    probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
    monkeypatch.setattr(probe,'load_tokenizer',lambda _:object())
    def messages(_tokenizer,_ctx,salt):
        return [{'role':'user','content':salt}],[1,2 if salt.startswith('left') else 3]
    monkeypatch.setattr(probe,'make_messages',messages)
    def parallel(calls):
        assert calls[0]['messages']!=calls[1]['messages']
        return [{'uid':uid,'t_first_s':0.0,'t_last_s':0.1,'ttft_s':0.01,
            'completion_tokens':2,'t_anchor_unix_s':1.0,
            'token_events':[{'uid':uid,'request_seq':n,'completion_tokens_delta':1,
                'completion_tokens_cumulative':n,'t_s':(n-1)/10} for n in (1,2)]}
            for uid in (11,12)]
    monkeypatch.setattr(probe,'_run_parallel',parallel)
    out=tmp_path/'cli_pair.json'
    assert probe.main(['two-decode','--ctx','2','--max-tokens','4',
        '--same-prompt','0','--reps','1','--out',str(out)])==0
    record(tmp_path,0,'prefill',[{'rid':11,'n_tokens':2},{'rid':12,'n_tokens':2}],ids(4))
    shared=np.stack((np.arange(10),np.arange(10))).astype(np.int16)[None,:,:]
    overlap=np.stack((np.arange(10),np.arange(5,15))).astype(np.int16)[None,:,:]
    record(tmp_path,1,'decode',[{'rid':11,'n_tokens':1},{'rid':12,'n_tokens':1}],shared)
    record(tmp_path,2,'decode',[{'rid':12,'n_tokens':1},{'rid':11,'n_tokens':1}],overlap)
    got=route_analyze.analyze(tmp_path,two_decode=out)
    assert got['R_B']['7']==pytest.approx((2+20/15)/2)
    assert got['decode_B2_steps']==2 and got['two_decode_pairs'][0]['uids']==[11,12]
