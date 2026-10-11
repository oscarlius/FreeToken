import importlib.util
from pathlib import Path
import pytest
P=Path(__file__).parents[1]/'t16_process_lifecycle.py';s=importlib.util.spec_from_file_location('life',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
def test_provenance_and_rounds(tmp_path):
 assert m.SOURCE_SHA256=='7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf'
 (tmp_path/'E2-R022-gate-D14').mkdir();assert m.next_round(tmp_path)==23
def test_receipt_race_rejected(tmp_path):
 if __import__('os').name!='posix': pytest.skip('symlink replacement proof is Linux-only')
 p=tmp_path/'receipt.json';m.write_exclusive(p,{'state':'reserved'});ident=(p.stat().st_dev,p.stat().st_ino);p.unlink();target=tmp_path/'target';target.write_text('{}');p.symlink_to(target)
 with pytest.raises(ValueError,match='identity changed'):m.publish_receipt(p,ident,{'state':'launched'})
def test_process_identity_is_frozen_for_this_process():
 value=m.process_identity(__import__('os').getpid())
 if value is None: pytest.skip('Linux proc proof')
 assert value['pid'] and value['start_ticks']>0 and 'python' in value['cmdline']
def test_reservation_failure_rolls_back_to_recorded_receipt(tmp_path):
 class Helper:
  def reserve_and_launch(self,*args): raise RuntimeError('launcher failed')
 receipt=tmp_path/'receipt.json'
 with pytest.raises(RuntimeError):m.reserve_process(Helper(),1,'E2-R999',['x'],receipt,{'state':'reserved'})
 assert __import__('json').loads(receipt.read_text())['state']=='launch_failed'
def test_lost_group_is_not_treated_as_owned(monkeypatch):
 if not hasattr(m.os,'getpgid'): pytest.skip('process group proof is Linux-only')
 class Proc:
  pid=123
  def poll(self): return None
 monkeypatch.setattr(m,'owned_group_alive',lambda pid:True)
 monkeypatch.setattr(m.os,'getpgid',lambda pid:999)
 with pytest.raises(RuntimeError,match='expected process group'):m.stop_owned_process(Proc(),0,0)
