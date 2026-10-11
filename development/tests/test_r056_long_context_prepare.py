"""R056 targeted CPU contracts, with the existing deny-socket guard installed."""
import hashlib,importlib.util,json,os,subprocess,sys,textwrap
from pathlib import Path
from types import SimpleNamespace,ModuleType
import pytest

ROOT=Path(__file__).parents[1]
def load(path):
    spec=importlib.util.spec_from_file_location(path.stem,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
m=load(ROOT/'r056_long_context_prepare.py')


def test_release_window_changes_only_kv_and_sequence_arguments():
    original=load(m.D07_SOURCE);d=m.load_d07();before=original.serve_argv(23456);after=d.serve_argv(23456)
    assert d.RID=='E2-R056' and d.CANDIDATE==m.CANDIDATE and d.WORKTREE==m.WT
    changed={i for i,(a,b) in enumerate(zip(before,after)) if a!=b}
    assert changed=={before.index('--kv-reserve-tokens')+1,before.index('--max-seq-len-override')+1}
    assert after[after.index('--memory-ratio')+1]=='0.88'
    assert all(after[i]=='98304' for i in changed)


def test_eleven_requests_preserve_original_sampling_and_87k_bytes(monkeypatch):
    payload={'model':m.MODEL,'messages':[{'role':'user','content':'original seed\n\noriginal task'}],
             'tools':[{'type':'function'}]*3,'temperature':0,'max_tokens':2048,'stream':True,'stream_options':{'include_usage':True}}
    monkeypatch.setattr(m,'real_seed_payload',lambda:payload)
    probe=SimpleNamespace(MODEL_DIR='offline',AutoTokenizer=SimpleNamespace(from_pretrained=lambda *a,**kw:object()),
                          build_text=lambda tok,target,cold_id:(cold_id+' unchanged builder text',target))
    perf=SimpleNamespace(SHORT_PROMPT='用三句话介绍混合专家模型的前缀缓存。')
    monkeypatch.setattr(m,'module',lambda path:probe if path==m.PROBE else perf)
    values=m.payloads();specs=[spec for spec,_ in values]
    assert [spec['kind'] for spec in specs]==['cold32']*4+['cold64']*2+['short']*3+['cold87']*2
    assert [spec['prompt_tokens'] for spec in specs]==[32064]*4+[65424]*2+[23]*3+[87100]*2
    assert values[9][1]==values[10][1]==payload and values[9][1] is not values[10][1]
    assert all(p['max_tokens']==128 and p['temperature']==0 and p['chat_template_kwargs']=={'enable_thinking':False} for _,p in values[:9])
    assert all('chat_template_kwargs' not in p for _,p in values[9:])


def test_wire_sha_matches_actual_senders_for_non_ascii_payload(monkeypatch,tmp_path):
    perf_path=m.PERF if m.PERF.is_file() else ROOT.parent/'scripts/ft_perf_decomp.py'
    agent_path=m.AGENT if m.AGENT.is_file() else ROOT/'e2r046_pausefix/scripts/_agent_trace_original.py'
    assert m.sha(perf_path)==m.PERF_SHA
    # The local source is the same release script with Windows line endings.
    assert hashlib.sha256(agent_path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()==m.AGENT_SHA
    perf=load(perf_path);agent=load(agent_path);sent=[]
    class Reply:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def __iter__(self):return iter([b'data: [DONE]\n'])
    def capture(request,timeout):sent.append(request.data);return Reply()
    monkeypatch.setattr(perf.urllib.request,'urlopen',capture)
    payload={'model':'中文模型','messages':[{'role':'user','content':'真实输入中文'}],'temperature':0}
    perf.post_stream('http://127.0.0.1:1/v1/chat/completions',payload)
    list(agent.post_events('http://127.0.0.1:1/v1/chat/completions',payload,1))
    assert sent[0]!=sent[1] and b'\\u' in sent[0] and b'\\u' not in sent[1]
    for index,spec in enumerate((m.request_specs()[0],m.request_specs()[-1])):
        directory=tmp_path/spec['name'];m.prepare_request(directory,spec,payload,file_dry_run=True)
        inputs=json.loads((directory/'inputs.json').read_text())
        assert inputs['payload_wire_sha256']==hashlib.sha256(sent[index]).hexdigest()
        assert inputs['payload_canonical_sha256']==m.digest(payload)
        reloaded=json.loads((directory/'request.json').read_text())
        assert m.wire_digest(spec,reloaded)!=inputs['payload_wire_sha256']  # sorted archive cannot replace original order


def test_87k_official_timing_recomputes_from_raw_before_consumer_clock(monkeypatch,tmp_path):
    agent_path=m.AGENT if m.AGENT.is_file() else ROOT/'e2r046_pausefix/scripts/_agent_trace_original.py'
    agent=load(agent_path);events=[{'choices':[{'delta':{'reasoning_content':'思考'}}]},
        {'choices':[{'delta':{'tool_calls':[{'index':0,'function':{'name':'read_file','arguments':'{}'}}]}}]},
        {'usage':{'prompt_tokens':87100,'completion_tokens':4},'choices':[{'delta':{},'finish_reason':'tool_calls'}]}]
    monkeypatch.setattr(agent,'post_events',lambda *args:iter(events))
    monkeypatch.setattr(m,'module',lambda path:agent)
    clock=iter([100.0,110.0,111.0,120.0,121.0,130.0,131.0])
    monkeypatch.setattr(m.time,'perf_counter',lambda:next(clock))
    spec=m.request_specs()[-1];directory=tmp_path/spec['name'];payload={'fixture':'原始完整请求'}
    m.prepare_request(directory,spec,payload,file_dry_run=False)
    record=m.measure(directory,spec,payload,23456)
    raw=[json.loads(line) for line in (directory/'stream.jsonl').read_text().splitlines()]
    assert record['ttft_any_s']==round(raw[0]['relative_seconds'],3)==10.0
    assert record['original_agent_ttft_any_s']==11.0
    assert record['decode_any_tps']==3/(raw[1]['relative_seconds']-raw[0]['relative_seconds'])
    assert record['cached_tokens_reported'] is False and record['cached_tokens'] is None


@pytest.mark.parametrize('name,observe',[('production',False),('cold87_0',True),('cold87_1',True)])
def test_real_service_file_prepare_has_no_dev_switches_or_start(monkeypatch,tmp_path,name,observe):
    monkeypatch.setenv('FT_DEV_ROUTE_TRACE','foreign');monkeypatch.setenv('FT_DEV_PAUSE_ENDPOINT','1');monkeypatch.setenv('R055_SERVICE_BIRTH','foreign')
    prepared=m.prepare_service(m.load_d07(),tmp_path/name,23456,observe,start=False)
    argv=prepared['argv'];env=prepared['env']
    assert argv[:6]==['taskset','-c','1,3-47',str(m.VENV/'bin/python'),str(m.OBSERVER),'serve']
    assert not any(key.startswith('FT_DEV') or key.startswith('R055') for key in env)
    assert env['R056_OBSERVE_REQUESTS']==str(int(observe))
    for filename in ('ENV.json','ENV.txt','SERVE_CMD.txt','serve.log','serve_argv.json','owned_process.json','health.json','serve_args.txt','model_memory.jsonl','startup_memory.json','memory_summary.json'):
        assert (tmp_path/name/filename).is_file()


def test_three_fresh_services_run_only_the_assigned_serial_requests(monkeypatch,tmp_path):
    calls=[];process=SimpleNamespace(pid=77,poll=lambda:None)
    def start(d,directory,port,observe,**kwargs):directory.mkdir();calls.append(('start',directory.name,observe));return process
    monkeypatch.setattr(m,'prepare_service',start);monkeypatch.setattr(m,'startup',lambda directory,proc:calls.append(('loaded',directory.name)))
    monkeypatch.setattr(m,'memory_rows',lambda directory,proc,complete:{'request_complete':complete})
    def measure(directory,spec,payload,port):
        calls.append(('request',spec['name']));m.write(directory/'result.json',{'spec':spec});return {'ok':True}
    monkeypatch.setattr(m,'measure',measure)
    lifecycle=SimpleNamespace(stop_owned_process=lambda proc:calls.append(('stop',proc.pid)),owned_group_alive=lambda pid:False)
    d=SimpleNamespace(dynamic_fixture_port=lambda:23456,load_owned_lifecycle=lambda:lifecycle)
    values=[(spec,{'fixture':spec['name']}) for spec in m.request_specs()]
    records=m.run_services(d,tmp_path,values,file_dry_run=False)
    assert len(records)==11
    assert [call for call in calls if call[0]=='start']==[('start','production',False),('start','cold87_0',True),('start','cold87_1',True)]
    assert [call[1] for call in calls if call[0]=='request']==[spec['name'] for spec,_ in values]
    assert len([call for call in calls if call[0]=='stop'])==3


def test_actual_observer_records_kv_bytes_and_real_user_message(monkeypatch,tmp_path):
    from test_r055b_owned_launch import install_fake_product,message
    Scheduler,IO,Engine=install_fake_product(monkeypatch)
    def initialize(self):
        self.kv_cache=SimpleNamespace(_kv_buffer=SimpleNamespace(shape=(2,12,769,128,2,256),numel=lambda:123456,element_size=lambda:2))
        self.num_pages=768;self.max_seq_len=98304
    Engine.__init__=initialize
    observer=load(m.OBSERVER);birth={'pid':1,'start_ticks':2,'execution_id':'1:2','pgid':1,'session':1}
    monkeypatch.setattr(observer,'birth',lambda:birth)
    monkeypatch.setenv('R056_SERVICE_BIRTH',json.dumps(birth));monkeypatch.setenv('R056_MODEL_MEMORY',str(tmp_path/'memory.jsonl'));monkeypatch.setenv('R056_OBSERVE_REQUESTS','1')
    observer.install();Engine();Scheduler()._process_one_msg(message('UserMsg',uid=31));IO()._reply_tokenizer_rank0([message('DetokenizeMsg',uid=31,finished=True)])
    rows=[json.loads(line) for line in (tmp_path/'memory.jsonl').read_text().splitlines()]
    assert [row['event'] for row in rows]==['model_loaded','request_before','request_after']
    assert rows[0]['kv_storage_bytes']==246912 and rows[0]['max_seq_len']==98304
    assert rows[1]['uid']==rows[2]['uid']=='31'


def test_actual_spawn_installs_observer_before_worker_target(tmp_path):
    files={
        'freetoken/__init__.py':'', 'freetoken/engine/__init__.py':'', 'freetoken/scheduler/__init__.py':'',
        'freetoken/engine/engine.py':'''\
from types import SimpleNamespace
class Engine:
    def __init__(self):
        self.kv_cache=SimpleNamespace(_kv_buffer=SimpleNamespace(shape=(2,12,769,128,2,256),numel=lambda:123456,element_size=lambda:2))
        self.num_pages=768;self.max_seq_len=98304
''',
        'freetoken/scheduler/scheduler.py':'''\
class Scheduler:
    def _process_one_msg(self,msg):return msg
''',
        'freetoken/scheduler/io.py':'''\
class SchedulerIOMixin:
    def _reply_tokenizer_rank0(self,messages):return messages
''',
        'freetoken/fake_worker.py':'''\
from freetoken.engine.engine import Engine
from freetoken.scheduler.scheduler import Scheduler
from freetoken.scheduler.io import SchedulerIOMixin
class UserMsg:
    uid=31
class DetokenizeMsg:
    uid=31;finished=True
def run():
    Engine()
    Scheduler()._process_one_msg(UserMsg())
    SchedulerIOMixin()._reply_tokenizer_rank0([DetokenizeMsg()])
''',
        'freetoken/cli.py':'''\
import multiprocessing
from freetoken.fake_worker import run
def main():
    worker=multiprocessing.get_context('spawn').Process(target=run)
    worker.start();worker.join(15)
    if worker.is_alive():worker.terminate();worker.join();raise RuntimeError('spawn fixture timed out')
    if worker.exitcode!=0:raise RuntimeError('spawn fixture worker failed')
''',
        'torch.py':'''\
from types import SimpleNamespace
cuda=SimpleNamespace(mem_get_info=lambda device:(6000000,8000000),memory_allocated=lambda device:1000000,
                     memory_reserved=lambda device:2000000,max_memory_allocated=lambda device:1000000,
                     max_memory_reserved=lambda device:2000000)
''',
    }
    for name,source in files.items():
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(textwrap.dedent(source),encoding='utf-8')
    site=(ROOT/'d16_cpu_sitecustomize.py').read_text()+'''\nimport os\nos.environ['CUDA_VISIBLE_DEVICES']=''\n'''
    if os.name=='nt':
        # Windows still runs an actual spawn. Only Linux /proc identity reads
        # need an OS fixture; the leader repeats this test with actual /proc.
        site+='''\
from pathlib import Path
_read_text=Path.read_text
def _proc_read(self,*args,**kwargs):
    if self.as_posix().startswith('/proc/'):
        fields=['R','1',str(os.getpid()),str(os.getpid())]+['0']*15+['9']
        return str(os.getpid())+' (cpu-fixture) '+' '.join(fields)
    return _read_text(self,*args,**kwargs)
Path.read_text=_proc_read
'''
    (tmp_path/'sitecustomize.py').write_text(site,encoding='utf-8')
    env=dict(os.environ,PYTHONPATH=str(tmp_path),PYTHONDONTWRITEBYTECODE='1',CUDA_VISIBLE_DEVICES='',
             R056_MODEL_MEMORY=str(tmp_path/'memory.jsonl'),R056_OBSERVE_REQUESTS='1')
    env.pop('R056_SERVICE_BIRTH',None)
    result=subprocess.run([sys.executable,str(m.OBSERVER),'serve'],cwd=tmp_path,env=env,capture_output=True,text=True,timeout=25,start_new_session=True)
    assert result.returncode==0,result.stdout+'\n'+result.stderr
    rows=[json.loads(line) for line in (tmp_path/'memory.jsonl').read_text().splitlines()]
    assert [row['event'] for row in rows]==['model_loaded','request_before','request_after']
    assert rows[0]['kv_storage_bytes']==246912 and rows[0]['max_seq_len']==98304
    assert rows[1]['uid']==rows[2]['uid']=='31'
    assert rows[0]['worker_birth']['pid']!=rows[0]['service_birth']['pid']
    assert all(row['worker_birth']==rows[0]['worker_birth'] and row['service_birth']==rows[0]['service_birth'] for row in rows)


def test_87k_absent_cache_counter_stays_absent_and_warm_is_rejected():
    spec=m.request_specs()[-1]
    record={'prompt_tokens':87100,'completion_tokens':20,'finish_reason':'tool_calls','cached_tokens':None,'ttft_any_s':10.0,'decode_any_tps':30.0}
    assert m.check_result(spec,record)['cached_tokens'] is None
    record['cached_tokens']=10
    with pytest.raises(RuntimeError,match='not cold'):m.check_result(spec,record)
    record.update(cached_tokens=0,prompt_tokens=87099)
    with pytest.raises(RuntimeError,match='usage/terminal'):m.check_result(spec,record)


def test_performance_failure_stops_before_next_request_and_cleans_once(monkeypatch,tmp_path):
    calls=[];process=SimpleNamespace(pid=77,poll=lambda:None)
    def start(d,directory,*args,**kwargs):directory.mkdir();return process
    monkeypatch.setattr(m,'prepare_service',start);monkeypatch.setattr(m,'startup',lambda *_:None)
    def oom(*args):calls.append('request');raise RuntimeError('CUDA out of memory')
    monkeypatch.setattr(m,'measure',oom)
    lifecycle=SimpleNamespace(stop_owned_process=lambda proc:calls.append('stop'),owned_group_alive=lambda pid:False)
    d=SimpleNamespace(dynamic_fixture_port=lambda:23456,load_owned_lifecycle=lambda:lifecycle)
    with pytest.raises(RuntimeError,match='out of memory'):m.run_services(d,tmp_path,[(spec,{}) for spec in m.request_specs()],file_dry_run=False)
    assert calls==['request','stop']


def test_startup_cleanup_failure_is_not_retried(monkeypatch,tmp_path):
    calls=[];process=SimpleNamespace(pid=77)
    def fail(*args,**kwargs):
        error=RuntimeError('cleanup failed');error.owned_process=process;error.owned_cleanup_failed=True;raise error
    monkeypatch.setattr(m,'prepare_service',fail)
    d=SimpleNamespace(dynamic_fixture_port=lambda:23456,load_owned_lifecycle=lambda:SimpleNamespace(stop_owned_process=lambda proc:calls.append(proc)))
    with pytest.raises(RuntimeError,match='cleanup failed') as raised:m.run_services(d,tmp_path,[(spec,{}) for spec in m.request_specs()],file_dry_run=False)
    assert raised.value.owned_process is process and not calls


def test_real_file_dry_runs_all_producer_paths_without_launch(monkeypatch,tmp_path):
    wt=tmp_path/'wt';wt.mkdir();out=tmp_path/'rounds';out.mkdir();source=tmp_path/'source.py';source.write_text('readonly source');source.chmod(0o444)
    monkeypatch.setattr(m.sys,'platform','linux');monkeypatch.setattr(m.os,'getuid',lambda:1000,raising=False)
    monkeypatch.setattr(m,'WT',wt);monkeypatch.setattr(m,'ROUNDS',out);monkeypatch.setattr(m,'packet',lambda:{'fixture_only':True})
    monkeypatch.setattr(m,'source_paths',lambda:(source,));monkeypatch.setattr(m,'payloads',lambda:[(spec,{'fixture':spec['name']}) for spec in m.request_specs()])
    monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**kw:pytest.fail('file dry must not launch'))
    try:
        receipt=m.dry_run(wt,out);target=m.dry_directory(out)
        assert receipt['passed'] and receipt['formal_rid_created'] is False and not (out/m.RID).exists()
        assert receipt['schema']=='ft_r056_file_dry/v2' and target.name=='.dryrun_R056_v2_E2-R056'
        assert m.REVIEW_DIR.name=='E2-R056-v2'
        assert (target/'production/cold32_0/inputs.json').is_file() and (target/'cold87_1/cold87_1/result.json').is_file()
        assert len(list(target.rglob('request.json')))==11 and len(list(target.glob('completed_*.json')))==11
        assert (target/'metadata/pre_d04.json').is_file() and (target/'runtime_sources/source.py').stat().st_mode&0o222
        assert not source.stat().st_mode&0o222
    finally:source.chmod(0o644)


@pytest.mark.parametrize('schema,rid',[('ft_r046b_dry_run/v2','E2-R046b'),('ft_r056_file_dry/v1','E2-R056')])
def test_old_or_wrong_owner_file_dry_is_rejected_before_review(monkeypatch,tmp_path,schema,rid):
    monkeypatch.setattr(m.os,'getuid',lambda:1000,raising=False)
    target=m.dry_directory(tmp_path);target.mkdir();receipt=target/'dry_run_receipt.json'
    receipt.write_text(json.dumps({'schema':schema,'rid':rid}));receipt.chmod(0o444)
    try:
        with pytest.raises(RuntimeError,match='identity/source'):m.admission_receipts(tmp_path)
    finally:receipt.chmod(0o644)


def test_cross_window_medians_exclude_first_shot_and_do_not_claim_benefit(monkeypatch):
    historical={'cold32_excluding_first':{'ttft_s':6,'decode_tps':38},'cold64':{'ttft_s':13,'decode_tps':36},'short':{'decode_tps':39,'values':[{'ttft_s':2},{'ttft_s':3},{'ttft_s':4}]}}
    monkeypatch.setattr(m,'sealed',lambda *_:{'performance':historical})
    records=[(spec,{'ttft_s':1000 if spec['name']=='cold32_0' else 5,'decode_tps':40}) for spec in m.request_specs()]
    result=m.comparison(records)
    assert result['current_window']==98304 and result['historical_window']==73728
    assert result['observations'][0]['current']==5 and result['first_shot_current']['ttft_s']==1000
    assert result['historical_first_shot'] is None and 'no same-window' in result['scope']


def test_cpu_network_guard_and_no_visible_cuda():
    import socket
    assert os.environ['CUDA_VISIBLE_DEVICES']==''
    with socket.socket() as sock:
        with pytest.raises(PermissionError):sock.connect(('127.0.0.1',8095))
