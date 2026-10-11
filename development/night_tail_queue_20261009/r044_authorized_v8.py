"""Task-owned R044 FILEdry clone with only independent queue policy changed."""
from __future__ import annotations
import argparse, importlib.util
from pathlib import Path
from queue_authorization import factual, policy
HERE=Path(__file__).resolve().parent; SOURCE=HERE.parent/'r044_runtime_v7'/'r044_prepare_v6.py'
def main():
 p=argparse.ArgumentParser();p.add_argument('--file-dry-run',type=Path,required=True);a=p.parse_args();spec=importlib.util.spec_from_file_location('night_r044_v8',SOURCE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 def queue(d):
  if d.LOCK.exists() or d.LOCK.is_symlink():raise RuntimeError('foreign GPU lock exists; T10 remains queued')
  t20=d.require_t20_failed_harness();d.require_closed_round('E2-R052','failed_harness');d.require_closed_round('E2-R040f','failed_harness');return {'t20':str(t20),'r040g':factual('E2-R040g'),'r052a':{'actual_status':'not_run','required_by_frozen_source':'measured','authorization':'policy_override_only'},'night_tail_queue':policy('E2-R044')}
 original=m.packet
 def packet(wt=m.WT):
  value=original(wt);value['queue_authorization']=policy('E2-R044');value['factual_r040g']=factual('E2-R040g');value['run_requires']=[x for x in value['run_requires'] if x not in ('E2-R052a measured','E2-R040g measured')]+['independent queue terminal for R052a (measured or not_met)','factual E2-R040g failed_harness recorded'] ;return value
 m.require_queue=queue;m.packet=packet;m.file_dry_run(a.file_dry_run)
if __name__=='__main__':main()
