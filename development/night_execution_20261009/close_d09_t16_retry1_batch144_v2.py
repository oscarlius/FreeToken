"""Root-only D04 closure for D09 T16 retry1 batch144.

This script is deliberately not a dry run: root must inspect it and execute it
once.  It performs no GPU, HTTP, service, or compilation operation.  It only
binds completed artifacts, revalidates the recorded retry1 process identities,
and performs formal D04/file-system closure.
"""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess


ROOT = Path('/data2/FreeToken')
NIGHT = ROOT / 'development/night_execution_20261009'
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
RID = 'E2-D09-T16-night-20261010-retry1'
RUN = ROUNDS / RID
PYTHON = ROOT / 'venv/bin/python'
CLOSER = ROOT / 'runs/dev_D16/r041_accept_final_20261005_2012/d04_server_round_close_db7b2787.py'
APPENDER = ROOT / 'scripts/round_json_append.py'

CLOSER_SHA256 = 'db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
REVIEW_SHA256 = '7975b5518db6ba08d93ae8a9cd1564876079e7e323fefe3c041a849cdaef098e'
CLEANUP_SHA256 = '92dcb93d2e831b5f614df1992c2f85d28f6b743496fbd2379e475fa1de22f105'
STATUS_SHA256 = 'b011370ead1ad1dfecedb8793936837b011b282f977ee2ea5d4ed40a498b62ae'
GATE_SHA256 = 'a5de3b46600d137da810291fc5d2b054a868e6306e04f2ffe6ceaf2a9f4843ab'
BINDING_SHA256 = 'f7d75d189e2e0199360bda6c7ae214bba7b2dc487cbe5ceb342c66c9a363c0b5'
TOOLS_SHA256 = '02605c3c72df196978adbb2cc7036bdf0aab2109a34701fb72653389eeb0d85b'
LAUNCH_SHA256 = 'db0745e5757252d3b4d5d4bb1d3e25e9b25e9c84545288e92df7e1552aeee117'
ROOT_RECEIPT_SHA256 = '2e318e74bdafd3c406b5576841456f0aa5bdb5e92e6a9466e59cf3fe81c70fbc'
COUNT_REVIEW_SHA256 = '48adea9d0b998e1223dc13d963959d1daeb143cf602493200edd7a7289fd95bd'

PARENT = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'
CANDIDATE = 'c17b69a46cd512fbf3d127d3879bce92caae457b'
ARMS = (
    'PARENT_b144', 'NEW_b144', 'PARENT_P_b144', 'NEW_P_b144',
    'CHUNK_PARENT_b144', 'CHUNK_NEW_b144', 'CHUNK_PARENT_P_b144', 'CHUNK_NEW_P_b144',
)
NEW_ARMS = {'NEW_b144', 'NEW_P_b144', 'CHUNK_NEW_b144', 'CHUNK_NEW_P_b144'}
CHUNK_ARMS = {'CHUNK_PARENT_b144', 'CHUNK_NEW_b144', 'CHUNK_PARENT_P_b144', 'CHUNK_NEW_P_b144'}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def put_new_json(path: Path, value: dict) -> None:
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def copy_new(source: Path, target: Path) -> None:
    assert not target.exists(), target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    assert sha256(target) == sha256(source), target


def process_absent(identity: dict) -> bool:
    """Check the PID/start-ticks identity only; a PID reuse must fail closed."""
    assert set(identity) >= {'pid', 'start_ticks', 'execution_id'}
    assert identity['execution_id'] == f"{identity['pid']}:{identity['start_ticks']}"
    try:
        fields = Path(f"/proc/{identity['pid']}/stat").read_text().rsplit(')', 1)[1].split()
    except FileNotFoundError:
        return True
    return fields[0] == 'Z' or int(fields[19]) != identity['start_ticks']


