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


def test_exact_predecessor_verdicts():
    calls=[];m.require_predecessors(SimpleNamespace(require_closed_round=lambda *args:calls.append(args)))
    assert calls==[('E2-R055-gate-D06','kept'),('E2-R050-gate-D15','kept'),
                   ('E2-R041-gate-D17','kept'),('E2-R040','failed_harness'),('E2-R046','failed_harness')]


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


def test_only_on_service_is_started_and_off_remains_external(monkeypatch,tmp_path):
    rounds=tmp_path/'rounds';off=rounds/'E2-R046/g3g4/g3_off';off.mkdir(parents=True)
    (off/'cold.json').write_text('original off')
    run=tmp_path/'new';run.mkdir();calls=[]
    monkeypatch.setattr(m,'ROUNDS',rounds)
    monkeypatch.setattr(m,'require_retained_off',lambda **_:{'off_rerun':False})
    def start(directory,wt,port,route):
        calls.append(('start',directory.name));(directory/'serve.log').write_text('CUDA graph disabled for development route trace')
        return object()
    def cold(wt,port,cold_id,out):
        assert cold_id=='E2-R046-cold';out.write_text('new on')
    def analyzer(wt,route,trace,serve,summary):summary.write_text(json.dumps({'business_uids':[0],'suffix_tokens':[1]}))
    d=SimpleNamespace(dynamic_fixture_port=lambda:20000,start_server=start,invoke_cold_eq=cold,
       invoke_agent_trace=lambda wt,port,path:path.write_text('{}'),invoke_analyzer=analyzer,
       load_owned_lifecycle=lambda:SimpleNamespace(stop_owned_process=lambda proc:calls.append(('stop',))),
       g3_compare=lambda first,second:{'first':str(first),'second':str(second)})
    result=m.run_g3g4(d,m.WT,run)
    assert calls==[('start','g3_on'),('stop',)]
    assert not (run/'g3g4/g3_off').exists()
    assert (off/'cold.json').read_text()=='original off'
    assert result['g3']['first']==str(off/'cold.json')


def test_exact_source_review_path_and_private_child_schema():
    assert m.REVIEW_DIR.name=='E2-R046a-v1'
    assert m.RID=='E2-R046a' and m.WT.name=='e2base1-p1'


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
    owned=SimpleNamespace(stop_owned_process=stop,process_identity=lambda pid:birth)
    helper=SimpleNamespace(LOCK=tmp_path/'lock',
        require_closed_round=lambda *_:proof,require_r041_kept=lambda *_:proof,
        take_d07_gpu_lock=lambda *args:{'owner':m.RID,'batch':74},
        release_d07_gpu_lock=lambda owner:released.append(owner),
        require_gpu_idle=lambda:[0],dynamic_fixture_port=lambda:24567,
        start_server=start,load_owned_lifecycle=lambda:owned,write_new=m.write_new)
    monkeypatch.setattr(m.sys,'platform','linux')
    monkeypatch.setattr(m,'load_d07',lambda:helper)
    monkeypatch.setattr(m,'require_output_root',lambda *_:None)
    monkeypatch.setattr(m,'require_startup_review',lambda:{'approved':True})
    monkeypatch.setattr(m,'packet',lambda *_:{})
    monkeypatch.setattr(m,'require_t20_terminal_decision',lambda:proof)
    monkeypatch.setattr(m,'require_receipt',lambda *_:None)
    monkeypatch.setattr(m,'invoke_seed',lambda *args:None)
    monkeypatch.setattr(m,'invoke_two',lambda *args:None)
    monkeypatch.setattr(m,'invoke_analysis',lambda *args,**kwargs:None)
    monkeypatch.setattr(m,'seed_paths',lambda:{role:proof for role in m.SEEDS})
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
