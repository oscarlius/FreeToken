import pytest
import importlib.util,json,subprocess,sys,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; TOOL=ROOT/'r055_gate_d06_prepare.py'
def load():
 s=importlib.util.spec_from_file_location('r055',TOOL);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def test_fixed_identity_and_dual_default_coverage():
 m=load(); assert m.ASSIGNED_RID=='E2-R055-gate-D06'; c=m.CASES['D06']; assert c['parent_commit'].startswith('0aa23431') and c['new_commit']=='effb9969706922ddad9e59b96377e46469ebe97f' and c['ordinary_prefill'] is True
def test_uses_private_runner_gate_and_private_cold_client_without_d0_or_tax():
 m=load(); source=TOOL.read_text()
 assert m.CandidateRunner.__bases__ == (m.PrivateRunner,)
 assert 'def private_probe_bootstrap(self):' in source
 assert 'self.private_probe_bootstrap()' in source
 assert "ft_probe_ckpt_tax.py" not in source
 assert "FT_DEV_D0" not in source

def test_preflight_uses_sealed_raw_helpers_not_drifted_root_probe(monkeypatch, tmp_path):
 m=load(); raw=tmp_path/'raw';raw.mkdir(); parser=tmp_path/'serve_args_diff.py'
 probe=raw/'probe_ft_cold32k.py'; cold=raw/'cold_eq.py'
 probe.write_text('URL="http://127.0.0.1:8095/v1/chat/completions"\n'); cold.write_text('import probe_ft_cold32k\nURL=probe_ft_cold32k.URL\n')
 parser.write_text('def parse(path): return {}\n')
 for path in (probe,cold): path.chmod(0o444)
 spec={name:(path,hashlib.md5(path.read_bytes()).hexdigest(),hashlib.sha256(path.read_bytes()).hexdigest(),readonly)
       for name,path,readonly in (('probe_ft_cold32k.py',probe,True),('cold_eq.py',cold,True),('serve_args_diff.py',parser,False))}
 monkeypatch.setattr(m,'R055_TOOL_SPECS',spec)
 evidence=m.r055_tool_preflight()
 assert evidence['probe_ft_cold32k.py']['path']==str(probe)
 assert evidence['probe_ft_cold32k.py']['readonly'] is True
 probe.chmod(0o644)
 with pytest.raises(RuntimeError,match='writable'):m.r055_tool_preflight()

def test_private_bootstrap_uses_sealed_probe_and_cold_with_private_url(monkeypatch,tmp_path):
 m=load(); raw=tmp_path/'raw';raw.mkdir(); probe=raw/'probe_ft_cold32k.py';cold=raw/'cold_eq.py';out=tmp_path/'out.json'
 probe.write_text("URL='http://127.0.0.1:8095/v1/chat/completions'\n")
 cold.write_text("import json,sys,probe_ft_cold32k\nURL=probe_ft_cold32k.URL\ndef main():\n assert URL == 'http://127.0.0.1:48123/v1/chat/completions'\n json.dump({'argv':sys.argv,'url':URL},open(sys.argv[2],'w'))\n")
 spec={name:(path,'','',False) for name,path in (('probe_ft_cold32k.py',probe),('cold_eq.py',cold),('serve_args_diff.py',tmp_path/'parser.py'))}
 monkeypatch.setattr(m,'R055_TOOL_SPECS',spec)
 runner=m.CandidateRunner.__new__(m.CandidateRunner);runner.port=48123
 subprocess.run([sys.executable,'-c',runner.private_probe_bootstrap(),'id',str(out)],check=True)
 got=json.loads(out.read_text());assert got['argv']==[str(cold),'id',str(out)] and got['url'].endswith(':48123/v1/chat/completions')
def test_default_prepare_is_inert():
 r=subprocess.run([sys.executable,str(TOOL)],capture_output=True,text=True); assert r.returncode==0,r.stderr; d=json.loads(r.stdout); assert d['rid']=='E2-R055-gate-D06' and d['requests_sent'] is False and d['gpu_lock_taken'] is False
def test_rejects_wrong_rid_or_commit():
 m=load(); from types import SimpleNamespace
 for rid,commit in [('E2-R046',m.CASES['D06']['new_commit']),(m.ASSIGNED_RID,'0'*40)]:
  try:m.validate_identity(SimpleNamespace(case='D06',rid=rid,batch=1,candidate_commit=commit))
  except ValueError:pass
  else:raise AssertionError('wrong identity accepted')

def test_frozen_observer_hook_precedes_startup_and_uses_keyword_pool_signature(tmp_path):
 m=load(); runner=m.CandidateRunner.__new__(m.CandidateRunner); runner._freeze_observer(tmp_path)
 source=(tmp_path/'t17_d14_observe.py').read_text()
 assert source.index('def r055_install_decode_hook') < source.index('def startup')
 assert 'dev_slots=[slot], length=int(req.device_len), uid=uid' in source
 compile(source,'r055_observer.py','exec')

def test_state_triplet_real_torch_dump_rejects_drift(monkeypatch,tmp_path):
 import shutil
 torch=pytest.importorskip("torch")
 from types import SimpleNamespace
 import importlib.util
 leafp=Path(__file__).parents[1]/'r055_gate_d06_prepare.py'; spec=importlib.util.spec_from_file_location('r055leaf_state',leafp); leaf=importlib.util.module_from_spec(spec); spec.loader.exec_module(leaf)
 runner=leaf.CandidateRunner.__new__(leaf.CandidateRunner)
 roles=('conv_states','recurrent_states','slot:ple_conv','slot:ple_ngram_ctx')
 def arm(name,delta=0,uid='7',sha='a',missing=False):
  root=tmp_path/name; dump=root/'state_dump';dump.mkdir(parents=True); shutil.copy2(Path(__file__).parents[1]/'t17_d14_runner.py',root/'t17_d14_runner.py')
  files={}
  for i,role in enumerate(roles):
   if missing and i==0: continue
   rel=f'{role}.pt';torch.save(torch.tensor([i+delta],dtype=torch.int32),dump/rel);files[role]=rel
  (dump/'index.jsonl').write_text(json.dumps({'kind':'r055_before_decode','length':3,'uid':uid,'files':files})+'\n')
  (root/'t17_observations.jsonl').write_text('\n'.join((json.dumps({'kind':'input','uid':uid,'ids_int32le_sha256':sha}),json.dumps({'kind':'token','uid':uid,'token':99,'finished':True})))+'\n')
  return root
 a,b,c=arm('a'),arm('b'),arm('c')
 assert runner.compare_state_triplet(a,b,c,uid='7',length=3)['binding']['state_labels']==sorted(roles)
 with pytest.raises(ValueError): runner.compare_state_triplet(a,b,arm('bad',1),uid='7',length=3)
 with pytest.raises(ValueError): runner.compare_state_triplet(a,b,arm('uid',uid='8'),uid='7',length=3)
 with pytest.raises(ValueError): runner.compare_state_triplet(a,b,arm('sha',sha='other'),uid='7',length=3)
 with pytest.raises(ValueError): runner.compare_state_triplet(a,arm('unstable',1),c,uid='7',length=3)
 with pytest.raises(ValueError): runner.compare_state_triplet(a,b,arm('missing',missing=True),uid='7',length=3)