def process_group_absent(identity: dict) -> bool:
    """Only inspect the historical owner PGID; do not inspect or alter global GPU state."""
    assert set(identity) >= {'pid', 'start_ticks', 'execution_id', 'pgid', 'session'}
    assert identity['execution_id'] == f"{identity['pid']}:{identity['start_ticks']}"
    assert identity['pid'] == identity['pgid'] == identity['session']
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if fields[0] != 'Z' and int(fields[2]) == identity['pgid']:
            return False
    return True


def verify_measurements(binding: dict, gate: dict) -> None:
    assert binding['card'] == binding['case'] == 'D09'
    assert binding['parent_commit'] == binding['parent_native_commit'] == PARENT
    assert binding['new_commit'] == CANDIDATE
    assert binding['default_off_public_flag'] == {'enable_message_boundary_ckpt': False}
    assert gate['parent_commit'] == PARENT and gate['new_commit'] == CANDIDATE
    assert gate['proposed_verdict'] == 'kept' and tuple(gate['arms']) == ARMS
    assert not (RUN / 'round.json').exists() and not (RUN / 'MANIFEST.sha256').exists()

    cold_calls = 0
    for arm in ARMS:
        directory = RUN / arm
        assert directory.is_dir() and not directory.is_symlink(), arm
        for name in ('SERVE_CMD.txt', 'ENV.txt', 'serve_args.txt', 'serve.log', 'ready_sayok.json', 'tax.json', 'owned_process.json'):
            assert (directory / name).is_file() and (directory / name).stat().st_size > 0, (arm, name)
        serve_args = (directory / 'serve_args.txt').read_text(encoding='utf-8')
        checked = directory / 'args_checked.json'
        if arm in NEW_ARMS:
            assert 'message_boundary_ckpt=False' in serve_args, arm
            diff = load(checked)
            assert diff['message_boundary_ckpt'] == [None, 'False']
        else:
            assert 'message_boundary_ckpt=' not in serve_args and not checked.exists(), arm

        tax = load(directory / 'tax.json')
        assert tax['reps'] == 5 and len(tax['single']) == len(tax['multi']) == 5
        assert all(isinstance(value, (int, float)) and value > 0 for value in tax['single'] + tax['multi'])

        expected_cases = ('short', 'chunked') if arm in CHUNK_ARMS else ('det',)
        for case in expected_cases:
            record = load(directory / f'{case}.json').get('record')
            assert isinstance(record, dict)
            assert record['cached_tokens'] == 0 and record['completion_tokens'] == 128
            assert record['finish_reason'] == 'length'
            if case == 'short':
                assert (record['built_tokens'], record['prompt_tokens']) == (2000, 2012)
            else:
                assert (record['built_tokens'], record['prompt_tokens']) == (32052, 32064)
            cold_calls += 1

    actual_calls = len(ARMS) + cold_calls + len(ARMS) * 5 * 2
    assert cold_calls == 12 and actual_calls == 100


