import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

P = Path(__file__).parents[1] / "r055_owned_launch.py"
S = importlib.util.spec_from_file_location("r055_owned", P)
m = importlib.util.module_from_spec(S); S.loader.exec_module(m)


def test_default_is_inert(capsys):
    assert m.main([]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["rid"] == m.RID and not doc["requests_sent"] and not doc["gpu_lock_taken"]
    assert doc["source_execution_ready"] is False

def test_source_binding_covers_private_runner_and_t17_dependencies():
    assert {"t16_private_port_base_runner.py","t17_d14_runner.py","t17_d14_observe.py","t16_full_tail_base_runner.py"} <= set(m.source_hashes())


def test_new_review_path_preserves_prior_review_artifact():
    assert m.review_path().name == f"{m.RID}_startup_review_v2.json"


def test_foreign_lock_precedes_prerequisite_or_batch(monkeypatch, tmp_path):
    lock = tmp_path / "gpu.lock"; lock.write_text("foreign")
    gate = SimpleNamespace(LOCK=lock, require_r041_kept=lambda *_: pytest.fail("must not inspect predecessor"))
    monkeypatch.setattr(m, "d07", lambda: gate); monkeypatch.setattr(m.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="foreign GPU lock"):
        m.controller()


def test_controller_reserves_once_and_publishes_actual_birth(monkeypatch, tmp_path):
    receipt = tmp_path / "launch.json"; calls = []
    birth = {"pid": 23, "start_ticks": 77, "execution_id": "23:77"}
    class Owned:
        def verified_module(self, *_): return SimpleNamespace(next_batch=lambda _: 92)
        def reserve_process(self, helper, batch, rid, argv, path, reserved):
            calls.append((batch, rid, argv, reserved)); path.write_text(json.dumps({**reserved, "state": "launched", "batch_pid": 23})); return json.loads(path.read_text())
        def process_identity(self, pid): return birth if pid == 23 else None
        def publish_receipt(self, path, inode, value): path.write_text(json.dumps(value)); calls.append(("publish", inode, value))
    gate = SimpleNamespace(ATOMIC_HELPER_SHA="atomic", ROUNDS=tmp_path, argv_sha256=lambda argv: "argv", process_birth=lambda: {"pid": 8, "start_ticks": 9, "execution_id":"8:9"}, load_owned_lifecycle=lambda: Owned())
    monkeypatch.setattr(m, "admission", lambda g: calls.append("admitted")); monkeypatch.setattr(m, "d07", lambda: gate); monkeypatch.setattr(m.sys, "platform", "linux")
    monkeypatch.setattr(m, "ROOT", tmp_path)
    result = m.controller()
    assert calls[0] == "admitted" and calls[1][0:2] == (92, m.RID)
    assert result["child"] == birth and result["batch"] == 92


def test_wrong_receipt_rejected_before_lock(monkeypatch, tmp_path):
    path = tmp_path / "receipt.json"; mine = {"pid": 5, "start_ticks": 6, "execution_id": "5:6"}
    path.write_text(json.dumps({"schema":m.RECEIPT_SCHEMA,"state":"launched","rid":m.RID,"batch":4,"candidate_commit":"wrong","argv_sha256":"argv","batch_pid":5,"child":mine}))
    gate = SimpleNamespace(process_birth=lambda: mine, argv_sha256=lambda _: "argv")
    with pytest.raises(RuntimeError, match="binding differs"):
        m.require_receipt(gate, 4, path)


def test_child_runs_leaf_under_outer_owner_and_releases(monkeypatch, tmp_path):
    calls=[]
    class Leaf:
        write_new=staticmethod(lambda path,value: path.write_text(json.dumps(value)))
        class CandidateRunner:
            def __init__(self, opts): self.options=opts; self.proc=None; self.directory=tmp_path/'round';self.directory.mkdir()
            def execute(self): calls.append(("execute", self.options.rid, self.options.batch))
            def stop(self): return None
    gate=SimpleNamespace(take_d07_gpu_lock=lambda *a: {"owner":a,"lock_token":"token","lock_inode":9}, release_d07_gpu_lock=lambda owner:calls.append(("release",owner)), require_gpu_idle=lambda:calls.append(("idle",)), load_owned_lifecycle=lambda:SimpleNamespace(owned_group_alive=lambda _:False))
    monkeypatch.setattr(m,"d07",lambda:gate); monkeypatch.setattr(m,"admission",lambda *_:None); monkeypatch.setattr(m,"require_receipt",lambda *_:None); monkeypatch.setattr(m,"adapter_module",lambda:Leaf); monkeypatch.setattr(m,"pause_smoke",lambda *_:{"actual": True}); monkeypatch.setattr(m.sys,"platform","linux")
    assert m.child(17,tmp_path/"r")["source_execution_ready"] is False
    assert ("idle",) in calls and ("execute",m.RID,17) in calls and calls[-1][0] == "release"


def test_child_cleanup_failure_keeps_lock(monkeypatch, tmp_path):
    released=[]
    class Leaf:
        write_new=staticmethod(lambda path,value: path.write_text(json.dumps(value)))
        class CandidateRunner:
            def __init__(self, opts): self.options=opts; self.proc=None;self.directory=tmp_path/'round';self.directory.mkdir()
            def execute(self): self.stop()
            def stop(self): raise RuntimeError("stop failed")
    gate=SimpleNamespace(take_d07_gpu_lock=lambda *a:{"lock_token":"token","lock_inode":9},release_d07_gpu_lock=lambda _:released.append(True),require_gpu_idle=lambda:None,load_owned_lifecycle=lambda:SimpleNamespace(owned_group_alive=lambda _:False))
    monkeypatch.setattr(m,"d07",lambda:gate);monkeypatch.setattr(m,"admission",lambda *_:None);monkeypatch.setattr(m,"require_receipt",lambda *_:None);monkeypatch.setattr(m,"adapter_module",lambda:Leaf);monkeypatch.setattr(m,"pause_smoke",lambda *_:{"actual": True});monkeypatch.setattr(m.sys,"platform","linux")
    with pytest.raises(RuntimeError,match="stop failed"):m.child(3,tmp_path/"r")
    assert released == []


def test_cli_routes_only_controller_or_bound_child(monkeypatch, tmp_path):
    seen=[];monkeypatch.setattr(m,"controller",lambda:seen.append("controller"));monkeypatch.setattr(m,"child",lambda b,r:seen.append((b,r)))
    assert m.main(["--run"]) == 0
    assert m.main(["--run","--owned-child","--batch","7","--launch-receipt",str(tmp_path/"r")]) == 0
    assert seen[0] == "controller" and seen[1][0] == 7
    with pytest.raises(SystemExit):m.main(["--owned-child","--batch","7"])


def test_pause_smoke_uses_dynamic_service_then_cold_pause_cancel_and_recovery(monkeypatch, tmp_path):
    events=[]
    proc=SimpleNamespace(pid=77)
    lifecycle=SimpleNamespace(stop_owned_process=lambda p: events.append(("stop",p.pid)))
    gate=SimpleNamespace(dynamic_fixture_port=lambda: 49123,
        start_server=lambda run,wt,port,trace: events.append(("start",port,trace.name)) or proc,
        invoke_cold_eq=lambda wt,port,cold,out: events.append(("cold",cold,port)) or out.write_text("{}"),
        load_owned_lifecycle=lambda:lifecycle)
    monkeypatch.setattr(m,"ROOT",tmp_path);monkeypatch.setattr(m,"require_candidate",lambda:tmp_path/"wt")
    replies=iter([{"status":"accepted","request_id":"pause-1"},{"status":"timeout","request_id":"pause-2","error":"scheduler acknowledgement deadline expired"}])
    def pause(port,seconds,timeout):
        events.append(("pause",seconds,timeout)); value=next(replies)
        if isinstance(value,BaseException): raise value
        return value
    monkeypatch.setattr(m,"pause_request",pause)
    result=m.pause_smoke(gate,12)
    assert events == [("start",49123,"route"),("cold",m.RID+"-pause-before",49123),("pause",1.0,5.0),("pause",30.0,0.05),("cold",m.RID+"-pause-after-cancel",49123),("stop",77)]
    assert Path(result["pause"]).is_file() and Path(result["cancel"]).is_file()


def test_admission_requires_only_r041_plus_small_native_metadata(monkeypatch, tmp_path):
    calls=[]
    gate=SimpleNamespace(LOCK=tmp_path/"lock",require_r041_kept=lambda root:calls.append(("r041",root)))
    monkeypatch.setattr(m,"require_candidate",lambda:calls.append("candidate"))
    monkeypatch.setattr(m,"require_native_reuse",lambda:calls.append("native"))
    monkeypatch.setattr(m,"require_leaf_review",lambda:calls.append("review"))
    m.admission(gate)
    assert calls[0][0] == "r041" and calls[1:] == ["candidate","native","review"]

def test_native_reuse_rejects_writable_or_wrong_hash(monkeypatch,tmp_path):
    a,b=tmp_path/"a",tmp_path/"b";a.write_text("a");b.write_text("b");a.chmod(0o444);b.chmod(0o444)
    monkeypatch.setattr(m,"NATIVE_REUSE",a);monkeypatch.setattr(m,"PARENT_NATIVE",b);monkeypatch.setattr(m,"NATIVE_REUSE_SHA",__import__("hashlib").sha256(b"a").hexdigest());monkeypatch.setattr(m,"PARENT_NATIVE_SHA",__import__("hashlib").sha256(b"b").hexdigest())
    assert m.require_native_reuse()["eff_native_reuse_sha256"] == __import__("hashlib").sha256(b"a").hexdigest()
    a.chmod(0o644)
    with pytest.raises(RuntimeError,match="absent or writable"):m.require_native_reuse()


def test_pause_smoke_rejects_timeout_without_request_identity(monkeypatch,tmp_path):
    gate=SimpleNamespace(dynamic_fixture_port=lambda:49001,start_server=lambda *a:SimpleNamespace(pid=1),invoke_cold_eq=lambda *a:a[-1].write_text("{}"),load_owned_lifecycle=lambda:SimpleNamespace(stop_owned_process=lambda *_:None))
    monkeypatch.setattr(m,"ROOT",tmp_path);monkeypatch.setattr(m,"require_candidate",lambda:tmp_path); monkeypatch.setattr(m,"pause_request",lambda *a:{"status":"timeout"})
    with pytest.raises(RuntimeError,match="pause endpoint lacks"):m.pause_smoke(gate,1)

def test_pause_trace_requires_backend_result_cancel_and_same_process_delivery(tmp_path):
    run=tmp_path/'run';run.mkdir();birth={"pid":70,"start_ticks":4,"execution_id":"70:4","pgid":70,"session":70}
    (run/'owned_process.json').write_text(json.dumps({'pid':70,'birth':birth}))
    rows=[
      {'kind':'backend','request_id':'a','message':'DevPauseBackendMsg','time_ns':1,'pid':71,'service_pid':70,'service_birth':birth},
      {'kind':'pause_result','request_id':'a','status':'accepted','time_ns':2,'pid':71,'service_pid':70,'service_birth':birth},
      {'kind':'backend','request_id':'b','message':'DevPauseCancelBackendMsg','time_ns':3,'pid':71,'service_pid':70,'service_birth':birth},
      {'kind':'input','uid':'u','time_ns':4,'pid':71,'service_pid':70,'service_birth':birth},
      {'kind':'delivery','uid':'u','time_ns':5,'pid':71,'service_pid':70,'service_birth':birth},
    ]
    (run/'pause_observations.jsonl').write_text('\n'.join(json.dumps(row) for row in rows)+'\n')
    assert m._trace_pause_backend(run,'a','b')['post_cancel']['delivery']['uid'] == 'u'
    (run/'pause_observations.jsonl').write_text('\n'.join(json.dumps(row) for row in rows[:-1])+'\n')
    with pytest.raises(RuntimeError,match='delivery'):m._trace_pause_backend(run,'a','b')
