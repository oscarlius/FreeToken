"""CPU-only contracts for the new R046b entry; no model, sockets, or GPU."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import urllib.error
import urllib.request

import pytest

ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('r046b_cpu',ROOT/'r046b_d07_t06_prepare.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def plan():
    return {'baseline_memory_ratio':'0.88','memory_ratio':'0.80','independent_review_sha256':'a'*64,
            'r055a_round_sha256':m.R055A_ROUND_SHA,'estimated_route_overhead_bytes':None,
            'minimum_free_bytes':1144717312,'total_bytes':25250627584,'required_free_bytes':m.MIN_FREE_BYTES,
            'predicted_free_bytes':None,'prediction_not_gpu_proof':True,'calculation':'no GPU route-growth estimate',
            'r056_measured':'fixture/R056/round.json'}


def test_all_service_ratios_change_only_the_authorized_argument():
    source=m.D07_SOURCE.read_bytes()
    original_spec=importlib.util.spec_from_file_location('d07_original',m.D07_SOURCE)
    original=importlib.util.module_from_spec(original_spec);original_spec.loader.exec_module(original)
    d=m.load_d07();before=original.serve_argv(23456);after=d.serve_argv(23456)
    changes={'--memory-ratio':'0.80','--kv-reserve-tokens':'98304','--max-seq-len-override':'98304'}
    expected=before[:]
    for flag,value in changes.items():expected[expected.index(flag)+1]=value
    assert before[before.index('--memory-ratio')+1]=='0.88' and after==expected
    assert (d.RID,d.CANDIDATE,d.WORKTREE)==(m.RID,m.CANDIDATE,m.WT)
    assert m.D07_SOURCE.read_bytes()==source


@pytest.mark.parametrize('arm',['g3_off','g3_on','G_seed12k','G_seed_45k','G_seed_real','G_two'])
def test_actual_file_prepare_installs_observer_for_every_service(tmp_path,arm):
    d=m.load_d07();directory=tmp_path/arm;route=None if arm=='g3_off' else directory/'route'
    prepared=m.prepare_service(d,directory,m.WT,23456,route,start=False,pause_observer=True)
    assert prepared['argv'][:2]==[str(m.VENV/'bin/python'),str(directory/'r055b_pause_startup.py')]
    assert prepared['argv'][prepared['argv'].index('--memory-ratio')+1]=='0.80'
    assert prepared['env']['R055B_MODEL_MEMORY']==str(directory/'model_process_cuda.jsonl')
    env=json.loads((directory/'ENV.json').read_text())
    assert env['R055B_MODEL_MEMORY']==str(directory/'model_process_cuda.jsonl')
    assert ('FT_DEV_ROUTE_TRACE' in env)==(arm!='g3_off')
    if arm.startswith('G_'):assert env['FT_DEV_PAUSE_ENDPOINT']=='1'
    assert 'elif name=="UserMsg":' in (directory/'r055b_pause_observer.py').read_text()


def test_off_is_rerun_and_new_on_is_its_only_comparison(monkeypatch,tmp_path):
    calls=[];run=tmp_path/'new';run.mkdir()
    monkeypatch.setattr(m,'require_historical_r046',lambda:{'used_for_comparison':False})
    def prepare(d,directory,wt,port,route,**kwargs):
        directory.mkdir();(directory/'serve.log').write_text('CUDA graph disabled for development route trace')
        assert kwargs=={'start':True,'pause_observer':True}
        assert d.serve_argv(port)[d.serve_argv(port).index('--memory-ratio')+1]=='0.80'
        calls.append(('start',directory.name,route is not None));return SimpleNamespace(pid=99)
    monkeypatch.setattr(m,'prepare_service',prepare)
    monkeypatch.setattr(m,'require_t06_loaded_memory',lambda directory,*_:calls.append(('loaded',directory.name)))
    monkeypatch.setattr(m,'summarize_t06_memory',lambda directory,*args,**kwargs:calls.append(('summary',directory.name,args[-1],kwargs['pause_required'])))
    def cold(wt,port,cold_id,out):
        calls.append(('cold',out.parent.name,cold_id));out.write_text('{}')
    def analyzer(wt,route,trace,serve,out):out.write_text(json.dumps({'business_uids':['1','2'],'suffix_tokens':[1,2]}))
    compared=[]
    d=SimpleNamespace(serve_argv=lambda port:['ft','--memory-ratio','0.88'],dynamic_fixture_port=lambda:23456,
                      invoke_cold_eq=cold,invoke_agent_trace=lambda wt,port,out:(calls.append(('trace',out.parent.name)),out.write_text('{}')),
                      invoke_analyzer=analyzer,g3_compare=lambda off,on:(compared.append((off,on)),{'byte_identical':True})[1],
                      load_owned_lifecycle=lambda:SimpleNamespace(stop_owned_process=lambda proc:calls.append(('stop',proc.pid))))
    result=m.run_g3g4(d,m.WT,run,plan())
    assert compared==[(run/'g3g4/g3_off/cold.json',run/'g3g4/g3_on/cold.json')]
    assert calls==[('start','g3_off',False),('loaded','g3_off'),('cold','g3_off','E2-R046-cold'),('stop',99),
                   ('summary','g3_off',1,False),('start','g3_on',True),('loaded','g3_on'),
                   ('cold','g3_on','E2-R046-cold'),('trace','g3_on'),('stop',99),('summary','g3_on',3,False)]
    assert result['off_rerun'] and result['memory_ratio']=='0.80'
    for arm in ('g3_off','g3_on'):
        diff=json.loads((run/'g3g4'/arm/'serve_args_diff.json').read_text())
        assert diff['target_keys']=={'memory_ratio':'0.80','kv_reserve_tokens':98304,'max_seq_len_override':98304} and diff['all_d07_t06_arms']


def test_historical_off_reads_only_registered_metadata_not_cold_payload(monkeypatch,tmp_path):
    directory=tmp_path/'E2-R046';directory.mkdir()
    record=directory/'round.json';record.write_text(json.dumps({'round_id':'E2-R046','verdict':'failed_harness'}))
    manifest=directory/'MANIFEST.sha256'
    manifest.write_text('0ccee4b9e5a0917b5284a334acc3f0ca3bd5b871d287f674eca907b7f1f47d6d  ./g3g4/g3_off/cold.json\n')
    monkeypatch.setattr(m,'ROUNDS',tmp_path)
    record.chmod(0o444);manifest.chmod(0o444)
    try:
        result=m.require_historical_r046()
        assert not (directory/'g3g4/g3_off/cold.json').exists()
        assert result['used_for_comparison'] is False and result['old_off_declared_sha256'].startswith('0ccee4b9')
    finally:record.chmod(0o644);manifest.chmod(0o644)


def test_r056_measured_is_required_without_old_static_route_budget(tmp_path):
    calls=[];closure=tmp_path/'round.json';closure.write_text('{}')
    d=SimpleNamespace(require_closed_round=lambda rid,verdict:(calls.append((rid,verdict)),closure)[1])
    assert m.require_r056(d)==closure and calls==[('E2-R056','measured')]
    assert not hasattr(m,'read_longest_review') and not hasattr(m,'validate_longest_budget')
    assert m.window_contract()=={'kv_reserve_tokens':98304,'max_seq_len_override':98304,'completion_reserve_tokens':2048,'max_prompt_tokens':96256}


def test_partial_or_failed_r056_cannot_supply_admission(monkeypatch):
    def reject(*_):raise RuntimeError('R056 is not canonical measured+D04')
    monkeypatch.setattr(m,'load_d07',lambda:SimpleNamespace(require_closed_round=reject))
    with pytest.raises(RuntimeError,match='canonical measured'):m.packet()
    with pytest.raises(RuntimeError,match='canonical measured'):m.memory_plan()


def test_seed_completion_allows_only_bound_natural_window_hit():
    binding={'schema':'ft_t06_seed_trace_binding/v2','seed_raw_sha256':m.SEEDS['seed_real'],
             'window':98304,'completion_reserve_tokens':2048,'max_prompt_tokens':96256,'max_tokens':2048,
             'completed_k':2,'window_hit_count':1,'window_hit':{'request_k':3,'actual_prompt_tokens':96257,'input_binding':{'actual_input_ids_sha256':'a'*64}}}
    assert m.validate_seed_completion(binding,'seed_real')==2
    binding['window_hit']['request_k']=4
    with pytest.raises(RuntimeError,match='natural window hit'):m.validate_seed_completion(binding,'seed_real')
    binding['window_hit']=None;binding['window_hit_count']=0
    with pytest.raises(RuntimeError,match='incomplete trace'):m.validate_seed_completion(binding,'seed_real')
    binding.update(window=49152)
    with pytest.raises(RuntimeError,match='identity differs'):m.validate_seed_completion(binding,'seed_real')


def test_route_analysis_uses_actual_completed_k_instead_of_twelve(monkeypatch,tmp_path):
    g=tmp_path/'G_seed_real';g.mkdir();trace=g/'trace_seed_real.json';trace.write_text('{}')
    binding={'schema':'ft_t06_seed_trace_binding/v2','seed_raw_sha256':m.SEEDS['seed_real'],
             'window':98304,'completion_reserve_tokens':2048,'max_prompt_tokens':96256,'max_tokens':2048,
             'completed_k':2,'window_hit_count':1,'window_hit':{'request_k':3,'actual_prompt_tokens':96257,'input_binding':{'actual_input_ids_sha256':'a'*64}}}
    trace.with_suffix('.seed_binding.json').write_text(json.dumps(binding));summary=tmp_path/'summary.json'
    def analyze(*args,**kwargs):
        summary.write_text(json.dumps({'analysis_scope':'trace_bound_business_requests','suffix_tokens':[1,2],
                                      'business_uids':['1','2'],'completion_count':2,
                                      'completions':{'1':{'max_tokens':2048},'2':{'max_tokens':2048}},'missing_business_routes':[]}))
    monkeypatch.setattr(m.subprocess,'run',analyze)
    monkeypatch.setattr(m,'load_d07',lambda:SimpleNamespace(clean_environment=lambda _:{}))
    m.invoke_analysis(m.WT,g,summary,trace=trace)
    assert json.loads(summary.read_text())['completion_count']==2


def test_actual_observer_records_user_message_boundaries(monkeypatch,tmp_path):
    from test_r055b_owned_launch import install_fake_product,exec_observer,message
    owner=m.load_pause_observer()
    monkeypatch.setenv('R055B_MODEL_MEMORY',str(tmp_path/'memory.jsonl'))
    monkeypatch.setenv('R055_PAUSE_OBSERVATIONS',str(tmp_path/'pause.jsonl'))
    Scheduler,IO,Engine=install_fake_product(monkeypatch);exec_observer(owner)
    Engine();Scheduler()._process_one_msg(message('UserMsg',uid=31))
    IO()._reply_tokenizer_rank0([message('DetokenizeMsg',uid=31,finished=True,next_token=7)])
    rows=[json.loads(line) for line in (tmp_path/'memory.jsonl').read_text().splitlines()]
    assert [row['event'] for row in rows]==['model_loaded','request_before','request_after']
    assert rows[1]['uid']==rows[2]['uid']=='31'


@pytest.mark.parametrize('body,valid',[(b'{"status":"timeout","request_id":"p"}',True),
                                     (b'not-json',False),(b'{"status":"accepted","request_id":"p"}',False),
                                     (b'{"status":"timeout","request_id":""}',False),
                                     (b'{"status":"timeout","request_id":"p","error":"cancel enqueue failed"}',False)])
def test_actual_504_helper_keeps_only_valid_timeout_receipts(monkeypatch,tmp_path,body,valid):
    def answer(request,timeout):
        raise urllib.error.HTTPError(request.full_url,504,'timeout',{},io.BytesIO(body))
    monkeypatch.setattr(urllib.request,'urlopen',answer)
    with pytest.raises(RuntimeError):m.invoke_t06_pause(23456,tmp_path)
    if valid:assert json.loads((tmp_path/'pause_completed.json').read_text())=={'status':'timeout','request_id':'p','http_status':504}
    else:assert not (tmp_path/'pause_completed.json').exists()


def test_d07_memory_summary_rejects_missing_request_before(monkeypatch,tmp_path):
    birth={'pid':1,'start_ticks':2};worker={'pid':3,'start_ticks':4}
    def event(kind,t,**fields):return {'schema':'ft_r055b_model_process_cuda/v1','event':kind,'time_ns':t,
                                      'service_birth':birth,'worker_birth':worker,'device':0,
                                      'free_bytes':m.MIN_FREE_BYTES,'total_bytes':24*1024**3,**fields}
    loaded=event('model_loaded',1);monkeypatch.setattr(m,'require_t06_loaded_memory',lambda *_:loaded)
    rows=[loaded,event('request_before',2,uid='31'),event('request_after',3,uid='31')]
    output=tmp_path/'model_process_cuda.jsonl';output.write_text('\n'.join(json.dumps(row) for row in rows))
    assert m.summarize_t06_memory(tmp_path,{'observer_source_sha256':'a'*64},None,1,pause_required=False)['complete']
    rows.pop(1);output.write_text('\n'.join(json.dumps(row) for row in rows))
    with pytest.raises(RuntimeError,match='every business request-before/after'):
        m.summarize_t06_memory(tmp_path,{'observer_source_sha256':'a'*64},None,1,pause_required=False)


def test_new_source_and_receipt_identity_reject_old_or_changed_inputs(monkeypatch,tmp_path):
    source=tmp_path/'frozen.py';source.write_text('frozen entry')
    monkeypatch.setattr(m,'runtime_sources',lambda:(source,))
    config={'requested_path':'overlay/config.json','resolved_path':'model/config.json.qwen4_exp.orig','sha256':'c'*64}
    monkeypatch.setattr(m,'model_config_binding',lambda:config)
    target=m.dry_run_directory(tmp_path);target.mkdir();receipt=target/'dry_run_receipt.json'
    value={'schema':'ft_r046b_dry_run/v4','rid':m.RID,'candidate_commit':m.CANDIDATE,'passed':True,
           'model_config_source':config,
           'source_sha256':{str(source.resolve()):m.sha(source)},
           'owner':{'path':str(Path(m.__file__).resolve()),'uid':getattr(m.os,'getuid',lambda:None)(),
                    'user':m.os.environ.get('USER') or m.os.environ.get('LOGNAME')},
           'cwd':str(m.ROOT),'worktree':{'path':str(m.WT),'parent':str(m.WT.parent)},
           **{flag:False for flag in ('formal_rid_directory_created','service_started','requests_sent','gpu_lock_taken','batch_allocated')}}
    def publish():
        receipt.chmod(0o644) if receipt.exists() else None
        receipt.write_text(json.dumps(value));receipt.chmod(0o444)
    publish();assert m.require_dry_run_receipt(tmp_path)['sha256']==m.sha(receipt)
    value['schema']='ft_r046b_dry_run/v3';publish()
    with pytest.raises(RuntimeError,match='identity differs'):m.require_dry_run_receipt(tmp_path)
    value.update(schema='ft_r046a_dry_run/v2',rid='E2-R046a');publish()
    with pytest.raises(RuntimeError,match='identity differs'):m.require_dry_run_receipt(tmp_path)
    value.update(schema='ft_r046b_dry_run/v4',rid=m.RID,model_config_source={**config,'resolved_path':'other/config.json'});publish()
    with pytest.raises(RuntimeError,match='config source binding'):m.require_dry_run_receipt(tmp_path)
    value['model_config_source']=config;publish();source.write_text('changed')
    with pytest.raises(RuntimeError,match='source SHA'):m.require_dry_run_receipt(tmp_path)
    assert target.name=='.dryrun_R046b_v4_E2-R046b' and m.REVIEW_DIR.name=='E2-R046b-v4'


def test_readonly_source_copy_is_explicitly_writable_without_mutating_source(tmp_path):
    source=tmp_path/'source.py';copy=tmp_path/'copy.py';source.write_text('readonly source');source.chmod(0o444)
    original=m.sha(source)
    try:
        result=m._copy_runtime_source(source,copy)
        assert result['source_sha256']==result['copy_sha256']==original
        assert copy.stat().st_mode&0o222 and not source.stat().st_mode&0o222
    finally:source.chmod(0o644)


@pytest.mark.parametrize('linked',[False,True])
def test_model_config_archives_resolved_regular_source_and_preserves_overlay_mapping(monkeypatch,tmp_path,linked):
    if linked and m.sys.platform=='win32':pytest.skip('POSIX model overlay symlink proof requires Linux')
    overlay=tmp_path/'overlay';overlay.mkdir();requested=overlay/'config.json'
    canonical=tmp_path/'model/config.json.qwen4_exp.orig';canonical.parent.mkdir();canonical.write_text('{"model_type":"qwen4_exp"}')
    if linked:requested.symlink_to(canonical)
    else:requested.write_bytes(canonical.read_bytes())
    monkeypatch.setattr(m,'MODEL_PATH',overlay)
    for key,name in (('SEED_CLIENT','seed_client.py'),('D07_SOURCE','d07.py'),('FILE_PREP_SOURCE','file_prepare.py'),
                     ('R055B_OBSERVER_SOURCE','observer.py'),('PAUSE_HARNESS_SOURCE','pause.py'),('ROUND_WRITER','writer.py')):
        source=tmp_path/name;source.write_text(key);monkeypatch.setattr(m,key,source)
    wt=tmp_path/'wt';tokenize=wt/'python/freetoken/tokenizer/tokenize.py';tokenize.parent.mkdir(parents=True);tokenize.write_text('fixture tokenizer')
    monkeypatch.setattr(m,'WT',wt)
    binding=m.model_config_binding();resolved=canonical if linked else requested
    assert binding=={'requested_path':str(requested),'resolved_path':str(resolved.resolve()),'sha256':m.sha(resolved)}
    sources=m.runtime_sources();assert len(sources)==9 and sources[-1]==resolved.resolve()
    archive=tmp_path/'archive';archive.mkdir();rows=m.archive_runtime_sources(archive)
    copied=next(row for row in rows if row['source']==str(resolved.resolve()))
    assert copied['copy']==str(archive/resolved.name) and copied['source_sha256']==copied['copy_sha256']==binding['sha256']
    assert requested.is_symlink() is linked and requested.read_bytes()==canonical.read_bytes()
    if linked:
        with pytest.raises(RuntimeError,match='runtime source unavailable'):m._copy_runtime_source(requested,tmp_path/'unresolved_copy')


def test_owned_startup_cleanup_failure_is_not_retried(monkeypatch,tmp_path):
    monkeypatch.setattr(m,'require_historical_r046',lambda:{})
    process=SimpleNamespace(pid=71);calls=[]
    def fail(*args,**kwargs):
        error=RuntimeError('cleanup failed');error.owned_process=process;error.owned_cleanup_failed=True;raise error
    monkeypatch.setattr(m,'prepare_service',fail)
    d=SimpleNamespace(serve_argv=lambda port:['ft','--memory-ratio','0.88'],dynamic_fixture_port=lambda:23456,
                      load_owned_lifecycle=lambda:SimpleNamespace(stop_owned_process=lambda proc:calls.append(proc)))
    with pytest.raises(RuntimeError,match='cleanup failed') as raised:m.run_g3g4(d,m.WT,tmp_path,plan())
    assert raised.value.owned_process is process and not calls


def test_loaded_memory_gate_uses_owned_worker_sample_before_requests(tmp_path):
    directory=tmp_path/'g3_off';directory.mkdir()
    observer=directory/'r055b_pause_observer.py';observer.write_text('observer')
    birth={'pid':77,'start_ticks':9,'execution_id':'77:9','pgid':77,'session':77}
    worker={'pid':79,'start_ticks':10,'execution_id':'79:10','pgid':77,'session':77}
    row={'schema':'ft_r055b_model_process_cuda/v1','event':'model_loaded','device':0,
         'service_birth':birth,'worker_birth':worker,'free_bytes':m.MIN_FREE_BYTES,'total_bytes':24*1024**3}
    (directory/'owned_process.json').write_text(json.dumps({'birth':{**birth,'state':'R'}}))
    path=directory/'model_process_cuda.jsonl';path.write_text(json.dumps(row)+'\n')
    p={'observer_source_sha256':m.sha(observer),'total_bytes':row['total_bytes']}
    assert m.require_t06_loaded_memory(directory,p,SimpleNamespace(pid=77))['event']=='model_loaded'
    row['free_bytes']-=1;path.write_text(json.dumps(row)+'\n')
    with pytest.raises(RuntimeError,match='below 1.5GiB'):m.require_t06_loaded_memory(directory,p,SimpleNamespace(pid=77))


@pytest.mark.skipif(m.sys.platform=='win32',reason='POSIX readonly-directory proof requires Linux')
@pytest.mark.parametrize('mutation',[None,'writer_drift','round_writable','manifest_writable',
                                   'pin_writable','directory_writable','member_writable',
                                   'writer_missing','writer_directory','writer_symlink',
                                   'wrong_base','wrong_pin_candidate','wrong_schema','top_candidate_only'])
def test_failed_r046a_uses_644_bound_external_checker_and_keeps_metadata_sealed(monkeypatch,tmp_path,mutation):
    root=tmp_path/'root';rounds=tmp_path/'rounds';directory=rounds/'E2-R046a';directory.mkdir(parents=True)
    document={'schema':'ft_round/v2','round_id':'E2-R046a','base':{'commit':m.CANDIDATE,'parent_commit':'0aa23431e5b800797543bdecbf35a01045131d7d'},'verdict':'failed_harness'}
    round_json=directory/'round.json';round_json.write_text(json.dumps(document))
    manifest=directory/'MANIFEST.sha256';manifest.write_text('sealed failed metadata')
    writer=root/'scripts/round_json_append.py';writer.parent.mkdir(parents=True);writer.write_text('external canonical writer')
    pin=root/'runs/plan_batches/closed_round_pins/E2-R046a.json';pin.parent.mkdir(parents=True)
    binding={'schema':'ft_closed_round_pin/v1','rid':'E2-R046a','candidate_commit':m.CANDIDATE,'verdict':'failed_harness',
             'round_sha256':m.sha(round_json),'manifest_sha256':m.sha(manifest)}
    pin.write_text(json.dumps(binding))
    before=set(directory.iterdir());calls=[]
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'ROUNDS',rounds);monkeypatch.setattr(m,'ROUND_WRITER',writer)
    monkeypatch.setattr(m,'R046A_ROUND_SHA',m.sha(round_json));monkeypatch.setattr(m,'ROUND_WRITER_SHA',m.sha(writer))
    monkeypatch.setattr(m.subprocess,'run',lambda argv,**kwargs:(calls.append(argv),SimpleNamespace(returncode=0))[1])
    for path in (round_json,manifest,pin):path.chmod(0o444)
    writer.chmod(0o644)
    directory.chmod(0o555)
    try:
        if mutation=='writer_drift':writer.write_text('changed canonical writer')
        elif mutation in ('round_writable','manifest_writable','pin_writable'):
            {'round_writable':round_json,'manifest_writable':manifest,'pin_writable':pin}[mutation].chmod(0o644)
        elif mutation=='directory_writable':directory.chmod(0o755)
        elif mutation=='member_writable':
            directory.chmod(0o755);(directory/'unsealed.json').write_text('{}');directory.chmod(0o555)
        elif mutation in ('writer_missing','writer_directory','writer_symlink'):
            writer.unlink()
            if mutation=='writer_directory':writer.mkdir()
            elif mutation=='writer_symlink':writer.symlink_to(round_json)
        elif mutation in ('wrong_base','wrong_pin_candidate','wrong_schema','top_candidate_only'):
            if mutation=='wrong_base':document['base']['commit']='0'*40
            elif mutation=='wrong_pin_candidate':binding['candidate_commit']='0'*40
            elif mutation=='wrong_schema':document['schema']='ft_round/v1'
            else:document.pop('base');document['candidate_commit']=m.CANDIDATE
            round_json.chmod(0o644);round_json.write_text(json.dumps(document));round_json.chmod(0o444)
            binding['round_sha256']=m.sha(round_json);monkeypatch.setattr(m,'R046A_ROUND_SHA',binding['round_sha256'])
            pin.chmod(0o644);pin.write_text(json.dumps(binding));pin.chmod(0o444)
        if mutation is None:
            result=m.require_failed_r046a()
            assert 'candidate_commit' not in json.loads(round_json.read_text())
            assert writer.stat().st_mode&0o777==0o644
            assert calls==[[str(m.VENV/'bin/python'),str(writer),str(directory),'check']]
            assert result['verdict']=='failed_harness' and set(directory.iterdir())==before
        else:
            with pytest.raises(RuntimeError):m.require_failed_r046a()
            assert not calls
    finally:
        directory.chmod(0o755)
        for path in (round_json,manifest,pin):path.chmod(0o644)
        if writer.is_symlink():writer.unlink()


@pytest.mark.skipif(m.sys.platform=='win32',reason='POSIX sealed review-directory proof requires Linux')
@pytest.mark.parametrize('old_field',[None,'review_schema','pin_schema','config_mapping'])
def test_v4_startup_review_rejects_old_signature_schemas_or_config_mapping(monkeypatch,tmp_path,old_field):
    root=tmp_path/'root';wt=root/'wt';review_dir=root/'reviews/E2-R046b-v4';review_dir.mkdir(parents=True)
    executor=root/'runs/plan_batches/e2_launch.py';executor.parent.mkdir(parents=True);executor.write_text('fixture allocator')
    files=[executor]
    for name in ('agent_trace.py','_agent_trace_original.py','route_analyze.py','multisession_probe.py'):
        source=wt/'scripts'/name;source.parent.mkdir(parents=True,exist_ok=True);source.write_text(name);files.append(source)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'WT',wt);monkeypatch.setattr(m,'REVIEW_DIR',review_dir)
    monkeypatch.setattr(m,'runtime_sources',lambda:(executor,));monkeypatch.setattr(m,'require_historical_r046',lambda:{'fixture':'sealed'})
    config={'requested_path':'overlay/config.json','resolved_path':'model/config.json.qwen4_exp.orig','sha256':'c'*64}
    monkeypatch.setattr(m,'model_config_binding',lambda:config)
    dry={'path':str(tmp_path/'dry_run_receipt.json'),'sha256':'a'*64}
    document={'schema':'ft_r046b_source_startup_review/v4','rid':m.RID,'verdict':'PASS','model_config_source':config,
              'source_execution_ready':True,'candidate_commit':m.CANDIDATE,'historical_r046':{'fixture':'sealed'},
              'sources':{str(path):m.sha(path) for path in files},'dry_run_receipt':dry['path'],'dry_run_receipt_sha256':dry['sha256']}
    if old_field=='review_schema':document['schema']='ft_r046b_source_startup_review/v3'
    elif old_field=='config_mapping':document['model_config_source']={**config,'resolved_path':'other/config.json'}
    review=review_dir/'review.json';review.write_text(json.dumps(document));review.chmod(0o444)
    binding={'schema':'ft_r046b_review_pin/v4','rid':m.RID,'review_sha256':m.sha(review)}
    if old_field=='pin_schema':binding['schema']='ft_r046b_review_pin/v3'
    pin=review_dir/'pin.json';pin.write_text(json.dumps(binding));pin.chmod(0o444);review_dir.chmod(0o555)
    try:
        if old_field is None:assert m.require_startup_review(dry)['path']==str(review)
        else:
            with pytest.raises(RuntimeError,match='review pin differs|review identity differs|config source binding'):m.require_startup_review(dry)
    finally:
        review_dir.chmod(0o755);review.chmod(0o644);pin.chmod(0o644)


def test_cpu_guard_is_active_and_rejects_8095():
    import os,socket
    assert os.environ['CUDA_VISIBLE_DEVICES']==''
    with socket.socket() as sock:
        with pytest.raises(PermissionError):sock.connect(('127.0.0.1',8095))
