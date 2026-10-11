import importlib.util, json
from pathlib import Path
import pytest
p=Path(__file__).parents[1]/'r049_t21_prepare.py';s=importlib.util.spec_from_file_location('r049',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_fixed_nine_process_protocol_and_training_partition():
 rows=m.assert_plan(m.arms());assert [x['name'] for x in rows]==list(m.PROCESS_ORDER)
 assert all(x['workloads']==['cold32k_1','cold32k_2','seed_45k','seed_real','two_decode_diff512'] for x in rows)
 assert [x['d0'] for x in rows]==[False]*6+[True]*3


def test_r046b_paths_and_packet_keep_the_exact_training_partition():
 assert m.TRAIN_ROUTE==m.ROUNDS/'E2-R046b/G_seed12k/route'
 assert m.HELDOUT=={'seed_45k':m.ROUNDS/'E2-R046b/G_seed_45k/trace_seed_45k.json','seed_real':m.ROUNDS/'E2-R046b/G_seed_real/trace_seed_real.json'}
 packet=m.packet()
 assert packet['training_route']=='E2-R046b/G_seed12k/route'
 assert packet['heldout_routes']==['E2-R046b/G_seed_45k','E2-R046b/G_seed_real','E2-R046b/G_two']
 assert 'R046b measured' in packet['run_requires'] and 'R046a' not in json.dumps(packet)
 argv=m.load_d07().serve_argv(40123)
 assert argv[argv.index('--memory-ratio')+1]=='0.88'
 assert all(argv[argv.index(flag)+1]=='98304' for flag in ('--kv-reserve-tokens','--max-seq-len-override'))


@pytest.fixture
def r046b_producer():
 path=Path(__file__).parents[1]/'r046b_d07_t06_prepare.py'
 spec=importlib.util.spec_from_file_location('_r049_r046b_manifest_producer',path);producer=importlib.util.module_from_spec(spec)
 spec.loader.exec_module(producer)
 return producer


@pytest.fixture
def t06_manifest(monkeypatch,tmp_path,r046b_producer):
 monkeypatch.setattr(m,'ROUNDS',tmp_path)
 path=tmp_path/'E2-R046b/manifest.json';run=path.parent;run.mkdir()
 def write_fixture(target):
  target.parent.mkdir(parents=True,exist_ok=True);target.write_text('{"fixture_only":true,"not_measurement":true}\n')
 for arm in ('g3_off','g3_on'):
  for name in ('cold.json','model_process_cuda.jsonl','cuda_memory_summary.json','serve_args_diff.json','serve.log'):
   write_fixture(run/'g3g4'/arm/name)
 g_dirs={role:run/f'G_{role}' for role in (*r046b_producer.SEEDS,'two')}
 for role,directory in g_dirs.items():
  for name in ('serve.log','model_process_cuda.jsonl','cuda_memory_summary.json','pause_completed.json','serve_args_diff.json'):
   write_fixture(directory/name)
  write_fixture(directory/'route/fixture_only.json');write_fixture(run/f'route_summary_{role}.json')
  if role=='two':write_fixture(directory/'two_decode.json')
  else:
   trace=directory/f'trace_{role}.json';write_fixture(trace);write_fixture(trace.with_suffix('.seed_binding.json'))
   trace.with_suffix('.seed_binding.json').write_text(json.dumps({'schema':'ft_t06_seed_trace_binding/v2','seed_raw_sha256':r046b_producer.SEEDS[role],'window':98304,'completion_reserve_tokens':2048,'max_prompt_tokens':96256,'max_tokens':2048,'completed_k':12,'window_hit':None,'window_hit_count':0}))
 document=r046b_producer.manifest(run,g_dirs,{'fixture_only':True},{'fixture_only':True})
 path.write_text(json.dumps(document))
 return path,document


def test_r046b_manifest_requires_exact_identity_and_partition(t06_manifest):
 path,_=t06_manifest
 assert m.require_t06_metadata()==path


def test_current_r046b_producer_manifest_is_consumed_without_translation(t06_manifest,r046b_producer):
 path,document=t06_manifest
 assert document['schema']=='ft_r046b_route_manifest/v1' and document['rid']==r046b_producer.RID=='E2-R046b'
 assert document['candidate_commit']==r046b_producer.CANDIDATE==m.PARENT
 assert document['memory_ratio']==r046b_producer.MEMORY_RATIO=='0.80'
 assert document['window']=={'kv_reserve_tokens':98304,'max_seq_len_override':98304,'completion_reserve_tokens':2048,'max_prompt_tokens':96256}
 assert [arm['role'] for arm in document['arms']]==['seed12k','seed_45k','seed_real','two']
 assert [arm['d15_training_input'] for arm in document['arms']]==[True,False,False,False]
 assert document['files'] and m.require_t06_metadata()==path


@pytest.mark.parametrize(('key','value'),[
 ('rid','E2-R046a'),('rid','E2-R046c'),
 ('schema','ft_r046_route_manifest/v1'),('schema','ft_t06_route_manifest/v1'),('candidate_commit','wrong-tree'),
])
def test_r046b_manifest_rejects_failed_old_round_and_other_identity(t06_manifest,key,value):
 path,document=t06_manifest;document[key]=value;path.write_text(json.dumps(document))
 with pytest.raises(RuntimeError,match='R046b T06 route manifest identity'):
  m.require_t06_metadata()


@pytest.mark.parametrize('change',[
 lambda doc:doc.update(d15_training_route='G_seed_45k/route'),
 lambda doc:doc.update(heldout_routes=['G_seed12k/route','G_seed_real/route','G_two/route']),
 lambda doc:doc['heldout_routes'].append('G_two/route'),
 lambda doc:doc['arms'].append(dict(doc['arms'][0])),
 lambda doc:doc['arms'][1].update(role='seed12k'),
 lambda doc:doc['arms'][1].update(d15_training_input=True),
 lambda doc:doc['arms'][0].update(d15_training_input=1),
 lambda doc:doc['arms'][2].update(directory='G_seed12k'),
])
def test_r046b_manifest_rejects_partition_pollution(t06_manifest,change):
 path,document=t06_manifest;change(document);path.write_text(json.dumps(document))
 with pytest.raises(RuntimeError,match='R046b T06 .* binding|R046b T06 train/heldout'):
  m.require_t06_metadata()


def test_r049_rejects_previous_window_manifest(t06_manifest):
 path,document=t06_manifest;document['window']['kv_reserve_tokens']=49152;path.write_text(json.dumps(document))
 with pytest.raises(RuntimeError,match='release window differs'):m.require_t06_metadata()


@pytest.mark.parametrize('registered',[
 {'E2-R046a':'failed_harness'}, {'E2-R046b':'failed_harness'},
])
def test_r049_admission_does_not_use_failed_a_or_failed_b(monkeypatch,tmp_path,registered):
 calls=[]
 class D:
  LOCK=tmp_path/'missing.lock'
  def require_closed_round(self,rid,verdict):
   calls.append((rid,verdict))
   if registered.get(rid)!=verdict:raise RuntimeError(f'{rid} formal D04 verdict is not {verdict}')
   return tmp_path/rid/'round.json'
 monkeypatch.setattr(m,'load_d07',lambda:D())
 monkeypatch.setattr(m.subprocess,'check_output',lambda *_args,**_kwargs:pytest.fail('failed predecessor reached candidate commands'))
 monkeypatch.setattr(m,'require_t06_metadata',lambda:pytest.fail('failed predecessor reached route metadata'))
 with pytest.raises(RuntimeError,match='E2-R046b formal D04 verdict is not measured'):
  m.admission()
 assert calls==[('E2-R046b','measured')]


def test_r049_admission_uses_r046b_measured_closure_and_exact_manifest(monkeypatch,t06_manifest):
 path,_=t06_manifest;calls=[]
 class D:
  LOCK=path.parent.parent/'missing.lock'
  def require_closed_round(self,rid,verdict):
   calls.append((rid,verdict));return path.parent.parent/rid/'round.json'
 monkeypatch.setattr(m,'load_d07',lambda:D())
 monkeypatch.setattr(m.subprocess,'check_output',lambda argv,**_kwargs:m.CANDIDATE if argv[-2:]==['rev-parse','HEAD'] else '')
 monkeypatch.setattr(m.subprocess,'run',lambda *_args,**_kwargs:type('Completed',(),{'returncode':0})())
 monkeypatch.setattr(m,'require_review',lambda *_args:path.parent.parent/'startup_review.json')
 _,closures,manifest,_=m.admission()
 assert calls==[('E2-R046b','measured'),('E2-R050-gate-D15','kept')]
 assert set(closures)=={'E2-R046b','E2-R050-gate-D15'} and manifest==path
def test_full_text_difference_stops():
 base={'texts':{'cold':'same','seed':'same'}}; rows={x:dict(base) for x in ('L1','P1','PA1','L2','P2','PA2')};assert m.assert_bitwise(rows)
 rows['PA2']={'texts':{'cold':'changed'}}
 with pytest.raises(RuntimeError,match='changed full text'):m.assert_bitwise(rows)
def test_d0_cost_includes_swap_and_actual_generated_tokens():
 journal={'sha256':'j'*64,'worker_birth':{'pid':2},'decode':[{'active':10,'missing':3,'hits':7,'h2d_bytes':50,'rids':[45],'step':1},{'active':10,'missing':2,'hits':8,'h2d_bytes':40,'rids':[46],'step':2}],'adapt':[{'policy_swap_bytes_delta':20,'rids':[45],'step':1}]}
 row=m.diagnostic_metrics(journal,{'seed_45k':10,'seed_real':10},{'seed_45k':[45],'seed_real':[46]});assert row['roles']['seed_45k']['h2d_plus_swap_bytes_per_token']==7 and row['roles']['seed_real']['common_miss_rate']==.2
 with pytest.raises(RuntimeError):m.diagnostic_metrics(journal,{'seed_45k':0,'seed_real':10},{'seed_45k':[45],'seed_real':[46]})
def test_default_is_inert(capsys):
 assert m.main([])==0;d=json.loads(capsys.readouterr().out);assert d['rid']==m.RID and not d['requests_sent']


def test_dry_run_declares_nine_arms_and_no_process_or_lock():
 source=Path(m.__file__).read_text(encoding='utf-8');body=source[source.index('def dry_run'):source.index('def main')]
 assert 'subprocess.Popen' not in body and 'take_d07_gpu_lock' not in body and '.connect(' not in body
 assert 'run_measurements(file_dry_run=True' in body and "formal_rid_directory_created':False" in body


def test_controller_reserves_exactly_once_after_admission(monkeypatch, tmp_path):
 calls=[]
 class Owned:
  def verified_module(self,*_): return type('H',(),{'next_batch':lambda self,root:calls.append(('batch',root)) or 81})()
  def reserve_process(self,helper,batch,rid,argv,receipt,reserved):
   calls.append(('reserve',batch,rid,argv));return {**reserved,'state':'launched','batch_pid':777}
  def process_identity(self,pid): return {'pid':pid,'start_ticks':9,'extra':'ignored'}
 d=type('D',(),{'ATOMIC_HELPER_SHA':'x','argv_sha256':lambda self,argv:'argv','process_birth':lambda self:{'pid':1,'start_ticks':2,'execution_id':'1:2'},'load_owned_lifecycle':lambda self:Owned(),'publish_child_binding':lambda self,path,row,child,**_:calls.append(('publish',child)) or {**row,'child':child}})()
 monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m,'require_dry_run_receipt',lambda:{'path':'dry','sha256':'0'*64});monkeypatch.setattr(m,'admission',lambda *_:(d,None,None,None));monkeypatch.setattr(m,'ROOT',tmp_path)
 out=m.controller();assert [x[0] for x in calls]==['batch','reserve','publish'];assert out['child']=={'pid':777,'start_ticks':9,'execution_id':'777:9'}


