import importlib.util, socket, subprocess, hashlib, sys
from types import SimpleNamespace
from pathlib import Path
import pytest
p=Path(__file__).parents[1]/'r040a_d16_dryrun_v1.py';s=importlib.util.spec_from_file_location('r',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_actual_collector_loops_are_file_only(monkeypatch,tmp_path):
 monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'WT',tmp_path/'wt/e2base1');m.WT.mkdir(parents=True)
 class Source:
  @staticmethod
  def prepare(_):return {}
 monkeypatch.setattr(m,'_load',lambda:Source)
 monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(empty=lambda *_,**__:b'',int32='int32',save=lambda _value,stream:stream.write(b'FTPT')))
 monkeypatch.setattr(subprocess,'Popen',lambda *a,**k:pytest.fail('Popen forbidden'))
 monkeypatch.setattr(socket.socket,'connect',lambda *a,**k:pytest.fail('connect forbidden'))
 monkeypatch.setattr(socket.socket,'connect_ex',lambda *a,**k:pytest.fail('connect_ex forbidden'))
 value=m.dry_run(tmp_path/'runs/dev_D16/.dryrun_R040a_test')
 assert value['service_started'] is False and value['requests_sent'] is False
 assert [len(value['arms'][key]['arms']) for key in ('batch2','batch4','parking','cache','interleave')]==[6,10,4,4,6]
 assert len(value['anchor_pre_popen'])==6
 assert (tmp_path/'runs/dev_D16/.dryrun_R040a_test'/'dev_D16/native_slots_4/dev_D16_4_single_1_3/collection/file_only_output.pt').is_file()
 assert (tmp_path/'runs/dev_D16/.dryrun_R040a_test'/'dry_run_receipt.json').is_file()
 with pytest.raises(RuntimeError):m.dry_run(tmp_path/'runs/dev_D16/.dryrun_R040a_test')

def test_formal_entry_rejects_writable_receipt(monkeypatch,tmp_path):
 p=Path(__file__).parents[1]/'r040a_d16_supplement_prepare_v2.py';s=importlib.util.spec_from_file_location('entry',p);entry=importlib.util.module_from_spec(s);s.loader.exec_module(entry)
 monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'WT',tmp_path/'wt/e2base1');m.WT.mkdir(parents=True)
 monkeypatch.setattr(m,'_load',lambda:type('Source',(),{'prepare':staticmethod(lambda _: {})}))
 monkeypatch.setitem(sys.modules,'torch',SimpleNamespace(empty=lambda *_,**__:b'',int32='int32',save=lambda _value,stream:stream.write(b'FTPT')))
 receipt=m.dry_run(tmp_path/'runs/dev_D16/.dryrun_R040a_receipt');path=tmp_path/'runs/dev_D16/.dryrun_R040a_receipt/dry_run_receipt.json'
 monkeypatch.setattr(entry.os,'getuid',lambda:receipt['uid'],raising=False);monkeypatch.setattr(entry.getpass,'getuser',lambda:receipt['user']);monkeypatch.setattr(entry.os,'getcwd',lambda:receipt['cwd'])
 assert entry.require_dry_run_receipt(path)['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
 path.chmod(0o644)
 with pytest.raises(RuntimeError,match='sealed'):entry.require_dry_run_receipt(path)

def test_final_child_argv_uses_v2_entry_and_carries_receipt(tmp_path):
 p=Path(__file__).parents[1]/'r040a_d16_supplement_prepare_v2.py';s=importlib.util.spec_from_file_location('entry_argv',p);entry=importlib.util.module_from_spec(s);s.loader.exec_module(entry)
 base=type('Base',(),{'ROOT':tmp_path})()
 argv=entry.child_argv(base,71,tmp_path/'launch.json','E2-R048',tmp_path/'dry_run_receipt.json')
 assert argv[1]==str(p.resolve()) and '--dry-receipt' in argv and '--owned-child' in argv
