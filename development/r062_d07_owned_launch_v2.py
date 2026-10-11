"""R062 v2: rebind retained lifecycle identity to this actual entry."""
from __future__ import annotations
import hashlib,importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent;OLD=HERE/'r062_d07_owned_launch.py'
def runtime():
 s=importlib.util.spec_from_file_location('r062_v1',OLD);x=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(x)
 m=x.runtime();m.__file__=str(Path(__file__).resolve());m.DEV=HERE
 old=m.source_hashes
 def sources(card):
  out=old(card);out[Path(__file__).name]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
  out['r062_d07_owned_launch.py']=hashlib.sha256(OLD.read_bytes()).hexdigest()
  out['t16_r059_d07_candidate.py']=hashlib.sha256((HERE/'t16_r059_d07_candidate.py').read_bytes()).hexdigest()
  return out
 m.source_hashes=sources
 # New receipt/review namespace; controller argv now resolves m.__file__.
 m.review_path=lambda card:m.ROOT/'runs/dev_T16/reviews'/'E2-R062-gate-D07_startup_review_v2.json'
 m.dry_run_receipt_path=lambda card:m.ROOT/'runs/dev_T16/reviews'/'E2-R062-gate-D07_file_dry_run_v2.json'
 return m
if __name__=='__main__':runtime().main()