def main() -> None:
    assert not (RUN / 'round_history').exists(), 'round already D04 sealed'
    assert sha256(CLOSER) == CLOSER_SHA256
    assert not (NIGHT / 'D09_T16_RETRY1_D04_CLOSURE_RECEIPT_V1.json').exists()

    review = NIGHT / 'D09_T16_RETRY1_ACTUAL_TERMINAL_INDEPENDENT_REVIEW.json'
    cleanup_path = NIGHT / 'D09_T16_RETRY1_OWNED_CLEANUP_READBACK.json'
    root_receipt = NIGHT / 'D09_T16_RETRY1_ROOT_DRIVER_RECEIPT.json'
    launch_path = ROOT / 'runs/dev_T16/launch_E2-D09-T16-night-20261010-retry1_batch144.json'
    status_path, gate_path = RUN / 'status_batch144.json', RUN / 'gate_batch144.json'
    binding_path, tools_path = RUN / 'candidate_binding.json', RUN / 'tools_batch144.json'
    count_review = NIGHT / 'INDEPENDENT_T16_FULL_PROTOCOL_CALL_COUNT_REVIEW_V1.json'
    assert sha256(review) == REVIEW_SHA256
    assert sha256(cleanup_path) == CLEANUP_SHA256
    assert sha256(root_receipt) == ROOT_RECEIPT_SHA256
    assert sha256(launch_path) == LAUNCH_SHA256
    assert sha256(status_path) == STATUS_SHA256 and sha256(gate_path) == GATE_SHA256
    assert sha256(binding_path) == BINDING_SHA256 and sha256(tools_path) == TOOLS_SHA256
    assert sha256(count_review) == COUNT_REVIEW_SHA256

    status, gate, binding = load(status_path), load(gate_path), load(binding_path)
    launch, cleanup = load(launch_path), load(cleanup_path)
    assert status == cleanup['status']
    assert status['rid'] == RID and status['batch'] == 144
    assert status['state'] == 'complete_measurements_pending_review'
    assert status['proposed_verdict'] == 'kept'
    assert launch['rid'] == RID and launch['batch'] == 144
    assert launch['candidate_commit'] == CANDIDATE
    assert cleanup['rid'] == RID and cleanup['cleanup_ok'] is True
    assert cleanup['product_acceptance'] is False
    assert cleanup['launch_sha256'] == LAUNCH_SHA256
    assert cleanup['status_sha256'] == STATUS_SHA256

    # The launch/cleanup controller child has exactly the three identity fields.
    child = launch['child']
    cleanup_child = cleanup['child_absent']
    assert set(child) == {'pid', 'start_ticks', 'execution_id'}
    assert child == cleanup_child
    assert process_absent(child)

    # Owned-process records may include PGID/session and are checked separately.
    assert len(cleanup['owners']) == len(ARMS)
    expected_owner_paths = {str(RUN / arm / 'owned_process.json') for arm in ARMS}
    assert {entry['path'] for entry in cleanup['owners']} == expected_owner_paths
    for entry in cleanup['owners']:
        owner_path = Path(entry['path'])
        owner = load(owner_path)
        identity = entry['birth']
        assert sha256(owner_path) == entry['sha256']
        assert owner['birth'] == identity
        assert entry['group_absent'] is True
        assert process_absent(identity) and process_group_absent(identity)

    verify_measurements(binding, gate)

    evidence = RUN / 'closure_evidence'
    assert not evidence.exists()
    evidence.mkdir()
    copies = {
        'independent_review.json': review,
        'owned_cleanup_readback.json': cleanup_path,
        'root_driver_receipt.json': root_receipt,
        'launch_receipt.json': launch_path,
        'full_protocol_count_review.json': count_review,
    }
    for name, source in copies.items():
        copy_new(source, evidence / name)
    copy_new(RUN / 'batch144.sh', RUN / 'batch.sh')
    assert sha256(RUN / 'batch.sh') == sha256(RUN / 'batch144.sh')

    checked_at = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    revalidation = {
        'schema': 'ft_d09_retry1_owned_cleanup_revalidation/v1',
        'rid': RID,
        'checked_at': checked_at,
        'cleanup_source': {'path': 'closure_evidence/owned_cleanup_readback.json', 'sha256': sha256(evidence / 'owned_cleanup_readback.json')},
        'child_identity_fields': ['pid', 'start_ticks', 'execution_id'],
        'child_absent_now': True,
        'owned_process_count': len(ARMS),
        'all_owned_pid_identities_absent_now': True,
        'all_owned_process_groups_absent_now': True,
        'current_global_gpu_state_checked': False,
        'current_global_gpu_state_reason': 'outside retry1 ownership and intentionally not required',
    }
    put_new_json(evidence / 'owned_cleanup_revalidation.json', revalidation)

    arms = {arm: {'raw_source': str(RUN / arm)} for arm in ARMS}
    document = {
        'schema': 'ft_round/v2',
        'round_id': RID,
        'card': 'D09-T16',
        'batch': 144,
        'retry_of': 'E2-D09-T16-night-20261009',
        'retry_index': 1,
        'verdict': 'pending_review',
        'proposed_verdict': 'kept',
        'verdict_history': [],
        'retractions': [],
        'serve': {'arms': arms},
        'base': {'commit': PARENT},
        'experimental': {'candidate_commit': CANDIDATE},
        'actual_services': 8,
        'actual_generation_calls': 100,
        'product_acceptance': False,
        'batch_logs': [{'path': launch['batch_log'], 'sha256': sha256(Path(launch['batch_log']))}],
        'result_binding': {
            'status_batch144.json': {'path': 'status_batch144.json', 'sha256': sha256(status_path)},
            'gate_batch144.json': {'path': 'gate_batch144.json', 'sha256': sha256(gate_path)},
            'candidate_binding.json': {'path': 'candidate_binding.json', 'sha256': sha256(binding_path)},
            'tools_batch144.json': {'path': 'tools_batch144.json', 'sha256': sha256(tools_path)},
            'independent_review.json': {'path': 'closure_evidence/independent_review.json', 'sha256': sha256(evidence / 'independent_review.json')},
            'owned_cleanup_readback.json': {'path': 'closure_evidence/owned_cleanup_readback.json', 'sha256': sha256(evidence / 'owned_cleanup_readback.json')},
            'owned_cleanup_revalidation.json': {'path': 'closure_evidence/owned_cleanup_revalidation.json', 'sha256': sha256(evidence / 'owned_cleanup_revalidation.json')},
            'full_protocol_count_review.json': {'path': 'closure_evidence/full_protocol_count_review.json', 'sha256': sha256(evidence / 'full_protocol_count_review.json')},
        },
        'closure_scope': {
            'raw_evidence_preserved_in_place': True,
            'current_global_gpu_idle_not_required': True,
            'no_product_rerun_or_protocol_change': True,
        },
    }
    put_new_json(RUN / 'round.json', document)

    for argv in (
        [str(PYTHON), str(CLOSER), RID, '--round-root', str(ROUNDS)],
        [str(PYTHON), str(APPENDER), str(RUN), 'verdict', '--new', 'kept',
         '--reason', 'batch144 eight-arm measurement gate passed with default-off candidate and 100 actual protocol generation calls',
         '--evidence', str(evidence / 'independent_review.json'), str(gate_path), str(evidence / 'owned_cleanup_revalidation.json'),
         '--by', 'root'],
        [str(PYTHON), str(APPENDER), str(RUN), 'check'],
    ):
        result = subprocess.run(argv, capture_output=True, text=True)
        assert result.returncode == 0, (argv, result.stdout, result.stderr)

    manifest = RUN / 'MANIFEST.sha256'
    for line in manifest.read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        assert sha256(RUN / name.removeprefix('./')) == digest, name
    assert all(not path.stat().st_mode & 0o222 for path in [RUN, *RUN.rglob('*')])

    receipt = {
        'schema': 'ft_d09_retry1_d04_closure_receipt/v1',
        'rid': RID,
        'closed_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
        'verdict': 'kept',
        'formal_round': str(RUN),
        'manifest_sha256': sha256(manifest),
        'actual_services': 8,
        'actual_generation_calls': 100,
        'raw_evidence_preserved': True,
        'all_closed_round_paths_readonly': True,
        'global_gpu_idle_not_checked': True,
    }
    receipt_path = NIGHT / 'D09_T16_RETRY1_D04_CLOSURE_RECEIPT_V1.json'
    put_new_json(receipt_path, receipt)
    os.chmod(receipt_path, stat.S_IMODE(receipt_path.stat().st_mode) & ~0o222)
    print(json.dumps(receipt, sort_keys=True))


if __name__ == '__main__':
    main()
