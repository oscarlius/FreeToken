"""Task-owned R047 FILEdry clone with only independent-queue policy gating changed."""
from __future__ import annotations
import argparse, importlib.util
from pathlib import Path
from queue_authorization import factual, policy

HERE=Path(__file__).resolve().parent; SOURCE=HERE.parent/'r047_runtime_v12'/'r047_prepare_v11.py'
def source():
 spec=importlib.util.spec_from_file_location('night_r047_v13',SOURCE); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
def predecessors(m):
 helper=m.load_closed_round_helper(); result={rid:str(helper(rid,verdict)) for rid,verdict in (('E2-R041-gate-D17','kept'),('E2-R040','failed_harness'),('E2-R040f','failed_harness'),('E2-R046g','measured'))}
 result.update({'E2-R040g':{'actual':factual('E2-R040g'),'required_by_frozen_source':'measured','authorization':'policy_override_only'},'E2-R045':{'actual':factual('E2-R045_latest'),'required_by_frozen_source':'measured','authorization':'policy_override_only'},'E2-R044':{'actual_status':'not_run','required_by_frozen_source':'measured','authorization':'policy_override_only'},'historical_t20_commit':m.HISTORICAL_T20_COMMIT,'night_tail_queue':policy('E2-R047')})
 return result
def main():
 p=argparse.ArgumentParser();p.add_argument('--file-dry-run',type=Path,required=True);p.add_argument('--executor',type=Path,required=True);p.add_argument('--review-receipt',type=Path,required=True);p.add_argument('--worktree',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();m=source();m.require_predecessors=lambda:predecessors(m);m.file_dry_run(a.file_dry_run,a.executor,a.review_receipt,a.worktree,a.out)
if __name__=='__main__':main()
