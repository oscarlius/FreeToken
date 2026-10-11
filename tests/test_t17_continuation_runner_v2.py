import hashlib, importlib.util, json
from pathlib import Path
import pytest
import os
from test_t17_continuation_selection import inputs, repo, SOURCE_ROOT, r041_proof, retained_review
PATH=SOURCE_ROOT/"t17_continuation_runner_v2.py"; spec=importlib.util.spec_from_file_location("runner_v2",PATH); runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
def input_file(tmp_path):
 raw=json.dumps(inputs(),separators=(",",":")).encode(); p=tmp_path/"real.json";p.write_bytes(raw);return p,hashlib.sha256(raw).hexdigest(),json.loads(raw)

@pytest.mark.parametrize('fault', ['none', 'input_changed', 'measurement'])
def test_full_t20_runtime_callback_uses_bound_inputs_and_original_lock(tmp_path, monkeypatch, fault):
 from types import SimpleNamespace
 runtime=runner._runtime()
 spec=importlib.util.spec_from_file_location('retained_t20_callback_test', SOURCE_ROOT/'t17_continuation_runner.py')
 old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
 source,digest,document=input_file(tmp_path)
 lock=tmp_path/'owned.lock'; events=[]; calls=[]
 class Base:
  def __init__(self, options): self.options=options;self.proc=None
  def set_status(self, **values): events.append(values['state'])
  def stop(self): events.append('stop');self.proc=None
  def lock_release(self):
   assert lock.read_text()==self.token
   assert lock.stat().st_ino==self.lock_inode
   lock.unlink();events.append('release')
 gpu=SimpleNamespace(Run=Base, helper=SimpleNamespace(), protocol={'Runner':Base,'LOCK':lock})
 monkeypatch.setattr(old,'_imports',lambda:(gpu,object()))
 def continuation(resources, case):
  assert lock.exists()
  if fault=='input_changed': source.write_text('{}')
  return {'result':'measurements_pass_pending_independent_review'}
 monkeypatch.setattr(old,'_suite_modules',lambda wt:(None,None,SimpleNamespace(run_case=continuation)))
 def full(base, **kwargs):
  assert lock.exists() and not (base.directory/'result.json').exists()
  calls.append(kwargs)
  if fault=='measurement': raise RuntimeError('measurement failed')
  return {'all_sections_measured':True,'admitted':False}
 original_spec=importlib.util.spec_from_file_location
 class Loader:
  def create_module(self, spec): return None
  def exec_module(self, module): module.run_full_measurements=full
 def component_spec(name, path, *args, **kwargs):
  if name=='ft_t20_actual_measurements':
   return importlib.util.spec_from_loader(name,Loader())
  return original_spec(name,path,*args,**kwargs)
 monkeypatch.setattr(importlib.util,'spec_from_file_location',component_spec)
 name=document['cases'][0]['name']; directory=tmp_path/'round'
 plan={'directory':str(directory),'candidate':{'worktree':str(tmp_path),'candidate_commit':'a'*40,'parent_commit':'b'*40},
  'prior_t16':{'round':'E2-R041-gate-D17','batch':67},'case_choices':[{'name':name,'allow_cold_envelope':True}],
  'rid':'E2-R040','batch':68,'inputs':str(source),'inputs_sha256':digest,'input_provenance':None,
  'execution_archive':None,'selection':{'schema':'test-selection'},
  't20_full':{'d16_source_review':'review.json','d16_source_review_sha256':'c'*64}}
 if fault=='none':
  result=runtime._execute_lifecycle(old,plan,cases_by_name={name:document['cases'][0]},run_kind='t20')
  assert result['t20_measurements']=={'all_sections_measured':True,'admitted':False}
  assert (directory/'v2_result.json').exists()
 else:
  error=runtime.RuntimeErrorV2 if fault=='input_changed' else RuntimeError
  with pytest.raises(error,match='input source changed|measurement failed'):
   runtime._execute_lifecycle(old,plan,cases_by_name={name:document['cases'][0]},run_kind='t20')
  assert (directory/'failed_harness.json').exists()
  assert not (directory/'result.json').exists() and not (directory/'v2_result.json').exists()
 assert not lock.exists() and events[-2:]==['stop','release']
 assert len(calls)==(0 if fault=='input_changed' else 1)
 if calls:
  assert calls[0]['candidate_commit']=='a'*40 and calls[0]['realinputs']==document
  assert calls[0]['d16_source_review_sha256']=='c'*64
  assert calls[0]['d16_wrapper']==SOURCE_ROOT/'d16_exact_service_startup.py'
