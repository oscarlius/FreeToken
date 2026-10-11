import importlib.util,json
from pathlib import Path
import pytest
HERE=Path(__file__).parent;s=importlib.util.spec_from_file_location('r',HERE/'runner.py');r=importlib.util.module_from_spec(s);s.loader.exec_module(r)
def dump(p, full_sha):
 p.mkdir();files={}
 for role in r.STATE_ROLES:
  name=role.replace(':','_')+'.bin';(p/name).write_bytes(role.encode());files[role]=name
 (p/'index.jsonl').write_text(json.dumps({'seq':1,'kind':'t17-boundary','uid':'7','length':20282,'files':files})+'\n')
 (p/'boundary_receipts.jsonl').write_text(json.dumps({'source':'hot','uid':7,'length':20282,'input_ids_sha256':full_sha,'prefix_int32le_sha256':'prefix','index_seq':1})+'\n')
 return p

def test_boundary_equal_before_output(tmp_path):
 # Different complete requests can represent the same boundary state. Each full
 # input is independently bound while the common prefix controls equivalence.
 a=r.boundary_state_hash(dump(tmp_path/'a','full_a'),uid=7,length=20282,source='hot',input_sha256='full_a',prefix_sha256='prefix')
 b=r.boundary_state_hash(dump(tmp_path/'b','full_b'),uid=7,length=20282,source='hot',input_sha256='full_b',prefix_sha256='prefix')
 assert a==b

@pytest.mark.parametrize('changed', ['source','uid','length','input_sha256','prefix_sha256'])
def test_boundary_identity_mismatch_fails_before_output(tmp_path, changed):
 p=dump(tmp_path/'a','full_a');wanted={'uid':7,'length':20282,'source':'hot','input_sha256':'full_a','prefix_sha256':'prefix'}
 wanted[changed]='wrong'
 with pytest.raises(r.BoundaryStateError):r.boundary_state_hash(p,**wanted)

def test_boundary_mismatch_or_missing_fails_before_output(tmp_path):
 p=dump(tmp_path/'a','full_a');(p/'recurrent_states.bin').unlink()
 with pytest.raises(r.BoundaryStateError):r.boundary_state_hash(p,uid=7,length=20282,source='hot',input_sha256='full_a',prefix_sha256='prefix')
