from __future__ import annotations
import hashlib, importlib.util, json
from pathlib import Path
import pytest
DEV=Path(__file__).parents[1]
def load(name):
 s=importlib.util.spec_from_file_location(name,DEV/f"{name}.py");m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m
def dump(p,v):p.write_text(json.dumps(v),encoding="utf-8")
def fixture(tmp_path,prep):
 d=tmp_path/prep.RID;d.mkdir(); arms=list(prep.ARMS)
 prep.CANONICAL_ROUND=d.resolve()
 for n in arms:
  a=d/n;a.mkdir()
  for f in ("SERVE_CMD.txt","serve.log","tax.json","prefill_seq.txt", *(("short.json","chunked.json") if n.startswith("CHUNK_") else ("det.json",))): (a/f).write_text("x")
  (a/"serve_args.txt").write_text("{'_unique_suffix': '.pid=999999'}")
  (a/"ENV.txt").write_text(prep.PARENT if n.startswith(("PARENT","CHUNK_PARENT")) else prep.CANDIDATE)
 gate={"arms":arms,"candidate_case":"D03-continuation","gate":"D03","parent_commit":prep.PARENT,"new_commit":prep.CANDIDATE,"layer_major":{"D0":{"det":{"records":[{"ttft_s":1}]}},"PROD":{"det":{"records":[{"ttft_s":2}]}},"prefill":{"parent_rows":13,"new_rows":13}},"non_layer_major":{"D0":{"short":{"records":[{"ttft_s":1}]},"chunked":{"records":[{"ttft_s":2}]}},"PROD":{"short":{"records":[{"ttft_s":1}]},"chunked":{"records":[{"ttft_s":2}]}},"prefill":{"parent_rows":23,"new_rows":23}}}
 dump(d/"gate_batch46.json",gate); prep.RAW_SHA=prep.sha(d/"gate_batch46.json")
 dump(d/"status_batch46.json",{"state":"complete_measurements_pending_review","batch_pid":3451139,"batch":46,"rid":prep.RID,"candidate_case":"D03-continuation"})
 dump(d/"candidate_binding.json",{"candidate_runner_sha256":prep.RUNNER_SHA,"base_runner_sha256":prep.BASE_SHA})
 (d/"batch46.sh").write_bytes(b"wrapper"); prep.WRAPPER_SHA=prep.sha(d/"batch46.sh")
 (d/'runner_batch46.py').write_bytes(b'synthetic runner')
 (d/'base_runner_batch46.py').write_bytes(b'synthetic base')
 prep.RUNNER_SHA=prep.sha(d/'runner_batch46.py')
 prep.BASE_SHA=prep.sha(d/'base_runner_batch46.py')
 dump(d/'candidate_binding.json',{'candidate_runner_sha256':prep.RUNNER_SHA,'base_runner_sha256':prep.BASE_SHA,'case':'D03-continuation','card':'D03','parent_commit':prep.PARENT,'new_commit':prep.CANDIDATE,'parent_wt':'e1r003st','new_wt':'e2d03-continuation'})
 prep.RECEIPT_PATH=tmp_path/'receipt.json'
 dump(prep.RECEIPT_PATH,{'schema':'ft_candidate_gate_launch/v1','state':'launched','rid':prep.RID,'batch':46,'case':'D03-continuation','card':'D03','candidate_commit':prep.CANDIDATE,'parent_commit':prep.PARENT,'runner_sha256':prep.RUNNER_SHA,'base_runner_sha256':prep.BASE_SHA,'wrapper_sha256':prep.WRAPPER_SHA,'batch_pid':3451139,'batch_pgid':3451139})
 prep.RECEIPT_SHA=prep.sha(prep.RECEIPT_PATH)
 dump(d/"review_batch46.json",{"schema":"ft_independent_raw_review/v1","reviewer":"/root/d06_server_review","scope":"raw measurement replay and source integrity; not formal acceptance","receipt_sha256":prep.RECEIPT_SHA,"formal_verdict":"pending_review","verdict":"PASS","rid":prep.RID,"batch":46,"candidate_commit":prep.CANDIDATE,"parent_commit":prep.PARENT,"runner_sha256":prep.RUNNER_SHA,"base_runner_sha256":prep.BASE_SHA,"wrapper_sha256":prep.WRAPPER_SHA,"batch_pid":3451139,"gate_sha256":prep.RAW_SHA,"candidate_binding_sha256":prep.sha(d/"candidate_binding.json")})
 prep.REVIEW_SHA=prep.sha(d/'review_batch46.json')
 return d
def test_prepare_writes_pending_metadata_and_eight_arms(tmp_path):
 p=load("t16_r018_prepare");d=fixture(tmp_path,p);r=p.prepare(d,d/"review_batch46.json")
 meta=json.loads((d/"initial_metadata.json").read_text());assert len(meta["design"]["serve_order"])==8 and meta["verdict"]=="pending_review" and meta["sub_conclusions"][0]["status"]=="pending";assert r["batch_sha256"]==p.sha(d/"batch.sh")