def test_dry_plan_binds_clean_candidate_and_all28(tmp_path):
 p,d,_=input_file(tmp_path); root,base,candidate=repo(tmp_path/"git",change=True); v=runner.plan(p,run_kind="t17",cases="all",envelope_cases="sample4",assigned_rid="E2-R035",candidate_worktree=root,candidate_sha=candidate,parent_sha=base,expected_input_sha256=d)
 assert len(v["case_choices"])==28 and sum(x["allow_cold_envelope"] for x in v["case_choices"])==4 and v["admitted"] is False


def test_remaining_plan_binds_receipt_and_declares_retained_source(tmp_path, monkeypatch):
 p,d,document=input_file(tmp_path); review,digest,_,_=retained_review(tmp_path/"review",document)
 class FakeRuntime:
  @staticmethod
  def verify_candidate(worktree, candidate_sha, parent_sha):
   return {"worktree":str(worktree),"candidate_commit":candidate_sha,"parent_commit":parent_sha,"clean":True}
 monkeypatch.setattr(runner,"_runtime",lambda:FakeRuntime)
 value=runner.plan(p,run_kind="t17",cases="remaining",envelope_cases="sample4",assigned_rid="E2-R038",
                   candidate_worktree=tmp_path,candidate_sha="a9dca443cd07e1f60d1533e0a678935a09d21636",
                   parent_sha="e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7",expected_input_sha256=d,
                   resume_review=review,resume_review_sha256=digest)
 assert len(value["case_choices"]) == 14
 assert value["retained_source_commit"] == "e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7"
def test_t20_without_r041_proof_forces_all28_even_when_tree_diff_exists(tmp_path):
 p,d,_=input_file(tmp_path);root,base,candidate=repo(tmp_path/"git",change=True);v=runner.plan(p,run_kind="t20",cases="t20-sample4",envelope_cases="sample4",assigned_rid="E2-R040",candidate_worktree=root,candidate_sha=candidate,parent_sha=base,d17_worktree=root,d17_base=base,d17_candidate=candidate,expected_input_sha256=d)
 assert len(v["case_choices"])==28


def test_full_t20_plan_pins_d16_review_without_admitting_execution(tmp_path):
 p,d,_=input_file(tmp_path);root,base,candidate=repo(tmp_path/'git',change=True)
 value=runner.plan(p,run_kind='t20',cases='t20-sample4',envelope_cases='sample4',assigned_rid='E2-R040',
  candidate_worktree=root,candidate_sha=candidate,parent_sha=base,expected_input_sha256=d,
  t20_full=True,d16_source_review=tmp_path/'review.json',d16_source_review_sha256='a'*64)
 assert value['t20_full']=={'d16_source_review':str((tmp_path/'review.json').resolve()),'d16_source_review_sha256':'a'*64}
 assert value['admitted'] is False and value['requests_sent'] is False and len(value['case_choices'])==28


@pytest.mark.parametrize('kind,rid,full,review,digest,message', [
 ('t17','E2-R038',True,'review','a'*64,'E2-R040/T20'),
 ('t20','E2-R040',True,None,None,'D16 source review'),
 ('t20','E2-R040',True,'review','invalid','D16 source review'),
 ('t20','E2-R040',False,'review','a'*64,'full T20 mode')])
def test_full_t20_mode_rejects_missing_or_misrouted_proof_before_inputs(kind,rid,full,review,digest,message):
 with pytest.raises(runner.V2Error,match=message):
  runner.plan('must-not-read.json',run_kind=kind,cases='all',envelope_cases='sample4',assigned_rid=rid,
   candidate_worktree='unused',candidate_sha='a'*40,parent_sha='b'*40,t20_full=full,
   d16_source_review=review,d16_source_review_sha256=digest)


def test_full_t20_preflight_rejects_missing_measurement_sources_before_services(tmp_path, monkeypatch):
 class Runtime:
  verify_cpu_report=staticmethod(lambda *a,**k:{'candidate_commit':'a'*40,'files':{}})
  verify_t16=staticmethod(lambda *a,**k:{})
 monkeypatch.setattr(runner,'_runtime',lambda:Runtime)
 with pytest.raises(runner.V2Error,match='inventory missing: t20_measurements.py'):
  runner.preflight({'candidate':{'candidate_commit':'a'*40,'parent_commit':'b'*40},'t20_full':{},'selection':{'run_kind':'t20'}},
   cpu_report='fixture',source_root=tmp_path,rounds='fixture',closure_binding='fixture',
   prior_t16_rid='E2-R041-gate-D17',prior_t16_batch=67,rid='E2-R040',batch=68,directory=tmp_path/'round')
 assert not (tmp_path/'round').exists()
