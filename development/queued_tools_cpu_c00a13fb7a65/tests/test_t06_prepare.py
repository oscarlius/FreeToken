import importlib.util,json,types
from pathlib import Path
import pytest
P=Path(__file__).parents[1]/"t06_prepare.py";s=importlib.util.spec_from_file_location("t06",P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_manifest_requires_three_seed_arms_and_different_two_decode(tmp_path):
 arms=[{"role":x,"rounds":12,"max_tokens":2048,"seed_raw_sha256":m.SEEDS[x]} for x in m.SEEDS]+[{"role":"two","same_prompt":False}]
 (tmp_path/"manifest.json").write_text(__import__('json').dumps({"schema":"ft_t06_route_manifest/v1","rid":m.RID,"candidate_commit":m.CANDIDATE,"arms":arms}))
 assert m.validate_manifest(tmp_path)["arms"][-1]["role"]=="two"
 arms[-1]["same_prompt"]=True;(tmp_path/"manifest.json").write_text(__import__('json').dumps({"schema":"ft_t06_route_manifest/v1","rid":m.RID,"candidate_commit":m.CANDIDATE,"arms":arms}))
 with pytest.raises(ValueError):m.validate_manifest(tmp_path)

def test_execute_single_service_cleanup_and_raw_manifest(monkeypatch,tmp_path):
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
  def dynamic_fixture_port(self): return 43123
  def load_owned_lifecycle(self):
   return types.SimpleNamespace(verified_module=lambda *_:types.SimpleNamespace(next_batch=lambda _:77),stop_owned_process=lambda _:order.append('stop'))
  def start_server(self,g,wt,port,route): (g/'serve.log').write_text('started');(route/'one').write_text('r');order.append('start');return object()
 d=D();monkeypatch.setattr(m,'load_d07',lambda:d);monkeypatch.setattr(m,'packet',lambda _:{'schema':'preflight'})
 r041=tmp_path/'r041';t20=tmp_path/'t20';r041.write_text('x');t20.write_text('y');monkeypatch.setattr(m,'require_d07',lambda:(r041,t20))
 seeds={}
 for role in m.SEEDS: p=tmp_path/f'{role}.txt';p.write_text(role);seeds[role]=p
 monkeypatch.setattr(m,'seed_paths',lambda:seeds)
 def seed(_wt,_port,role,_seed,out,log):
  out.write_text('{}');out.with_suffix('.seed_binding.json').write_text(json.dumps({'seed_raw_sha256':m.SEEDS[role],'actual_wire_first_content_sha256':'x'}));log.write_text('ok')
 monkeypatch.setattr(m,'invoke_seed',seed)
 monkeypatch.setattr(m,'invoke_two',lambda _wt,_p,out,log:(out.write_text(json.dumps({'same_prompt':False})),log.write_text('ok')))
 def analyze(_wt,g,_traces,_two,out): out.write_text(json.dumps({'suffix_tokens':[1],'business_uids':['u']}))
 monkeypatch.setattr(m,'invoke_analysis',analyze);monkeypatch.setattr(m.sys,'platform','linux')
 result=m.execute(worktree,tmp_path/'rounds')
 run=tmp_path/'rounds'/m.RID
 assert result['verdict']=='pending_review' and result['proposed_verdict']=='measured'
 assert result['round_id']==m.RID and result['card']=='T06' and result['base']['commit']==m.CANDIDATE
 assert (run/'result.json').is_file() and (run/'metadata'/'pre_d04.json').is_file()
 assert not (run/'round.json').exists() and not (run/'MANIFEST.sha256').exists()
 assert (run/'manifest.json').is_file() and (run/'owned_cleanup.json').is_file()
 assert order==['lock','idle','start','stop','unlock']
 spec=importlib.util.spec_from_file_location('d06_consumer',P.with_name('d06_g3g4_prepare.py'))
 consumer=importlib.util.module_from_spec(spec);spec.loader.exec_module(consumer)
 evidence=json.loads((run/'manifest.json').read_text())
 consumer._verify_t06_manifest(run,evidence)
 (run/'route_summary.json').write_text('tampered')
 with pytest.raises(RuntimeError,match='SHA differs'):
  consumer._verify_t06_manifest(run,evidence)