def test_bad_child_receipt_rejected_before_lock(monkeypatch, tmp_path):
 calls=[];d=type('D',(),{'take_d07_gpu_lock':lambda *_:pytest.fail('bad receipt took lock')})()
 monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m,'require_dry_run_receipt',lambda:{'path':'dry','sha256':'0'*64});monkeypatch.setattr(m,'load_d07',lambda:d);monkeypatch.setattr(m,'admission',lambda *_:None);monkeypatch.setattr(m,'require_receipt',lambda *_:(_ for _ in ()).throw(RuntimeError('bad receipt')))
 with pytest.raises(RuntimeError,match='bad receipt'):m.child(81,tmp_path/'launch.json')
 assert calls==[]


def test_foreign_lock_admission_precedes_batch(monkeypatch):
 class D:
  def load_owned_lifecycle(self): pytest.fail('foreign lock must precede batch helper')
 monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m,'require_dry_run_receipt',lambda:{'path':'dry','sha256':'0'*64});monkeypatch.setattr(m,'admission',lambda *_:(_ for _ in ()).throw(RuntimeError('foreign GPU lock exists')))
 with pytest.raises(RuntimeError,match='foreign GPU lock'):m.controller()


def test_main_dispatch(monkeypatch,tmp_path):
 calls=[];monkeypatch.setattr(m,'controller',lambda:calls.append('controller'));monkeypatch.setattr(m,'child',lambda b,r:calls.append(('child',b,r)))
 assert m.main(['--run'])==0;assert m.main(['--run','--owned-child','--batch','2','--launch-receipt',str(tmp_path/'r')])==0
 assert calls[0]=='controller' and calls[1][0:2]==('child',2)


