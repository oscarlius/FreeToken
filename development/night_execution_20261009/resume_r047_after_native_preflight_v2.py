"""Advance the approved night queue after exact D09 retry owner cleanup."""
import datetime, hashlib, importlib.util, json, os, socket, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
RID = 'E2-D09-T16-night-20261010-retry1'
ROUND = Path('/data2/_shared/runs/ft_rounds') / RID
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
helper = HERE / 'advance_d09_t16_to_strata_retry1_v5.py'
assert sha(helper) == '194ab227e367065594ea1fd47eacccd1caa9cd840d5a61daa30a84df48ecdfc2'
spec = importlib.util.spec_from_file_location('night_cleanup_helpers', helper)
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)


def main():
    cleanup = HERE / 'D09_T16_RETRY1_OWNED_CLEANUP_READBACK.json'
    h.require_regular(cleanup); c = json.loads(cleanup.read_text())
    assert c['rid'] == RID and c['cleanup_ok'] and c['gpu_compute_absent'] and c['gpu_lock_absent']
    assert h.absent(c['child_absent']['pid'], c['child_absent']['start_ticks'])
    for owner in c['owners']:
        assert h.absent(owner['birth']['pid'], owner['birth']['start_ticks'])
        for port in map(int, owner['ports_clear']): h.assert_no_listener(port)
    for name in ['/data2/_shared/gpu.lock', '/data2/FreeToken/run/production.active.json', '/data2/FreeToken/run/production.cleanup_failed.json']:
        q=Path(name); assert not q.exists() and not q.is_symlink()
    assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
    native_review=ROOT/'wt/r047-anchor-debug-20261010/INDEPENDENT_NATIVE_REUSE_R047_B60973D_V1.json'
    h.require_regular(native_review); assert not native_review.stat().st_mode & 0o222
    n=json.loads(native_review.read_text()); assert n['verdict'] == 'CPU_NATIVE_REUSE_READY_CONDITIONAL'
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    assert now.hour < 6 or now.hour == 6 and now.minute < 45, 'new round cutoff'
    wt = ROOT / 'wt/r047-anchor-debug-20261010'
    script = wt / 'development/r047_anchor_diagnostic_runner.py'
    review = wt / 'INDEPENDENT_STARTUP_REVIEW_R047_ANCHOR_DIAG_B60973D.json'
    dry = ROOT / 'runs/dev_R047_anchor_diag/FILEDRY_b60973d/FILEDRY.json'
    for p in [script, review, dry]:
        h.require_regular(p); assert not p.stat().st_mode & 0o222
    assert sha(review) == '297a8c0684215034572558f41f2c4221cd4bddd66868d739462a5f49b1476ed2'
    approved = json.loads(review.read_text())
    assert approved['verdict'] == 'CPU_APPROVE_CONDITIONAL_DIAGNOSTIC_RUN'
    assert sha(script) == approved['runner']['sha256'] and sha(dry) == approved['filedry']['sha256']
    spec = importlib.util.spec_from_file_location('r047_actual_diagnostic', script)
    r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
    readiness = r.checked_worktree(); assert readiness['commit'] == approved['candidate_commit']
    r.d07(); r.mature_r047()
    target = ROOT / 'runs/dev_R047_anchor_diag' / r.RID
    assert not target.exists() and not target.is_symlink()
    assert not list(target.parent.glob(f'launch_{r.RID}_batch*.json')), 'one-service diagnostic already attempted'
    admission = HERE / 'R047_DIAGNOSTIC_ROOT_ADMISSION.json'
    h.put(admission, {'at': now.isoformat(), 'admit': True, 'authority': 'NIGHT_SUPPLEMENT_20261010_0035', 'rid': r.RID, 'services_max': 1, 'generation_calls_max': 3, 'worktree': readiness, 'runner_sha256': sha(script), 'independent_review_sha256': sha(review), 'filedry_sha256': sha(dry), 'predecessor_cleanup': {'path': str(cleanup), 'sha256': sha(cleanup)}, 'diagnostic_only': True, 'r047_acceptance_remains': 'not_met', 'no_push': True, 'native_independent_review': {'path':str(native_review),'sha256':sha(native_review)}})
    argv = [str(ROOT / 'venv/bin/python'), '-B', '-u', str(script), '--run']
    receipt = HERE / 'R047_DIAGNOSTIC_ROOT_DRIVER_RECEIPT.json'; assert not receipt.exists() and not receipt.is_symlink()
    with (HERE / 'R047_DIAGNOSTIC_ROOT_DRIVER.log').open('xb') as log:
        proc = subprocess.Popen(argv, cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    fields = Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')', 1)[1].split()
    value = {'at': datetime.datetime.now().astimezone().isoformat(), 'pid': proc.pid, 'start_ticks': int(fields[19]), 'argv': argv, 'source_sha256': sha(script), 'root_admission_sha256': sha(admission), 'prior_cleanup_sha256': sha(cleanup)}
    h.put(receipt, value)
    with (HERE / 'COORDINATION_LOG.jsonl').open('a') as f:
        f.write(json.dumps(value | {'event': 'R047_BOUNDED_DIAGNOSTIC_STARTED_AFTER_D09_RETRY1_OWNED_CLEANUP'}) + chr(10)); f.flush(); os.fsync(f.fileno())
    print(json.dumps(value), flush=True)


if __name__ == '__main__': main()