def test_rejects_old_four_arm_status_receipt_and_overwrite(tmp_path):
 p=load("t16_r018_prepare");d=fixture(tmp_path,p)
 gate=json.loads((d/"gate_batch46.json").read_text());gate["arms"]=gate["arms"][:4];dump(d/"gate_batch46.json",gate)
 with pytest.raises((ValueError,FileExistsError)):p.prepare(d,d/"review_batch46.json")
 second=tmp_path/"second";second.mkdir();d=fixture(second,p);dump(d/"status_batch46.json",{"state":"complete","batch_pid":3451139,"batch":46,"rid":p.RID,"candidate_case":"D03-continuation"})
 with pytest.raises(ValueError):p.prepare(d,d/"review_batch46.json")
 third=tmp_path/"third";third.mkdir();d=fixture(third,p);p.prepare(d,d/"review_batch46.json")
 with pytest.raises(FileExistsError):p.prepare(d,d/"review_batch46.json")
def test_rejects_aliased_wrapper_and_wrong_review_binding(tmp_path):
 p=load("t16_r018_prepare");d=fixture(tmp_path,p);(d/"batch.sh").write_bytes(b"other")
 with pytest.raises(ValueError):p.prepare(d,d/"review_batch46.json")
 assert not (d/'initial_metadata.json').exists()
 second=tmp_path/"second";second.mkdir();d=fixture(second,p);review=json.loads((d/"review_batch46.json").read_text());review["gate_sha256"]="0"*64;dump(d/"review_batch46.json",review)
 with pytest.raises(ValueError):p.prepare(d,d/"review_batch46.json")

@pytest.mark.parametrize('failure',['receipt_bytes','receipt_identity','runner_bytes','live_pid','foreign_owner'])
def test_provenance_and_ownership_failures_prevent_metadata(tmp_path,monkeypatch,failure):
 p=load('t16_r018_prepare');d=fixture(tmp_path,p)
 if failure=='receipt_bytes':
  p.RECEIPT_PATH.write_text('{}')
 elif failure=='receipt_identity':
  receipt=json.loads(p.RECEIPT_PATH.read_text());receipt['candidate_commit']='0'*40;dump(p.RECEIPT_PATH,receipt);p.RECEIPT_SHA=p.sha(p.RECEIPT_PATH)
 elif failure=='runner_bytes':
  (d/'runner_batch46.py').write_bytes(b'changed')
 elif failure=='live_pid':
  monkeypatch.setattr(p,'terminal',lambda pid:False)
 else:
  monkeypatch.setattr(p.os,'geteuid',lambda:d.stat().st_uid+1,raising=False)
 with pytest.raises(ValueError):p.prepare(d,d/'review_batch46.json')
 assert not (d/'initial_metadata.json').exists() and not (d/'batch.sh').exists()

def test_partial_seal_failure_retains_all_proof(tmp_path,monkeypatch):
 closer=load('t16_r018_close')
 toolstage=tmp_path/'tools';toolstage.mkdir()
 monkeypatch.setattr(closer,'__file__',str(toolstage/'t16_r018_close.py'))
 source=b'import json\nfrom pathlib import Path\ndef exact_round(path):return Path(path).resolve()\ndef guarded_path(path):return Path(path).resolve()\ndef validate(*args):pass\ndef require(path):return path\ndef jb(data):return json.dumps(data).encode()\ndef prepare(directory,review):\n (directory/"initial_metadata.json").write_text("{}")\n (directory/"batch.sh").write_text("wrapper")\n'
 (toolstage/'t16_r018_prepare.py').write_bytes(source)
 monkeypatch.setattr(closer,'PREPARER_SHA',hashlib.sha256(source).hexdigest())
 runtime=tmp_path/'runtime';(runtime/'scripts').mkdir(parents=True)
 names={name:b'fixture tool' for name in closer.TOOLS}
 for name,data in names.items():(runtime/'scripts'/name).write_bytes(data)
 monkeypatch.setattr(closer,'TOOLS',{name:hashlib.md5(data).hexdigest() for name,data in names.items()})
 directory=tmp_path/closer.RID;directory.mkdir();(tmp_path/'batch46.log').write_text('fixture batch')
 def partial_seal(*args,**kwargs):
  (directory/'round_history').mkdir();(directory/'round_history/round.v001.json').write_text('{}')
  (directory/'MANIFEST.sha256').write_text('partial proof')
  raise RuntimeError('injected post-seal failure')
 monkeypatch.setattr(closer.subprocess,'run',partial_seal)
 with pytest.raises(RuntimeError,match='retained'):closer.close(directory,runtime)
 for name in ('round.json','initial_metadata.json','batch.sh','round_history/round.v001.json','MANIFEST.sha256'):
  assert (directory/name).exists()

def test_copied_round_and_replaced_review_are_rejected(tmp_path):
 import shutil
 p=load('t16_r018_prepare');d=fixture(tmp_path,p)
 copied=tmp_path/'copy'/p.RID;shutil.copytree(d,copied)
 with pytest.raises(ValueError,match='canonical'):p.prepare(copied,copied/'review_batch46.json')
 review=json.loads((d/'review_batch46.json').read_text());review['reviewer']='replacement';dump(d/'review_batch46.json',review)
 with pytest.raises(ValueError,match='review bytes'):p.prepare(d,d/'review_batch46.json')
 assert not (copied/'initial_metadata.json').exists() and not (d/'initial_metadata.json').exists()

@pytest.mark.skipif(__import__('sys').platform!='linux',reason='Linux symlink boundary')
def test_same_round_through_symlink_ancestor_is_rejected(tmp_path):
 p=load('t16_r018_prepare');d=fixture(tmp_path,p)
 alias=tmp_path/'alias';alias.symlink_to(tmp_path,target_is_directory=True)
 with pytest.raises(ValueError,match='symlink'):p.prepare(alias/p.RID,alias/p.RID/'review_batch46.json')
 assert not (d/'initial_metadata.json').exists()