def test_plan_forwards_r041_pins_and_preserves_recomputed_proof(tmp_path, monkeypatch):
 p,d,_=input_file(tmp_path); root,base,candidate=repo(tmp_path/"git",change=True)
 calls={}
 class FakeSelection:
  INPUTS_SHA256=d
  @staticmethod
  def load_realinput28(path, expected_document_sha256):
   assert expected_document_sha256 == d
   return inputs()
  @staticmethod
  def select(document, **kwargs):
   calls.update(kwargs)
   assert kwargs["expected_verifier_sha256"] == "8" * 64
   return {"measurement_cases":["prefix-8192-tail-65"],
           "ordinary_cold_envelope_cases":["prefix-8192-tail-65"],
           "case_input_sha256":{"prefix-8192-tail-65": document["cases"][0]["input_ids_sha256"]},
           "r041_proof":{"r041_round":"/sealed/R041", "independent_review":"/sealed/review",
                         "verifier_sha256":"8" * 64,
                         "verification_inputs": {key: str(value) if isinstance(value, Path) else value
                                                 for key, value in r041_proof(tmp_path).items()}}}
 class FakeRuntime:
  @staticmethod
  def verify_candidate(worktree, candidate_sha, parent_sha):
   return {"candidate_commit":candidate_sha,"parent_commit":parent_sha}
 monkeypatch.setattr(runner,"_selection",lambda:FakeSelection)
 monkeypatch.setattr(runner,"_runtime",lambda:FakeRuntime)
 doc=runner.plan(p,run_kind="t20",cases="t20-sample4",envelope_cases="sample4",assigned_rid="E2-R040",
                 candidate_worktree=root,candidate_sha=candidate,parent_sha=base,expected_input_sha256=d,
                 **r041_proof(tmp_path))
 assert calls["r041_round"] == r041_proof(tmp_path)["r041_round"]
 assert doc["selection"]["r041_proof"]["verifier_sha256"] == "8" * 64
 assert doc["selection"]["r041_proof"]["verification_inputs"] == {
  key: str(value) if isinstance(value, Path) else value
  for key, value in r041_proof(tmp_path).items()
 }
 assert doc["case_choices"] == [{"name":"prefix-8192-tail-65", "input_ids_sha256":inputs()["cases"][0]["input_ids_sha256"], "allow_cold_envelope":True}]


def test_cli_forwards_r041_inputs_to_plan(tmp_path, monkeypatch, capsys):
 p,d,_=input_file(tmp_path); root,base,candidate=repo(tmp_path/"git")
 calls={}
 def fake_plan(realinput28, **kwargs):
  calls["realinput28"], calls["kwargs"] = realinput28, kwargs
  return {"dry": True}
 monkeypatch.setattr(runner,"plan",fake_plan)
 proof=r041_proof(tmp_path)
 argv=["--realinput28",str(p),"--candidate-worktree",str(root),"--candidate-sha",candidate,
       "--parent-sha",base,"--run-kind","t20","--cases","t20-sample4","--rid","E2-R040","--batch","64"]
 for key,value in proof.items():
  argv.extend(["--"+key.replace("_","-"),str(value)])
 assert runner.main(argv) == 0
 assert calls["realinput28"] == str(p)
 assert calls["kwargs"]["expected_verifier_sha256"] == "8" * 64
 assert calls["kwargs"]["r041_round"] == str(proof["r041_round"])
 assert json.loads(capsys.readouterr().out) == {"dry": True}


def test_plan_rejects_unknown_r041_field(tmp_path):
 p,d,_=input_file(tmp_path);root,base,candidate=repo(tmp_path/"git")
 with pytest.raises(runner.V2Error,match="unknown R041"):
  runner.plan(p,run_kind="t17",cases="all",envelope_cases="none",assigned_rid="E2-R035",candidate_worktree=root,candidate_sha=candidate,parent_sha=base,expected_input_sha256=d,permit=True)