def test_nine_services_production_before_d0(monkeypatch,tmp_path):
 starts=[];stops=[]
 d=type('D',(),{'dynamic_fixture_port':lambda self:40000+len(starts)})()
 monkeypatch.setattr(m,'ROUNDS',tmp_path);monkeypatch.setattr(m,'load_d07',lambda:d)
 def profile(run):
  p=run/'seed12k_only.strp';p.write_bytes(b'profile');return p,['build','seed12k']
 monkeypatch.setattr(m,'build_profile',profile)
 monkeypatch.setattr(m,'start_service',lambda d,directory,port,policy,profile,d0:starts.append((directory.name,policy,d0,profile.name)) or object())
 monkeypatch.setattr(m,'stop_service',lambda d,process:stops.append(process))
 def workload(directory,port,spec,*_):
  policy=spec['policy'];rate={'lru':2.,'profile':3.,'profile+adapt':4.}[policy]
  if spec['production']:return {'d0_enabled':False,'texts':{'cold':'same','heldout':'same','two':'same'},'timing':{name:{'ttft_s':1.,'decode_tps':rate,'completion_tokens':128} for name in ('cold32k_1','cold32k_2','seed_45k','seed_real','two_decode_diff512')}}
  miss={'lru':3,'profile':2,'profile+adapt':1}[policy];bytes_={'lru':3,'profile':2,'profile+adapt':1}[policy]
  return {'d0_enabled':True,'generated_tokens':10,'texts':production['L1']['texts'] if (production:={}) else {'cold':'same','heldout':'same','two':'same'},'timing':{name:{'ttft_s':1.,'decode_tps':rate,'completion_tokens':128} for name in ('cold32k_1','cold32k_2','seed_45k','seed_real','two_decode_diff512')},'request_input_bindings':{'seed_45k':[{'ack_uids':[45]}],'seed_real':[{'ack_uids':[46]}]}}
 monkeypatch.setattr(m,'run_workloads',workload)
 monkeypatch.setattr(m,'_d0_rows',lambda path: {'sha256':'j'*64,'worker_birth':{'pid':2},'decode':[{'active':10,'missing':{'L_D0':3,'P_D0':2,'PA_D0':1}[path.name],'hits':{'L_D0':7,'P_D0':8,'PA_D0':9}[path.name],'h2d_bytes':{'L_D0':3,'P_D0':2,'PA_D0':1}[path.name],'rids':[45],'step':1},{'active':10,'missing':{'L_D0':3,'P_D0':2,'PA_D0':1}[path.name],'hits':{'L_D0':7,'P_D0':8,'PA_D0':9}[path.name],'h2d_bytes':{'L_D0':3,'P_D0':2,'PA_D0':1}[path.name],'rids':[46],'step':2}],'adapt':[{'policy_swap_bytes_delta':0,'rids':[45],'step':1}]})
 result=m.run_measurements(88)
 assert [x[0] for x in starts]==list(m.PROCESS_ORDER) and [x[2] for x in starts]==[False]*6+[True]*3
 assert len(stops)==9 and result['production_speed_excludes_d0'] and result['benefit_claimed'] and result['heldout_benefit']['replicates']==2


def test_measurement_cleanup_failure_marks_error(monkeypatch,tmp_path):
 d=type('D',(),{'dynamic_fixture_port':lambda self:40000})()
 monkeypatch.setattr(m,'ROUNDS',tmp_path);monkeypatch.setattr(m,'load_d07',lambda:d)
 def profile(run):
  path=run/'p.strp';path.write_bytes(b'x');return path,['build']
 monkeypatch.setattr(m,'build_profile',profile)
 monkeypatch.setattr(m,'start_service',lambda *_:object());monkeypatch.setattr(m,'run_workloads',lambda *_:(_ for _ in ()).throw(RuntimeError('probe failed')))
 monkeypatch.setattr(m,'stop_service',lambda *_:(_ for _ in ()).throw(RuntimeError('stop failed')))
 with pytest.raises(RuntimeError,match='stop failed') as error:m.run_measurements(9)
 assert getattr(error.value,'owned_cleanup_failed',False)


