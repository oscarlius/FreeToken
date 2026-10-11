"""R062 v3 strict admission wrapper."""
from __future__ import annotations
import hashlib,importlib.util,json,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent;V2=HERE/'r062_d07_owned_launch_v2.py';RID='E2-R062-gate-D07';BASE='151ee718b88882b57dba75317bb53c697d5f235f';CAND='4fc2320dc0a29422ab61e383e5e1579460e9926e';PROOF=Path('/data2/FreeToken/runs/dev_R046d/r062_native_provenance_20261007.json');PROOF_SHA='c03de16a78e6b855ca84eaa3dec81ea56b8fbe0eae98548e9c07ee6d16551d13'
def runtime():
 s=importlib.util.spec_from_file_location('r062v2',V2);x=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(x);m=x.runtime();m.__file__=str(Path(__file__).resolve())
 old=m.require_candidate
 def candidate(card):
  wt=old(card);dirty=subprocess.check_output(['git','-C',str(wt),'status','--porcelain','--untracked-files=no'],text=True);anc=subprocess.run(['git','-C',str(wt),'merge-base','--is-ancestor',BASE,'HEAD']).returncode
  if dirty or anc:raise RuntimeError('R062 candidate cleanliness/ancestry differs')
  return wt
 m.require_candidate=candidate
 oldhash=m.source_hashes;m.source_hashes=lambda card:{**oldhash(card),Path(__file__).name:hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),str(PROOF):PROOF_SHA}
 m.dry_run_receipt_path=lambda card:m.ROOT/'runs/dev_T16/reviews'/'E2-R062-gate-D07_file_dry_run_v3.json';m.review_path=lambda card:m.ROOT/'runs/dev_T16/reviews'/'E2-R062-gate-D07_startup_review_v3.json'
 return m
if __name__=='__main__':runtime().main()
