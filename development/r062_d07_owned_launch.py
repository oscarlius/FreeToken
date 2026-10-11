"""R062 controller: retained R059 owner lifecycle with a new candidate case."""
from __future__ import annotations
import hashlib, importlib.util, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; RID='E2-R062-gate-D07'; BASE='151ee718b88882b57dba75317bb53c697d5f235f'; CANDIDATE='4fc2320dc0a29422ab61e383e5e1579460e9926e'
def runtime():
 p=HERE/'r059_d07_owned_launch.py';s=importlib.util.spec_from_file_location('r062_retained_launch',p);m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m)
 m.SPECS={'D07':(RID,CANDIDATE,'t16_r062_d07_candidate.py')};m.PARENT_COMMIT=BASE
 def candidate(card):
  wt=m.ROOT/'wt/e2d07-trace-backpressure'; head=m.subprocess.check_output(['git','-C',str(wt),'rev-parse','HEAD'],text=True).strip()
  if head!=CANDIDATE:raise RuntimeError('R062 candidate differs')
  return wt
 m.require_candidate=candidate
 return m
if __name__=='__main__':runtime().main()
