from __future__ import annotations
import importlib.util
import os
import json
from pathlib import Path
import pytest
from types import SimpleNamespace

DEV=Path(__file__).parents[1]
def load(name):
 spec=importlib.util.spec_from_file_location(name,DEV/name);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def test_retry_runner_changes_only_assigned_rid():
 old=(DEV/'t10_raw_phase1.py').read_text(encoding='utf-8')
 new=(DEV/'t10_raw_phase1_retry.py').read_text(encoding='utf-8')
 assert new.replace('E2-R016','E2-R012') == old
def test_launcher_uses_exact_retry_arguments_and_gpu_environment(monkeypatch):
 m=load('d03_t10_retry_launch.py')
 assert m.arguments(77)[m.arguments(77).index('--rid')+1] == 'E2-R016'
 monkeypatch.delenv('CUDA_VISIBLE_DEVICES',raising=False)
 with pytest.raises(ValueError,match='CUDA_VISIBLE_DEVICES'):
  m.preflight(Path('missing.py'),77)


def test_launch_reserves_only_after_complete_preflight_and_writes_receipt(tmp_path,monkeypatch):
 m=load('d03_t10_retry_launch.py'); order=[]; dev=tmp_path/'dev';dev.mkdir(); rounds=tmp_path/'rounds';rounds.mkdir(); gate=tmp_path/'gate';gate.mkdir();(gate/'round.json').write_text('{}')
 wrapper=tmp_path/'batch.sh';wrapper.write_text('x');log=tmp_path/'batch.log'
 class Atomic:
  def next_batch(self,_): order.append('next');return 88
  def reserve_and_launch(self,*args): order.append('reserve');return SimpleNamespace(pid=77),wrapper,log
 monkeypatch.setattr(m,'DEV',dev);monkeypatch.setattr(m,'ROUNDS',rounds);monkeypatch.setattr(m,'verify_sources',lambda:SimpleNamespace(prerequisite=lambda:(order.append('prereq') or gate)))
 monkeypatch.setattr(m,'preflight',lambda runner,batch:order.append(('preflight',batch)))
 monkeypatch.setattr(m,'load',lambda *args:Atomic())
 monkeypatch.setattr(m,'sha',lambda path:'a'*64)
 monkeypatch.setenv('CUDA_VISIBLE_DEVICES','0')
 receipt=m.launch()
 assert order==['prereq','next',('preflight',88),'next','reserve']
 assert receipt['batch_pid']==77 and receipt['cuda_visible_devices']=='0'
 assert (dev/f'launch_{m.RID}.json').is_file()


@pytest.mark.parametrize('fault',["env","source","preflight","changed_batch"])
def test_launch_faults_do_not_reserve(tmp_path,monkeypatch,fault):
 m=load('d03_t10_retry_launch.py'); called=[]; monkeypatch.setattr(m,'DEV',tmp_path);monkeypatch.setattr(m,'ROUNDS',tmp_path)
 class Atomic:
  def next_batch(self,_): return 2 if fault!='changed_batch' or called else 3
  def reserve_and_launch(self,*args): called.append('reserve');raise AssertionError('reserved')
 if fault=='env': monkeypatch.delenv('CUDA_VISIBLE_DEVICES',raising=False)
 else: monkeypatch.setenv('CUDA_VISIBLE_DEVICES','0')
 monkeypatch.setattr(m,'load',lambda *args:Atomic())
 if fault=='source': monkeypatch.setattr(m,'verify_sources',lambda:(_ for _ in ()).throw(ValueError('source')))
 else: monkeypatch.setattr(m,'verify_sources',lambda:SimpleNamespace(prerequisite=lambda:tmp_path))
 if fault=='preflight': monkeypatch.setattr(m,'preflight',lambda *a:(_ for _ in ()).throw(ValueError('preflight')))
 elif fault=='changed_batch': monkeypatch.setattr(m,'preflight',lambda *a:called.append('checked'))
 else: monkeypatch.setattr(m,'preflight',lambda *a:None)
 with pytest.raises(ValueError):m.launch()
 assert called!=['reserve'] and 'reserve' not in called


def test_receipt_race_after_preflight_does_not_reserve(tmp_path,monkeypatch):
 m=load('d03_t10_retry_launch.py'); monkeypatch.setattr(m,'DEV',tmp_path);monkeypatch.setattr(m,'ROUNDS',tmp_path);monkeypatch.setenv('CUDA_VISIBLE_DEVICES','0')
 class Atomic:
  def next_batch(self,_): return 4
  def reserve_and_launch(self,*a): raise AssertionError('must not reserve')
 monkeypatch.setattr(m,'load',lambda *a:Atomic());monkeypatch.setattr(m,'verify_sources',lambda:SimpleNamespace(prerequisite=lambda:tmp_path))
 def preflight(*a): (tmp_path/f'launch_{m.RID}.json').write_text('{"foreign":true}')
 monkeypatch.setattr(m,'preflight',preflight)
 with pytest.raises(FileExistsError):m.launch()


def test_publish_failure_preserves_reserved_receipt(tmp_path,monkeypatch):
 m=load('d03_t10_retry_launch.py'); path=tmp_path/'r.json';path.write_text('{"state":"reserved"}')
 identity=(path.stat().st_dev,path.stat().st_ino)
 monkeypatch.setattr(m.os,'replace',lambda *a:(_ for _ in ()).throw(OSError('publish')))
 with pytest.raises(OSError):m.publish_receipt(path,identity,{'state':'launched'})
 assert json.loads(path.read_text())['state']=='reserved'


def test_pinned_load_rejects_changed_source_before_exec(tmp_path):
 m=load('d03_t10_retry_launch.py'); source=tmp_path/'x.py';source.write_text('raise AssertionError("executed")')
 with pytest.raises(ValueError,match='frozen import source changed'):m.load(source,'0'*64)
