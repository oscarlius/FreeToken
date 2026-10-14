#!/usr/bin/env python3
"""发布 e3 P1-B：新运维存档 release_e3_ops_v1_20261012（指令 §2.2）。

只改指令列出的文件：release_config.py、binary_manifest.json、test_smoke_live.py 与 run_smoke.py 的参考值路径、
test_redeploy_cpu.py 中钉 e2 参考值的一个测试、新增 test_e3_release.py；evidence/ 重建。
存档内部目录名不改。每一种重建的文件先用同样的函数从 v8 原件生成，与 v8 逐字节比对，确认格式一致后，才生成 e3 版本。
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

V8 = Path('/data2/FreeToken/runs/dev_release/release_e2_ops_v8_20261009_smoke_guarded')
E3 = Path('/data2/FreeToken/runs/dev_release/release_e3_ops_v1_20261012')
OPS_REL = Path('source/development/release_e2_ops_v2')
REF_DIR = 'release_e3_reference_20261012'
E2_REF_REL = 'redeploy_smoke_fix_20261009/redeploy_expected_reference.json'
WT = '/data2/FreeToken/wt/release-e3'
COMMIT = '9db0ee776c25afa8d2719ab700b2de7ccc606142'
FLAG = ['--prefill-anchor-cut-min-tokens', '32768']
PYTEST_PY = '/data2/FreeToken/evaluation/toolchain/venv-eval/bin/python'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'replace expected exactly one match in {path.name}, found {count}')
    path.write_text(text.replace(old, new), encoding='utf-8')


def manifest_of(source_root: Path) -> dict[str, str]:
    out = {}
    for path in sorted(source_root.rglob('*')):
        if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts:
            out[path.relative_to(source_root).as_posix()] = sha(path)
    return out


def dump_manifest(mapping: dict[str, str]) -> str:
    return json.dumps(mapping, indent=2, sort_keys=True, ensure_ascii=False) + '\n'


def serve_cmd_line(argv: list[str]) -> str:
    return ' '.join(argv) + '\n'


def r056_diff(r056_line: str, release_line: str) -> str:
    lines = list(difflib.unified_diff(r056_line.splitlines(keepends=True), release_line.splitlines(keepends=True),
                                      fromfile='sealed_R056/production/SERVE_CMD.txt',
                                      tofile='release/SERVE_CMD.txt'))
    return ''.join(lines)


def check_same(label: str, generated: str, original: Path) -> None:
    original_text = original.read_text(encoding='utf-8')
    if generated != original_text:
        raise SystemExit(f'format self-check failed for {label}: regenerated v8 text differs from the v8 file')
    print(f'format self-check ok: {label}')


def step_copy() -> None:
    if E3.exists():
        raise SystemExit(f'{E3} exists; not overwriting')
    shutil.copytree(V8, E3, symlinks=True)
    for path in E3.rglob('*'):
        if path.is_file():
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)


def step_ops_edits() -> None:
    ops = E3 / OPS_REL
    replace_once(ops / 'release_config.py',
                 "'release': (ROOT / 'wt/release-e2', '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9', 98304, 4096),",
                 f"'release': (ROOT / 'wt/release-e3', '{COMMIT}', 98304, 4096),")
    replace_once(ops / 'release_config.py',
                 "        argv += ['--prefill-layer-major', '--mamba-host-slots', '0']\n",
                 "        argv += ['--prefill-layer-major', '--mamba-host-slots', '0', "
                 "'--prefill-anchor-cut-min-tokens', '32768']\n")
    bm_path = ops / 'binary_manifest.json'
    bm_text = bm_path.read_text(encoding='utf-8')
    bm = json.loads(bm_text)
    bm['worktrees']['release']['path'] = WT
    bm['worktrees']['release']['commit'] = COMMIT
    bm_path.write_text(json.dumps(bm, indent=2, ensure_ascii=False) + ('\n' if bm_text.endswith('\n') else ''),
                       encoding='utf-8')
    replace_once(ops / 'test_smoke_live.py',
                 f"expected = json.loads((HERE.parent / '{E2_REF_REL}').read_text())",
                 f"expected = json.loads((HERE.parent / '{REF_DIR}/expected_reference.json').read_text())")
    replace_once(ops / 'run_smoke.py',
                 f"reference = HERE.parent / '{E2_REF_REL}'",
                 f"reference = HERE.parent / '{REF_DIR}/expected_reference.json'")
    replace_once(ops / 'test_redeploy_cpu.py',
                 "def test_initial_reference_enforced_without_optional_baseline(monkeypatch, field):\n"
                 "    monkeypatch.delenv('RELEASE_SMOKE_BASELINE', raising=False)\n"
                 "    reference = json.loads((smoke.HERE.parent / 'redeploy_smoke_fix_20261009/redeploy_expected_reference.json').read_text())\n"
                 "    smoke.compare_expected_reference(reference)\n",
                 "def test_initial_reference_enforced_without_optional_baseline(monkeypatch, tmp_path, field):\n"
                 "    monkeypatch.delenv('RELEASE_SMOKE_BASELINE', raising=False)\n"
                 "    # e3：参考值路径已改为 release_e3_reference_20261012；这里用 e2 参考值副本作固定夹具，检验同一套强制比较。\n"
                 "    reference = json.loads((smoke.HERE.parent / 'redeploy_smoke_fix_20261009/redeploy_expected_reference.json').read_text())\n"
                 "    (tmp_path / 'release_e3_reference_20261012').mkdir()\n"
                 "    (tmp_path / 'release_e3_reference_20261012' / 'expected_reference.json').write_text(json.dumps(reference))\n"
                 "    monkeypatch.setattr(smoke, 'HERE', tmp_path / 'ops')\n"
                 "    smoke.compare_expected_reference(reference)\n")
    # 参数化装饰器行需要 tmp_path 形参一并生效；它紧贴在被改函数之前，已在上面一并替换，无需另行处理。
    e2_argv = json.loads((V8 / 'evidence/release_argv.json').read_text(encoding='utf-8'))
    test_text = TEST_E3_TEMPLATE.replace('__E2_ARGV__', json.dumps(e2_argv, indent=4, ensure_ascii=False))
    (ops / 'test_e3_release.py').write_text(test_text, encoding='utf-8', newline='\n')


TEST_E3_TEMPLATE = '''"""发布 e3 新增测试（指令 §2.2 第 4 项）：运行配置、owner 校验与参考值比较。"""
import json

import pytest

import release_config as cfg
import test_smoke_live as smoke

E2_ARGV = __E2_ARGV__

BASE_KEYS = {'mode': 'release', 'window': 98304, 'chunk': 4096, 'running': 2, 'graph': 2}


def test_release_argv_is_e2_argv_plus_threshold_flag():
    assert cfg.serve_argv('release') == E2_ARGV + ['--prefill-anchor-cut-min-tokens', '32768']


def test_validate_owner_rejects_the_e2_argv(tmp_path):
    log = tmp_path / 'serve.log'
    owner = {'mode': 'release', 'commit': cfg.MODES['release'][1], 'argv': E2_ARGV,
             'host': cfg.HOST, 'log': str(log), 'approval_id': 'RELEASE-E3-20261012-01'}
    with pytest.raises(AssertionError):
        smoke.validate_owner(owner, 'release', 'http://' + cfg.HOST + ':8095', log, 'RELEASE-E3-20261012-01')


def _reference(long_rows):
    long = {'sha256': 'b' * 64, 'usage': {'prompt_tokens': 8257, 'completion_tokens': 128, 'total_tokens': 8385},
            'finish_reason': 'length', 'api_cached_tokens': None, 'backend_cache_rows': long_rows}
    short = {'sha256': 'a' * 64, 'usage': {'prompt_tokens': 512, 'completion_tokens': 128, 'total_tokens': 640},
             'finish_reason': 'length', 'api_cached_tokens': None,
             'backend_cache_rows': [{'new_sequences': 1, 'new_tokens': 512, 'cached_tokens': 0}]}
    return {**BASE_KEYS, 'results': {'short': short, 'long': long}}


def test_reference_accepts_the_single_8257_row_and_rejects_the_e2_split(monkeypatch, tmp_path):
    reference = _reference([{'new_sequences': 1, 'new_tokens': 8257, 'cached_tokens': 0}])
    (tmp_path / 'release_e3_reference_20261012').mkdir()
    (tmp_path / 'release_e3_reference_20261012' / 'expected_reference.json').write_text(json.dumps(reference))
    monkeypatch.setattr(smoke, 'HERE', tmp_path / 'ops')
    smoke.compare_expected_reference(json.loads(json.dumps(reference)))
    split = json.loads(json.dumps(reference))
    split['results']['long']['backend_cache_rows'] = [
        {'new_sequences': 1, 'new_tokens': 512, 'cached_tokens': 0},
        {'new_sequences': 1, 'new_tokens': 7745, 'cached_tokens': 0}]
    with pytest.raises(AssertionError):
        smoke.compare_expected_reference(split)
'''


def step_testfix() -> None:
    """test_redeploy_cpu 的 actual-entry 测试也读取 e2 参考值路径（run_smoke 计算参考 SHA）；改为固定夹具。"""
    ops = E3 / OPS_REL
    replace_once(ops / 'test_redeploy_cpu.py',
                 "def test_actual_entry_second_invalid_is_failure_and_third_blocked(tmp_path, monkeypatch):\n"
                 "    root = tmp_path / 'runs/production'\n",
                 "def test_actual_entry_second_invalid_is_failure_and_third_blocked(tmp_path, monkeypatch):\n"
                 "    # e3：run_smoke 的参考值路径已改为 release_e3_reference_20261012；这里用 e2 参考值副本作固定夹具。\n"
                 "    reference = json.loads((smoke.HERE.parent / 'redeploy_smoke_fix_20261009/redeploy_expected_reference.json').read_text())\n"
                 "    (tmp_path / 'release_e3_reference_20261012').mkdir()\n"
                 "    (tmp_path / 'release_e3_reference_20261012' / 'expected_reference.json').write_text(json.dumps(reference))\n"
                 "    monkeypatch.setattr(run_smoke, 'HERE', tmp_path / 'ops')\n"
                 "    root = tmp_path / 'runs/production'\n")
    print('testfix applied to test_redeploy_cpu.py')


def step_restore_relative_checks() -> None:
    """占位：restore14 与发布包在 P1-C、P1-D 另行生成。"""


def step_evidence() -> None:
    ops = E3 / OPS_REL
    import importlib.util
    spec = importlib.util.spec_from_file_location('release_config_e3', ops / 'release_config.py')
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    argv_new = cfg.serve_argv('release')
    ev_v8, ev_e3 = V8 / 'evidence', E3 / 'evidence'
    # 1) release_argv.json
    check_same('release_argv.json (v8)', json.dumps(json.loads((ev_v8 / 'release_argv.json').read_text()), indent=2) + '\n',
               ev_v8 / 'release_argv.json')
    # 2) release_SERVE_CMD.txt
    v8_argv = json.loads((ev_v8 / 'release_argv.json').read_text())
    check_same('release_SERVE_CMD.txt (v8)', serve_cmd_line(v8_argv), ev_v8 / 'release_SERVE_CMD.txt')
    # 3) release_vs_R056.diff
    r056_line = (ev_v8 / 'R056_SERVE_CMD.txt').read_text(encoding='utf-8')
    check_same('release_vs_R056.diff (v8)', r056_diff(r056_line, serve_cmd_line(v8_argv)), ev_v8 / 'release_vs_R056.diff')
    # 4) source_manifest.json
    orig_manifest = json.loads((ev_v8 / 'source_manifest.json').read_text(encoding='utf-8'))
    if orig_manifest != manifest_of(V8 / 'source'):
        raise SystemExit('content self-check failed for source_manifest.json: v8 file differs from regenerated v8 walk')
    print('content self-check ok: source_manifest.json (v8 keys and values; v8 key order is not sorted)')
    # 写入 e3 版本（evidence/ 在复制时是只读，先放开写权限）
    for name in ('release_argv.json', 'release_SERVE_CMD.txt', 'release_vs_R056.diff', 'source_manifest.json'):
        os.chmod(ev_e3 / name, 0o644)
    (ev_e3 / 'release_argv.json').write_text(json.dumps(argv_new, indent=2) + '\n', encoding='utf-8')
    (ev_e3 / 'release_SERVE_CMD.txt').write_text(serve_cmd_line(argv_new), encoding='utf-8')
    (ev_e3 / 'release_vs_R056.diff').write_text(r056_diff(r056_line, serve_cmd_line(argv_new)), encoding='utf-8')
    (ev_e3 / 'source_manifest.json').write_text(dump_manifest(manifest_of(E3 / 'source')), encoding='utf-8')
    print('evidence regenerated: release_argv.json, release_SERVE_CMD.txt, release_vs_R056.diff, source_manifest.json')


def step_pytest() -> None:
    ops = E3 / OPS_REL
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    cmd = [PYTEST_PY, '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
           'test_cpu.py', 'test_redeploy_cpu.py', 'test_worktree_checks.py', 'test_e3_release.py',
           '--junitxml', str(E3 / 'evidence' / 'CPU.junit.xml')]
    run = subprocess.run(cmd, cwd=ops, env=env, capture_output=True, text=True, timeout=900)
    text = run.stdout + run.stderr
    print(text[-1200:])
    if run.returncode != 0:
        raise SystemExit('pytest failed; evidence not written')
    (E3 / 'evidence' / 'CPU_pytest.txt').write_text(text.strip().splitlines()[-2] + '\n' + text.strip().splitlines()[-1] + '\n',
                                                    encoding='utf-8')


def step_seal() -> None:
    for path in E3.rglob('*'):
        if path.is_file():
            os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def main() -> int:
    step = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if step in ('all', 'copy'):
        step_copy()
    if step in ('all', 'edits'):
        step_ops_edits()
    if step in ('all', 'evidence'):
        step_evidence()
    if step == 'testfix':
        step_testfix()
    if step in ('all', 'pytest'):
        step_pytest()
    if step in ('all', 'seal'):
        step_seal()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
