import importlib.util, hashlib, json
from pathlib import Path
import pytest
spec=importlib.util.spec_from_file_location('source_admission_tests',Path(__file__).parents[1]/'d17_source_admission.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def report():
 return {'schema':'ft_d17_gate_cpu_stage/v2','verdict':'PASS','runtime_lifecycle_verified':False,'admitted':False,'gpu_started':False,'requests_sent':False,'fixture_only':True,'synthetic_endpoints':True,'synthetic_states':True,'cpu_lifecycle_contract_verified':True,'real_gpu_lock_unchanged':True}

@pytest.mark.parametrize('flag',['runtime_lifecycle_verified','admitted','gpu_started'])
def test_cpu_source_gate_rejects_model_or_gpu_acceptance_flags(flag):
 value=report();value[flag]=True
 with pytest.raises(m.AdmissionError,match='cannot substitute model acceptance'):m.cpu_flags(value)

@pytest.mark.parametrize('path',['../outside.json','/tmp/outside.json'])
def test_evidence_inventory_rejects_path_escape(tmp_path,path):
 with pytest.raises(m.AdmissionError,match='unsafe evidence path'):m.verify_map(tmp_path,{path:'a'*64})

def test_readonly_inventory_bytes_must_match(tmp_path):
 path=tmp_path/'source.py';path.write_text('new bytes');path.chmod(0o444)
 with pytest.raises(m.AdmissionError,match='SHA differs'):m.verify_map(tmp_path,{'source.py':hashlib.sha256(b'old bytes').hexdigest()})


@pytest.fixture
def external_review(monkeypatch,tmp_path):
 package=tmp_path/'cpu_package';package.mkdir()
 monkeypatch.setattr(m,'HERE',package/'source_tools')
 checked={'stage_report_sha256':'a'*64,'candidate_commit':m.CANDIDATE,'control_commit':m.CONTROL,'source_execution_ready':False,'model_admitted':False}
 monkeypatch.setattr(m,'check_cpu_package',lambda path:checked.copy())
 folder=tmp_path/'independent';folder.mkdir()
 path=folder/'review.json'
 value={'schema':'ft_d17_gpu_test_source_admission/v1','scope':'owned-gpu-test-startup-only','verdict':'PASS','stage_report_sha256':'a'*64,'candidate_commit':m.CANDIDATE,'control_commit':m.CONTROL,'runtime_lifecycle_verified':False,'model_admitted':False,'admitted':False,'gpu_started':False,'requests_sent':False,'reviewer_identity':'/root/r_overlap_review'}
 def write(value):
  folder.chmod(0o755)
  if path.exists():path.chmod(0o644)
  path.write_text(json.dumps(value));path.chmod(0o444);folder.chmod(0o555)
  return m.sha(path)
 pin=write(value)
 try:yield path,value,pin,write
 finally:
  folder.chmod(0o755);path.chmod(0o644)


def test_sealed_external_review_allows_only_source_startup(external_review):
 path,value,pin,write=external_review
 result=m.verify(Path('cpu.json'),path,pin)
 assert result['source_execution_ready'] is True
 assert result['model_admitted'] is False
 assert result['scope']=='owned-gpu-test-startup-only'
 assert result['independent_review_sha256']==pin


def test_writable_review_parent_rejected(external_review):
 path,value,pin,write=external_review;path.parent.chmod(0o755)
 with pytest.raises(m.AdmissionError,match='sealed evidence directory'):m.verify(Path('cpu.json'),path,pin)


def test_replaced_readonly_review_bytes_rejected(external_review):
 path,value,pin,write=external_review;value['extra']='replacement';write(value)
 with pytest.raises(m.AdmissionError,match='review SHA differs'):m.verify(Path('cpu.json'),path,pin)


@pytest.mark.parametrize('pin',[None,'','not-a-sha'])
def test_external_review_requires_caller_pin(external_review,pin):
 path,value,original,write=external_review
 with pytest.raises(m.AdmissionError,match='caller-pinned'):m.verify(Path('cpu.json'),path,pin)


@pytest.mark.parametrize('key,bad',[
 ('scope','model-acceptance'),('stage_report_sha256','b'*64),
 ('candidate_commit','bad'),('control_commit','bad'),
 ('runtime_lifecycle_verified',True),('model_admitted',True),
 ('admitted',True),('gpu_started',True),('requests_sent',True),
 ('reviewer_identity','/root/producer'),('verdict','PARTIAL')])
def test_external_review_binding_rejected(external_review,key,bad):
 path,value,pin,write=external_review;value[key]=bad;pin=write(value)
 with pytest.raises(m.AdmissionError,match='review binding differs'):m.verify(Path('cpu.json'),path,pin)


@pytest.mark.parametrize('key',['admitted','requests_sent'])
def test_missing_false_review_flags_rejected(external_review,key):
 path,value,pin,write=external_review;del value[key];pin=write(value)
 with pytest.raises(m.AdmissionError,match='review binding differs'):m.verify(Path('cpu.json'),path,pin)