def test_startup_failure_keeps_owned_process_for_failed_cleanup(monkeypatch,tmp_path):
 process=type('P',(),{'pid':321,'poll':lambda self:None})()
 lifecycle=type('L',(),{'process_identity':lambda self,pid:{'pid':pid,'pgid':0,'session':0}})()
 d=type('D',(),{'clean_environment':lambda *_:{},'serve_argv':lambda *_:['ft','serve'],'load_owned_lifecycle':lambda self:lifecycle})()
 monkeypatch.setattr(m.subprocess,'Popen',lambda *args,**kwargs:process)
 monkeypatch.setattr(m,'stop_service',lambda *_:(_ for _ in ()).throw(RuntimeError('cleanup failed')))
 with pytest.raises(RuntimeError,match='cleanup failed') as error:m.start_service(d,tmp_path,40123,'lru',tmp_path/'p',False)
 assert getattr(error.value,'owned_cleanup_failed',False) and error.value.owned_process is process


class _Tokenizer:
 def __init__(self): self.calls=[]
 def apply_chat_template(self,messages,**kwargs): self.calls.append((messages,kwargs));return '|'.join(item['content'] for item in messages)
 def encode(self,text,add_special_tokens=False): return list(range(1,len(text)+1))

def test_cold_binding_is_request_ids_and_service_count(monkeypatch,tmp_path):
 token=_Tokenizer(); out=tmp_path/'cold.json';out.write_text(json.dumps({'record':{'prompt_tokens':3}}))
 probe=type('Probe',(),{'build_text':lambda self,tokenizer,target,cold_id:('abc',target)})()
 d=type('D',(),{'COLD_RAW_SHA':'c'*64})()
 monkeypatch.setattr(m,'_frozen_probe',lambda _:probe);monkeypatch.setattr(m,'_frontend_contract',lambda:{'frontend_renderer_sha256':'f'*64})
 row=m._cold_binding(d,token,'cold',out)
 assert row['input_ids_sha256']==m._token_sha256([1,2,3]) and row['service_prompt_tokens_equal_frontend']
 assert row['binding_origin']=='client_frontend_reconstruction_not_server_capture' and not row['server_capture']
 assert token.calls[0][1]['enable_thinking'] is False

def test_agent_binding_requires_service_prompt_tokens_and_exact_template(monkeypatch,tmp_path):
 monkeypatch.setattr(m,'_frontend_contract',lambda:{'frontend_renderer_sha256':'f'*64})
 token=_Tokenizer(); trace=tmp_path/'trace.json'; replay=tmp_path/'replay.json'
 trace.write_text(json.dumps({'meta':{'params':{'thinking':False}},'tools':[{'type':'function'}],'rounds':[{'messages':[{'role':'user','content':'abc'}]}]}))
 replay.write_text(json.dumps({'rounds':[{'round':0,'prompt_tokens':3,'completion_tokens':1,'token_events':[{'uid':11,'completion_tokens_delta':1,'completion_tokens_cumulative':1}]}]}))
 rows=m._agent_bindings(token,trace,replay)
 assert rows[0]['frontend_token_count']==3 and token.calls[0][1]=={'tokenize':False,'add_generation_prompt':True,'enable_thinking':False,'tools':[{'type':'function'}]}
 replay.write_text(json.dumps({'rounds':[{'round':0,'prompt_tokens':2}]}))
 with pytest.raises(RuntimeError,match='possible truncation'):
  m._agent_bindings(token,trace,replay)

def test_two_decode_tap_keeps_interleaved_ack_streams_separate(monkeypatch,tmp_path):
 writes=[]
 class Probe:
  def _sse_events(self,response):
   yield from response
  def run_two_decode(self,args):
   streams={7:[{'ft_dev':{'uid':7},'choices':[{'delta':{'content':'A','tool_calls':[{'id':'t7'}]}}]},{'choices':[{'delta':{'reasoning_content':'R7'}}]}],8:[{'ft_dev':{'uid':8},'choices':[{'delta':{'content':'B'}}]},{'choices':[{'delta':{'tool_calls':[{'id':'t8','function':{'arguments':'{}'}}]}}]}]}
   barrier=__import__('threading').Barrier(2)
   def consume(stream):
    iterator=self._sse_events(stream);next(iterator);barrier.wait();list(iterator)
   threads=[__import__('threading').Thread(target=consume,args=(stream,)) for stream in streams.values()]
   [thread.start() for thread in threads];[thread.join() for thread in threads]
   return {'schema':'multisession_probe/v1','reps':[{'rep':0,'_records':[{'uid':7,'token_events':[],'usage':{'prompt_tokens':3},'completion_tokens':512},{'uid':8,'token_events':[],'usage':{'prompt_tokens':3},'completion_tokens':512}],'prompt_sha256':['a'*64,'b'*64],'frontend_token_counts':[3,3]}]}
  def _per_way(self,row,path): return {'uid':row['uid'],'token_timestamps':str(path)}
  def write_exclusive(self,path,value): writes.append((Path(path).name,value));Path(path).write_text(json.dumps(value))
 probe=Probe();original=probe._sse_events
 monkeypatch.setattr(m,'_load_probe_module',lambda:probe);monkeypatch.setattr(m,'_frontend_contract',lambda:{'frontend_renderer_sha256':'f'*64});monkeypatch.setattr(m,'sha',lambda path:'d'*64 if Path(path).name=='multisession_probe.py' else __import__('hashlib').sha256(Path(path).read_bytes()).hexdigest())
 target,rows=m._run_two_decode_bound(tmp_path,'http://localhost/v1','lru',tmp_path/'p',False)
 assert probe._sse_events.__func__ is original.__func__ and [x['input_ids_sha256'] for x in rows]==['a'*64,'b'*64]
 sidecars=[value for name,value in writes if name.endswith('.sse.json')]
 assert len(sidecars)==2 and sidecars[0]['uid']==7 and sidecars[1]['uid']==8
 assert 't7' in json.dumps(sidecars[0]) and 't8' not in json.dumps(sidecars[0])
 assert 't8' in json.dumps(sidecars[1]) and 't7' not in json.dumps(sidecars[1])
 assert 'full_text' in json.loads(target.read_text())['reps'][0]['per_way'][0]


