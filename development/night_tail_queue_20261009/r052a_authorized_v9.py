"""Task-owned R052a FILEdry clone with only R045 scheduling policy changed."""
from __future__ import annotations
import importlib.util
from pathlib import Path
from queue_authorization import factual, policy
HERE=Path(__file__).resolve().parent; SOURCE=HERE.parent/'r052_runtime_v8'/'r052_t11_followup_prepare.py'
def main():
 spec=importlib.util.spec_from_file_location('night_r052a_v9',SOURCE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 def admission(d):
  r041=d.require_r041_kept(m.ROOT);t20=d.require_t20_failed_harness();d.checked_worktree(m.WT);failed={rid:str(d.require_closed_round(rid,v)) for rid,v in m.FAILED_METADATA_GATES}
  return {'r041':str(r041),'t20':str(t20),'r045':{'actual':factual('E2-R045_latest'),'required_by_frozen_source':'measured','authorization':'policy_override_only'},'failed_metadata':failed,'queue_exception':policy('E2-R052a')}
 m.admission=admission;m.dry_run()
if __name__=='__main__':main()
