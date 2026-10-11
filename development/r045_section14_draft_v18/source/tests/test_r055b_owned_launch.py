import importlib.util
import json
import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]

def load():
    spec = importlib.util.spec_from_file_location('r055b_owned_execution_test', ROOT/'r055b_owned_launch.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def install_fake_product(monkeypatch, *, engine_raises=False):
    class Scheduler:
        def _process_one_msg(self, msg):
            if type(msg).__name__ == 'ForwardErrorMsg':
                raise RuntimeError('forward failed')
            return msg
        def _forward(self, value):
            raise RuntimeError('GPU forward failed')
    class IOMixin:
        def _reply_tokenizer_rank0(self, messages): return messages
    class Engine:
        def __init__(self):
            if engine_raises: raise RuntimeError('load failed')
    scheduler = types.ModuleType('freetoken.scheduler.scheduler'); scheduler.Scheduler=Scheduler
    io = types.ModuleType('freetoken.scheduler.io'); io.SchedulerIOMixin=IOMixin
    engine = types.ModuleType('freetoken.engine.engine'); engine.Engine=Engine
    for name,module in {'freetoken':types.ModuleType('freetoken'),'freetoken.scheduler':types.ModuleType('freetoken.scheduler'),'freetoken.scheduler.scheduler':scheduler,'freetoken.scheduler.io':io,'freetoken.engine':types.ModuleType('freetoken.engine'),'freetoken.engine.engine':engine}.items(): monkeypatch.setitem(sys.modules,name,module)
    cuda = types.SimpleNamespace(mem_get_info=lambda device:(70,100), memory_allocated=lambda device:12,
                                 memory_reserved=lambda device:18, max_memory_allocated=lambda device:25,
                                 max_memory_reserved=lambda device:30)
    monkeypatch.setitem(sys.modules,'torch',types.SimpleNamespace(cuda=cuda))
    return Scheduler,IOMixin,Engine

def message(name, **values): return type(name, (), values)()

def exec_observer(tool):
    namespace={};exec(tool.PAUSE_OBSERVER,namespace)
    class Proc:
        def __truediv__(self, _): return self
        def read_text(self): return 'x) R 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20'
    real=Path
    namespace['Path']=lambda value:Proc() if str(value)=='/proc' else real(value)
    namespace['install']();return namespace

def test_generated_pause_observer_executes_real_boundaries(monkeypatch,tmp_path):
    tool=load(); path=tmp_path/'memory.jsonl'; pause=tmp_path/'pause.jsonl'
    monkeypatch.setenv('R055B_MODEL_MEMORY',str(path)); monkeypatch.setenv('R055_PAUSE_OBSERVATIONS',str(pause))
    Scheduler,IOMixin,Engine=install_fake_product(monkeypatch)
    exec_observer(tool)
    Engine()
    scheduler=Scheduler(); io=IOMixin()
    scheduler._process_one_msg(message('InputTokenizedMsg',uid=41))
    scheduler._process_one_msg(message('DevPauseBackendMsg',request_id='pause-1'))
    scheduler._process_one_msg(message('DevPauseCancelBackendMsg',request_id='cancel-2'))
    io._reply_tokenizer_rank0([message('DevPauseResultMsg',request_id='pause-1',status='accepted'),message('DetokenizeMsg',uid=41,finished=True,next_token=7)])
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    assert [row['event'] for row in rows]==['model_loaded','request_before','pause_before','cancel_before','cancel_after','pause_after','request_after']
    assert rows[1]['uid']=='41' and rows[2]['request_id']=='pause-1' and rows[3]['request_id']=='cancel-2'
    assert all(row['service_birth']['pid']==os.getpid() and row['total_bytes']==100 for row in rows)
    controls=[json.loads(line) for line in pause.read_text().splitlines()]
    assert {row['request_id'] for row in controls if row['kind']=='backend'}=={'pause-1','cancel-2'}

def test_generated_observer_records_load_error_not_loaded(monkeypatch,tmp_path):
    tool=load(); monkeypatch.setenv('R055B_MODEL_MEMORY',str(tmp_path/'memory.jsonl'));monkeypatch.setenv('R055_PAUSE_OBSERVATIONS',str(tmp_path/'pause.jsonl'))
    _,_,Engine=install_fake_product(monkeypatch,engine_raises=True);exec_observer(tool)
    with pytest.raises(RuntimeError,match='load failed'):Engine()
    rows=[json.loads(line) for line in (tmp_path/'memory.jsonl').read_text().splitlines()]
    assert [row['event'] for row in rows]==['model_load_error']

def test_observer_contract_requires_service_pid_and_execution_id(monkeypatch,tmp_path):
    """Compatibility required by the inherited pause terminal verifier."""
    tool=load(); monkeypatch.setenv('R055B_MODEL_MEMORY',str(tmp_path/'memory.jsonl'));monkeypatch.setenv('R055_PAUSE_OBSERVATIONS',str(tmp_path/'pause.jsonl'))
    Scheduler,_,_=install_fake_product(monkeypatch);exec_observer(tool);Scheduler()._process_one_msg(message('InputTokenizedMsg',uid=1))
    row=json.loads((tmp_path/'pause.jsonl').read_text().splitlines()[0])
    assert row['service_pid']==os.getpid()
    assert row['service_birth']['execution_id']==f"{os.getpid()}:{row['service_birth']['start_ticks']}"


def test_generated_observer_preserves_cuda_forward_failure(monkeypatch, tmp_path):
    tool = load()
    monkeypatch.setenv('R055B_MODEL_MEMORY', str(tmp_path / 'memory.jsonl'))
    monkeypatch.setenv('R055_PAUSE_OBSERVATIONS', str(tmp_path / 'pause.jsonl'))
    Scheduler, _, _ = install_fake_product(monkeypatch)
    exec_observer(tool)
    with pytest.raises(RuntimeError, match='GPU forward failed'):
        Scheduler()._forward(types.SimpleNamespace(batch=types.SimpleNamespace(reqs=[types.SimpleNamespace(uid=42)])))
    rows = [json.loads(line) for line in (tmp_path / 'memory.jsonl').read_text().splitlines()]
    assert rows[0]['event'] == 'request_error' and rows[0]['uid'] == '42'
    assert 'GPU forward failed' in rows[0]['error'] and rows[0]['free_bytes'] == 70


def test_actual_pause_file_writer_keeps_pause_and_drops_route(monkeypatch, tmp_path):
    tool = load()
    legacy = types.SimpleNamespace(ROOT=tmp_path, RID=tool.RID, CANDIDATE_COMMIT='c' * 40)
    gate = types.SimpleNamespace(
        VENV=tmp_path / 'venv', dynamic_fixture_port=lambda: 51237,
        serve_argv=lambda port: ['ft', 'serve', '--port', str(port), '--memory-ratio', '0.88'],
        clean_environment=lambda wt, trace_dir=None: {
            'FT_DEV_ROUTE_TRACE': 'inherited-trace', 'PYTHONPATH': str(wt / 'python'),
            'VIRTUAL_ENV': str(tmp_path / 'venv'), 'CUDA_VISIBLE_DEVICES': '0', 'PATH': 'fixture'},
        start_server=lambda *_: pytest.fail('file-only flow started a service'),
    )
    original_env = gate.clean_environment
    result = tool.pause_smoke(legacy, gate, 1, tmp_path / 'PAUSE_ON',
                             file_dry_run=True, worktree_override=tmp_path / 'wt')
    assert result['port'] == 51237 and result['service_started'] is False
    assert gate.clean_environment is original_env
    env = json.loads((tmp_path / 'PAUSE_ON/ENV.txt').read_text())['environment']
    assert env['FT_DEV_PAUSE_ENDPOINT'] == '1' and env['FT_DEV_ROUTE_TRACE'] is None
    cmd = (tmp_path / 'PAUSE_ON/SERVE_CMD.txt').read_text()
    assert 'r055b_pause_startup.py' in cmd and 'FT_DEV_ROUTE_TRACE' not in cmd
    assert 'FT_DEV_PAUSE_ENDPOINT=1' in cmd and '0.88' in cmd
    observer = (tmp_path / 'PAUSE_ON/r055b_pause_observer.py').read_text()
    compile(observer, 'actual-generated-pause-observer', 'exec')
    assert (tmp_path / 'PAUSE_ON/model_process_cuda.jsonl').is_file()


@pytest.mark.parametrize('failure', [None, 'missing_after', 'wrong_birth', 'wrong_input', 'error'])
def test_real_memory_summary_rejects_partial_or_unbound_requests(tmp_path, failure):
    tool = load()
    birth = {'pid': 100, 'start_ticks': 200, 'execution_id': '100:200', 'pgid': 100, 'session': 100}
    worker = {**birth, 'pid': 101, 'start_ticks': 201, 'execution_id': '101:201'}
    (tmp_path / 'owned_process.json').write_text(json.dumps({'birth': birth}))
    rows = []
    entries = [('model_loaded', None, None), ('request_before', '0', None), ('request_after', '0', None),
               ('pause_before', None, 'p'), ('pause_after', None, 'p'), ('cancel_before', None, 'c'),
               ('cancel_after', None, 'c'), ('request_before', '1', None), ('request_after', '1', None)]
    for index, (event, uid, request_id) in enumerate(entries):
        rows.append({'schema': 'ft_r055b_model_process_cuda/v1', 'event': event, 'uid': uid,
                     'request_id': request_id, 'time_ns': index + 1, 'device': 0,
                     'service_birth': birth, 'worker_birth': worker, 'free_bytes': 7,
                     'total_bytes': 100, 'driver_used_bytes': 93, 'current_allocated_bytes': 60,
                     'current_reserved_bytes': 80, 'cumulative_allocated_peak_bytes': 70,
                     'cumulative_reserved_peak_bytes': 90})
    for prefix, suffix in (('before', '-pause-before'), ('after_cancel', '-pause-after-cancel')):
        case = {'record': {'cold_id': tool.RID + suffix, 'built_tokens': 32052, 'prompt_tokens': 32064,
                           'cached_tokens': 0, 'completion_tokens': 128, 'finish_reason': 'length'},
                'events': 128, 'text': 'actual output fixture'}
        if failure == 'wrong_input' and prefix == 'before':
            case['record']['prompt_tokens'] = 2
        (tmp_path / (prefix + '.json')).write_text(json.dumps(case))
    (tmp_path / 'r055b_pause_observer.py').write_text(tool.PAUSE_OBSERVER)
    if failure == 'missing_after': rows.pop()
    if failure == 'wrong_birth': rows[1] = {**rows[1], 'worker_birth': {**worker, 'pid': 99}}
    if failure == 'error': rows[2] = {**rows[2], 'event': 'request_error', 'error': 'CUDA OOM'}
    (tmp_path / 'model_process_cuda.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in rows))
    if failure:
        with pytest.raises(RuntimeError): tool.summarize_memory(tmp_path, 'p', 'c')
    else:
        summary = tool.summarize_memory(tmp_path, 'p', 'c')
        assert summary['complete'] is True and summary['min_free_bytes'] == 7
        assert [case['uid'] for case in summary['business_requests']] == [0, 1]
        assert summary['worker_birth'] == worker
