"""Read-only worktree, rollback parser and source-usage preflight; no service."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

from release_config import MODES, environment, serve_argv
from verify_rollback_usage import verify
from worktree_checks import validate_worktree

HERE = Path(__file__).resolve().parent
HISTORY = Path('/data2/_shared/runs/ft_rounds/_e0/paper_headroom_20261003/serve_final_8192.log')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=False)
    manifest_path = HERE / 'binary_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    before = {mode: subprocess.check_output(['git', '-C', str(MODES[mode][0]),
        'status', '--porcelain', '--untracked-files=all', '--ignored'], text=True)
        for mode in ('release', 'rollback')}
    checks = {mode: validate_worktree(MODES[mode][0], MODES[mode][1], manifest, mode)
              for mode in ('release', 'rollback')}
    usage = verify(*MODES['rollback'][:2])
    argv = serve_argv('rollback')
    ft_argv = argv[argv.index('serve') - 1:] + ['--help']
    env = environment('rollback')
    env['CUDA_VISIBLE_DEVICES'] = ''
    help_result = subprocess.run(ft_argv, cwd=out, env=env, capture_output=True, timeout=60)
    (out / 'ft_serve_help.stdout.txt').write_bytes(help_result.stdout)
    (out / 'ft_serve_help.stderr.txt').write_bytes(help_result.stderr)
    assert help_result.returncode == 0
    adapter = HERE.parent / 'r066b_canary_v2/sdk_adapter.py'
    spec = importlib.util.spec_from_file_location('h2_actual_prefill_parser', adapter)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    history = HISTORY.read_bytes()
    rows = module.cached_rows(history.decode())
    assert rows
    after = {mode: subprocess.check_output(['git', '-C', str(MODES[mode][0]),
        'status', '--porcelain', '--untracked-files=all', '--ignored'], text=True)
        for mode in ('release', 'rollback')}
    assert before == after
    receipt = {'schema': 'ft_release_h2_allowlist_preflight/v1', 'status': 'PASS',
        'read_only_worktrees': True, 'worktrees': checks,
        'binary_manifest_sha256': hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        'git_status_before': before, 'git_status_after': after,
        'rollback_argv': argv, 'exact_ft_argv_help': ft_argv, 'help_exit_code': help_result.returncode,
        'rollback_stream_usage': usage, 'usage_gate': 'retained',
        'history': {'path': str(HISTORY), 'sha256': hashlib.sha256(history).hexdigest(),
            'actual_parser_sha256': hashlib.sha256(adapter.read_bytes()).hexdigest(),
            'prefill_regex_matches': len(rows), 'first_rows': rows[:4],
            'historic_log_is_not_API_usage_evidence': True},
        'GPU_started': False, 'service_started': False, 'endpoint_calls': 0}
    (out / 'h2_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'status': receipt['status'], 'output': str(out),
                      'prefill_rows': len(rows), 'usage_gate': receipt['usage_gate']}))


if __name__ == '__main__':
    main()