def test_first_cold_difference_stops_before_second_workload(monkeypatch,tmp_path):
 token=_Tokenizer();monkeypatch.setattr(m,'_load_tokenizer',lambda _:token);monkeypatch.setattr(m,'_cold_binding',lambda *_:{'kind':'cold','input_ids_sha256':'c'*64})
 calls=[]
 class D:
  def invoke_cold_eq(self,*args):
   calls.append(args[2]);Path(args[-1]).write_text(json.dumps({'record':{'prompt_tokens':1},'text':'different'}))
 monkeypatch.setattr(m,'load_d07',lambda:D())
 baseline={'texts':{'cold32k_1':'expected'},'request_input_bindings':{'cold32k_1':{'kind':'cold','input_ids_sha256':'c'*64}}}
 with pytest.raises(m.T21NotMet):m.run_workloads(tmp_path,40125,{'name':'P1','policy':'lru','d0':False},baseline)
 assert calls==[f'{m.RID}-cold1'] and not (tmp_path/'cold32k_2.json').exists()

def test_run_workloads_records_three_client_bindings(monkeypatch,tmp_path):
 token=_Tokenizer(); traces={}
 for role in ('seed_45k','seed_real'):
  trace=tmp_path/f'{role}.json';trace.write_text(json.dumps({'meta':{'params':{'thinking':False}},'rounds':[{'messages':[{'role':'user','content':'abc'}]}]}));traces[role]=trace
 monkeypatch.setattr(m,'HELDOUT',traces);monkeypatch.setattr(m,'_load_tokenizer',lambda _:token)
 class D:
  def invoke_cold_eq(self,*args): Path(args[-1]).write_text(json.dumps({'record':{'prompt_tokens':3,'completion_tokens':128},'text':'cold'}))
 monkeypatch.setattr(m,'load_d07',lambda:D())
 monkeypatch.setattr(m,'_cold_binding',lambda *args:{'kind':'cold_eq','input_ids_sha256':'c'*64})
 def timed(port,trace,target,*_):
  target.write_text(json.dumps({'rounds':[{'round':0,'prompt_tokens':3,'completion_tokens':10,'text':'heldout','token_events':[{'t_s':.1}]}]}));return {'sse_timing_bound':True}
 monkeypatch.setattr(m,'_timed_agent_replay',timed)
 monkeypatch.setattr(m,'_agent_bindings',lambda *args:[{'kind':'heldout_agent_replay','input_ids_sha256':'a'*64}])
 def two(directory,*_):
  target=directory/'two_decode.json';target.write_text(json.dumps({'completion_tokens':1024,'text':'two'}));return target,[{'kind':'two_decode','input_ids_sha256':'b'*64}]
 monkeypatch.setattr(m,'_run_two_decode_bound',two)
 row=m.run_workloads(tmp_path,40125,{'name':'L1','policy':'lru','d0':False})
 assert set(row['request_input_bindings'])=={'cold32k_1','cold32k_2','seed_45k','seed_real','two_decode_diff512'}
 assert row['d0_enabled'] is False and len(row['texts'])==5


def test_frontend_contract_binds_candidate_render_semantics(monkeypatch,tmp_path):
 source=tmp_path/'tokenize.py';source.write_text('self.tokenizer.apply_chat_template(\n tokenize=False,\n add_generation_prompt=True,\n **chat_template_kwargs,\n)\nadd_special_tokens=not templated\nchat_template_kwargs = {**chat_template_kwargs, "tools": tools}')
 monkeypatch.setattr(m,'FRONTEND_RENDER',source)
 row=m._frontend_contract()
 assert row['frontend_renderer_sha256']==m.sha(source) and 'add_generation_prompt=True' in row['frontend_template_contract']
 source.write_text('drift')
 with pytest.raises(RuntimeError,match='rendering contract differs'):
  m._frontend_contract()

def test_agent_thinking_on_preserves_absent_template_toggle(monkeypatch,tmp_path):
 monkeypatch.setattr(m,'_frontend_contract',lambda:{})
 token=_Tokenizer(); trace=tmp_path/'trace.json'; replay=tmp_path/'replay.json'
 trace.write_text(json.dumps({'meta':{'params':{'thinking':True}},'rounds':[{'messages':[{'role':'user','content':'abc'}]}]}));replay.write_text(json.dumps({'rounds':[{'round':0,'prompt_tokens':3,'completion_tokens':1,'token_events':[{'uid':11,'completion_tokens_delta':1,'completion_tokens_cumulative':1}]}]}))
 m._agent_bindings(token,trace,replay)
 assert token.calls[0][1]=={'tokenize':False,'add_generation_prompt':True}


