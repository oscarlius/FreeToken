"""Root-only D04 closure for the sealed E2-R067d retry1 product round, V2."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
RID = 'E2-R067d-d20-short-tail-retry1'
RAW = ROOT / 'runs/dev_R067' / RID
ROUND = Path('/data2/_shared/runs/ft_rounds') / RID
PACKET = ROOT / 'development/r067d_short_tail_retry1_20261010'
PY = str(ROOT / 'venv/bin/python')
CLOSER = ROOT / 'runs/dev_D16/r041_accept_final_20261005_2012/d04_server_round_close_db7b2787.py'
CLOSER_SHA256 = 'db7b278713f52b089a0079022cf73a46285ae1baef3fd7353da8194385f0585b'
RAW_MANIFEST_SHA256 = 'e2e3cf442b0a467a241b10d530920a12cc95893dd371255420f9af7e15bc7fb6'
TERMINAL_SHA256 = '666e60498c6b1ae400242befe5d2974565bb34716a828e1433df61e99f6ac636'
REVIEW_SHA256 = '12d812dd109023bb3201ec6b0969a81cd3d9802186d8466168f06794ff6b76e9'
CLEANUP_SHA256 = '4475e38c6fcecd5f8f5f1e98f27279bf12a1b8c8aa99c075a9892d1bf270c191'
CONFIG_SHA256 = '88a587c598cf53d0465d99e50d48286621ad0ed9b2313001fea5ca23482a8d92'
CPU_REVIEW_SHA256 = '2f5082bf5bcdf14c3e16d1b1b7ae31a9ea26c6e23f399dc9078b0a2429b773a8'
ADMISSION_SHA256 = '42dd9eb0b36ee0933397f27d28b38391fbbbff186fed82f6c0afd26e19003ba9'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def put_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def absent(identity):
    try:
        fields = Path(f"/proc/{identity['pid']}/stat").read_text().rsplit(')', 1)[1].split()
        return fields[0] == 'Z' or int(fields[19]) != identity['start_ticks']
    except FileNotFoundError:
        return True


def group_absent(identity):
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
            assert fields[0] == 'Z' or int(fields[2]) != identity['pgid']
        except (FileNotFoundError, ProcessLookupError):
            continue


def raw_manifest_paths():
    assert sha(RAW / 'RAW_MANIFEST.sha256') == RAW_MANIFEST_SHA256
    listed = {}
    for line in (RAW / 'RAW_MANIFEST.sha256').read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        assert len(digest) == 64 and name and not Path(name).is_absolute()
        assert name not in listed
        listed[name] = digest
    actual = {}
    for path in RAW.rglob('*'):
        assert not path.is_symlink()
        if path.is_file() and path.name != 'RAW_MANIFEST.sha256':
            actual[path.relative_to(RAW).as_posix()] = path
    assert set(listed) == set(actual) and len(listed) == 123
    for name, digest in listed.items():
        assert sha(actual[name]) == digest, name
    return actual


def copy_raw(actual):
    destination = ROUND / 'raw'
    destination.mkdir()
    for name in sorted(actual):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(actual[name], target)
        assert sha(target) == sha(actual[name]), name
    shutil.copy2(RAW / 'RAW_MANIFEST.sha256', destination / 'RAW_MANIFEST.sha256')
    assert sha(destination / 'RAW_MANIFEST.sha256') == RAW_MANIFEST_SHA256


def copy_startup_binding():
    binding = ROUND / 'startup_binding'
    binding.mkdir()
    names = (
        'R067D_RETRY1_CONFIG_CPU_ONLY.json',
        'CAN_CONSUME_CPU_APPROVE_R067D_RETRY1_V2.json',
        'R067D_RETRY1_ROOT_PREFLIGHT_V2.json',
        'R067D_RETRY1_ROOT_STARTUP_ADMISSION.json',
        'R067D_RETRY1_PREPARED_RUNNER_PACKET_V2.json',
        'RETRY1_SOURCE_FREEZE.json',
    )
    for name in names:
        shutil.copy2(PACKET / name, binding / name)
    return {name: {'path': f'startup_binding/{name}', 'sha256': sha(binding / name)} for name in names}


def copy_actual_serve_arms(raw_services):
    arms = {}
    for source in sorted(raw_services.iterdir()):
        assert source.is_dir() and not source.is_symlink()
        argv = load(source / 'argv.json')
        environment = load(source / 'environment.json')
        log = source / 'serve.log'
        lines = [line for line in log.read_text(encoding='utf-8', errors='strict').splitlines()
                 if line.startswith('ServerArgs(')]
        assert len(lines) == 1, f'started arm lacks exactly one ServerArgs: {source.name}'
        target = ROUND / source.name
        target.mkdir()
        shutil.copy2(log, target / 'serve.log')
        (target / 'SERVE_CMD.txt').write_text(shlex.join(argv) + '\n', encoding='utf-8')
        (target / 'ENV.txt').write_text(json.dumps(environment, indent=2) + '\n', encoding='utf-8')
        (target / 'serve_args.txt').write_text(lines[0] + '\n', encoding='utf-8')
        arms[source.name] = {
            'raw_source': str(source),
            'raw_argv_sha256': sha(source / 'argv.json'),
            'raw_environment_sha256': sha(source / 'environment.json'),
            'raw_serve_log_sha256': sha(log),
        }
    assert set(arms) == {'hot_p8192', 'hot_p8256', 'cold_A_p8192_t1', 'cold_B_p8192_t1'}
    return arms


def main():
    assert not ROUND.exists(), f'formal round already exists: {ROUND}'
    assert sha(CLOSER) == CLOSER_SHA256
    terminal = load(RAW / 'terminal.json')
    review = load(HERE / 'R067D_RETRY1_ACTUAL_TERMINAL_INDEPENDENT_REVIEW.json')
    cleanup = load(HERE / 'R067D_RETRY1_OWNED_CLEANUP_READBACK.json')
    launch = load(ROOT / 'runs/dev_R067' / f'launch_{RID}_batch143.json')
    binding = load(RAW / 'launch_binding.json')
    config = load(PACKET / 'R067D_RETRY1_CONFIG_CPU_ONLY.json')
    cpu_review = load(PACKET / 'CAN_CONSUME_CPU_APPROVE_R067D_RETRY1_V2.json')
    admission = load(PACKET / 'R067D_RETRY1_ROOT_STARTUP_ADMISSION.json')
    root_receipt = load(HERE / 'R067D_RETRY1_ROOT_DRIVER_RECEIPT.json')

    assert sha(RAW / 'terminal.json') == TERMINAL_SHA256
    assert sha(HERE / 'R067D_RETRY1_ACTUAL_TERMINAL_INDEPENDENT_REVIEW.json') == REVIEW_SHA256
    assert sha(HERE / 'R067D_RETRY1_OWNED_CLEANUP_READBACK.json') == CLEANUP_SHA256
    assert sha(PACKET / 'R067D_RETRY1_CONFIG_CPU_ONLY.json') == CONFIG_SHA256
    assert sha(PACKET / 'CAN_CONSUME_CPU_APPROVE_R067D_RETRY1_V2.json') == CPU_REVIEW_SHA256
    assert sha(PACKET / 'R067D_RETRY1_ROOT_STARTUP_ADMISSION.json') == ADMISSION_SHA256
    assert config['admission_state'] == 'pending_stop_approval_and_independent_startup_review'
    assert cpu_review['verdict'] == 'CPU_APPROVE_CONDITIONAL_QUEUE_ADMIT'
    assert admission['config_sha256'] == CONFIG_SHA256
    assert admission['independent_review_sha256'] == CPU_REVIEW_SHA256
    assert sha(PACKET / 'R067D_RETRY1_ROOT_PREFLIGHT_V2.json') == admission['root_preflight_sha256']
    assert sha(PACKET / 'R067D_RETRY1_PREPARED_RUNNER_PACKET_V2.json') == admission['prepared_runner_packet_sha256']
    assert root_receipt['admission_sha256'] == ADMISSION_SHA256
    assert root_receipt['prepared_packet_sha256'] == admission['prepared_runner_packet_sha256']
    assert terminal['rid'] == RID and terminal['batch'] == 143 and terminal['verdict'] == 'not_met'
    assert terminal['actual_services'] == 4 and terminal['actual_generation_calls'] == 8
    assert not terminal['cleanup_errors'] and terminal['GPU_lock_released'] is True
    assert terminal['planned_complete'] is False and terminal['product_acceptance'] is False
    assert len(terminal['requests']) == 8
    assert all(item['classification'] == 'valid' for item in terminal['requests'].values())
    cell = terminal['cells']
    assert len(cell) == 1 and cell[0] == {
        'classification': 'not_met', 'cold_A_equals_B': True, 'cold_token': 248046,
        'first_differing_character': 0, 'first_differing_token': 0, 'hot_equals_cold': False,
        'hot_token': 39, 'prefix': 8192, 'tail': 1,
    }
    assert review['independent_verdict'] == terminal['verdict'] == 'not_met'
    assert review['integrity']['terminal_sha256'] == TERMINAL_SHA256
    assert review['integrity']['raw_manifest_sha256_expected_and_actual'] == RAW_MANIFEST_SHA256
    assert review['actual_execution']['actual_services'] == 4
    assert review['actual_execution']['actual_generation_calls'] == 8
    assert cleanup['rid'] == RID and cleanup['cleanup_ok'] is True
    assert cleanup['terminal_sha256'] == TERMINAL_SHA256
    assert cleanup['actual_service_attempts'] == 4 and cleanup['actual_generation_calls'] == 8
    assert binding['batch'] == 143 and binding['config_sha256'] == CONFIG_SHA256
    child = binding['child']
    cleanup_child = cleanup['child_absent']
    assert {key: child[key] for key in ('pid', 'start_ticks', 'execution_id')} == cleanup_child
    assert child['pid'] == child['pgid'] == child['session']
    assert child['execution_id'] == f"{child['pid']}:{child['start_ticks']}"
    assert absent(child)
    actual_launch = ROOT / 'runs/dev_R067' / f'launch_{RID}_batch143.json'
    assert actual_launch == Path(binding['receipt'])
    assert launch == load(actual_launch) and sha(actual_launch) == cleanup['launch_sha256']
    assert len(cleanup['owners']) == 4
    for item in cleanup['owners']:
        owner = RAW / 'services' / item['service'] / 'owner.json'
        assert sha(owner) == item['sha256']
        assert load(owner)['pid_identity'] == item['birth']
        assert item['group_absent'] is True
        assert absent(item['birth'])
        group_absent(item['birth'])

    actual = raw_manifest_paths()
    ROUND.mkdir()
    copy_raw(actual)
    arms = copy_actual_serve_arms(RAW / 'services')
    startup_binding = copy_startup_binding()
    root_receipt_name = 'R067D_RETRY1_ROOT_DRIVER_RECEIPT.json'
    shutil.copy2(HERE / root_receipt_name, ROUND / 'startup_binding' / root_receipt_name)
    startup_binding[root_receipt_name] = {
        'path': f'startup_binding/{root_receipt_name}',
        'sha256': sha(ROUND / 'startup_binding' / root_receipt_name),
    }
    shutil.copy2(HERE / 'R067D_RETRY1_ACTUAL_TERMINAL_INDEPENDENT_REVIEW.json', ROUND / 'independent_review.json')
    shutil.copy2(HERE / 'R067D_RETRY1_OWNED_CLEANUP_READBACK.json', ROUND / 'owned_cleanup.json')
    for source, name in ((binding['receipt'], 'launch_receipt.json'),
                         (launch['wrapper'], 'batch.sh'),
                         (launch['batch_log'], 'batch143.log')):
        shutil.copy2(source, ROUND / name)
    put_new(ROUND / 'cleanup_readback.json', {
        'rid': RID,
        'source_cleanup': {'path': 'owned_cleanup.json', 'sha256': sha(ROUND / 'owned_cleanup.json')},
        'historical_owned_child_absent': True,
        'historical_owned_groups_absent': True,
        'current_global_gpu_state_excluded': True,
        'current_d09_round_not_inspected_or_modified': True,
    })
    document = {
        'schema': 'ft_round/v2', 'round_id': RID, 'card': 'R067', 'batch': 143,
        'retry_of': 'E2-R067d-d20-short-tail-v1', 'retry_index': 1,
        'verdict': 'pending_review', 'proposed_verdict': 'not_met', 'raw_terminal_verdict': 'not_met',
        'verdict_history': [], 'retractions': [], 'serve': {'arms': arms},
        'base': {'commit': '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'},
        'experimental': {'candidate_commit': 'd50be0f8f84ab1105f788be8f1354773ad539b63'},
        'batch_logs': [{'path': launch['batch_log'], 'sha256': sha(launch['batch_log'])}],
        'raw_run': str(RAW), 'raw_manifest': {'path': 'raw/RAW_MANIFEST.sha256', 'sha256': RAW_MANIFEST_SHA256},
        'result_binding': {name: {'path': name, 'sha256': sha(ROUND / name)} for name in (
            'independent_review.json', 'owned_cleanup.json', 'cleanup_readback.json', 'raw/terminal.json')},
        'startup_binding': startup_binding,
        'actual_services': 4, 'actual_generation_calls': 8, 'cells_comparable': 1,
        'product_acceptance': False,
        'early_product_stop': {'authorized': 'NIGHT_SUPPLEMENT_20261010_0035',
                               'reason': 'stable cold A/B differs from hot at first token'},
        'retry_policy': {
            'maximum_tooling_retries': 2,
            'tooling_retry_used': 1,
            'tooling_retry_remaining_scope_budget': 1,
            'automatic_product_retry_authorized': False,
            'reason': 'retry1 is a product not_met, not a tooling retry authorization',
        },
    }
    put_new(ROUND / 'round.json', document)
    close = subprocess.run([PY, str(CLOSER), RID, '--round-root', str(ROUND.parent)], capture_output=True, text=True)
    assert close.returncode == 0, (close.stdout, close.stderr)
    app = str(ROOT / 'scripts/round_json_append.py')
    append = subprocess.run([PY, app, str(ROUND), 'verdict', '--new', 'not_met',
                             '--reason', 'stable cold A/B differs from hot at first token',
                             '--evidence', str(ROUND / 'raw/terminal.json'),
                             str(ROUND / 'independent_review.json'), str(ROUND / 'owned_cleanup.json'),
                             '--by', 'root'], capture_output=True, text=True)
    assert append.returncode == 0, (append.stdout, append.stderr)
    check = subprocess.run([PY, app, str(ROUND), 'check'], capture_output=True, text=True)
    assert check.returncode == 0, (check.stdout, check.stderr)
    for line in (ROUND / 'MANIFEST.sha256').read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        assert sha(ROUND / name.removeprefix('./')) == digest, name
    assert all(not path.stat().st_mode & 0o222 for path in [ROUND, *ROUND.rglob('*')])
    print(json.dumps({
        'formal_round': str(ROUND), 'manifest_sha256': sha(ROUND / 'MANIFEST.sha256'),
        'D04': json.loads(close.stdout), 'history_check': json.loads(check.stdout),
        'all_hashes_match': True, 'all_read_only': True, 'raw_verdict': 'not_met', 'verdict': 'not_met',
    }))


if __name__ == '__main__':
    main()
