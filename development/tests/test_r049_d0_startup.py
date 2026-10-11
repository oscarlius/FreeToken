import importlib.util,sys,types,signal,os,pytest
slot=types.ModuleType('flashlib.kernels.slot_cache');slot.Stat=type('Stat',(),{'ACTIVE':0,'MISS':1});sys.modules['flashlib']=types.ModuleType('flashlib');sys.modules['flashlib.kernels']=types.ModuleType('flashlib.kernels');sys.modules['flashlib.kernels.slot_cache']=slot
from pathlib import Path
p=Path(__file__).parents[1]/'r049_d0_startup.py';s=importlib.util.spec_from_file_location('d0',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class T:
 def __init__(self,v):self.v=v
 def tolist(self):return self.v
 def sum(self,axis):return [sum(x[i] for x in self.v) for i in range(3)]
 def item(self):return self.v
class Row:
 def numel(self):return 2
 def element_size(self):return 4
class C:
 def __init__(self):self.lru_stats=T([[2,1,0]]);self.banks=[(None,[Row()])];self.policy_swap_bytes=T(0)
 def _d0_decode_counts(self):return ([self.lru_stats.v[0][1]],[self.lru_stats.v[0][1]])
 def _d0_begin_decode(self,b):pass
 def _d0_end_decode(self):pass
 def reset_stats(self):self.lru_stats=T([[0,0,0]])
 def apply_profile_adaptation(self,p,proof):self.policy_swap_bytes=T(8);return type('R',(),{'status':'verified','swaps':1})()
class B: reqs=[type('R',(),{'uid':7})()]
def test_step_and_swap_journal(monkeypatch):
 monkeypatch.setattr(m,'source_pin',lambda:{'sha256':'x'});j=[];m.install(C,j);c=C();c._d0_begin_decode(B());c.lru_stats=T([[5,3,0]]);c._d0_end_decode();assert j[0]['missing']==2 and j[0]['fetched']==2 and j[0]['rids']==[7];c.apply_profile_adaptation(None,type('P',(),{'boundary_seq':4})());assert j[1]['policy_swap_bytes_delta']==8
def test_reset_between_begin_end_rejects(monkeypatch):
 monkeypatch.setattr(m,'source_pin',lambda:{'sha256':'x'});j=[];m.install(C,j);c=C();c._d0_begin_decode(B());c.reset_stats()
 try:c._d0_end_decode()
 except RuntimeError as e:assert 'boundary reset' in str(e)
 else:raise AssertionError('reset accepted')

import json
def test_journal_exclusive_flush_and_terminal(tmp_path):
 j=m.Journal(tmp_path/'arm'/'d0.jsonl');j.append({'kind':'decode','step':1,'generation':0,'rids':[7]});j.terminal('complete')
 rows=[json.loads(x) for x in (tmp_path/'arm'/'d0.jsonl').read_text().splitlines()]
 assert rows[0]['seq']==1 and rows[-1]['kind']=='terminal' and rows[-1]['status']=='complete'
 try:m.Journal(tmp_path/'arm'/'d0.jsonl')
 except RuntimeError:pass
 else:raise AssertionError('journal overwrite accepted')



class _SpawnScheduler:
 def __init__(self):
  cache=C();cache.lru_stats=T([[100,70,0]]);self.engine=type('Engine',(),{'moe_offload_cache':cache})();self.did_shutdown=False
 def shutdown(self):self.did_shutdown=True
class _SpawnStartup:
 def run_scheduler(self,args,queue):
  scheduler=_SpawnScheduler();self.install_scheduler_capture(scheduler);cache=scheduler.engine.moe_offload_cache;cache._d0_begin_decode(B());cache.lru_stats=T([[108,72,0]]);cache._d0_end_decode();cache.apply_profile_adaptation(None,type('P',(),{'boundary_seq':9})());scheduler.shutdown();return scheduler.did_shutdown
def _spawn_d0_worker(path,queue):
 import os
 os.environ['FT_T21_DIAG_JOURNAL']=path
 m.source_pin=lambda:{'sha256':'cache'}
 m.startup_pin=lambda:{'sha256':'startup'}
 m._startup_module=lambda:_SpawnStartup()
 queue.put(m.worker_run_scheduler(object(),object()))

def test_spawn_target_installs_worker_callback_and_writes_terminal(monkeypatch,tmp_path):
 monkeypatch.setenv('FT_T21_DIAG_JOURNAL',str(tmp_path/'worker.jsonl'))
 monkeypatch.setattr(m,'source_pin',lambda:{'sha256':'cache'})
 monkeypatch.setattr(m,'startup_pin',lambda:{'sha256':'startup'})
 class Scheduler:
  def __init__(self):self.engine=type('Engine',(),{'moe_offload_cache':C()})();self.did_shutdown=False
  def shutdown(self):self.did_shutdown=True
 class Startup:
  def run_scheduler(self,args,queue):
   scheduler=Scheduler();self.install_scheduler_capture(scheduler);scheduler.shutdown();return scheduler
 startup=Startup();monkeypatch.setattr(m,'_startup_module',lambda:startup)
 scheduler=m.worker_run_scheduler(object(),object())
 rows=[json.loads(x) for x in (tmp_path/'worker.jsonl').read_text().splitlines()]
 assert scheduler.did_shutdown and rows[-1]['kind']=='terminal' and rows[-1]['status']=='complete'


class _TermStartup:
 def run_scheduler(self,args,queue):
  scheduler=_SpawnScheduler();self.install_scheduler_capture(scheduler);cache=scheduler.engine.moe_offload_cache;cache._d0_begin_decode(B());cache.lru_stats=T([[108,72,0]]);cache._d0_end_decode()
  try: signal.raise_signal(signal.SIGTERM)
  except KeyboardInterrupt: scheduler.shutdown();return 'graceful-term'
def _spawn_sigterm_worker(path,queue):
 os.environ['FT_T21_DIAG_JOURNAL']=path;m.source_pin=lambda:{'sha256':'cache'};m.startup_pin=lambda:{'sha256':'startup'};m._startup_module=lambda:_TermStartup();queue.put(m.worker_run_scheduler(object(),object()))
class _FailStartup:
 def run_scheduler(self,args,queue): raise RuntimeError('startup exploded')

def test_spawn_target_executes_callback_in_child(tmp_path):
 import multiprocessing
 ctx=multiprocessing.get_context('spawn');queue=ctx.Queue();path=tmp_path/'spawn.jsonl';assert not path.exists();proc=ctx.Process(target=_spawn_d0_worker,args=(str(path),queue));proc.start();proc.join(10)
 assert proc.exitcode==0 and queue.get(timeout=2) is True
 rows=[json.loads(x) for x in path.read_text().splitlines()]
 assert rows[0]['kind']=='install' and rows[-1]['kind']=='terminal' and rows[-1]['status']=='complete'
 decode=next(row for row in rows if row['kind']=='decode');swap=next(row for row in rows if row['kind']=='adapt')
 assert decode['active']==8 and decode['missing']==2 and decode['fetched']==2 and decode['hits']==6 and swap['policy_swap_bytes_delta']==8
 assert all(row['worker_birth']['pid']==proc.pid for row in rows)


def test_spawn_sigterm_uses_shutdown_and_seals_terminal(tmp_path):
 import multiprocessing
 ctx=multiprocessing.get_context('spawn');queue=ctx.Queue();path=tmp_path/'term.jsonl';proc=ctx.Process(target=_spawn_sigterm_worker,args=(str(path),queue));proc.start();proc.join(10)
 assert proc.exitcode==0 and queue.get(timeout=2)=='graceful-term'
 rows=[json.loads(x) for x in path.read_text().splitlines()];assert [x['kind'] for x in rows][-1]=='terminal' and rows[-1]['status']=='complete'

def test_worker_startup_error_writes_failed_terminal(monkeypatch,tmp_path):
 monkeypatch.setenv('FT_T21_DIAG_JOURNAL',str(tmp_path/'failed.jsonl'));monkeypatch.setattr(m,'_startup_module',lambda:_FailStartup())
 with pytest.raises(RuntimeError,match='startup exploded'):m.worker_run_scheduler(object(),object())
 rows=[json.loads(x) for x in (tmp_path/'failed.jsonl').read_text().splitlines()];assert rows[-1]['kind']=='terminal' and rows[-1]['status']=='failed'


def test_pins_match_canonical_candidate_git_lf_bytes(tmp_path):
 candidate=Path(__file__).parents[1]/'e2d15'
 for relative,pin,check in (('python/freetoken/moe/offload_cache.py',m.SOURCE_SHA,m.source_pin),('scripts/equiv_suite/service_capture_startup.py',m.STARTUP_SHA,m.startup_pin)):
  source=candidate/relative;normalized=source.read_bytes().replace(b'\r\n',b'\n');fixture=tmp_path/source.name;fixture.write_bytes(normalized)
  assert m.sha(fixture)==pin
  assert check(fixture)['sha256']==pin
