"""R046e preparation: retained G3/G4+T06 tool under the D07 backpressure candidate."""
from __future__ import annotations
import importlib.util, hashlib, json
from pathlib import Path
HERE=Path(__file__).resolve().parent; RETAINED=HERE/'r046d_d07_t06_prepare.py'
RID='E2-R046e'; CANDIDATE='4fc2320dc0a29422ab61e383e5e1579460e9926e'; WT=Path('/data2/FreeToken/wt/e2d07-trace-backpressure')
NATIVE=Path('/data2/FreeToken/runs/dev_R046d/r062_native_provenance_20261007.json'); NATIVE_SHA='c03de16a78e6b855ca84eaa3dec81ea56b8fbe0eae98548e9c07ee6d16551d13'
BASE='151ee718b88882b57dba75317bb53c697d5f235f'
def _sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def require_native_provenance(worktree=WT, proof=NATIVE, proof_sha=NATIVE_SHA):
 proof,worktree=Path(proof),Path(worktree)
 if proof.is_symlink() or not proof.is_file() or proof.stat().st_mode&0o222 or _sha(proof)!=proof_sha: raise RuntimeError('R046e native proof differs')
 value=json.loads(proof.read_text())
 if value.get('schema')!='ft_r062_native_provenance/v1' or value.get('candidate_commit')!=CANDIDATE or value.get('parent_commit')!=BASE or value.get('kernel_source_diff_empty') is not True: raise RuntimeError('R046e native identity differs')
 native={}
 for name,row in value.get('native',{}).items():
  path=Path(row.get('candidate_path',''))
  if path.parent!=worktree/'python/freetoken/kernel' or path.is_symlink() or not path.is_file() or path.stat().st_mode&0o222 or not row.get('candidate_regular_copy') or _sha(path)!=row.get('sha256') or path.stat().st_size!=row.get('size'): raise RuntimeError('R046e native artifact differs: '+name)
  native[name]={'path':str(path),'sha256':row['sha256'],'size':row['size'],'regular_copy':True}
 if set(native)!={'_cpu_moe','_pinned_tensor'}: raise RuntimeError('R046e native module set differs')
 return {'path':str(proof),'sha256':proof_sha,'native':native}
def runtime():
 s=importlib.util.spec_from_file_location('r046e_retained',RETAINED);m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m)
 m.__file__=str(Path(__file__).resolve());m.RID=RID;m.CANDIDATE=CANDIDATE;m.WT=WT;m.NATIVE_PROVENANCE=NATIVE;m.NATIVE_PROVENANCE_SHA256=NATIVE_SHA
 m.require_native_provenance=require_native_provenance
 return m
if __name__=='__main__':runtime().main()
