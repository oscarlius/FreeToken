"""Advance the approved night queue after exact D10 T16 owner cleanup."""
import datetime, hashlib, importlib.util, json, os, socket, subprocess, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
RID = 'E2-D10-T16-night-20261010'
ROUND = Path('/data2/_shared/runs/ft_rounds') / RID
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
helper = HERE / 'advance_d09_t16_to_strata_retry1_v5.py'
assert sha(helper) == '194ab227e367065594ea1fd47eacccd1caa9cd840d5a61daa30a84df48ecdfc2'
spec = importlib.util.spec_from_file_location('night_cleanup_helpers', helper)
h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)


def main():
    launch = ROOT / 'runs/dev_T16' / f'launch_{RID}_batch146.json'
    h.require_regular(launch)
    binding = json.loads(launch.read_text())
    child = binding['child']
    assert child == {'pid': 599675, 'start_ticks': 166680770, 'execution_id': '599675:166680770'}
    while not h.absent(child['pid'], child['start_ticks']):
        time.sleep(30)
    for name in ['/data2/_shared/gpu.lock', '/data2/FreeToken/run/production.active.json', '/data2/FreeToken/run/production.cleanup_failed.json']:
        p = Path(name); assert not p.exists() and not p.is_symlink(), name
    assert not subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
    status_path = ROUND / 'status_batch146.json'
    h.require_regular(status_path)
    status = json.loads(status_path.read_text())
    assert status['rid'] == RID and status['batch'] == 146 and status['batch_pid'] == child['pid']
    assert status['state'] == 'complete_measurements_pending_review', 'partial or failed T16 requires root independent cleanup path'
    owners = []
    for p in sorted(ROUND.glob('*/owned_process.json')):
        h.require_regular(p)
        owner = json.loads(p.read_text()); birth = owner.get('birth', owner)
        assert h.absent(birth['pid'], birth['start_ticks'])
        pgid = birth.get('pgid', owner.get('pgid', birth['pid']))
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit(): continue
            try:
                fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
                assert fields[0] == 'Z' or int(fields[2]) != pgid
            except (FileNotFoundError, ProcessLookupError): pass
        port = owner['port']; assert type(port) is int and 1024 <= port <= 65534
        states = {}; sockets = []
        try:
            for value in [port, port + 1]:
                states[str(value)] = h.assert_no_listener(value)
                sock = socket.socket(); sockets.append(sock)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); sock.bind(('0.0.0.0', value))
        finally:
            for sock in sockets: sock.close()
        owners.append({'path': str(p), 'sha256': sha(p), 'birth': birth, 'pgid': pgid, 'group_absent': True, 'ports_clear': states, 'ports_rebound': True})
    assert len(owners) == 8, 'complete T16 requires every actual arm owner' 
    cleanup = HERE / 'D10_T16_OWNED_CLEANUP_READBACK.json'
    h.put(cleanup, {'at': datetime.datetime.now().astimezone().isoformat(), 'rid': RID, 'cleanup_ok': True, 'child_absent': child, 'launch_sha256': sha(launch), 'status': status, 'status_sha256': sha(status_path), 'owners': owners, 'gpu_compute_absent': True, 'gpu_lock_absent': True, 'product_acceptance': False})
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
    assert now.hour < 6 or now.hour == 6 and now.minute < 45, 'new round cutoff'
    assert (now.replace(hour=7, minute=30, second=0, microsecond=0)-now).total_seconds() >= 90*60, 'insufficient time for R044 retry before restore'
    packet = ROOT / 'development/r044_capture_path_retry1_20261010_v3'
    script = packet / 'r044_prepare_v6.py'
    h.require_regular(script)
    assert not script.stat().st_mode & 0o222 and sha(script) == 'c9b0d32efd95057b12783245b335dc06736971e7f60b444bea061bb44fc1cbc7'
    import sys
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(packet))
    spec = importlib.util.spec_from_file_location('r044_actual_retry', script)
    r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
    review = r.require_startup_review()
    assert sha(review) == 'd95f443fb964a07c5dd9d31489e0dbb66f0f3c2e9f8350febb7099a9c2280d3e'
    assert r.RID == 'E2-R044-night-20261010-retry1'
    r.require_queue(r.load_d07())
    target = r.ROUNDS / r.RID
    assert not target.exists() and not target.is_symlink(), 'R044 retry1 already attempted'
    admission = HERE / 'R044_RETRY1_ROOT_ADMISSION_V1.json'
    h.put(admission, {'at':now.isoformat(), 'admit':True, 'authority':'NIGHT_SUPPLEMENT_20261010_0035',
                     'rid':r.RID, 'services_max':6, 'generation_calls_max':144, 'worktree':str(r.WT),
                     'runner_sha256':sha(script), 'startup_review_sha256':sha(review),
                     'predecessor_cleanup':{'path':str(cleanup),'sha256':sha(cleanup)},
                     'original_failed_harness_unchanged':True, 'no_push':True})
    argv = [str(ROOT/'venv/bin/python'), '-B', '-u', str(script), '--run']
    receipt = HERE / 'R044_RETRY1_ROOT_DRIVER_RECEIPT_V1.json'; assert not receipt.exists()
    with (HERE/'R044_RETRY1_ROOT_DRIVER_V1.log').open('xb') as log:
        proc = subprocess.Popen(argv,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    fields = Path(f'/proc/{proc.pid}/stat').read_text().rsplit(')',1)[1].split()
    value = {'at':datetime.datetime.now().astimezone().isoformat(),'pid':proc.pid,'start_ticks':int(fields[19]),
             'argv':argv,'source_sha256':sha(script),'root_admission_sha256':sha(admission),'prior_cleanup_sha256':sha(cleanup)}
    h.put(receipt,value)
    with (HERE/'COORDINATION_LOG.jsonl').open('a') as f:
        f.write(json.dumps(value|{'event':'R044_RETRY1_STARTED_AFTER_D10_T16_OWNED_CLEANUP'})+chr(10));f.flush();os.fsync(f.fileno())
    print(json.dumps(value),flush=True)

if __name__ == '__main__':main()
