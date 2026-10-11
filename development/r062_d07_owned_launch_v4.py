"""R062 v4 strict native provenance admission."""
from __future__ import annotations
import hashlib,importlib.util,json,os
from pathlib import Path
HERE=Path(__file__).resolve().parent;V3=HERE/'r062_d07_owned_launch_v3.py';PROOF=Path('/data2/FreeToken/runs/dev_R046d/r062_native_provenance_20261007.json');PIN='c03de16a78e6b855ca84eaa3dec81ea56b8fbe0eae98548e9c07ee6d16551d13'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def native():
 if PROOF.is_symlink() or not PROOF.is_file() or PROOF.stat().st_mode&0o222 or sha(PROOF)!=PIN:raise RuntimeError('R062 native proof differs')
 d=json.loads(PROOF.read_text());
 if d.get('schema')!='ft_r062_native_provenance/v1' or d.get('parent_commit')!='151ee718b88882b57dba75317bb53c697d5f235f' or d.get('candidate_commit')!='4fc2320dc0a29422ab61e383e5e1579460e9926e' or d.get('kernel_source_diff_empty') is not True:raise RuntimeError('R062 native identity differs')
 for n,row in d['native'].items():
  for key in ('parent_path','candidate_path'):
   p=Path(row[key]);
   if not p.is_file() or sha(p)!=row['sha256'] or p.stat().st_size!=row['size'] or (key=='candidate_path' and p.stat().st_mode&0o222):raise RuntimeError('R062 native bytes differ')
  if Path(row['candidate_path']).is_symlink() or not row.get('candidate_regular_copy'):raise RuntimeError('R062 candidate native is not regular')
 return d
def runtime():
 s=importlib.util.spec_from_file_location('r062v3',V3);x=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(x);m=x.runtime();m.__file__=str(Path(__file__).resolve());old=m.require_candidate
 def candidate(card):native();return old(card)
 m.require_candidate=candidate; oldsrc=m.source_hashes;m.source_hashes=lambda card:{**oldsrc(card),Path(__file__).name:sha(__file__)}
 m.dry_run_receipt_path=lambda card:m.ROOT/'runs/dev_T16/reviews'/'E2-R062-gate-D07_file_dry_run_v4.json';m.review_path=lambda card:m.ROOT/'runs/dev_T16/reviews'/'E2-R062-gate-D07_startup_review_v4.json';return m
if __name__=='__main__':runtime().main()