def test_execute_rejects_caller_admitted_without_sealed_preflight_paths(tmp_path):
 p,d,doc=input_file(tmp_path);root,base,candidate=repo(tmp_path/"git"); plan=runner.plan(p,run_kind="t17",cases="all",envelope_cases="none",assigned_rid="E2-R035",candidate_worktree=root,candidate_sha=candidate,parent_sha=base,expected_input_sha256=d); plan.update(admitted=True,rid="E2-R035",batch=1,directory=str(tmp_path/"out"))
 receipt=tmp_path/"sealed.json"; receipt.write_text(json.dumps(plan,sort_keys=True)); receipt.chmod(0o444)
 runtime=runner._runtime()
 with pytest.raises((KeyError, runtime.RuntimeErrorV2)):
  runtime.execute(plan,cases_by_name={x["name"]:x for x in doc["cases"]},sealed_preflight=receipt)

def test_cpu_dry_plan_pass_cannot_admit_runtime(tmp_path):
 report=tmp_path/"cpu.json"
 report.write_text(json.dumps({"verdict":"PASS","runtime_lifecycle_verified":False}))
 report.chmod(0o444)
 runtime=runner._runtime()
 with pytest.raises(runtime.RuntimeErrorV2,match="dry-plan tests cannot admit execution"):
  runtime.verify_cpu_report(report,tmp_path)

@pytest.mark.skipif(os.name == 'nt', reason='POSIX immutable archive permissions')
@pytest.mark.parametrize('bad_path', ['../outside.log', '/tmp/outside.log'])
def test_cpu_log_inventory_cannot_escape_archive(tmp_path, bad_path):
 runtime=runner._runtime()
 report=tmp_path/'cpu.json'
 report.write_text(json.dumps({'verdict':'PASS','runtime_lifecycle_verified':True,
  'files':{'x.py':'0'*64},'argv':['pytest'],'candidate_commit':'a'*40,
  'log_path':bad_path,'log_sha256':'0'*64}))
 report.chmod(0o444)
 with pytest.raises(runtime.RuntimeErrorV2, match='invalid CPU source path'):
  runtime.verify_cpu_report(report,tmp_path)

@pytest.mark.skipif(os.name == 'nt', reason='POSIX immutable archive permissions')
def test_cpu_archive_requires_generated_startup_dependencies(tmp_path):
 runtime=runner._runtime(); log=tmp_path/'pytest.log';log.write_text('PASS');log.chmod(0o444)
 files={}
 for name in runtime.REQUIRED_SOURCE_FILES:
  path=tmp_path/name;path.write_text(name);path.chmod(0o444)
  files[name]=hashlib.sha256(path.read_bytes()).hexdigest()
 value={'verdict':'PASS','runtime_lifecycle_verified':True,'files':files,
  'argv':['pytest'],'candidate_commit':'a'*40,'log_path':'pytest.log',
  'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
 report=tmp_path/'cpu.json';report.write_text(json.dumps(value));report.chmod(0o444)
 with pytest.raises(runtime.RuntimeErrorV2, match='required frozen source inventory'):
  runtime.verify_cpu_report(report,tmp_path)

@pytest.mark.skipif(os.name == 'nt', reason='POSIX symlink and archive permissions')
def test_cpu_archive_rejects_symlink_ancestor(tmp_path):
 runtime=runner._runtime(); outside=tmp_path/'outside';outside.mkdir()
 source=outside/'x.py';source.write_text('x');source.chmod(0o444)
 root=tmp_path/'archive';root.mkdir();(root/'linked').symlink_to(outside,target_is_directory=True)
 with pytest.raises(runtime.RuntimeErrorV2, match='symlink'):
  runtime._source_file(root,'linked/x.py')


@pytest.mark.skipif(os.name == 'nt', reason='POSIX immutable archive permissions')
def test_runtime_true_boolean_cannot_replace_independent_source_review(tmp_path):
 runtime=runner._runtime();log=tmp_path/'pytest.log';log.write_text('100 passed');log.chmod(0o444)
 files={}
 for name in (*runtime.REQUIRED_SOURCE_FILES,*runtime.GENERATED_SOURCE_FILES):
  path=tmp_path/name;path.write_text(name);path.chmod(0o444)
  files[name]=hashlib.sha256(path.read_bytes()).hexdigest()
 value={'verdict':'PASS','runtime_lifecycle_verified':True,'files':files,
        'argv':['pytest'],'candidate_commit':'a'*40,'log_path':'pytest.log',
        'log_sha256':hashlib.sha256(log.read_bytes()).hexdigest()}
 report=tmp_path/'cpu.json';report.write_text(json.dumps(value));report.chmod(0o444)
 with pytest.raises(runtime.RuntimeErrorV2,match='runtime boolean cannot authorize'):
  runtime.verify_cpu_report(report,tmp_path)
