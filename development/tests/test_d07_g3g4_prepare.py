import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

PATH = Path(__file__).parents[1] / "d07_g3g4_prepare.py"
SPEC = importlib.util.spec_from_file_location("d07_g3g4_prepare", PATH)
d07 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d07)


def test_ephemeral_port_is_never_the_shared_service_port():
    port = d07.dynamic_fixture_port()
    assert 1024 <= port <= 65535
    assert port != 8095


def test_user_disposition_preserves_failed_verdict_in_queue_gate(monkeypatch):
    seen = []
    monkeypatch.setattr(d07, "require_closed_round", lambda rid, verdict: seen.append((rid, verdict)))
    d07.require_t20_failed_harness()
    d07.require_t20_kept()
    assert seen == [("E2-R040", "failed_harness"), ("E2-R040", "kept")]


def test_g3_requires_utf8_text_equality(tmp_path):
    off, on = tmp_path / "off.json", tmp_path / "on.json"
    record = {"cold_id": "same", "finish_reason": "stop", "built_tokens": 32052, "completion_tokens": 4}
    off.write_text(json.dumps({"record": record, "text": "逐字相同"}), encoding="utf-8")
    on.write_text(json.dumps({"record": record, "text": "逐字相同"}), encoding="utf-8")
    got = d07.g3_compare(off, on)
    assert got["byte_identical"] is True
    assert got["text_utf8_sha256"] == hashlib.sha256("逐字相同".encode()).hexdigest()
    on.write_text(json.dumps({"record": record, "text": "不同"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="G3 failed"):
        d07.g3_compare(off, on)


def test_prepared_packet_labels_cpu_guard_and_non_acceptance(monkeypatch, tmp_path):
    monkeypatch.setattr(d07, "checked_worktree", lambda path: {"worktree": str(path), "commit": d07.CANDIDATE, "tracked_clean": True})
    monkeypatch.setattr(d07, "verify_d07_tools", lambda path: {"verified": True})
    monkeypatch.setattr(d07, "verify_frozen_cold_helpers", lambda path: {"frozen": True})
    monkeypatch.setattr(d07, "dynamic_fixture_port", lambda: 43001)
    packet = d07.prepared_packet(tmp_path)
    assert packet["fixture_port"] == 43001
    assert packet["cuda_visible_devices_cpu_guard"] == ""
    assert packet["run_requires"] == ["explicit --run", "Linux host", "R041 D04 kept", "T20 E2-R040 D04 kept", "atomic D07 O_EXCL lock", "GPU idle gate"]
    assert packet["timing"].startswith("not a performance")


def test_g3_rejects_different_ids_and_missing_response_fields(tmp_path):
    off, on = tmp_path / "off.json", tmp_path / "on.json"
    good = {"record": {"cold_id": "off", "finish_reason": "stop", "built_tokens": 32052, "completion_tokens": 1}, "text": "x"}
    off.write_text(json.dumps(good), encoding="utf-8")
    on.write_text(json.dumps({**good, "record": {**good["record"], "cold_id": "on"}}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="IDs differ"):
        d07.g3_compare(off, on)
    on.write_text(json.dumps({"record": {"cold_id": "off"}, "text": ""}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="incomplete"):
        d07.g3_compare(off, on)


def test_candidate_frozen_companion_hash_mismatch_fails_before_gpu(tmp_path):
    scripts = tmp_path / "scripts"; scripts.mkdir()
    (scripts / "agent_trace.py").write_text('_SHA256 = "' + "0" * 64 + '"\n', encoding="utf-8")
    (scripts / "_agent_trace_original.py").write_text("changed\n", encoding="utf-8")
    (scripts / "route_analyze.py").write_text("pass\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="frozen companion hash mismatch"):
        d07.verify_d07_tools(tmp_path)


def test_linux_rejects_normalized_only_companion_binding(monkeypatch, tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    companion = b"pass\r\n"
    expected = hashlib.sha256(b"pass\n").hexdigest()
    (scripts / "agent_trace.py").write_text('_SHA256 = "' + expected + '"\n', encoding="utf-8")
    (scripts / "_agent_trace_original.py").write_bytes(companion)
    (scripts / "route_analyze.py").write_bytes(b"pass\n")
    monkeypatch.setattr(d07.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="frozen companion hash mismatch"):
        d07.verify_d07_tools(tmp_path)


def test_candidate_frozen_companion_accepts_crlf_checkout_when_lf_pin_matches(monkeypatch, tmp_path):
    monkeypatch.setattr(d07.sys, "platform", "win32")
    scripts = tmp_path / "scripts"; scripts.mkdir()
    payload = b"one\ntwo\n"
    digest = hashlib.sha256(payload).hexdigest()
    (scripts / "agent_trace.py").write_text(f'_SHA256 = "{digest}"\n', encoding="utf-8")
    (scripts / "_agent_trace_original.py").write_bytes(payload.replace(b"\n", b"\r\n"))
    (scripts / "route_analyze.py").write_text("pass\n", encoding="utf-8")
    assert d07.verify_d07_tools(tmp_path)["frozen_companion_lf_sha256"] == digest


def test_cold_adapter_preloads_owned_probe_before_raw_cold_import(monkeypatch, tmp_path):
    helpers = tmp_path / "helpers/raw"; helpers.mkdir(parents=True)
    probe = helpers / "probe_ft_cold32k.py"
    probe.write_text('URL="live-url"\n', encoding="utf-8")
    cold = helpers / "cold_eq.py"
    cold.write_text(
        'import json,sys\nsys.path.insert(0,"/definitely-not-live")\nfrom probe_ft_cold32k import URL\n'
        'json.dump({"url":URL},open(sys.argv[2],"w"))\n', encoding="utf-8"
    )
    monkeypatch.setattr(d07, "verify_frozen_cold_helpers", lambda _: {"verified": True})
    out = tmp_path / "cold.json"
    d07.invoke_cold_eq(tmp_path, 43001, "cold", out, tmp_path)
    assert json.loads(out.read_text(encoding="utf-8"))["url"] == "http://127.0.0.1:43001/v1/chat/completions"


def test_startup_failure_stops_entire_owned_process_group(monkeypatch, tmp_path):
    class Process:
        pid = 123
        returncode = None
        def poll(self): return None
    stopped = []
    class Owned:
        def stop_owned_process(self, process): stopped.append(process.pid)
        def process_identity(self, pid): return {"pid": pid, "pgid": pid, "session": pid, "start_ticks": 1}
    monkeypatch.setattr(d07.subprocess, "Popen", lambda *_, **__: Process())
    monkeypatch.setattr(d07, "load_owned_lifecycle", lambda: Owned())
    ticks = iter((0, 901))
    monkeypatch.setattr(d07.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(d07, "clean_environment", lambda *_1, **_2: {})
    with pytest.raises(TimeoutError):
        d07.start_server(tmp_path, tmp_path, 43001, None)
    assert stopped == [123]


def test_process_receipt_failure_also_cleans_owned_group(monkeypatch, tmp_path):
    from types import SimpleNamespace
    process = SimpleNamespace(pid=123)
    stopped = []
    owned = SimpleNamespace(
        process_identity=lambda pid: {"pid": pid, "pgid": pid, "session": pid, "start_ticks": 1},
        stop_owned_process=lambda child: stopped.append(child.pid),
    )
    monkeypatch.setattr(d07.subprocess, "Popen", lambda *_, **__: process)
    monkeypatch.setattr(d07, "load_owned_lifecycle", lambda: owned)
    monkeypatch.setattr(d07, "clean_environment", lambda *_1, **_2: {})
    def fail_write(*args):
        raise OSError("receipt disk failure")
    monkeypatch.setattr(d07, "write_new", fail_write)
    with pytest.raises(OSError, match="receipt disk failure"):
        d07.start_server(tmp_path, tmp_path, 43001, None)
    assert stopped == [123]


def test_startup_cleanup_failure_carries_lock_preserving_identity(monkeypatch,tmp_path):
    from types import SimpleNamespace
    process=SimpleNamespace(pid=123)
    calls=[]
    def stop(child):
        calls.append(child.pid)
        raise RuntimeError('owned cleanup failed')
    owned=SimpleNamespace(process_identity=lambda pid:{'pid':pid,'pgid':pid,'session':pid,'start_ticks':8},stop_owned_process=stop)
    monkeypatch.setattr(d07.subprocess,'Popen',lambda *args,**kwargs:process)
    monkeypatch.setattr(d07,'load_owned_lifecycle',lambda:owned)
    monkeypatch.setattr(d07,'clean_environment',lambda *_,**kwargs:{})
    monkeypatch.setattr(d07,'write_new',lambda *args:(_ for _ in ()).throw(OSError('receipt failed')))
    with pytest.raises(RuntimeError,match='owned cleanup failed') as caught:
        d07.start_server(tmp_path,tmp_path,43001,None)
    assert caught.value.owned_process is process and caught.value.owned_cleanup_failed is True
    assert calls==[123]


def test_d07_lock_is_exclusive_bound_and_refuses_foreign_release(monkeypatch, tmp_path):
    lock = tmp_path / "gpu.lock"
    monkeypatch.setattr(d07, "LOCK", lock)
    monkeypatch.setattr(d07, "process_birth", lambda: {"pid": 7, "start_ticks": 8, "execution_id": "7:8"})
    owner = d07.take_d07_gpu_lock("E2-R043", 69)
    assert json.loads(lock.read_text(encoding="utf-8"))["batch"] == 69
    with pytest.raises(RuntimeError, match="foreign GPU lock"):
        d07.take_d07_gpu_lock("E2-R043", 70)
    d07.release_d07_gpu_lock(owner)
    assert not lock.exists()
    lock.write_text("foreign", encoding="utf-8")
    with pytest.raises(RuntimeError, match="foreign/replaced"):
        d07.release_d07_gpu_lock(owner)


def test_failed_cleanup_preserves_lock_when_owned_group_is_live(monkeypatch, tmp_path):
    from types import SimpleNamespace
    closure = tmp_path / "kept.json"
    closure.write_text('{}')
    released = []
    monkeypatch.setattr(d07.sys, "platform", "linux")
    monkeypatch.setattr(d07, "require_r041_kept", lambda _: closure)
    monkeypatch.setattr(d07, "require_t20_kept", lambda: closure)
    owned = SimpleNamespace(owned_group_alive=lambda _: True)
    monkeypatch.setattr(d07, "load_owned_lifecycle", lambda: owned)
    monkeypatch.setattr(d07, "take_d07_gpu_lock", lambda *args: {"batch": 77})
    monkeypatch.setattr(d07, "release_d07_gpu_lock", lambda owner: released.append(owner))
    monkeypatch.setattr(d07, "require_gpu_idle", lambda: [4])
    monkeypatch.setattr(d07, "prepared_packet", lambda _: {})
    monkeypatch.setattr(d07, "require_child_receipt", lambda *_: {})
    def fail_start(*args):
        failure = RuntimeError("cleanup failed")
        failure.owned_process = SimpleNamespace(pid=123)
        raise failure
    monkeypatch.setattr(d07, "start_server", fail_start)
    with pytest.raises(RuntimeError, match="preserve GPU lock"):
        d07.execute(tmp_path, tmp_path / "runs", owned_child=True, batch=77, launch_receipt=tmp_path / "receipt.json")
    assert released == []
    assert not list((tmp_path / "runs").glob("*/owned_cleanup.json"))


def test_controller_reserves_atomic_batch_and_child_receipt_binds_birth(monkeypatch,tmp_path):
    from types import SimpleNamespace
    closure=tmp_path/'kept';closure.write_text('{}'); calls=[]; batches=iter((88,89,88))
    monkeypatch.setattr(d07.sys,'platform','linux');monkeypatch.setattr(d07,'require_r041_kept',lambda _:closure);monkeypatch.setattr(d07,'require_t20_kept',lambda:closure)
    monkeypatch.setattr(d07,'prepared_packet',lambda _:{'source':'ok'});monkeypatch.setattr(d07,'process_birth',lambda pid=None:{'pid':91 if pid is None else pid,'start_ticks':7,'execution_id':f'{91 if pid is None else pid}:7'})
    class Owned:
      def verified_module(self,*_):return SimpleNamespace(next_batch=lambda _:next(batches))
      def reserve_process(self,helper,batch,rid,argv,path,reserved):
       if path.exists():raise FileExistsError(path)
       calls.append((batch,rid,argv,reserved));path.write_text(json.dumps({**reserved,'state':'launched','batch_pid':123}));return json.loads(path.read_text())
      def process_identity(self,pid):return {'pid':pid,'start_ticks':9,'execution_id':f'{pid}:9'}
      def publish_receipt(self,path,identity,value):path.write_text(json.dumps(value))
    monkeypatch.setattr(d07,'load_owned_lifecycle',lambda:Owned());monkeypatch.setattr(d07,'RUNS',tmp_path);monkeypatch.setattr(d07,'LOCK',tmp_path/'gpu.lock')
    result=d07.execute(tmp_path,tmp_path/'out'); second=d07.execute(tmp_path,tmp_path/'out')
    assert calls[0][0]==88 and result['child']=={'pid':123,'start_ticks':9,'execution_id':'123:9'} and result['argv_sha256']==d07.argv_sha256(calls[0][2])
    receipt=tmp_path/'launch_E2-R043_batch88.json'; second_receipt=tmp_path/'launch_E2-R043_batch89.json'
    assert receipt.is_file() and second_receipt.is_file() and second['batch']==89
    with pytest.raises(FileExistsError):d07.execute(tmp_path,tmp_path/'out')
    monkeypatch.setattr(d07,'process_birth',lambda _=None:{'pid':123,'start_ticks':9,'execution_id':'123:9'})
    with pytest.raises(RuntimeError,match='binding differs'):d07.require_child_receipt(receipt,89,tmp_path,tmp_path/'out')


def test_default_main_is_preflight_only_and_never_allocates_batch(monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(d07,'prepared_packet',lambda _:{'preflight':True})
    monkeypatch.setattr(d07,'execute',lambda *_a,**_k:(_ for _ in ()).throw(AssertionError('must not allocate')))
    assert d07.main(['--worktree',str(tmp_path)])==0
    assert json.loads(capsys.readouterr().out)=={'preflight':True}



def test_closed_round_gate_reads_only_registered_metadata_and_stat_tree(monkeypatch,tmp_path):
 root,rounds=tmp_path/'root',tmp_path/'rounds';rid='E2-R041-gate-D17';directory=rounds/rid;history=directory/'round_history';history.mkdir(parents=True)
 round_json=directory/'round.json';manifest=directory/'MANIFEST.sha256';checker=directory/'round_json_append.py';payload=directory/'large_raw.bin'
 round_json.write_text(json.dumps({'round_id':rid,'verdict':'kept'}));manifest.write_text('sealed manifest metadata\n');checker.write_text('# pinned checker\n');(history/'0001.json').write_text('{}');payload.write_bytes(b'raw payload must not be read')
 for path in (round_json,manifest,checker,history/'0001.json',payload): path.chmod(0o444)
 history.chmod(0o555);directory.chmod(0o555)
 pins=root/'runs/plan_batches/closed_round_pins';pins.mkdir(parents=True)
 pins.joinpath(rid+'.json').write_text(json.dumps({'rid':rid,'round_sha256':d07.sha256(round_json),'manifest_sha256':d07.sha256(manifest)}));pins.joinpath(rid+'.json').chmod(0o444)
 monkeypatch.setattr(d07,'ROOT',root);monkeypatch.setattr(d07,'ROUNDS',rounds);monkeypatch.setattr(d07,'VENV',tmp_path/'venv')
 commands=[];monkeypatch.setattr(d07.subprocess,'run',lambda argv,**_kwargs:(commands.append(argv),type('R',(),{'returncode':0})())[1])
 original=Path.read_bytes
 def guard(self):
  if self==payload: raise AssertionError('raw payload was read')
  return original(self)
 monkeypatch.setattr(Path,'read_bytes',guard)
 assert d07.require_closed_round(rid,'kept')==round_json
 assert commands==[[str(tmp_path/'venv/bin/python'),str(checker),str(directory),'check']]

def test_closed_round_gate_rejects_bad_pin_writable_tree_and_history_failure(monkeypatch,tmp_path):
 root,rounds=tmp_path/'root',tmp_path/'rounds';rid='E2-R040';directory=rounds/rid;directory.mkdir(parents=True);history=directory/'round_history';history.mkdir()
 round_json=directory/'round.json';manifest=directory/'MANIFEST.sha256';checker=directory/'round_json_append.py'
 round_json.write_text(json.dumps({'round_id':rid,'verdict':'kept'}));manifest.write_text('manifest');checker.write_text('checker');(history/'0001.json').write_text('{}')
 for path in (round_json,manifest,checker,history/'0001.json'):path.chmod(0o444)
 history.chmod(0o555);directory.chmod(0o555);pins=root/'runs/plan_batches/closed_round_pins';pins.mkdir(parents=True);pin=pins/(rid+'.json');pin.write_text(json.dumps({'rid':rid,'round_sha256':'bad','manifest_sha256':d07.sha256(manifest)}));pin.chmod(0o444)
 monkeypatch.setattr(d07,'ROOT',root);monkeypatch.setattr(d07,'ROUNDS',rounds);monkeypatch.setattr(d07,'VENV',tmp_path/'venv');monkeypatch.setattr(d07.subprocess,'run',lambda *_a,**_k:type('R',(),{'returncode':0})())
 with pytest.raises(RuntimeError,match='SHA differs'):d07.require_closed_round(rid,'kept')
 pin.chmod(0o644);pin.write_text(json.dumps({'rid':rid,'round_sha256':d07.sha256(round_json),'manifest_sha256':d07.sha256(manifest)}));pin.chmod(0o444)
 directory.chmod(0o755)
 payload=directory/'payload.bin';payload.write_text('x');payload.chmod(0o644)
 directory.chmod(0o555)
 with pytest.raises(RuntimeError,match='writable'):d07.require_closed_round(rid,'kept')
 payload.chmod(0o444);monkeypatch.setattr(d07.subprocess,'run',lambda *_a,**_k:type('R',(),{'returncode':1})())
 with pytest.raises(RuntimeError,match='history check failed'):d07.require_closed_round(rid,'kept')

def test_d06_delegates_kept_prerequisite_to_d07_closed_round_gate(monkeypatch,tmp_path):
 source=PATH.with_name('d06_g3g4_prepare.py');spec=importlib.util.spec_from_file_location('d06_closed_round_delegate',source);d06=importlib.util.module_from_spec(spec);spec.loader.exec_module(d06)
 closure=tmp_path/'round.json';closure.write_text('{}');calls=[]
 class Gate:
  def require_closed_round(self,rid,verdict): calls.append((rid,verdict));return closure
 monkeypatch.setattr(d06,'_d07_closed_round_gate',lambda:Gate())
 assert d06.require_kept('E2-R040')==closure and calls==[('E2-R040','kept')]


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX readonly binding')
@pytest.mark.parametrize('mutation', [None, 'r046', 'wrong_sha', 'relative', 'writable', 'different_round'])
def test_failed_r040_can_use_only_pinned_external_readonly_history_checker(monkeypatch, tmp_path, mutation):
 root, rounds = tmp_path/'root', tmp_path/'rounds'
 rid = 'E2-R039' if mutation == 'different_round' else ('E2-R046' if mutation == 'r046' else 'E2-R040')
 directory = rounds/rid; directory.mkdir(parents=True)
 rj = directory/'round.json'; rj.write_text(json.dumps({'round_id':rid,'verdict':'failed_harness'}))
 manifest = directory/'MANIFEST.sha256'; manifest.write_text('frozen raw manifest')
 raw = directory/'raw.bin'; raw.write_bytes(b'must never read raw')
 for path in (rj,manifest,raw): path.chmod(0o444)
 directory.chmod(0o555)
 checker = tmp_path/'external_writer.py'; checker.write_bytes(b'canonical writer fixture')
 expected = d07.sha256(checker); monkeypatch.setattr(d07,'ROUND_WRITER_SHA',expected)
 checker.chmod(0o644 if mutation == 'writable' else 0o444)
 registered = {'rid':rid,'round_sha256':d07.sha256(rj),'manifest_sha256':d07.sha256(manifest),
               'history_checker_path':'relative.py' if mutation == 'relative' else str(checker),
               'history_checker_sha256':'0'*64 if mutation == 'wrong_sha' else expected}
 pins=root/'runs/plan_batches/closed_round_pins'; pins.mkdir(parents=True)
 pin=pins/(rid+'.json'); pin.write_text(json.dumps(registered)); pin.chmod(0o444)
 monkeypatch.setattr(d07,'ROOT',root); monkeypatch.setattr(d07,'ROUNDS',rounds)
 calls=[]
 monkeypatch.setattr(d07.subprocess,'run',lambda argv,**_:(calls.append(argv),type('R',(),{'returncode':0})())[1])
 original=Path.read_bytes
 def guard(path):
  if path==raw: pytest.fail('startup must not reread raw')
  return original(path)
 monkeypatch.setattr(Path,'read_bytes',guard)
 if mutation in (None, 'r046'):
  assert d07.require_closed_round(rid,'failed_harness')==rj
  assert calls[0][1:]==[str(checker),str(directory),'check']
 else:
  with pytest.raises(RuntimeError,match='checker'):
   d07.require_closed_round(rid,'failed_harness')
  assert not calls
