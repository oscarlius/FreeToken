import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


SPEC = importlib.util.spec_from_file_location(
    "d06_g3g4_prepare", Path(__file__).parents[1] / "d06_g3g4_prepare.py"
)
d06 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d06)


@pytest.fixture(autouse=True)
def offline_guard(monkeypatch):
    monkeypatch.setattr(d06.socket, 'socket', lambda *a, **k: pytest.fail('offline CPU tests must not open a socket'))
    monkeypatch.setattr(d06.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('offline CPU tests must not send HTTP'))


def test_controller_normalizes_real_identity_before_atomic_publish(monkeypatch,tmp_path):
    import json
    gate=d06._d07_closed_round_gate();proof=tmp_path/'proof.json';proof.write_text('{}')
    monkeypatch.setattr(d06.sys,'platform','linux')
    monkeypatch.setattr(d06,'RUNS',tmp_path/'runs')
    monkeypatch.setattr(d06,'LOCK',tmp_path/'gpu.lock')
    monkeypatch.setattr(d06,'require_kept',lambda _:proof)
    monkeypatch.setattr(d06,'require_d07_g3g4_result',lambda:(proof,proof))
    monkeypatch.setattr(d06,'require_t06_measured',lambda:proof)
    monkeypatch.setattr(d06,'acquire_gpu_lock',lambda _:pytest.fail('controller must not take GPU lock'))
    monkeypatch.setattr(gate,'process_birth',lambda:{'pid':111,'start_ticks':99,'execution_id':'111:99'})
    seen={}
    def reserve(helper,batch,rid,argv,path,packet):
        assert path.parent.is_dir() and 'batch72' in path.name and '--launch-receipt' in argv
        receipt={**packet,'state':'launched','batch_pid':222};path.write_text(json.dumps(receipt));return receipt
    def publish(path,identity,value):
        assert value['child']=={'pid':222,'start_ticks':123,'execution_id':'222:123'}
        assert (path.stat().st_dev,path.stat().st_ino)==identity
        seen['value']=value
    owned=SimpleNamespace(verified_module=lambda *a:SimpleNamespace(next_batch=lambda _:72),reserve_process=reserve,process_identity=lambda _: {'pid':222,'start_ticks':123,'pgid':222,'session':222},publish_receipt=publish)
    monkeypatch.setattr(d06,'load_owned_lifecycle',lambda:owned)
    monkeypatch.setattr(d06,'_d07_closed_round_gate',lambda:gate)
    result=d06.execute(tmp_path/'wt',tmp_path/'out')
    assert result==seen['value'] and result['batch']==72


def test_child_rejects_misbound_receipt_before_gpu_lock(monkeypatch,tmp_path):
    monkeypatch.setattr(d06.sys,'platform','linux')
    def reject(*a,**kw):
        assert kw['rid']==d06.RID and kw['schema']=='ft_d06_owned_launch/v1'
        raise RuntimeError('wrong child receipt')
    monkeypatch.setattr(d06,'_d07_closed_round_gate',lambda:SimpleNamespace(require_child_receipt=reject))
    monkeypatch.setattr(d06,'acquire_gpu_lock',lambda _:pytest.fail('invalid child must not take GPU lock'))
    with pytest.raises(RuntimeError,match='wrong child receipt'):
        d06.execute(tmp_path/'wt',tmp_path/'out',owned_child=True,batch=72,launch_receipt=tmp_path/'wrong.json')


