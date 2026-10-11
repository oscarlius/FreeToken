import importlib.util
import hashlib,json,pytest
from pathlib import Path
DEV=Path(__file__).parents[1]
def test_r046e_runtime_isolated_identity():
 s=importlib.util.spec_from_file_location('r046e',DEV/'r046e_d07_t06_prepare.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);r=m.runtime()
 assert r.RID=='E2-R046e' and r.CANDIDATE=='4fc2320dc0a29422ab61e383e5e1579460e9926e' and r.WT.name=='e2d07-trace-backpressure'
def test_r062_native_validator_accepts_and_rejects_bytes(tmp_path):
 s=importlib.util.spec_from_file_location('r046e_n',DEV/'r046e_d07_t06_prepare.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);k=tmp_path/'wt/python/freetoken/kernel';k.mkdir(parents=True);rows={}
 for n in ('_cpu_moe','_pinned_tensor'):
  p=k/f'{n}.cpython-310-x86_64-linux-gnu.so';p.write_bytes(n.encode());p.chmod(0o444);rows[n]={'candidate_path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size,'candidate_regular_copy':True}
 proof=tmp_path/'proof.json';proof.write_text(json.dumps({'schema':'ft_r062_native_provenance/v1','candidate_commit':m.CANDIDATE,'parent_commit':m.BASE,'kernel_source_diff_empty':True,'native':rows}));proof.chmod(0o444);digest=hashlib.sha256(proof.read_bytes()).hexdigest();assert m.require_native_provenance(tmp_path/'wt',proof,digest)['native']['_cpu_moe']['regular_copy']
 p.chmod(0o644);p.write_bytes(b'bad');p.chmod(0o444)
 with pytest.raises(RuntimeError):m.require_native_provenance(tmp_path/'wt',proof,digest)
