import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).parents[1]
spec=importlib.util.spec_from_file_location('r046a_cpu',ROOT/'r046a_d07_t06_prepare.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_local_helper_uses_measurement_tree_without_mutating_source():
    source=m.D07_SOURCE.read_bytes(); helper=m.load_d07()
    assert (helper.CANDIDATE,helper.WORKTREE,helper.RID)==(m.CANDIDATE,m.WT,'E2-R046a')
    assert m.D07_SOURCE.read_bytes()==source


def test_exact_predecessor_verdicts(monkeypatch):
    source=Path(m.__file__).read_text()
    assert 'E2-R055b-gate-D06' in source and '0c7467a274b93cfd54cdd7d3e70e4b43da6289f93c9a61519dbb3749d75e15b3' in source


def test_foreign_lock_precedes_review_or_batch(monkeypatch,tmp_path):
    lock=tmp_path/'gpu.lock';lock.write_text('foreign')
    monkeypatch.setattr(m.sys,'platform','linux')
    monkeypatch.setattr(m,'require_output_root',lambda *_:None)
    monkeypatch.setattr(m,'load_d07',lambda:SimpleNamespace(LOCK=lock))
    monkeypatch.setattr(m,'require_startup_review',lambda:pytest.fail('foreign lock must precede review'))
    with pytest.raises(RuntimeError,match='foreign GPU lock'):m.execute()


def test_retained_off_startup_never_reads_raw(monkeypatch,tmp_path):
    rounds=tmp_path/'rounds';root=tmp_path/'root'
    cold=rounds/'E2-R046/g3g4/g3_off/cold.json';cold.parent.mkdir(parents=True);cold.write_text('raw')
    review=root/'runs/dev_D17/r046_live_incremental_r_overlap_g3off/review.json';review.parent.mkdir(parents=True);review.write_text('R')
    cold.chmod(0o444);review.chmod(0o444)
    monkeypatch.setattr(m,'ROUNDS',rounds);monkeypatch.setattr(m,'ROOT',root)
    def digest(path):
        if path==cold:pytest.fail('startup must not read predecessor raw')
        return 'e42524eee0ec7ea5e9e971528b2a14f953306d58968712ed7826ba1264779450'
    monkeypatch.setattr(m,'sha',digest)
    try:
        value=m.require_retained_off()
        assert value['off_rerun'] is False and value['off_candidate']!=value['on_candidate']
    finally:cold.chmod(0o644);review.chmod(0o644)


def test_g3g4_file_dry_run_never_hashes_or_reads_retained_cold(monkeypatch,tmp_path):
    run=tmp_path/'dry';run.mkdir();cold=tmp_path/'old-cold.json';cold.write_text('old')
    monkeypatch.setattr(m,'require_retained_off',lambda *,verify_cold=False:{'review':'small','off_rerun':False})
    monkeypatch.setattr(m,'prepare_service',lambda *_args,**_kwargs:{'argv':[]})
    monkeypatch.setattr(m,'sha',lambda path:pytest.fail('dry-run must not read retained cold') if Path(path)==cold else 'a'*64)
    d=SimpleNamespace(dynamic_fixture_port=lambda:23456)
    value=m.run_g3g4(d,m.WT,run,file_dry_run=True)
    assert value['not_measurement'] is True


def test_only_on_service_is_started_and_off_remains_external(monkeypatch,tmp_path):
    rounds=tmp_path/'rounds';off=rounds/'E2-R046/g3g4/g3_off';off.mkdir(parents=True)
    (off/'cold.json').write_text('original off')
    run=tmp_path/'new';run.mkdir();calls=[]
    monkeypatch.setattr(m,'ROUNDS',rounds)
    monkeypatch.setattr(m,'require_retained_off',lambda **_:{'off_rerun':False})
    def start(directory,wt,port,route):
        directory.mkdir(parents=True,exist_ok=True)
        calls.append(('start',directory.name));(directory/'serve.log').write_text('CUDA graph disabled for development route trace')
        return object()
    def cold(wt,port,cold_id,out):
        assert cold_id=='E2-R046-cold';out.write_text('new on')
    def analyzer(wt,route,trace,serve,summary):summary.write_text(json.dumps({'business_uids':[0],'suffix_tokens':[1]}))
    monkeypatch.setattr(m,'prepare_service',lambda _d,directory,wt,port,route,**_:start(directory,wt,port,route))
    d=SimpleNamespace(dynamic_fixture_port=lambda:20000,invoke_cold_eq=cold,
       invoke_agent_trace=lambda wt,port,path:path.write_text('{}'),invoke_analyzer=analyzer,
       load_owned_lifecycle=lambda:SimpleNamespace(stop_owned_process=lambda proc:calls.append(('stop',))),
       g3_compare=lambda first,second:{'first':str(first),'second':str(second)})
    result=m.run_g3g4(d,m.WT,run)
    assert calls==[('start','g3_on'),('stop',)]
    assert not (run/'g3g4/g3_off').exists()
    assert (off/'cold.json').read_text()=='original off'
    assert result['g3']['first']==str(off/'cold.json')


def test_exact_source_review_path_and_private_child_schema():
    assert m.REVIEW_DIR.name=='E2-R046a-v4'
    assert m.RID=='E2-R046a' and m.WT.name=='e2base1-p1'


def test_t20_admission_uses_closed_round_metadata_not_old_raw(tmp_path):
    receipt=tmp_path/'terminal.json'
    receipt.write_text(json.dumps({'schema':'ft_t20_batch71_failed_terminal_observation/v1','rid':'E2-R040','batch':71,
                                   'state':'failed_harness_pending_D04','round_tree_readonly':True,'controller_absent':True}))
    receipt.chmod(0o444);calls=[]
    gate=SimpleNamespace(require_closed_round=lambda rid,verdict:calls.append((rid,verdict)))
    assert m.require_t20_terminal_decision(gate,receipt,m.sha(receipt))==receipt
    assert calls==[('E2-R040','failed_harness')]


@pytest.mark.parametrize('failure_arm',['startup','seed12k','seed_45k','seed_real','two'])
def test_first_cleanup_failure_preserves_lock_without_retry(monkeypatch,tmp_path,failure_arm):
    proof=tmp_path/'proof.json';proof.write_text('{}')
    rounds=tmp_path/'rounds';rounds.mkdir()
    calls=[];released=[];active=[None]
    process=SimpleNamespace(pid=987)
    birth={'pid':987,'start_ticks':654,'pgid':987,'session':987}
    def stop(proc):
        calls.append(active[0])
        if active[0]==failure_arm:raise RuntimeError('first cleanup failed')
    def start(directory,*args):
        active[0]=directory.name.removeprefix('G_')
        return process
    owned=SimpleNamespace(stop_owned_process=stop,process_identity=lambda pid:birth,owned_group_alive=lambda pid:False)
    helper=SimpleNamespace(LOCK=tmp_path/'lock',
        require_closed_round=lambda *_:proof,require_r041_kept=lambda *_:proof,
        take_d07_gpu_lock=lambda *args:{'owner':m.RID,'batch':74},
        release_d07_gpu_lock=lambda owner:released.append(owner),
        require_gpu_idle=lambda:[0],dynamic_fixture_port=lambda:24567,
        start_server=start,load_owned_lifecycle=lambda:owned,write_new=m.write_new)
    monkeypatch.setattr(m.sys,'platform','linux')
    monkeypatch.setattr(m,'load_d07',lambda:helper)
    monkeypatch.setattr(m,'require_output_root',lambda *_:None)
    monkeypatch.setattr(m,'require_startup_review',lambda *_:{'approved':True})
    monkeypatch.setattr(m,'require_dry_run_receipt',lambda *_:{'path':'dry','sha256':'0'*64})
    monkeypatch.setattr(m,'packet',lambda *_:{})
    monkeypatch.setattr(m,'require_t20_terminal_decision',lambda *_:proof)
    monkeypatch.setattr(m,'require_receipt',lambda *_:None)
    monkeypatch.setattr(m,'require_predecessors',lambda *_:None)
    monkeypatch.setattr(m,'memory_plan',lambda:{'memory_ratio':'0.88','baseline_memory_ratio':'0.88','prediction_not_gpu_proof':True})
    monkeypatch.setattr(m,'apply_t06_memory_plan',lambda *_:None)
    monkeypatch.setattr(m,'require_t06_loaded_memory',lambda *_: {})
    monkeypatch.setattr(m,'invoke_t06_pause',lambda *_: {})
    monkeypatch.setattr(m,'summarize_t06_memory',lambda *_: {})
    monkeypatch.setattr(m,'write_memory_diff',lambda *_:None)
    monkeypatch.setattr(m,'invoke_seed',lambda *args:None)
    monkeypatch.setattr(m,'invoke_two',lambda *args:None)
    monkeypatch.setattr(m,'invoke_analysis',lambda *args,**kwargs:None)
    monkeypatch.setattr(m,'seed_paths',lambda:{role:proof for role in m.SEEDS})
    monkeypatch.setattr(m,'prepare_service',lambda _d,directory,*args,**kwargs:(directory.mkdir(parents=True,exist_ok=True),start(directory))[1])
    def g3(*args):
        if failure_arm=='startup':
            active[0]='startup'
            error=RuntimeError('startup cleanup failed')
            error.owned_process=process;error.owned_cleanup_failed=True
            raise error
        return {}
    monkeypatch.setattr(m,'run_g3g4',g3)
    with pytest.raises(RuntimeError,match='preserve GPU lock'):
        m.execute(output_root=rounds,owned_child=True,batch=74,launch_receipt=proof)
    assert calls.count(failure_arm)==(0 if failure_arm=='startup' else 1)
    assert released==[]
    closure=json.loads((rounds/m.RID/'owned_cleanup.json').read_text())
    assert closure['lock_released'] is False
    assert closure['service_pid']==987 and closure['service_birth']==birth


def test_dry_run_receipt_rejects_source_drift_and_requires_false_flags(monkeypatch,tmp_path):
    target=m.dry_run_directory(tmp_path);target.mkdir();receipt=target/'dry_run_receipt.json'
    sources=(m.__file__,m.SEED_CLIENT,m.D07_SOURCE,m.FILE_PREP_SOURCE,m.R055B_OBSERVER_SOURCE,m.PAUSE_HARNESS_SOURCE)
    value={'schema':'ft_r046a_dry_run/v2','rid':m.RID,'candidate_commit':m.CANDIDATE,'passed':True,
           'source_sha256':{str(Path(p).resolve()):m.sha(p) for p in sources},
           'owner':{'path':str(Path(m.__file__).resolve()),'uid':getattr(m.os,'getuid',lambda:None)(),
                    'user':m.os.environ.get('USER') or m.os.environ.get('LOGNAME')},
           'cwd':str(m.ROOT),'worktree':{'path':str(m.WT),'parent':str(m.WT.parent)},
           'formal_rid_directory_created':False,'service_started':False,'requests_sent':False,
           'gpu_lock_taken':False,'batch_allocated':False}
    receipt.write_text(json.dumps(value));receipt.chmod(0o444)
    assert m.require_dry_run_receipt(tmp_path)['sha256']==m.sha(receipt)
    receipt.chmod(0o644);value['source_sha256'][str(m.SEED_CLIENT.resolve())]='0'*64;receipt.write_text(json.dumps(value));receipt.chmod(0o444)
    with pytest.raises(RuntimeError,match='source SHA'):m.require_dry_run_receipt(tmp_path)


def test_dry_run_has_no_popen_lock_or_request_paths():
    source=Path(m.__file__).read_text(encoding='utf-8')
    body=source[source.index('def dry_run'):source.index('def require_dry_run_receipt')]
    assert 'subprocess.Popen' not in body and 'take_d07_gpu_lock' not in body and '.connect(' not in body
    assert 'run_g3g4(d,wt,target,file_dry_run=True)' in body and 'verify_cold=True' not in body
    for name in ('manifest.json','result.json','metadata/pre_d04.json','route_summary_two.json','two_decode.json'):
        assert name in body


def test_new_file_probe_is_json_serializable(tmp_path):
    value=m.file_output(tmp_path/'output.json','formal output',file_dry_run=True)
    assert isinstance(value,dict) and json.dumps({'cpu_file_probes':[value]})
    assert m.dry_run_directory(tmp_path).name==f'.dryrun_R046a_v5_{m.RID}'


def test_packet_requires_failed_r055_metadata_and_r055a_retained_cold_evidence(monkeypatch):
    monkeypatch.setattr(m,'load_d07',lambda:SimpleNamespace(checked_worktree=lambda _: {},verify_d07_tools=lambda _: {},dynamic_fixture_port=lambda:23456))
    monkeypatch.setattr(m,'require_retained_off',lambda:{})
    monkeypatch.setattr(m,'seed_paths',lambda:{role:Path(role) for role in m.SEEDS})
    packet=m.packet();assert 'R055a/R055b failed_harness sealed metadata; R055 gate ended by section ten' in packet['run_requires']
    assert 'R055a-gate-D06 failed_harness with independently PASS retained six cold arms' in packet['run_requires']
    assert 'R055-gate-D06 kept' not in packet['run_requires']
    assert 'foreign GPU lock deny' in packet['run_requires'] and packet['cuda_visible_devices_cpu_guard']==''


def test_file_preparation_whitelists_environment_and_writes_env_txt(tmp_path):
    fileprep=m.load_file_prepare()
    env={'CUDA_VISIBLE_DEVICES':'0','PYTHONPATH':'/safe/python','VIRTUAL_ENV':'/safe/venv',
         'PYTHONDONTWRITEBYTECODE':'1','PYTHONUNBUFFERED':'1','FT_DEV_ROUTE_TRACE':'/safe/route',
         'FT_SSH_PASSWORD':'fake-password','OTHER_SECRET':'fake-secret'}
    d=SimpleNamespace(clean_environment=lambda *_args,**_kwargs:env,serve_argv=lambda port:['ft','serve','--port',str(port)])
    prepared=fileprep.prepare_server_files(d,tmp_path/'arm',m.WT,23456,tmp_path/'route')
    assert prepared['env']==env
    for path in (tmp_path/'arm/ENV.json',tmp_path/'arm/ENV.txt',tmp_path/'arm/SERVE_CMD.txt'):
        text=path.read_text();assert text and 'fake-password' not in text and 'fake-secret' not in text
    assert 'CUDA_VISIBLE_DEVICES=0' in (tmp_path/'arm/ENV.txt').read_text()


def test_formal_service_requires_logged_parsed_arguments_and_dry_probes_same_files():
    helper=Path(m.FILE_PREP_SOURCE).read_text(encoding='utf-8')
    assert 'text.find("Parsed arguments")' in helper and 'serve_args.txt' in helper
    source=Path(m.__file__).read_text(encoding='utf-8')
    for name in ('owned_process.json','health.json','serve_args.txt'):
        assert name in source


def test_review_must_bind_the_exact_required_dry_receipt(monkeypatch,tmp_path):
    review_dir=tmp_path/'review';review_dir.mkdir();bound=tmp_path/'bound.json';required=tmp_path/'required.json'
    for path in (bound,required): path.write_text('{}');path.chmod(0o444)
    root=tmp_path/'root';wt=root/'wt';(root/'runs/plan_batches').mkdir(parents=True);(wt/'scripts').mkdir(parents=True)
    (root/'runs/plan_batches/e2_launch.py').write_text('launch')
    for name in ('agent_trace.py','_agent_trace_original.py','route_analyze.py','multisession_probe.py'):(wt/'scripts'/name).write_text(name)
    monkeypatch.setattr(m,'ROOT',root);monkeypatch.setattr(m,'WT',wt)
    mandatory={str(Path(m.__file__).resolve()):m.sha(m.__file__),str(m.D07_SOURCE):m.sha(m.D07_SOURCE),
               str(m.FILE_PREP_SOURCE):m.sha(m.FILE_PREP_SOURCE),str(m.SEED_CLIENT):m.sha(m.SEED_CLIENT),str(m.R055B_OBSERVER_SOURCE):m.sha(m.R055B_OBSERVER_SOURCE),str(m.PAUSE_HARNESS_SOURCE):m.sha(m.PAUSE_HARNESS_SOURCE),
               str(m.ROOT/'runs/plan_batches/e2_launch.py'):m.sha(m.ROOT/'runs/plan_batches/e2_launch.py')}
    mandatory.update({str(m.WT/'scripts'/name):m.sha(m.WT/'scripts'/name) for name in ('agent_trace.py','_agent_trace_original.py','route_analyze.py','multisession_probe.py')})
    document={'schema':'ft_r046a_source_startup_review/v1','verdict':'PASS','source_execution_ready':True,
              'candidate_commit':m.CANDIDATE,'retained_off':{'sealed':True},'sources':mandatory,
              'dry_run_receipt':str(bound),'dry_run_receipt_sha256':m.sha(bound)}
    review=review_dir/'review.json';review.write_text(json.dumps(document));review.chmod(0o444)
    pin=review_dir/'pin.json';pin.write_text(json.dumps({'schema':'ft_r046a_review_pin/v1','rid':m.RID,'review_sha256':m.sha(review)}));pin.chmod(0o444)
    review_dir.chmod(0o555)
    monkeypatch.setattr(m,'REVIEW_DIR',review_dir);monkeypatch.setattr(m,'require_retained_off',lambda:{'sealed':True})
    with pytest.raises(RuntimeError,match='different dry-run receipt'):
        m.require_startup_review({'path':str(required),'sha256':m.sha(required)})


def sealed_memory_fixture(monkeypatch,tmp_path):
 rounds=tmp_path/'rounds';round_path=rounds/'E2-R055b-gate-D06'/'round.json';round_path.parent.mkdir(parents=True)
 round_path.write_text(json.dumps({'verdict':'failed_harness'}));round_path.chmod(0o444)
 manifest=round_path.parent/'MANIFEST.sha256';manifest.write_text('sealed metadata');manifest.chmod(0o444)
 r055a=rounds/'E2-R055a-gate-D06'/'round.json';r055a.parent.mkdir();r055a.write_text(json.dumps({'verdict':'failed_harness','verdict_history':[{'reason':'628 MiB request / 625.69 MiB free'}]}));r055a.chmod(0o444)
 birth={'pid':41,'start_ticks':8};worker={'pid':43,'start_ticks':10};total=25250627584;minimum=1144717312
 def event(kind,time_ns,**values):return {'event':kind,'time_ns':time_ns,'service_birth':birth,'worker_birth':worker,'device':0,'free_bytes':minimum,'total_bytes':total,**values}
 record={'round_id':'E2-R055b-gate-D06','candidate_commit':m.CANDIDATE,'verdict':'failed_harness','retained_R055a_metadata':{'old_verdict_unchanged':'failed_harness','partial_cold_verdict':'PASS','independent_raw_review_sha256':'10161a2fe801414c3aa611487ead1d8a64a2e7baf1853d90ad4bca7fa7a08aa4','history_check_returncode':0},'cuda_memory_summary':{'schema':'ft_r055b_cuda_memory_summary/v1','service_birth':birth,'worker_birth':worker,'device':0,'complete':False,'events':[event('model_loaded',1),event('request_after',3,uid='91')],'min_free_bytes':minimum,'total_bytes':total}}
 review=tmp_path/'review.json';pin=tmp_path/'pin.json'
 def reseal():
  if review.exists():review.chmod(0o644)
  review.write_text(json.dumps(record));review.chmod(0o444);monkeypatch.setattr(m,'R055B_REVIEW_SHA',m.sha(review))
  if pin.exists():pin.chmod(0o644)
  pin.write_text(json.dumps({'rid':'E2-R055b-gate-D06','candidate_commit':m.CANDIDATE,'verdict':'failed_harness','round_sha256':m.sha(round_path),'manifest_sha256':m.sha(manifest),'review_sha256':m.sha(review)}));pin.chmod(0o444)
 monkeypatch.setattr(m,'ROUNDS',rounds);monkeypatch.setattr(m,'R055B_REVIEW',review);monkeypatch.setattr(m,'R055A_ROUND_SHA',m.sha(r055a));reseal()
 return pin,record,reseal


def test_memory_plan_uses_sealed_failed_review_and_only_changes_t06_argv(monkeypatch,tmp_path):
 pin,record,reseal=sealed_memory_fixture(monkeypatch,tmp_path)
 plan=m.memory_plan(pin)
 assert plan['memory_ratio']=='0.80' and plan['changed'] and plan['prediction_not_gpu_proof']
 assert plan['r055b_complete_pause_chain_required'] is False and plan['retained_six_cold_verdict']=='PASS'
 assert plan['predicted_free_bytes']>=m.MIN_FREE_BYTES
 assert plan['estimated_existing_route_bytes']>0 and plan['route_estimate_buffer_bytes']==256*1024**2
 d=SimpleNamespace(serve_argv=lambda _:['ft','serve','--memory-ratio','0.88','--prefill-layer-major'])
 assert d.serve_argv(1)[3]=='0.88'
 m.apply_t06_memory_plan(d,plan);assert d.serve_argv(1)[3]=='0.80'
 record['cuda_memory_summary']['events'].append({**record['cuda_memory_summary']['events'][0],'event':'request_error','error':'actual failure'})
 reseal()
 with pytest.raises(RuntimeError,match='observer event'):m.memory_plan(pin)
 record['cuda_memory_summary']['events'].pop();record['cuda_memory_summary']['events'][0]['free_bytes']=-1;reseal()
 with pytest.raises(RuntimeError,match='memory sample'):m.memory_plan(pin)
 record['cuda_memory_summary']['events'][0]['free_bytes']=1144717312;record['cuda_memory_summary']['device']=1;reseal()
 with pytest.raises(RuntimeError,match='identity'):m.memory_plan(pin)


def test_memory_plan_never_reopens_observer_or_raw_memory(monkeypatch,tmp_path):
 pin,record,reseal=sealed_memory_fixture(monkeypatch,tmp_path)
 digest=m.sha
 def metadata_only(path):
  if 'PAUSE_ON' in Path(path).parts:pytest.fail('predecessor raw must not be read')
  return digest(path)
 monkeypatch.setattr(m,'sha',metadata_only)
 assert m.memory_plan(pin)['memory_ratio']=='0.80'


def test_ratio_requires_complete_route_budget_and_rejects_below_080():
 minimum,total=1144717312,25250627584
 full_route=minimum-m.R055A_OOM_FREE_BYTES+m.ROUTE_OOM_ALLOCATION_BYTES
 assert m.calculate_t06_ratio(minimum,total,full_route)['memory_ratio']=='0.81'
 budget=full_route+m.ROUTE_ESTIMATE_BUFFER_BYTES
 assert m.calculate_t06_ratio(minimum,total,budget)['memory_ratio']=='0.80'
 assert minimum+7*total//100-budget<m.MIN_FREE_BYTES
 with pytest.raises(RuntimeError,match='below 0.80'):
  m.calculate_t06_ratio(minimum,total,budget+total//100)


def test_predecessors_keep_failures_and_retained_cold_proof(monkeypatch):
 calls=[];retained={'partial_cold_verdict':'PASS','cold_arms_replayed':False}
 monkeypatch.setattr(m,'load_pause_observer',lambda:SimpleNamespace(require_retained_cold=lambda legacy:retained))
 gate=SimpleNamespace(require_closed_round=lambda rid,verdict:calls.append((rid,verdict)))
 assert m.require_predecessors(gate)==retained
 assert ('E2-R055b-gate-D06','failed_harness') in calls
 assert all(verdict!='kept' for rid,verdict in calls if rid.startswith('E2-R055'))



def test_t06_pause_observer_prepares_real_command_and_reads_model_loaded(monkeypatch,tmp_path):
 def freeze(directory):
  observer=directory/'r055b_pause_observer.py';observer.write_text('observer');observer.chmod(0o444)
  startup=directory/'r055b_pause_startup.py';startup.write_text('startup');startup.chmod(0o444);return startup
 monkeypatch.setattr(m,'load_pause_observer',lambda:SimpleNamespace(_freeze_pause_observer=freeze))
 d=SimpleNamespace(clean_environment=lambda *_args,**kwargs:{'CUDA_VISIBLE_DEVICES':'0','PYTHONPATH':'p','VIRTUAL_ENV':'v','FT_DEV_ROUTE_TRACE':str(kwargs['trace_dir']),'FT_DEV_PAUSE_ENDPOINT':'1'},serve_argv=lambda p:['ft','serve','--port',str(p),'--memory-ratio','0.88'])
 prepared=m.prepare_service(d,tmp_path/'G_seed12k',m.WT,23456,tmp_path/'G_seed12k/route',start=False,pause_observer=True)
 assert prepared['argv'][:2]==[str(m.VENV/'bin/python'),str(tmp_path/'G_seed12k/r055b_pause_startup.py')]
 assert 'R055B_MODEL_MEMORY' in (tmp_path/'G_seed12k/ENV.txt').read_text() and 'FT_DEV_ROUTE_TRACE' in (tmp_path/'G_seed12k/ENV.txt').read_text()
 birth={'pid':77,'start_ticks':9,'execution_id':'77:9','pgid':77,'session':77};worker={'pid':79,'start_ticks':10,'execution_id':'79:10','pgid':77,'session':77};row={'schema':'ft_r055b_model_process_cuda/v1','event':'model_loaded','device':0,'service_birth':birth,'worker_birth':worker,'free_bytes':m.MIN_FREE_BYTES,'total_bytes':24*1024**3}
 (tmp_path/'G_seed12k/owned_process.json').write_text(json.dumps({'birth':{**birth,'state':'R'}}))
 (tmp_path/'G_seed12k/model_process_cuda.jsonl').write_text(json.dumps(row)+'\n')
 plan={'observer_source_sha256':m.sha(tmp_path/'G_seed12k/r055b_pause_observer.py')}
 assert m.require_t06_loaded_memory(tmp_path/'G_seed12k',plan,SimpleNamespace(pid=77))['event']=='model_loaded'
 (tmp_path/'G_seed12k/owned_process.json').write_text(json.dumps({'birth':{**birth,'state':'S'}}))
 assert m.require_t06_loaded_memory(tmp_path/'G_seed12k',plan,SimpleNamespace(pid=77))['event']=='model_loaded'
 for key in ('pid','start_ticks','execution_id','pgid','session'):
  wrong={**birth,key:'wrong' if key=='execution_id' else birth[key]+1,'state':'S'}
  (tmp_path/'G_seed12k/owned_process.json').write_text(json.dumps({'birth':wrong}))
  with pytest.raises(RuntimeError,match='owned service parent birth'):
   m.require_t06_loaded_memory(tmp_path/'G_seed12k',plan,SimpleNamespace(pid=77))
 (tmp_path/'G_seed12k/owned_process.json').write_text(json.dumps({'birth':{**birth,'state':'S'}}))
 row['free_bytes']=m.MIN_FREE_BYTES-1;(tmp_path/'G_seed12k/model_process_cuda.jsonl').write_text(json.dumps(row)+'\n')
 with pytest.raises(RuntimeError,match='below 1.5GiB'):
  m.require_t06_loaded_memory(tmp_path/'G_seed12k',plan,SimpleNamespace(pid=77))


def test_r046a_installs_actual_user_message_observer(monkeypatch,tmp_path):
 from test_r055b_owned_launch import install_fake_product,exec_observer,message
 owner=m.load_pause_observer()
 assert owner._pause_harness_v2_installed is True
 monkeypatch.setenv('R055B_MODEL_MEMORY',str(tmp_path/'memory.jsonl'))
 monkeypatch.setenv('R055_PAUSE_OBSERVATIONS',str(tmp_path/'pause.jsonl'))
 Scheduler,IO,Engine=install_fake_product(monkeypatch);exec_observer(owner)
 Engine();Scheduler()._process_one_msg(message('UserMsg',uid=31));IO()._reply_tokenizer_rank0([message('DetokenizeMsg',uid=31,finished=True,next_token=7)])
 rows=[json.loads(line) for line in (tmp_path/'memory.jsonl').read_text().splitlines()]
 assert [row['event'] for row in rows]==['model_loaded','request_before','request_after']
 assert rows[1]['uid']==rows[2]['uid']=='31'


def test_actual_r046a_pause_helper_retains_504_and_stops_normal_pause(monkeypatch,tmp_path):
 import io,urllib.error,urllib.request
 receipt={'status':'timeout','request_id':'pause-id'}
 def response(request,timeout):
  assert request.full_url=='http://127.0.0.1:51449/dev/pause'
  assert json.loads(request.data)=={'seconds':1.0,'timeout':5.0}
  raise urllib.error.HTTPError(request.full_url,504,'timeout',{},io.BytesIO(json.dumps(receipt).encode()))
 monkeypatch.setattr(urllib.request,'urlopen',response)
 with pytest.raises(RuntimeError,match='pause_chain_failure') as raised:
  m.invoke_t06_pause(51449,tmp_path)
 assert raised.value.pause_chain_failure is True
 assert json.loads((tmp_path/'pause_completed.json').read_text())=={**receipt,'http_status':504}


def test_r046a_pause_accepted_receipt_is_recorded(monkeypatch,tmp_path):
 receipt={'status':'accepted','request_id':'pause-id'};calls=[]
 monkeypatch.setattr(m,'load_pause_harness',lambda:SimpleNamespace(pause_request=lambda *args:(calls.append(args),receipt)[1]))
 assert m.invoke_t06_pause(51449,tmp_path)==receipt and calls==[(51449,1.0,5.0)]
 assert json.loads((tmp_path/'pause_completed.json').read_text())==receipt


def test_request_memory_summary_requires_every_boundary(monkeypatch,tmp_path):
 birth={'pid':1,'start_ticks':2};worker={'pid':3,'start_ticks':4}
 def row(event,time_ns,**fields):return {'schema':'ft_r055b_model_process_cuda/v1','event':event,'time_ns':time_ns,'service_birth':birth,'worker_birth':worker,'device':0,'free_bytes':m.MIN_FREE_BYTES,'total_bytes':25250627584,**fields}
 loaded=row('model_loaded',1)
 monkeypatch.setattr(m,'require_t06_loaded_memory',lambda *_:loaded)
 rows=[loaded,row('pause_after',2,request_id='pause-id'),row('request_before',3,uid='0'),row('request_after',4,uid='0')]
 path=tmp_path/'model_process_cuda.jsonl';path.write_text('\n'.join(json.dumps(value) for value in rows)+'\n')
 (tmp_path/'pause_completed.json').write_text(json.dumps({'status':'accepted','request_id':'pause-id'}))
 value=m.summarize_t06_memory(tmp_path,{'observer_source_sha256':'a'*64},None,1)
 assert value['complete'] and value['business_requests'][0]['uid']=='0'
 rows.pop(2);path.write_text('\n'.join(json.dumps(value) for value in rows)+'\n')
 with pytest.raises(RuntimeError,match='every business request-before/after'):
  m.summarize_t06_memory(tmp_path,{'observer_source_sha256':'a'*64},None,1)


def test_t06_formal_sequence_admits_memory_then_pause_then_business():
 source=Path(m.__file__).read_text(encoding='utf-8');body=source[source.index('def execute'):source.index('def main')]
 assert 'require_t06_loaded_memory(g,plan,process);invoke_t06_pause(port,g);trace=' in body
 assert 'require_t06_loaded_memory(g,plan,process);invoke_t06_pause(port,g);two=' in body
 assert 'summarize_t06_memory(g,plan,completed_process,12)' in body
 assert 'summarize_t06_memory(g,plan,completed_process,2)' in body