def test_two_decode_tap_rejects_missing_or_duplicate_ack_uid():
 class Probe:
  def _sse_events(self,response):yield from response
  def run_two_decode(self,args):
   list(self._sse_events([{'choices':[{'delta':{'content':'missing'}}]}]))
   return {'reps':[]}
 with pytest.raises(RuntimeError,match='lacks ACK UID'):m._two_decode_with_sse(Probe(),object())
 class Duplicate(Probe):
  def run_two_decode(self,args):
   list(self._sse_events([{'ft_dev':{'uid':7},'choices':[{'delta':{'content':'a'}}]}]))
   list(self._sse_events([{'ft_dev':{'uid':7},'choices':[{'delta':{'content':'b'}}]}]))
   return {'reps':[]}
 with pytest.raises(RuntimeError,match='duplicate ACK UID'):m._two_decode_with_sse(Duplicate(),object())


def test_production_timing_rejects_elapsed_only_and_requires_each_workload(tmp_path):
 (tmp_path/'cold.json').write_text(json.dumps({'record':{'completion_tokens':128,'ttft_s':1.2,'decode_tps':10.}}))
 assert m._timing_from_document(tmp_path/'cold.json','cold32k_1')['decode_tps']==10.
 (tmp_path/'heldout.json').write_text(json.dumps({'rounds':[{'completion_tokens':8,'elapsed_s':3.,'ttft_s':.2}]}))
 assert m._timing_from_document(tmp_path/'heldout.json','seed_45k') is None
 with pytest.raises(RuntimeError,match='seed_real'):m._require_production_timing({'cold32k_1':{},'cold32k_2':{},'seed_45k':{},'two_decode_diff512':{}})

def test_d0_journal_rejects_missing_terminal_or_bad_delta(tmp_path):
 path=tmp_path/'d0_journal.jsonl';birth={'pid':7,'start_ticks':8,'execution_id':'7:8'}
 rows=[{'seq':1,'kind':'install','worker_birth':birth},{'seq':2,'kind':'decode','worker_birth':birth,'active':5,'missing':2,'fetched':2,'hits':3,'expert_row_bytes':4,'h2d_bytes':8,'rids':[45],'step':1}]
 path.write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
 with pytest.raises(RuntimeError,match='complete'):m._d0_rows(tmp_path)
 rows.append({'seq':3,'kind':'terminal','status':'complete','worker_birth':birth});path.write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
 assert m._d0_rows(tmp_path)['decode'][0]['h2d_bytes']==8


def test_benefit_gate_requires_two_replicates_and_only_heldout_metrics():
 def arm(rate):return {'timing':{role:{'decode_tps':rate,'completion_tokens':128} for role in m.HELDOUT}}
 production={'L1':arm(10),'L2':arm(10),'P1':arm(12),'P2':arm(12),'PA1':arm(13),'PA2':arm(13)}
 def diag(miss,bytes_):return {'roles':{role:{'common_miss_rate':miss,'h2d_plus_swap_bytes_per_token':bytes_,'completion_tokens':128} for role in m.HELDOUT}}
 diagnostic={'L_D0':diag(.4,10),'P_D0':diag(.3,9),'PA_D0':diag(.2,8)}
 assert m.benefit_gate(production,diagnostic)['replicates']==2
 diagnostic['P_D0']=diag(.5,9)
 with pytest.raises(m.T21NotMet,match='benefit'):m.benefit_gate(production,diagnostic)


def test_d0_journal_is_read_only_after_service_cleanup(monkeypatch,tmp_path):
 order=[];d=type('D',(),{'dynamic_fixture_port':lambda self:40000})()
 monkeypatch.setattr(m,'ROUNDS',tmp_path);monkeypatch.setattr(m,'load_d07',lambda:d)
 def profile(run):
  path=run/'p.strp';path.write_bytes(b'p');return path,['build']
 monkeypatch.setattr(m,'build_profile',profile)
 rows=[{'name':'L_D0','policy':'lru','d0':True,'production':False,'workloads':[]}]
 monkeypatch.setattr(m,'arms',lambda:rows);monkeypatch.setattr(m,'assert_plan',lambda _:rows)
 monkeypatch.setattr(m,'start_service',lambda *_:object())
 monkeypatch.setattr(m,'run_workloads',lambda *_:{'d0_enabled':True,'generated_tokens':4,'timing':{'seed_45k':{'completion_tokens':2},'seed_real':{'completion_tokens':2}},'request_input_bindings':{'seed_45k':[{'ack_uids':[45]}],'seed_real':[{'ack_uids':[46]}]}})
 monkeypatch.setattr(m,'stop_service',lambda *_:order.append('stopped'))
 monkeypatch.setattr(m,'_d0_rows',lambda _: (order.append('read') or {'sha256':'j'*64,'worker_birth':{'pid':2},'decode':[{'active':4,'missing':1,'hits':3,'h2d_bytes':4,'rids':[45],'step':1},{'active':4,'missing':1,'hits':3,'h2d_bytes':4,'rids':[46],'step':2}],'adapt':[]}))
 monkeypatch.setattr(m,'assert_bitwise',lambda _:True);monkeypatch.setattr(m,'benefit_gate',lambda *_:{})
 m.run_measurements(7);assert order==['stopped','read']

def test_start_service_uses_d0_helper_only_for_diagnostics(monkeypatch,tmp_path):
 captured=[];proc=type('P',(),{'pid':9,'poll':lambda self:None})()
 life=type('L',(),{'process_identity':lambda self,pid:{'pid':pid,'pgid':pid,'session':pid},'stop_owned_process':lambda self,process:None})()
 d=type('D',(),{'clean_environment':lambda *_:{},'serve_argv':lambda _,port:['ft','serve','--port',str(port)],'load_owned_lifecycle':lambda self:life})()
 def popen(argv,**kwargs):
  captured.append((argv,kwargs['env']));kwargs['stdout'].write('Parsed arguments\nServerArgs(model_path="x")\n');kwargs['stdout'].flush();return proc
 monkeypatch.setattr(m.subprocess,'Popen',popen)
 class Response:
  def __enter__(self):return self
  def __exit__(self,*_):return False
  def read(self):return b'{"status":"ok"}'
 monkeypatch.setattr(m.urllib.request,'urlopen',lambda *_,**__:Response())
 (tmp_path/'prod').mkdir();(tmp_path/'diag').mkdir()
 production=m.start_service(d,tmp_path/'prod',40120,'lru',tmp_path/'p',False)
 assert production is proc and captured[0][0][0]=='ft' and 'FT_T21_DIAG_JOURNAL' not in captured[0][1]
 diagnostic=m.start_service(d,tmp_path/'diag',40121,'lru',tmp_path/'p',True)
 assert diagnostic is proc and captured[1][0][1]==str(m.D0_HELPER) and 'FT_T21_DIAG_JOURNAL' in captured[1][1]


