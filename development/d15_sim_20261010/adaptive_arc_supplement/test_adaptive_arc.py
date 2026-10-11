import sys
import pickle
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).parent));from adaptive_arc import ARC,replay
from run_cpu_scan import EXPECTED_LRU_2700, fixed_replay_with_turns
def test_physical_prefill_clear_and_ghosts():
 a=ARC(4);a.ensure(0,np.array([1,2]));assert a.slots[1]>=0;a.prefill();assert a.slots[1]==-1 and 1 in a.b1
def test_arc_small_trace_accounting():
 ops=[('s',np.zeros((48,1),dtype=np.int16)),('p',None),('s',np.ones((48,1),dtype=np.int16))]
 miss,active=replay(ops,2700);assert miss==96 and active==96

def test_arc_refreshes_and_protects_full_current_topk_before_replacement():
 a=ARC(4);a.ensure(0,np.array([1,2,3,4]));a.ensure(0,np.array([1,2,5]))
 assert a.slots[1]>=0 and a.slots[2]>=0 and a.slots[5]>=0
 assert len(a.t1)+len(a.b1)<=a.n
 assert len(a.t1)+len(a.t2)+len(a.b1)+len(a.b2)<=2*a.n

def test_arc_canonical_list_bounds_survive_physical_prefill_clear():
 a=ARC(4);a.ensure(0,np.array([1,2,3,4]));a.prefill()
 assert (a.ids<0).all()
 assert len(a.t1)+len(a.b1)<=a.n
 assert len(a.t1)+len(a.t2)+len(a.b1)+len(a.b2)<=2*a.n

def test_reviewed_lru_baseline_small_trace_group():
 path=Path(__file__).parent.parent/'review_r4'/'stream_G_two.pkl'
 ops=pickle.loads(path.read_bytes())['ops']
 missing,active,_=fixed_replay_with_turns(ops,2700,'lru')
 assert (missing,active)==EXPECTED_LRU_2700['G_two']
