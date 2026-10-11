import importlib.util,json
from pathlib import Path
import pytest
DEV=Path(__file__).parent
def load():
 s=importlib.util.spec_from_file_location('r049_manifest_v3',DEV/'r049_t21_ordinary_prepare_v3.py');m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m
def document(m):
 arms=[{'role':'seed12k','directory':'G_seed12k','d15_training_input':True},{'role':'seed_45k','directory':'G_seed_45k','d15_training_input':False},{'role':'seed_real','directory':'G_seed_real','d15_training_input':False},{'role':'two','directory':'G_two','d15_training_input':False}]
 return {'schema':'ft_r046c_route_manifest/v1','rid':'E2-R046f','candidate_commit':'4fc2320dc0a29422ab61e383e5e1579460e9926e','memory_ratio':'0.88','window':{'kv_reserve_tokens':98304,'max_seq_len_override':98304,'completion_reserve_tokens':2048,'max_prompt_tokens':96256},'arms':arms,'d15_training_route':'G_seed12k/route','heldout_routes':['G_seed_45k/route','G_seed_real/route','G_two/route']}
def write(m,tmp,doc):
 m.ROUNDS=tmp;path=tmp/m.T06_RID/'manifest.json';path.parent.mkdir();path.write_text(json.dumps(doc));return path
def test_r046f_manifest_accepts_exact_training_heldout_closure(tmp_path):
 m=load();path=write(m,tmp_path,document(m));assert m.require_t06_metadata()==path
@pytest.mark.parametrize('field,value',[('rid','E2-R046c'),('candidate_commit','bad'),('schema','ft_r046f_route_manifest/v1'),('heldout_routes',['G_seed12k/route','G_seed_real/route','G_two/route'])])
def test_r046f_manifest_rejects_identity_and_training_partition_splices(tmp_path,field,value):
 m=load();d=document(m);d[field]=value;write(m,tmp_path,d)
 with pytest.raises(RuntimeError):m.require_t06_metadata()
def test_r046f_manifest_rejects_missing_arm_and_heldout_profile_source(tmp_path):
 m=load();d=document(m);d['arms'].pop();write(m,tmp_path,d)
 with pytest.raises(RuntimeError):m.require_t06_metadata()
