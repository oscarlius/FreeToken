"""Audit or seal the exact R028 initialization failure while preserving raw evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path('/data2/FreeToken')
ROUNDS = Path('/data2/_shared/runs/ft_rounds')
RID = 'E2-R028-diagnostic-T17'
CPU_SHA = '85310fd65f781b755cb374a3aa4c2c5716907c723a58f9371f5e326a67a9bf0d'
CONFIG_SHA = 'deef67a61f3311faf051b23dc4192f442c7fee4f9cd2f38cbcbe4da55c763a80'
TOOLS = {'round_json_append.py': '67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff',
         'round_close.py': 'fd3d40c25b045920cc6a247c0e3e09e11bf831c4d24ddfaa67dfb562dec60fb5',
         'round_close.sh': '6df87a2f2edfcbc985a2d593edb16349bf923e1f301939cdda1590d52d1f55f9'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def terminal(pid, ticks):
    path = Path('/proc') / str(pid) / 'stat'
    if not path.exists():
        return
    fields = path.read_text().rpartition(') ')[2].split()
    if int(fields[19]) != ticks or fields[0] != 'Z':
        raise ValueError('owned process remains live or identity changed')


def audit():
    directory = ROUNDS / RID
    if any(p.is_symlink() or p.stat().st_uid != os.geteuid() for p in (directory, *directory.rglob('*'))):
        raise ValueError('regular owned evidence required')
    if any((directory / n).exists() for n in ('round.json', 'MANIFEST.sha256', 'round_history', 'failure_review.json', 'source_tools', 'batch.sh')):
        raise ValueError('exact unprepared failed round required')
    status = json.loads((directory / 'status_batch56.json').read_bytes())
    if any(status.get(k) != v for k, v in {'rid': RID, 'batch': 56, 'batch_pid': 618600,
                                          'batch_start_ticks': 122614666, 'state': 'failed'}.items()):
        raise ValueError('exact R028 failure status required')
    if 'expected PLE owner at decoder index 2, got 1' not in status.get('error', ''):
        raise ValueError('different failure; do not substitute diagnosis')
    receipt = json.loads((ROOT / 'runs/dev_D14' / ('launch_' + RID + '.json')).read_bytes())
    if any(receipt.get(k) != v for k, v in {'rid': RID, 'batch': 56, 'batch_pid': 618600, 'batch_pgid': 618600,
                                          'cpu_stage_sha256': CPU_SHA, 'FT_LM_CHUNK': 4096, 'diagnostic_only': True}.items()):
        raise ValueError('exact launch/source receipt required')
    terminal(618600, 122614666)
    arm = directory / 'projection_warm'
    identity = json.loads((arm / 'process_identity.json').read_bytes())
    expected = {'pid': 619025, 'pgid': 619025, 'session': 619025, 'start_ticks': 122615309}
    if any(identity.get(k) != v for k, v in expected.items()):
        raise ValueError('known warm service identity differs')
    if json.loads((arm / 'stop_identity.json').read_bytes()) != {'terminal': True, **identity}:
        raise ValueError('owned terminal receipt differs')
    terminal(619025, 122615309)
    lock = Path('/data2/_shared/gpu.lock')
    if lock.exists() and json.loads(lock.read_bytes()).get('owner') == RID:
        raise ValueError('owned lock remains')
    if (directory / 'projection_cold').exists() or (directory / 'diagnostic_batch56.json').exists():
        raise ValueError('unexpected measurement/cold arm')
    log = (arm / 'serve.log').read_text()
    if "ValueError: expected PLE owner at decoder index 2, got 1" not in log:
        raise ValueError('actual failed operator traceback missing')
    config = ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay/config.json'
    if sha(config) != CONFIG_SHA or json.loads(config.read_bytes())['text_config']['ple_layer_ids'] != [2]:
        raise ValueError('actual model configuration changed')
    sys.path.insert(0, str(ROOT / 'wt/e2d14/python'))
    from types import SimpleNamespace
    import torch
    from freetoken.models.qwen4_exp.config import parse_config
    parser_source = Path(sys.modules[parse_config.__module__].__file__)
    if sha(parser_source) != '72905266db8c384ea3cd267a1b739c58a32b8b069f37039b778665cc2be14607':
        raise ValueError('actual candidate config parser changed')
    document = json.loads(config.read_bytes())
    hf = SimpleNamespace(**document)
    hf.text_config = SimpleNamespace(**document['text_config'])
    if isinstance(getattr(hf, 'vision_config', None), dict):
        hf.vision_config = SimpleNamespace(**hf.vision_config)
    parsed_config = parse_config(hf)
    if parsed_config.qwen4_args.ple_layer_ids != (1,) or torch.cuda.is_initialized():
        raise ValueError('actual CPU config mapping proof differs')
    stage, frozen = Path(receipt['source_stage']), Path(receipt['frozen_runner']).parent
    if sha(stage / 'cpu_validation.json') != CPU_SHA:
        raise ValueError('CPU source proof differs')
    for name, digest in receipt['source_files'].items():
        if sha(stage / name) != digest or sha(frozen / name) != digest:
            raise ValueError('frozen executed source differs')
    if sha(Path(receipt['wrapper'])) != receipt['wrapper_sha256']:
        raise ValueError('actual batch wrapper differs')
    parser = ROOT / 'scripts/serve_args_diff.py'
    if hashlib.md5(parser.read_bytes()).hexdigest() != 'ce123cb0af201d99baac91f7f8e4f8c7':
        raise ValueError('retained common parsed-arguments source differs')
    parsed = runpy.run_path(str(parser))['parse'](str(arm / 'serve.log'))
    if parsed.get('_unique_suffix') != repr('.pid=619025'):
        raise ValueError('actual parsed service PID differs')
    derived_args = encoded(parsed)
    for name, digest in TOOLS.items():
        if sha(HERE / name) != digest or sha(ROOT / 'scripts' / name) != digest:
            raise ValueError('tested canonical D04 source differs')
    prior = ROUNDS / 'E2-R023-gate-T17'
    if sha(prior / 'round.json') != '92618df52121bf141a6f231d46961d394860ade1b756295b6a5cf6c228c08c1d':
        raise ValueError('retained original not_met changed')
    raw = {p.relative_to(directory).as_posix(): sha(p) for p in sorted(directory.rglob('*')) if p.is_file()}
    return {'schema': 'ft_r028_initialization_failure_review/v1', 'rid': RID, 'batch': 56,
            'receipt': receipt, 'status': status, 'owned_service': identity, 'original_raw_files': raw,
            'model_config_sha256': CONFIG_SHA, 'actual_ple_decoder_indices': [1], 'source_HF_ple_layer_ids': [2], 'first_decoder_has_ple': False,
            'config_parser': {'path': str(parser_source), 'sha256': sha(parser_source), 'cuda_initialized': False},
            'diagnosis': 'Observer incorrectly treated one-indexed HF PLE id2 as decoder index2; actual candidate parser maps it to zero-indexed decoder1.',
            'measurements_completed': False, 'original_T17_verdict': 'not_met_retained',
            'derived_serve_args': {'path': 'projection_warm/serve_args.txt', 'sha256': hashlib.sha256(derived_args).hexdigest(),
                                   'parsed': parsed, 'parser_sha256': sha(parser),
                                   'source_log_sha256': sha(arm / 'serve.log'), 'source_command_sha256': sha(arm / 'SERVE_CMD.txt')},
            'proposed_verdict': 'failed_harness', 'batch_log_sha256': sha(ROUNDS / 'batch56.log')}


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


def encoded(value):
    return (json.dumps(value, indent=2, allow_nan=False) + '\n').encode()


def close():
    review = audit()
    if json.loads((HERE / 'review.json').read_bytes()) != review:
        raise ValueError('separately reviewed failure audit differs')
    directory = ROUNDS / RID
    receipt = review['receipt']
    frozen = Path(receipt['frozen_runner']).parent
    for name in receipt['source_files']:
        write(directory / 'source_tools/runtime' / name, (frozen / name).read_bytes())
    for path in HERE.iterdir():
        if path.is_file():
            write(directory / 'source_tools/closure' / path.name, path.read_bytes())
    stage = Path(receipt['source_stage'])
    for path in stage.iterdir():
        if path.is_file() and path.suffix in ('.json', '.log'):
            write(directory / 'source_tools/launch_cpu' / path.name, path.read_bytes())
    write(directory / 'model_config.json', (ROOT / 'models/Qwen3.8-Flash-Next-NVFP4-overlay/config.json').read_bytes())
    config_parser = Path(review['config_parser']['path'])
    if sha(config_parser) != review['config_parser']['sha256']:
        raise ValueError('actual config parser changed before archival')
    write(directory / 'source_tools/target_structure/config.py', config_parser.read_bytes())
    derived = review['derived_serve_args']
    write(directory / derived['path'], encoded(derived['parsed']))
    parser = ROOT / 'scripts/serve_args_diff.py'
    if sha(parser) != derived['parser_sha256']:
        raise ValueError('parsed-arguments derivation source changed')
    write(directory / 'source_tools/runtime_metadata/serve_args_diff.py', parser.read_bytes())
    write(directory / 'failure_review.json', encoded(review))
    write(directory / 'batch.sh', Path(receipt['wrapper']).read_bytes())
    for name in TOOLS:
        write(directory / name, (HERE / name).read_bytes())
    metadata = {'schema': 'ft_round/v2', 'round_id': RID, 'epoch': 2, 'card': 'T17',
                'title': 'Original-chunk projection diagnostic initialization failed', 'parent': 'E2-R023-gate-T17',
                'base': {'commit': receipt['candidate_commit'], 'code_version': 'D14 candidate@e4f3202'},
                'experimental': {'diagnostic_only': True, 'FT_LM_CHUNK': 4096},
                'serve': {'arms': {'projection_warm': review['owned_service']}}, 'diagnostics': review,
                'anomalies': [{'kind': 'failed_harness', 'reason': review['diagnosis']}],
                'results': {'measurements_completed': False}, 'proposed_verdict': 'failed_harness',
                'verdict': 'pending_review', 'verdict_history': [], 'retractions': [],
                'batch_logs': [{'path': str(ROUNDS / 'batch56.log'), 'sha256': review['batch_log_sha256']}]}
    write(directory / 'round.json', encoded(metadata))
    subprocess.run(['bash', str(directory / 'round_close.sh'), RID, '--round-root', str(ROUNDS)],
                   env={**os.environ, 'FT_ROUND_PYTHON': sys.executable}, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'verdict',
                    '--new', 'failed_harness', '--reason', review['diagnosis'] + ' No diagnostic measurements; original R023 not_met retained.',
                    '--by', 'Codex mainline', '--evidence', 'failure_review.json', 'model_config.json'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable, str(directory / 'round_json_append.py'), str(directory), 'check'], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(['sha256sum', '-c', 'MANIFEST.sha256'], cwd=directory, check=True, stdout=subprocess.DEVNULL)
    if any(sha(directory / name) != digest for name, digest in review['original_raw_files'].items()):
        raise ValueError('original failure bytes changed')
    if any(p.stat().st_mode & 0o222 for p in (directory, *directory.rglob('*'))):
        raise ValueError('failure round not read-only')
    print(json.dumps({'rid': RID, 'verdict': 'failed_harness', 'original_raw_files_verified': len(review['original_raw_files']),
                      'round_sha256': sha(directory / 'round.json'), 'manifest_sha256': sha(directory / 'MANIFEST.sha256')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--close', action='store_true')
    options = parser.parse_args()
    if options.close:
        close()
    else:
        print(json.dumps(audit()))
