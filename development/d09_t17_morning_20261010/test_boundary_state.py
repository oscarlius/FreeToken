import importlib.util,json
from pathlib import Path
import pytest
HERE=Path(__file__).parent;s=importlib.util.spec_from_file_location('r',HERE/'runner.py');r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
ROLES={'conv_states','recurrent_states','slot:ple_conv','slot:ple_ngram_ctx'}
def make_dump(dump, *, source, uid, length, input_sha, changed=False):
 dump.mkdir(parents=True);files={}
 for role in sorted(ROLES):
  name=role.replace(':','_')+'.bin';(dump/name).write_bytes((role+('!' if changed else '')).encode());files[role]=name
 (dump/'index.jsonl').write_text(json.dumps({'seq':9,'kind':'t17-boundary','uid':str(uid),'length':length,'files':files})+'\n')
 (dump/'boundary_receipts.jsonl').write_text(json.dumps({'source':source,'uid':uid,'length':length,'input_ids_sha256':input_sha,'prefix_int32le_sha256':'p','index_seq':9})+'\n')
def test_real_dump_schema_hashes_all_ft_roles(tmp_path):
 make_dump(tmp_path/'a',source='hot',uid=2,length=20282,input_sha='x');make_dump(tmp_path/'b',source='hot',uid=2,length=20282,input_sha='x')
 assert r.boundary_state_hash(tmp_path/'a',source='hot',uid=2,length=20282,input_sha256='x',prefix_sha256='p')==r.boundary_state_hash(tmp_path/'b',source='hot',uid=2,length=20282,input_sha256='x',prefix_sha256='p')
def test_missing_or_changed_real_state_fails_before_verdict(tmp_path):
 make_dump(tmp_path/'a',source='coldA',uid=1,length=20282,input_sha='x')
 (tmp_path/'a'/'index.jsonl').write_text(json.dumps({'seq':9,'kind':'t17-boundary','uid':'1','length':20282,'files':{'conv_states':'conv_states.bin'}})+'\n')
 with pytest.raises(r.BoundaryStateError):r.boundary_state_hash(tmp_path/'a',source='coldA',uid=1,length=20282,input_sha256='x',prefix_sha256='p')

def test_judge_rejects_mismatch_before_output(tmp_path):
 c={'services':[]}
 for source,uid in (('coldA',1),('coldB',1),('hot',2)):
  arm=tmp_path/source;c['services'].append({'kind':source,'cell_index':0,'arm':str(arm),'requests':[{'sha256':'x'}]})
  make_dump(arm/'state_dump',source=source,uid=uid,length=20282,input_sha='x',changed=source=='hot')
 with pytest.raises(r.BoundaryStateError):r.judge_boundary(c,0,20282,{'coldA':{'uid':1,'input_sha256':'x','prefix_sha256':'p'},'coldB':{'uid':1,'input_sha256':'x','prefix_sha256':'p'},'hot':{'uid':2,'input_sha256':'x','prefix_sha256':'p'}})

def test_observer_uses_ping_pong_slot_not_slot_index():
 source=(HERE/'tooling'/'t17_d14_observe.py').read_text();assert "slots[slot_index]" in source and "dev_slots=slot" in source