def test_receipt_write_failure_cleans_started_service(monkeypatch, tmp_path):
    stopped = []
    process = SimpleNamespace(pid=123)
    owned = SimpleNamespace(
        process_identity=lambda pid: {"pid": pid, "pgid": pid, "session": pid, "start_ticks": 1},
        stop_owned_process=lambda child: stopped.append(child.pid),
    )
    monkeypatch.setattr(d06, "environment", lambda *args: {key: "" for key in (
        "CUDA_VISIBLE_DEVICES", "FT_DEV_PAUSE_ENDPOINT", "FT_DEV_D0", "FT_DEV_D0_PATH",
        "FT_DEV_D0_TIMELINE", "FT_DEV_D0_TIMELINE_STEPS", "PYTHONPATH", "VIRTUAL_ENV",
        "R055_PAUSE_OBSERVATIONS", "R055B_MODEL_MEMORY"
    )})
    monkeypatch.setattr(d06.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(d06, "load_owned_lifecycle", lambda: owned)
    original_write = d06.write_new
    def fail_write(path, value):
        if path.name == 'owned_process.json':
            raise OSError("receipt disk failure")
        return original_write(path, value)
    monkeypatch.setattr(d06, "write_new", fail_write)
    with pytest.raises(OSError, match="receipt disk failure"):
        d06.start_server(tmp_path, tmp_path, 43001)
    assert stopped == [123]


def test_foreign_lock_is_preserved_and_cannot_produce_success(monkeypatch, tmp_path):
    lock = tmp_path / "gpu.lock"
    lock.write_text("owned")
    monkeypatch.setattr(d06, "LOCK", lock)
    monkeypatch.setattr(d06, "LOCK_TOKEN", "owned")
    monkeypatch.setattr(d06, "LOCK_INODE", lock.stat().st_ino)
    lock.write_text("foreign")
    with pytest.raises(RuntimeError, match="foreign/replaced"):
        d06.release_gpu_lock()
    assert lock.read_text() == "foreign"


def test_service_writer_executes_reviewed_usermsg_observer(monkeypatch, tmp_path):
    from test_r055b_owned_launch import install_fake_product, exec_observer, message
    import json
    env, argv = d06.prepare_service_files(tmp_path, tmp_path / 'wt', 51449)
    assert argv[1].endswith('d06_pause_startup_v3.py')
    assert argv[argv.index('--memory-ratio') + 1] == '0.88'
    owner = SimpleNamespace(PAUSE_OBSERVER=(tmp_path / 'd06_pause_observer_v3.py').read_text())
    assert 'elif name=="UserMsg":' in owner.PAUSE_OBSERVER
    for key in ('R055B_MODEL_MEMORY', 'R055_PAUSE_OBSERVATIONS'):
        monkeypatch.setenv(key, env[key])
    Scheduler, IO, Engine = install_fake_product(monkeypatch)
    exec_observer(owner); Engine()
    Scheduler()._process_one_msg(message('UserMsg', uid=41))
    IO()._reply_tokenizer_rank0([message('DetokenizeMsg', uid=41, finished=True, next_token=7)])
    rows = [json.loads(row) for row in (tmp_path / 'model_process_cuda.jsonl').read_text().splitlines()]
    assert [row['event'] for row in rows] == ['model_loaded', 'request_before', 'request_after']
    assert rows[1]['uid'] == rows[2]['uid'] == '41'


def test_actual_pause_chain_preserves_504_and_binds_resume(monkeypatch, tmp_path):
    from test_r055b_owned_launch import install_fake_product, exec_observer, message
    import io
    import json
    import urllib.error
    env, _ = d06.prepare_service_files(tmp_path, tmp_path / 'wt', 51449)
    for key in ('R055B_MODEL_MEMORY', 'R055_PAUSE_OBSERVATIONS'):
        monkeypatch.setenv(key, env[key])
    Scheduler, IO, Engine = install_fake_product(monkeypatch)
    namespace = exec_observer(SimpleNamespace(PAUSE_OBSERVER=(tmp_path / 'd06_pause_observer_v3.py').read_text()))
    birth = namespace['_birth']()
    (tmp_path / 'owned_process.json').write_text(json.dumps({'pid': birth['pid'], 'birth': {**birth, 'state': 'R'}}))
    Engine(); scheduler, delivery = Scheduler(), IO()
    # Earlier G3/G4 requests stay in the memory journal; the pause pair is bound
    # to its own actual time window rather than assuming exactly two total inputs.
    scheduler._process_one_msg(message('UserMsg', uid=90))
    delivery._reply_tokenizer_rank0([message('DetokenizeMsg', uid=90, finished=True, next_token=7)])
    def cold(worktree, port, cold_id, output):
        uid = 1 if output.name == 'before.json' else 2
        scheduler._process_one_msg(message('UserMsg', uid=uid))
        delivery._reply_tokenizer_rank0([message('DetokenizeMsg', uid=uid, finished=True, next_token=7)])
        output.write_text(json.dumps({'record': {'cold_id': cold_id, 'built_tokens': 32052, 'prompt_tokens': 32064,
            'completion_tokens': 128, 'cached_tokens': 0, 'finish_reason': 'length'}, 'events': 128, 'text': 'resumed output'}))
    monkeypatch.setattr(d06, '_d07_closed_round_gate', lambda: SimpleNamespace(invoke_cold_eq=cold))
    calls = []
    def answer(request, timeout):
        calls.append(json.loads(request.data))
        request_id = 'pause-1' if len(calls) == 1 else 'cancel-2'
        scheduler._process_one_msg(message('DevPauseBackendMsg', request_id=request_id))
        if len(calls) == 1:
            delivery._reply_tokenizer_rank0([message('DevPauseResultMsg', request_id=request_id, status='accepted')])
            return io.BytesIO(json.dumps({'status': 'accepted', 'request_id': request_id}).encode())
        scheduler._process_one_msg(message('DevPauseCancelBackendMsg', request_id=request_id))
        raise urllib.error.HTTPError(request.full_url, 504, 'Gateway Timeout', {},
            io.BytesIO(json.dumps({'status': 'timeout', 'request_id': request_id}).encode()))
    monkeypatch.setattr(d06.urllib.request, 'urlopen', answer)
    result = d06.run_pause_chain(tmp_path, tmp_path / 'wt', 51449)
    assert result['complete'] is True and result['cuda_memory_summary']['request_count'] == 3
    assert json.loads((tmp_path / 'pause_cancel.json').read_text())['http_status'] == 504
    assert result['backend_evidence']['post_cancel']['delivery']['uid'] == '2'
    assert calls == [{'seconds': 1.0, 'timeout': 5.0}, {'seconds': 30.0, 'timeout': 0.05}]


def test_memory_summary_rejects_missing_request_before(tmp_path):
    import json
    birth = {'pid': 1, 'start_ticks': 2, 'execution_id': '1:2', 'pgid': 1, 'session': 1}
    (tmp_path / 'owned_process.json').write_text(json.dumps({'pid': 1, 'birth': birth}))
    rows = [{'schema': 'ft_r055b_model_process_cuda/v1', 'event': event, 'uid': uid, 'device': 0,
             'service_birth': birth, 'worker_birth': birth, 'free_bytes': 70, 'total_bytes': 100,
             'driver_used_bytes': 30, 'current_allocated_bytes': 12, 'current_reserved_bytes': 18,
             'cumulative_allocated_peak_bytes': 25, 'cumulative_reserved_peak_bytes': 30, 'time_ns': index}
            for index, (event, uid) in enumerate((('model_loaded', None), ('request_after', '1')), 1)]
    (tmp_path / 'model_process_cuda.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
    with pytest.raises(RuntimeError, match='request-before/after'):
        d06.summarize_model_memory(tmp_path)
