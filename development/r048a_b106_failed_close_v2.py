"""Close only the independently reviewed, post-measurement capture failure R048a/b106."""
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
ROUND = Path('/data2/_shared/runs/ft_rounds/E2-R048a')
CANDIDATE = '8bf0ad396f5d3104d9b4385fc6a3962c2c81dfd8'
BASE = 'effb9969706922ddad9e59b96377e46469ebe97f'
LAUNCH = ROOT / 'runs/dev_R048/launch_E2-R048a_batch106.json'
OBSERVATION = ROOT / 'runs/dev_R048/root_terminal_observation_batch106.json'
OBS_SHA = 'a3c8acbd554d317c0d0c0aa9ee8e62bffca8233d1e8d5aacce7702add9cdba86'
LAUNCH_SHA = '3b92f9f6f5f5038f9df3d5f21849274689b45bdb9ea87deac7c688a3befe4326'
GENERIC_SHA = 'dbfecaee0c31fa1a7057a922e2c8e09944cdb8c51f22fe1e6fb6b8e6b3329835'
REVIEW_SHA = '713c83b9386f9f98a34b7835535408e72b2e5bb9982d11a8f40f991b0694be65'
WRITER_SHA = '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'
PERF = 'batch106/V0/performance'
DIAG = 'batch106/V0/diagnostic'
OWNED_PIDS = {2051222, 2051291, 2074140}


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
    require(review_sha == REVIEW_SHA, 'review must match the independently reviewed b106 terminal receipt')
    require(ROUND.is_dir() and not ROUND.is_symlink(), 'exact open R048 directory required')
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
    require((rv.get('schema'), rv.get('rid'), rv.get('batch'), rv.get('verdict'), rv.get('proposed_verdict')) == ('ft_r048a_terminal_review/v1', 'E2-R048a', 106, 'PASS', 'failed_harness'), 'independent failed-harness review required')
    require(rv.get('candidate_commit') == CANDIDATE and rv.get('launch', {}).get('sha256') == LAUNCH_SHA, 'review launch/candidate differs')
    require(rv.get('terminal_observation', {}).get('sha256') == OBS_SHA, 'review does not bind actual terminal observation')
    require(obs.get('child_birth') == launch.get('child') and obs.get('child_exited') is True and obs.get('services_exited') is True and not obs.get('services_remaining'), 'actual process identity/cleanup differs')
    require(obs.get('completed_variant_arms') == 0 and obs.get('performance_binding_receipts') == 6 and obs.get('diagnostic_binding_receipts') == 0 and obs.get('measurement_started') is True, 'partial measured failure scope differs')
    require(obs.get('completed_phase_directories') == [PERF] and obs.get('service_launch_attempts') == 2, 'phase boundary differs')
    require(rv.get('measurement_boundary', {}).get('measurement_started') is True and rv.get('retry_eligibility', {}).get('automatic_retry_authorized') is False and rv.get('retry_eligibility', {}).get('requires_explicit_user_approval') is True, 'measured retry restriction missing')
    require(len(rv.get('verified_partial_performance', {}).get('requests', [])) == 6, 'independent partial request review missing')
    paths = [ROUND, *ROUND.rglob('*')]
    require(all(not p.is_symlink() and p.stat().st_uid == os.geteuid() and (p.is_dir() or p.is_file()) for p in paths), 'foreign or special raw member')
    actual = {str(p.relative_to(ROUND)): sha(p) for p in paths if p.is_file()}
    require(actual == obs['raw_inventory'] and len(actual) == 67, 'raw inventory changed since terminal observation')
    log = (ROUND / DIAG / 'serve.log').read_text()
    require(all(token in log for token in ('moe.py', 'current_stream().synchronize()', 'cudaErrorStreamCaptureUnsupported', 'cudaErrorStreamCaptureInvalidated')), 'actual capture error missing')
    require((ROUND / PERF / 'serve_args.txt').is_file() and not (ROUND / DIAG / 'serve_args.txt').exists() and not (ROUND / 'batch106/round.json').exists(), 'unexpected serve/result boundary')
    require(len(list((ROUND / PERF).glob('*.binding.json'))) == 6 and not list((ROUND / DIAG).glob('*.binding.json')) and not (ROUND / DIAG / 'health.json').exists(), 'request evidence boundary differs')
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
        print(json.dumps({'state': 'prevalidated', 'rid': ROUND.name, 'batch': 106, 'proposed_verdict': 'failed_harness', 'raw_files': len(raw)}))
        return
    for name, source in (('independent_terminal_review.json', args.review), ('terminal_observation.json', OBSERVATION), ('launch_receipt.json', LAUNCH), ('batch.sh', Path(launch['wrapper'])), ('round_json_append.py', writer_path), ('close_source/r048a_b106_failed_close_v2.py', Path(__file__)), ('close_source/initial_measurement_close.py', generic_path)):
        write_new(ROUND / name, source.read_bytes())
    now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S CST')
    doc = {'schema': 'ft_round/v2', 'round_id': ROUND.name, 'epoch': 2, 'card': 'T09', 'created_at': now, 'closed_at': now,
           'base': {'commit': BASE, 'code_version': 'E2-base.1@effb996'}, 'experimental': {'candidate_commit': CANDIDATE},
           'verdict': 'pending_review', 'proposed_verdict': 'failed_harness', 'verdict_history': [], 'retractions': [],
           'results': {'service_launch_attempts': 2, 'model_services_started': 2, 'completed_variant_arms': 0, 'completed_phases': [PERF], 'performance_requests_completed': 6, 'diagnostic_requests_sent': 0, 'failed_harness_events': 1, 'T09_passed': False},
           'partial_observations': review['verified_partial_performance'],
           'serve': {'arms': {arm: {'model_started': True, 'files': {name: raw[f'{arm}/{name}'] for name in ('SERVE_CMD.txt', 'serve.log', 'ENV.txt', 'serve_argv.json', 'owned_process.json', 'serve_args.txt') if f'{arm}/{name}' in raw}} for arm in (PERF, DIAG)}},
           'failure_archive': {'missing_serve_args': [{'arm': DIAG, 'reason': 'diagnostic service failed during CUDA Graph capture before ready and before the harness wrote serve_args.txt; actual argv, ENV and startup log retained', 'evidence': ['terminal_observation.json', 'independent_terminal_review.json', f'{DIAG}/serve.log', f'{DIAG}/serve_argv.json']}], 'missing_measurement_result': 'only V0 performance completed; diagnostic failed before requests; A/B/C/S unstarted', 'startup_diagnostic_files_are_valid_measurement': False},
           'independent_review_sha256': args.review_sha256, 'terminal_observation_sha256': OBS_SHA, 'launch_receipt_sha256': LAUNCH_SHA,
           'batch_logs': [obs['batch_log']], 'manifest': 'MANIFEST.sha256',
           'retry_classification': review['retry_eligibility'], 'raw_inventory_before_closure': raw}
    spec = importlib.util.spec_from_file_location('r048_initial_publisher', generic_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.publish(ROUND, module.build_control(ROUND, doc))
    writer = ROUND / 'round_json_append.py'
    subprocess.run([sys.executable, str(writer), str(ROUND), 'verdict', '--new', 'failed_harness', '--reason', 'Independent R verified CUDA stream synchronization during diagnostic graph capture; retain six V0 performance observations only, zero complete variant arms; owned processes exited and lock released. New GPU retry requires explicit user approval.', '--evidence', 'independent_terminal_review.json', 'terminal_observation.json', 'launch_receipt.json', '--by', 'root D04 closure'], check=True)
    subprocess.run([sys.executable, str(writer), str(ROUND), 'check'], check=True)
    require(all(sha(ROUND / name) == value for name, value in raw.items()), 'original raw bytes changed')
    for line in (ROUND / 'MANIFEST.sha256').read_text().splitlines():
        digest, relative = line.split('  ./', 1)
        require(sha(ROUND / relative) == digest, 'manifest mismatch: ' + relative)
    require(all(not p.stat().st_mode & 0o222 for p in (ROUND, *ROUND.rglob('*'))), 'round is not readonly')
    pin = {'schema': 'ft_closed_round_pin/v1', 'rid': ROUND.name, 'verdict': 'failed_harness', 'candidate_commit': CANDIDATE,
           'round_sha256': sha(ROUND / 'round.json'), 'manifest_sha256': sha(ROUND / 'MANIFEST.sha256'),
           'independent_review_sha256': args.review_sha256, 'readonly': True, 'original_raw_hashes_unchanged': True, 'batch': 106, 'time': now}
    target = ROOT / 'runs/plan_batches/closed_round_pins/E2-R048a.json'
    write_new(target, pin)
    target.chmod(0o444)
    result = {**pin, 'pin_path': str(target), 'pin_sha256': sha(target), 'snapshot_or_clone': False}
    out = ROOT / 'runs/dev_R048/r048a_b106_d04_failed_closure_v1.json'
    write_new(out, result)
    out.chmod(0o444)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
