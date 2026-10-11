import importlib.util,json,types
from pathlib import Path
import pytest

P=Path(__file__).parents[1]/"t06_prepare.py";s=importlib.util.spec_from_file_location("t06",P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def test_cpu_fixture_socket_guard_is_ephemeral_and_packet_declares_cuda_hidden(monkeypatch,tmp_path):
 source=P.with_name("d07_g3g4_prepare.py");spec=importlib.util.spec_from_file_location("t06_d07_socket",source);d07=importlib.util.module_from_spec(spec);spec.loader.exec_module(d07)
 port=d07.dynamic_fixture_port();assert 1024 <= port <= 65535 and port != 8095
 class D:
  def checked_worktree(self,_): return {"tracked_clean":True}
  def verify_d07_tools(self,_): return {"tools":True}
  def dynamic_fixture_port(self): return port
 monkeypatch.setattr(m,"load_d07",lambda:D());monkeypatch.setattr(m,"seed_paths",lambda:{role:tmp_path/f"{role}.txt" for role in m.SEEDS})
 for path in m.seed_paths().values(): path.write_text("seed")
 packet=m.packet(tmp_path);assert packet["fixture_port"]==port and packet["cuda_visible_devices_cpu_guard"]==""

def test_manifest_requires_four_independent_arms_and_seed12k_training_only(tmp_path):
 arms=[{"role":x,"directory":f"G_{x}","kind":"generate","rounds":12,"max_tokens":2048,"seed_raw_sha256":m.SEEDS[x]} for x in m.SEEDS]+[{"role":"two","directory":"G_two","kind":"two-decode","same_prompt":False,"ctx":8000,"max_tokens":256}]
 doc={"schema":"ft_t06_route_manifest/v1","rid":m.RID,"candidate_commit":m.CANDIDATE,"arms":arms,"d15_training_route":"G_seed12k/route","heldout_routes":["G_seed_45k/route","G_seed_real/route","G_two/route"]}
 (tmp_path/"manifest.json").write_text(json.dumps(doc));assert m.validate_manifest(tmp_path)["arms"][-1]["role"]=="two"
 doc["d15_training_route"]="G_seed_real/route";(tmp_path/"manifest.json").write_text(json.dumps(doc))
 with pytest.raises(ValueError,match="training/heldout"):m.validate_manifest(tmp_path)

def test_execute_four_serial_services_raw_manifest_and_d06_hash_consumer(monkeypatch,tmp_path):
 order=[]; worktree=tmp_path/'wt';(worktree/'scripts').mkdir(parents=True)
 for name in ('agent_trace.py','route_analyze.py','multisession_probe.py'):(worktree/'scripts'/name).write_text('')
 class D:
  ATOMIC_HELPER_SHA='pin'
  def write_new(self,p,d): m.write_new(p,d)
  def require_r041_kept(self,_): p=tmp_path/'r041.json';p.write_text('{}');return p
  def require_t20_kept(self): p=tmp_path/'t20.json';p.write_text('{}');return p
  def require_gpu_idle(self): order.append('idle');return [0]
  def take_d07_gpu_lock(self,r,b): order.append('lock');return {'owner':r,'batch':b}
  def release_d07_gpu_lock(self,o): order.append('unlock')
  def dynamic_fixture_port(self): return 43123+len(order)
  def load_owned_lifecycle(self): return types.SimpleNamespace(verified_module=lambda *_:types.SimpleNamespace(next_batch=lambda _:77),stop_owned_process=lambda _:order.append('stop'))
  def start_server(self,g,wt,port,route): (g/'serve.log').write_text(f'started {port}');(route/'one').write_text('r');order.append('start');return object()
 d=D();monkeypatch.setattr(m,'load_d07',lambda:d);monkeypatch.setattr(m,'packet',lambda _:{'schema':'preflight'})
 r041=tmp_path/'r041';t20=tmp_path/'t20';r041.write_text('x');t20.write_text('y');monkeypatch.setattr(m,'require_d07',lambda:(r041,t20))
 seeds={}
 for role in m.SEEDS: p=tmp_path/f'{role}.txt';p.write_text(role);seeds[role]=p
 monkeypatch.setattr(m,'seed_paths',lambda:seeds)
 def seed(_wt,_port,role,_seed,out,log): out.write_text('{}');out.with_suffix('.seed_binding.json').write_text(json.dumps({'seed_raw_sha256':m.SEEDS[role],'actual_wire_first_content_sha256':'x'}));log.write_text('ok')
 monkeypatch.setattr(m,'invoke_seed',seed);monkeypatch.setattr(m,'invoke_two',lambda _wt,_p,out,log:(out.write_text(json.dumps({'same_prompt':False})),log.write_text('ok')))
 def analyze(_wt,_g,out,**kwargs):
  if kwargs.get("trace") is not None:
   out.write_text(json.dumps({"analysis_scope":"trace_bound_business_requests","suffix_tokens":[{"uid":n,"n":1} for n in range(12)],"business_uids":list(range(12)),"missing_business_routes":[],"completion_count":12,"completions":{str(n):{"max_tokens":2048} for n in range(12)}},sort_keys=True))
  else:
   out.write_text(json.dumps({"analysis_scope":"all_prefill_requests","raw_suffix_tokens":{"1":1,"2":1},"business_uids":[],"two_decode_pairs":[{"uids":[1,2]}],"two_decode_pair_steps":{"pair":0},"R_B_pending":True,"R_B":{},"R_B_nullreason":"declared two-decode pair evidence or overlapping decode routes unavailable"},sort_keys=True))
 monkeypatch.setattr(m,'invoke_analysis',analyze);monkeypatch.setattr(m.sys,'platform','linux')
 result=m.execute(worktree,tmp_path/'rounds');run=tmp_path/'rounds'/m.RID
 assert result['verdict']=='pending_review' and result['proposed_verdict']=='measured'
 assert result['base']=={'code_version':'E2-base.1@0aa23431','commit':m.CANDIDATE}
 assert all((run/f'G_{role}'/'route').is_dir() for role in (*m.SEEDS,'two'))
 assert order==['lock','idle','start','stop','start','stop','start','stop','start','stop','unlock']
 assert not (run/'round.json').exists() and not (run/'MANIFEST.sha256').exists()
 spec=importlib.util.spec_from_file_location('d06_consumer',P.with_name('d06_g3g4_prepare.py'));consumer=importlib.util.module_from_spec(spec);spec.loader.exec_module(consumer)
 evidence=json.loads((run/'manifest.json').read_text());consumer._verify_t06_manifest(run,evidence)
 assert evidence['d15_training_route']=='G_seed12k/route' and 'G_seed_real/route' in evidence['heldout_routes']
 seed12=next(arm for arm in evidence["arms"] if arm["role"]=="seed12k")
 heldout=next(arm for arm in evidence["arms"] if arm["role"]=="seed_real")
 for key in ("serve_log","trace","seed_binding","route_summary"):
  seed12[key]=heldout[key];seed12[key+"_sha256"]=heldout[key+"_sha256"];evidence["files"][f"seed12k_{key}"]={"path":heldout[key],"sha256":heldout[key+"_sha256"]}
 with pytest.raises(RuntimeError,match="seed arm binding"):
  consumer._verify_t06_manifest(run,evidence)
 evidence=json.loads((run/'manifest.json').read_text())
 (run/'G_seed_real'/'serve.log').write_text('tampered')
 with pytest.raises(RuntimeError,match='SHA differs'):consumer._verify_t06_manifest(run,evidence)

def test_invoke_analysis_accepts_empty_two_business_uids_but_rejects_seed_missing_uid(monkeypatch,tmp_path):
 class D:
  def clean_environment(self,_): return {}
 monkeypatch.setattr(m,"load_d07",lambda:D())
 def fake_run(cmd,**_kwargs):
  out=Path(cmd[cmd.index("--out")+1])
  if "--traces" in cmd:
   out.write_text(json.dumps({"analysis_scope":"trace_bound_business_requests","suffix_tokens":[{"uid":n,"n":1} for n in range(12)],"business_uids":list(range(12)),"missing_business_routes":[],"completion_count":12,"completions":{str(n):{"max_tokens":2048} for n in range(12)}}))
  else:
   assert "--traces" not in cmd
   out.write_text(json.dumps({"analysis_scope":"all_prefill_requests","raw_suffix_tokens":{"1":1,"2":1},"business_uids":[],"two_decode_pairs":[{"uids":[1,2]}],"two_decode_pair_steps":{"pair":0},"R_B_pending":True,"R_B":{},"R_B_nullreason":"declared two-decode pair evidence or overlapping decode routes unavailable"}))
 monkeypatch.setattr(m.subprocess,"run",fake_run)
 g=tmp_path/"G_seed";g.mkdir();(g/"route").mkdir();(g/"serve.log").write_text("log");trace=g/"trace.json";trace.write_text("trace")
 m.invoke_analysis(tmp_path,g,tmp_path/"seed.json",trace=trace)
 two_g=tmp_path/"G_two";two_g.mkdir();(two_g/"route").mkdir();(two_g/"serve.log").write_text("log");two=two_g/"two.json";two.write_text("two")
 m.invoke_analysis(tmp_path,two_g,tmp_path/"two.json.out",two=two)
 def missing_uid(cmd,**_kwargs):
  out=Path(cmd[cmd.index("--out")+1]);out.write_text(json.dumps({"analysis_scope":"trace_bound_business_requests","suffix_tokens":[{"uid":1,"n":1}],"business_uids":[],"missing_business_routes":[],"completion_count":12,"completions":{str(n):{"max_tokens":2048} for n in range(12)}}))
 monkeypatch.setattr(m.subprocess,"run",missing_uid)
 (g/"route_analyze.log").unlink()
 with pytest.raises(RuntimeError,match="UID-bound"):
  m.invoke_analysis(tmp_path,g,tmp_path/"bad.json",trace=trace)
