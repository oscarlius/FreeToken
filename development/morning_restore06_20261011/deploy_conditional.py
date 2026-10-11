"""Run one review-gated restore, with mandatory stop-before-rollback recovery."""
import argparse, hashlib, json, subprocess, sys, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
def load(): return json.loads((HERE/'DEPLOYMENT_APPROVAL.json').read_text())

def command(name): return [sys.executable, str(HERE / name)]

def require_root_final_review(approval):
 review_path=HERE/'ROOT_FINAL_REVIEW.json'
 if not approval['conditions_met'] or not review_path.is_file():
  raise RuntimeError('PENDING root final review: execution refused')
 review=json.loads(review_path.read_text())
 approval_bytes=(HERE/'DEPLOYMENT_APPROVAL.json').read_bytes()
 if (hashlib.sha256(approval_bytes).hexdigest()!=review.get('approval_sha256')
     or json.loads(approval_bytes)!=approval):
  raise RuntimeError('restore approval content differs from final review')
 if (review.get('verdict')!='PASS' or review.get('reviewer_role')!='root_independent_final_reviewer'
     or review.get('package_source_manifest_sha256')!=approval['package_source_manifest_sha256']
     or review.get('approval_id')!=approval['approval_id']):
  raise RuntimeError('root final review is not bound to this exact package')
 manifest_path=HERE/'SOURCE_MANIFEST.json'
 if hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=review['package_source_manifest_sha256']:
  raise RuntimeError('restore package source manifest changed')
 manifest=json.loads(manifest_path.read_text())
 for name,digest in manifest['files'].items():
  if hashlib.sha256((HERE/name).read_bytes()).hexdigest()!=digest:
   raise RuntimeError('restore package source changed: '+name)

def recover_after_restore_failure(runner):
 """Rollback startup is forbidden until the frozen stop reports completion."""
 approval=load(); failed=Path(approval['run_dir']); smoke=failed/'smoke_execution_result.json'
 if failed.exists() and not smoke.exists():
  with smoke.open('x') as handle:
   json.dump({'classification':'failed','exit_code':1,'at':time.time(),
              'phase':'restore_start_or_readiness','smoke_generation_completed':False},handle,indent=2)
 stop=runner(command('stop_approved_restore.py'))
 if stop.returncode: return stop.returncode
 rollback_start=runner(command('start_approved_rollback.py'))
 if rollback_start.returncode: return rollback_start.returncode
 return runner(command('wait_rollback_and_smoke.py')).returncode

def execute(runner=subprocess.run):
 approval=load(); require_root_final_review(approval)
 try:
  started=runner(command('start_approved_release.py'))
 except subprocess.SubprocessError:
  return recover_after_restore_failure(runner)
 if started.returncode: return recover_after_restore_failure(runner)
 smoke=runner(command('wait_release_and_smoke.py'))
 if smoke.returncode: return recover_after_restore_failure(runner)
 return runner(command('post_night_observer.py')).returncode

def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',action='store_true');p.add_argument('--execute',action='store_true');a=p.parse_args()
 if a.plan: print(json.dumps(load(),sort_keys=True));return
 if a.execute:
  return execute()
 p.error('choose --plan')
if __name__=='__main__': raise SystemExit(main())
