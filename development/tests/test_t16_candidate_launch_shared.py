import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
P=Path(__file__).parents[1]/'t16_candidate_stage_shared.py';s=importlib.util.spec_from_file_location('stage',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
sys.path.insert(0,str(P.parent))
import t16_candidate_launch_shared as launch
def test_shared_stage_manifest_is_content_addressed():
 identity,files=m.source_manifest();assert len(identity)==64 and 't16_candidate_runner_full_tail.py' in files and 't16_process_lifecycle.py' in files


def test_stage_manifest_has_every_active_adapter_and_fixture():
 _,files=m.source_manifest()
 assert {'t16_candidate_runner.py','t16_candidate_runner_d07.py','t16_candidate_launch.py',
         't16_candidate_launch_d07.py','t16_candidate_launch_full_tail.py',
         'tests/fixtures/t16_failed_full_tail.json','t16_legacy_base_runner.py'}<=set(files)
 assert 'tests/test_t16_full_tail.py' in m.TESTS


def test_launch_executes_the_frozen_runner_with_run_flag(monkeypatch,tmp_path):
 stage=tmp_path/'stage';stage.mkdir();(stage/'cpu_validation.json').write_text('verified')
 report={'files':{launch.RUNNER:'runner',launch.BASE:'base'}}
 config={'card':'D07','new_commit':'candidate','parent_commit':'parent'}
 argv=['python','-u',str(stage/launch.RUNNER),'--case','D07']
 monkeypatch.setattr(launch,'preflight',lambda *_:(report,object(),argv,'E2-R024-gate-D07',52,config))
 monkeypatch.setattr(launch,'freeze',lambda *_:tmp_path/'frozen')
 def reserve(helper,batch,rid,actual,receipt,reserved):
  assert actual[-1]=='--run' and actual[2]==str(tmp_path/'frozen'/launch.RUNNER)
  assert batch==52 and rid=='E2-R024-gate-D07'
  assert reserved['cpu_stage_sha256']==launch.sha(stage/'cpu_validation.json')
  return {'state':'launched'}
 monkeypatch.setattr(launch.life,'reserve_process',reserve)
 assert launch.launch(stage,'D07')['state']=='launched'


def test_ledger_change_stops_before_reservation(monkeypatch):
 report={'files':{launch.RUNNER:'runner',Path(launch.__file__).name:'launch'}}
 stage=Path(launch.__file__).parent
 monkeypatch.setattr(launch,'receipt',lambda *_:report)
 monkeypatch.setattr(launch,'sha',lambda _:'launch')
 config={'card':'D07','new_commit':'candidate'}
 runner=SimpleNamespace(CASES={'D07':config})
 helper=SimpleNamespace(next_batch=lambda _:52)
 monkeypatch.setattr(launch.life,'verified_module',lambda path,*_:runner if path.name==launch.RUNNER else helper)
 calls=iter((24,25));monkeypatch.setattr(launch.life,'next_round',lambda _:next(calls))
 def command(argv,**_):
  assert '--run' not in argv
 monkeypatch.setattr(launch.subprocess,'run',command)
 with pytest.raises(ValueError,match='ledger changed'):
  launch.preflight(stage,'D07')


@pytest.fixture
def frozen_stage(tmp_path):
 stage=tmp_path/'cpu';stage.mkdir()
 _,files=m.source_manifest()
 for name,contents in files.items():
  path=stage/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(contents);path.chmod(0o444)
 log=stage/'cpu_validation.log';log.write_text('48 passed in 0.2s\n');log.chmod(0o444)
 report={'schema':'ft_t16_shared_cpu_stage/v1','gpu_started':False,'status':'passed','passed':48,
         'tests':list(m.TESTS),'files':{name:launch.sha(stage/name) for name in files},
         'log_sha256':launch.sha(log)}
 proof=stage/'cpu_validation.json';proof.write_text(json.dumps(report));proof.chmod(0o444)
 stage.chmod(0o555)
 yield stage
 stage.chmod(0o755)
 for path in stage.rglob('*'):
  path.chmod(0o755 if path.is_dir() else 0o644)


@pytest.mark.skipif(sys.platform!='linux',reason='Unix ownership/mode proof')
def test_receipt_accepts_exact_frozen_protocol_and_log(frozen_stage):
 assert launch.receipt(frozen_stage)['passed']==48


@pytest.mark.skipif(sys.platform!='linux',reason='Unix ownership/mode proof')
@pytest.mark.parametrize('failure',['source','log','failed_status','missing_suite'])
def test_receipt_rejects_tampered_or_incomplete_cpu_proof(frozen_stage,failure):
 stage=frozen_stage
 if failure in ('source','log'):
  path=stage/(launch.BASE if failure=='source' else 'cpu_validation.log')
  path.chmod(0o644);path.write_bytes(path.read_bytes()+b'changed');path.chmod(0o444)
 else:
  path=stage/'cpu_validation.json';proof=json.loads(path.read_text())
  if failure=='failed_status':proof['status']='failed'
  else:proof['tests']=proof['tests'][:-1]
  path.chmod(0o644);path.write_text(json.dumps(proof));path.chmod(0o444)
 with pytest.raises(ValueError):
  launch.receipt(stage)
