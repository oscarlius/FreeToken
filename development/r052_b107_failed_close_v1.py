"""Seal the independently reviewed R052/b107 shutdown failure in place."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/data2/FreeToken')
ROUND = Path('/data2/_shared/runs/ft_rounds/E2-R052')
CANDIDATE = '0aa23431e5b800797543bdecbf35a01045131d7d'
LAUNCH = ROOT / 'runs/dev_R052/launch_E2-R052_batch107.json'
OBSERVATION = ROOT / 'runs/dev_R052/root_terminal_observation_batch107.json'
OBS_SHA = '5192842d7374371b9e17698fb9514f84cd92206888055ee7a074c74f7fc75574'
LAUNCH_SHA = '8e73bcc3cd0f842928555aaafe6c83a302b0aed725ff26f6f38356c0f389a695'
REVIEW_SHA = '5f7b7489ffd5d3f208df7cffeaf5bb142404d8ffd413ef41a0953419188700a0'
GENERIC_SHA = 'dbfecaee0c31fa1a7057a922e2c8e09944cdb8c51f22fe1e6fb6b8e6b3329835'
WRITER_SHA = '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
OWNED_PIDS = {2130191, 2130257, 2130571}
REPLAYS = [f'replay_{i:02}.json' for i in range(8)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def precheck(review, review_sha):
    require(review_sha == REVIEW_SHA, 'review must match independently reviewed b107 terminal receipt')
    require(ROUND.is_dir() and not ROUND.is_symlink(), 'exact open R052 directory required')
    require(not any((ROUND / name).exists() for name in ('round.json', 'round_history', 'MANIFEST.sha256')), 'round already closed')
    require(not Path('/data2/_shared/gpu.lock').exists(), 'GPU lock exists')
    require(not any(Path('/proc', str(pid)).exists() for pid in OWNED_PIDS), 'owned process still exists')
    ps = subprocess.check_output(['ps', '-eo', 'pid,ppid,pgid,sid,stat,comm'], text=True)
    require(not any(set(map(int, line.split()[:4])) & OWNED_PIDS for line in ps.splitlines()[1:]), 'owned process group/session still exists')
    apps = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader'], text=True)
    require(not apps.strip(), 'GPU compute process exists')
    require(sha(OBSERVATION) == OBS_SHA and sha(LAUNCH) == LAUNCH_SHA, 'terminal/launch pin differs')
    require(review.is_file() and not review.is_symlink() and not review.stat().st_mode & 0o222 and sha(review) == review_sha, 'independent review pin differs')
    obs, launch, rv = load(OBSERVATION), load(LAUNCH), load(review)
    require((rv.get('schema'), rv.get('rid'), rv.get('batch'), rv.get('verdict'), rv.get('proposed_verdict')) == ('ft_r052_terminal_review/v1', 'E2-R052', 107, 'PASS', 'failed_harness'), 'independent failed-harness review required')
    require(rv.get('candidate_commit') == CANDIDATE and rv.get('launch', {}).get('sha256') == LAUNCH_SHA, 'review launch/candidate differs')
    require(rv.get('terminal_observation', {}).get('sha256') == OBS_SHA, 'review terminal observation differs')
    require(obs.get('child_birth') == launch.get('child') and obs.get('child_exited') is True and obs.get('service_exited') is True and obs.get('remaining_owned_process_groups') == [], 'actual process identity/cleanup differs')
    require(obs.get('replay_files') == REPLAYS and obs.get('followup_raw_exists') is True and obs.get('complete_T11_result_exists') is False and obs.get('measurement_started') is True, 'partial measured failure scope differs')
    require(rv.get('measurement_started') is True and rv.get('retry_eligibility', {}).get('automatic_retry_authorized') is False and rv.get('retry_eligibility', {}).get('requires_explicit_user_approval') is True, 'measured retry restriction missing')
    partial = rv.get('verified_partial_measurement', {})
    require(partial.get('replay_files') == REPLAYS and partial.get('raw_only_hypothesis', {}).get('not_a_T11_measured_verdict') is True and rv.get('review_scope', {}).get('accepted_T11_business_conclusion') is False, 'independent partial request review missing')
    paths = [ROUND, *ROUND.rglob('*')]
    require(all(not p.is_symlink() and p.stat().st_uid == os.geteuid() and (p.is_dir() or p.is_file()) for p in paths), 'foreign or special raw member')
    actual = {str(p.relative_to(ROUND)): sha(p) for p in paths if p.is_file()}
    require(actual == obs['raw_inventory'] == rv['raw_binding']['sha256'] and len(actual) == 27, 'raw inventory changed since terminal observation')
    worker, failure = load(ROUND / 'worker_shutdown.json'), load(ROUND / 'failed_harness.json')
    require(worker == rv['failed_harness']['worker_shutdown'] and worker.get('status') == 'failed' and worker.get('error') == 'KeyboardInterrupt()' and worker.get('scheduler_run_started') is True, 'worker shutdown failure differs')
    require(failure == obs['failure'] == rv['failed_harness']['failure'] and failure.get('service_cleanup_complete') is True, 'harness failure/cleanup differs')
    require(load(ROUND / 'owned_cleanup.json') == obs['owned_cleanup'] == rv['failed_harness']['owned_cleanup'] and obs['owned_cleanup']['lock_released'] is True, 'owned cleanup receipt differs')
    require(all((ROUND / name).is_file() for name in [*REPLAYS, 'followup_raw.json', 'serve_args.txt']) and not (ROUND / 'result.json').exists(), 'request/result boundary differs')
    require(sha(Path(launch['batch_log'])) == obs['batch_log']['sha256'], 'batch log changed')
    require(sha(Path(launch['wrapper'])) == launch['wrapper_sha256'], 'batch wrapper changed')
    generic_path = Path(__file__).with_name('initial_measurement_close.py')
    writer_path = Path(__file__).with_name('round_json_append.py')
    require(sha(generic_path) == GENERIC_SHA and sha(writer_path) == WRITER_SHA, 'D04 source pin differs')
    return obs, launch, rv, actual, generic_path, writer_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    obs, launch, review, raw, generic_path, writer_path = precheck(args.review, args.review_sha256)
    if not args.close:
        print(json.dumps({'state': 'prevalidated', 'rid': ROUND.name, 'batch': 107, 'proposed_verdict': 'failed_harness', 'raw_files': len(raw)}))
        return
    for name, source in (('independent_terminal_review.json', args.review), ('terminal_observation.json', OBSERVATION), ('launch_receipt.json', LAUNCH), ('batch.sh', Path(launch['wrapper'])), ('round_json_append.py', writer_path), ('close_source/r052_b107_failed_close_v1.py', Path(__file__)), ('close_source/initial_measurement_close.py', generic_path)):
        write_new(ROUND / name, source.read_bytes())
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S CST')
    doc = {'schema': 'ft_round/v2', 'round_id': ROUND.name, 'epoch': 2, 'card': 'T11', 'created_at': now, 'closed_at': now,
           'base': {'commit': CANDIDATE, 'code_version': 'E2-base.1 candidate@0aa23431'}, 'experimental': {'candidate_commit': CANDIDATE},
           'verdict': 'pending_review', 'proposed_verdict': 'failed_harness', 'verdict_history': [], 'retractions': [],
           'results': {'service_launch_attempts': 1, 'model_services_started': 1, 'replay_requests_completed': 8, 'followup_requests_completed': 1, 'failed_harness_events': 1, 'T11_passed': False},
           'partial_observations': review['verified_partial_measurement'],
           'serve': {'files': {name: raw[name] for name in ('SERVE_CMD.txt', 'serve.log', 'ENV.txt', 'serve_argv.json', 'owned_process.json', 'serve_args.txt')}},
           'failure_archive': {'missing_measurement_result': 'required model-worker D0 shutdown failed with KeyboardInterrupt; partial D0/API observations do not establish T11 acceptance', 'worker_shutdown': review['failed_harness']['worker_shutdown']},
           'independent_review_sha256': args.review_sha256, 'terminal_observation_sha256': OBS_SHA, 'launch_receipt_sha256': LAUNCH_SHA,
           'queue_exception': launch['queue_exception'], 'batch_logs': [obs['batch_log']], 'manifest': 'MANIFEST.sha256',
           'retry_classification': review['retry_eligibility'], 'raw_inventory_before_closure': raw}
    spec = importlib.util.spec_from_file_location('r052_initial_publisher', generic_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.publish(ROUND, module.build_control(ROUND, doc))
    writer = ROUND / 'round_json_append.py'
    subprocess.run([sys.executable, str(writer), str(ROUND), 'verdict', '--new', 'failed_harness', '--reason', 'Independent R verified repeated SIGTERM interrupted model-worker D0 shutdown. Retain eight replay requests and one follow-up as partial observations only; no T11 acceptance. Owned processes exited and lock released. New GPU retry requires explicit user approval.', '--evidence', 'independent_terminal_review.json', 'terminal_observation.json', 'launch_receipt.json', '--by', 'root D04 closure'], check=True)
    subprocess.run([sys.executable, str(writer), str(ROUND), 'check'], check=True)
    require(all(sha(ROUND / name) == value for name, value in raw.items()), 'original raw bytes changed')
    for line in (ROUND / 'MANIFEST.sha256').read_text().splitlines():
        digest, relative = line.split('  ./', 1)
        require(sha(ROUND / relative) == digest, 'manifest mismatch: ' + relative)
    require(all(not p.stat().st_mode & 0o222 for p in (ROUND, *ROUND.rglob('*'))), 'round is not readonly')
    pin = {'schema': 'ft_closed_round_pin/v1', 'rid': ROUND.name, 'verdict': 'failed_harness', 'candidate_commit': CANDIDATE,
           'round_sha256': sha(ROUND / 'round.json'), 'manifest_sha256': sha(ROUND / 'MANIFEST.sha256'),
           'independent_review_sha256': args.review_sha256, 'readonly': True, 'original_raw_hashes_unchanged': True, 'batch': 107, 'time': now}
    target = ROOT / 'runs/plan_batches/closed_round_pins/E2-R052.json'
    write_new(target, pin)
    target.chmod(0o444)
    result = {**pin, 'pin_path': str(target), 'pin_sha256': sha(target), 'snapshot_or_clone': False}
    out = ROOT / 'runs/dev_R052/r052_b107_d04_failed_closure_v1.json'
    write_new(out, result)
    out.chmod(0o444)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
