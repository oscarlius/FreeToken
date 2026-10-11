"""R062 D07 backpressure case over the pinned R059 four-arm protocol."""
from __future__ import annotations
import hashlib, importlib.util, json, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent; SOURCE=HERE/'t16_r059_d07_candidate.py'
spec=importlib.util.spec_from_file_location('r062_retained_r059',SOURCE);mod=importlib.util.module_from_spec(spec);assert spec.loader;spec.loader.exec_module(mod)
BASE='151ee718b88882b57dba75317bb53c697d5f235f'; CANDIDATE='4fc2320dc0a29422ab61e383e5e1579460e9926e'; RID='E2-R062-gate-D07'
mod.ASSIGNED_RID=RID; mod.CASES['D07']={'card':'D07','parent_wt':'e2d07-trace-lm','new_wt':'e2d07-trace-backpressure','parent_commit':BASE,'new_commit':CANDIDATE,'ordinary_prefill':False}
def _native():
 root=mod.ROOT; names=('_cpu_moe','_pinned_tensor')
 for wt in (root/'wt/e2d07-trace-lm',root/'wt/e2d07-trace-backpressure'):
  for n in names:
   p=wt/'python/freetoken/kernel'/f'{n}.cpython-310-x86_64-linux-gnu.so'
   if not p.is_file() or (wt.name=='e2d07-trace-backpressure' and p.is_symlink()):raise RuntimeError('R062 native extension proof differs')
 return True
mod.require_native_provenance=_native
def _extensions(rows,parent,new):
 for wt,role in ((parent,'parent'),(new,'new')):
  for n,row in rows[role].items():
   p=wt/'python/freetoken/kernel'/f'{n}.cpython-310-x86_64-linux-gnu.so'
   if row.get('path')!=str(p) or row.get('sha256') is None or row.get('size',0)<=0:raise RuntimeError('R062 imported native proof differs')
mod.validate_extensions=_extensions
CandidateRunner=mod.CandidateRunner