def test_heldout_timing_uses_sse_timestamp_deltas_not_elapsed(tmp_path):
 path=tmp_path/'replay.json';path.write_text(json.dumps({'rounds':[{'completion_tokens':3,'ttft_s':.2,'elapsed_s':99.,'token_events':[{'t_s':1.,'completion_tokens_delta':1},{'t_s':1.5,'completion_tokens_delta':1},{'t_s':2.,'completion_tokens_delta':1}]}]}))
 row=m._timing_from_document(path,'seed_real');assert row['decode_tps']==2.0 and row['ttft_s']==.2


def test_chunked_sse_output_hash_is_not_an_input_equivalence_gate(tmp_path):
 path=tmp_path/'same.json';path.write_text(json.dumps({'text':'same'}));texts={};bindings={}
 baseline={'texts':{'two':'%s' % m._full_text_sha256({'text':'same'})},'request_input_bindings':{'two':{'input_ids_sha256':'a'*64,'response_sse_sha256':'old'}}}
 m._checked_output(tmp_path,'two',path,{'input_ids_sha256':'a'*64,'response_sse_sha256':'new'},baseline,texts,bindings)
 assert bindings['two']['response_sse_sha256']=='new'


def test_ack_flag_is_minimal_and_production_keeps_d0_off(monkeypatch):
 d=type('D',(),{'clean_environment':lambda *_:{'FT_DEV_ROUTE_TRACE':'stale'}})()
 with pytest.raises(RuntimeError,match='route tracing'):m.env_for(d,'lru',Path('p'),False)
 d=type('D',(),{'clean_environment':lambda *_:{}})()
 production=m.env_for(d,'lru',Path('p'),False);diagnostic=m.env_for(d,'lru',Path('p'),True)
 assert production['FT_DEV_PAUSE_ENDPOINT']=='1' and 'FT_DEV_D0' not in production and 'FT_DEV_ROUTE_TRACE' not in production
 assert diagnostic['FT_DEV_D0']=='1'


def test_actual_candidate_companion_seam_preserves_ack_timestamp(tmp_path,monkeypatch):
 # Copy LF bytes because the candidate companion pins its raw sibling byte-for-byte.
 import shutil
 source=Path(__file__).parents[1]/'e2d15/scripts/agent_trace.py';raw=source.with_name('_agent_trace_original.py');agent=tmp_path/'agent_trace.py';original=tmp_path/'_agent_trace_original.py'
 agent.write_bytes(source.read_bytes().replace(b'\r\n',b'\n'));original.write_bytes(raw.read_bytes().replace(b'\r\n',b'\n'))
 spec=importlib.util.spec_from_file_location('r049_actual_companion',agent);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 m._install_timed_agent_capture(module);out=tmp_path/'out.json'
 def fake_main():
  events=[{'ft_dev':{'schema':'ft_dev_stream/v1','uid':19,'request_seq':1,'completion_tokens_delta':1,'completion_tokens_cumulative':1},'choices':[{'delta':{'content':'x'},'finish_reason':None}]},{'usage':{'completion_tokens':1},'choices':[{'delta':{},'finish_reason':'length'}]}]
  module._ns['consume_stream'](iter(events),m.time.perf_counter());module._ns['write_json'](out,{'rounds':[{'round':0}]})
 module._ns['main']=fake_main;monkeypatch.setattr(m.sys,'argv',[str(agent)]);module.main()
 assert json.loads(out.read_text())['rounds'][0]['token_events'][0]['uid']==19


def test_d0_workloads_receive_l1_equivalence_baseline(monkeypatch,tmp_path):
 seen=[];d=type('D',(),{'dynamic_fixture_port':lambda self:40123})()
 monkeypatch.setattr(m,'ROUNDS',tmp_path);monkeypatch.setattr(m,'load_d07',lambda:d)
 def profile(run):
  path=run/'p';path.write_text('p');return path,['build']
 monkeypatch.setattr(m,'build_profile',profile)
 rows=[{'name':'L1','policy':'lru','d0':False,'production':True},{'name':'L_D0','policy':'lru','d0':True,'production':False}];monkeypatch.setattr(m,'arms',lambda:rows);monkeypatch.setattr(m,'assert_plan',lambda _:rows);monkeypatch.setattr(m,'start_service',lambda *_:object());monkeypatch.setattr(m,'stop_service',lambda *_:None)
 timing={name:{'ttft_s':1.,'decode_tps':2.,'completion_tokens':2} for name in ('cold32k_1','cold32k_2','seed_45k','seed_real','two_decode_diff512')}
 def work(directory,port,spec,baseline):
  seen.append((spec['name'],baseline is not None));return {'d0_enabled':spec['d0'],'texts':{'x':'same'},'timing':timing,'generated_tokens':4,'request_input_bindings':{'seed_45k':[{'ack_uids':[45]}],'seed_real':[{'ack_uids':[46]}]}}
 monkeypatch.setattr(m,'run_workloads',work);monkeypatch.setattr(m,'_require_production_timing',lambda _:None);monkeypatch.setattr(m,'_d0_rows',lambda _:{'sha256':'j'*64,'worker_birth':{'pid':1},'decode':[{'active':2,'missing':1,'hits':1,'h2d_bytes':2,'rids':[45],'step':1},{'active':2,'missing':1,'hits':1,'h2d_bytes':2,'rids':[46],'step':2}],'adapt':[]});monkeypatch.setattr(m,'assert_bitwise',lambda _:True);monkeypatch.setattr(m,'benefit_gate',lambda *_:{})
 m.run_measurements(3);assert seen==[('L1',False),('L_D0',True)]


def test_actual_tokenizer_ack_source_path_is_valid():
 candidate=Path(__file__).parents[1]/'e2d15'
 relative=m.ACK_TOKENIZER.relative_to(m.WT)
 source=candidate/relative
 assert source.is_file()
 raw=source.read_text(encoding='utf-8')
 assert 'request_seqs[msg.uid]' in raw and 'completion_tokens_cumulative=completion_totals[msg.uid]' in raw


def test_dry_measurements_share_all_nine_service_and_workload_paths(monkeypatch,tmp_path):
 calls=[]
 class D:
  def dynamic_fixture_port(self):
   calls.append('bind');return 41000+len(calls)
  def clean_environment(self,*_):return {'FT_SSH_PASSWORD':'never-record'}
  def serve_argv(self,port):return ['ft','serve','--port',str(port)]
 d=D();monkeypatch.setattr(m,'ROUNDS',tmp_path);monkeypatch.setattr(m,'load_d07',lambda:d)
 def profile(run,**_):
  path=run/'seed12k_only.strp';path.write_bytes(b'STRP-test-profile');return path,['minimal-real-profile-builder']
 monkeypatch.setattr(m,'build_profile',profile)
 monkeypatch.setattr(m.subprocess,'Popen',lambda *_:pytest.fail('dry run must not start a service'))
 monkeypatch.setattr(m.urllib.request,'urlopen',lambda *_:pytest.fail('dry run must not connect'))
 row=m.run_measurements(file_dry_run=True)
 run=tmp_path/f'.dryrun_{m.RID}'
 assert row['arms']==list(m.PROCESS_ORDER) and len(calls)==9
 for arm in m.PROCESS_ORDER:
  directory=run/arm
  assert (directory/'owned_process.json').is_file() and (directory/'health.json').is_file()
  assert (directory/'cold32k_1.json').is_file() and (directory/'cold32k_2.json').is_file()
  assert (directory/'seed_45k_replay.json').is_file() and (directory/'seed_real_replay.json').is_file()
  assert (directory/'two_decode.json').is_file()
  assert 'never-record' not in (directory/'ENV.json').read_text()
  assert 'never-record' not in (directory/'ENV.txt').read_text()
 assert not (run/m.RID).exists()


@pytest.fixture
def profile_contract(monkeypatch):
 import sys
 root=Path(__file__).parents[1]/'e2d15'
 monkeypatch.setattr(sys,'path',list(sys.path))
 modules=[]
 for name,path in [('freetoken.moe.expert_profile',root/'python/freetoken/moe/expert_profile.py'),('_r049_cpu_profile_builder',root/'tools/build_expert_profile.py')]:
  spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
  monkeypatch.setitem(sys.modules,name,module);spec.loader.exec_module(module);modules.append(module)
 return tuple(modules)


@pytest.fixture
def high_expert_route(tmp_path):
 import numpy as np
 route=tmp_path/'synthetic_route';route.mkdir()
 np.savez(route/'route-000.npz',expert_ids=np.array([[[511,511,511,511,511,256,510,0,1,2]]],dtype=np.int16))
 return route


def test_build_profile_uses_candidate_reader_for_strp_geometry(monkeypatch,tmp_path,profile_contract,high_expert_route):
 import sys
 reader,builder=profile_contract
 calls=[]
 def fake_run(argv,**kwargs):
  calls.append(argv)
  if str(m.PROFILE_TOOL) in argv:
   builder.build(high_expert_route,Path(argv[3]),int(argv[-1]))
  else:
   assert argv[1]=='-c' and 'read_profile' in argv[2] and argv[-1]==str(m.WT/'python')
   with monkeypatch.context() as patch:
    patch.setattr(sys,'argv',['-c',*argv[3:]]);patch.setattr(sys,'path',list(sys.path))
    exec(argv[2],{'__name__':'__main__'})
  return type('Completed',(),{'returncode':0})()
 monkeypatch.setattr(m.subprocess,'run',fake_run)
 out,command=m.build_profile(tmp_path)
 assert m.MODEL_NUM_EXPERTS==512 and out.is_file() and command[-2:]==['--num-experts','512'] and len(calls)==2
 assert calls[0][2]==str(m.ROUNDS/'E2-R046b/G_seed12k/route')
 profile=reader.read_profile(out,num_layers=1,num_experts=512)
 assert profile.ranked[0]==(0,511) and (0,256) in profile.ranked and (0,510) in profile.ranked


def test_real_profile_builder_rejects_high_expert_ids_with_256_geometry(tmp_path,profile_contract,high_expert_route):
 _,builder=profile_contract;out=tmp_path/'wrong.strp'
 with pytest.raises(ValueError,match='route geometry differs'):
  builder.build(high_expert_route,out,256)
 assert not out.exists()


def test_real_profile_reader_rejects_256_header_for_512_cache(tmp_path,profile_contract):
 reader,_=profile_contract;out=tmp_path/'wrong.strp'
 reader.write_profile(out,reader.rank_frequencies(1,256,[1]*256))
 with pytest.raises(ValueError,match='STRP geometry 1x256 does not match cache geometry'):
  reader.read_profile(out,num_layers=1,num_experts=m.MODEL_NUM_EXPERTS)
