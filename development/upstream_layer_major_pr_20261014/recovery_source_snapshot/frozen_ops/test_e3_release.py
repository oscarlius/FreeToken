"""发布 e3 新增测试（指令 §2.2 第 4 项）：运行配置、owner 校验与参考值比较。"""
import json

import pytest

import release_config as cfg
import test_smoke_live as smoke

E2_ARGV = [
    "taskset",
    "-c",
    "1,3-47",
    "/data2/FreeToken/venv/bin/ft",
    "serve",
    "--model-path",
    "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay",
    "--served-model-name",
    "Qwen3.8-Flash-Next-NVFP4",
    "--host",
    "172.16.108.9",
    "--port",
    "8095",
    "--memory-ratio",
    "0.88",
    "--moe-cache-auto",
    "--moe-prefill-hit-d2d",
    "--ple-backend",
    "pinned",
    "--moe-strategy",
    "offload",
    "--quant-backend",
    "moe.nvfp4=triton",
    "--max-running-requests",
    "2",
    "--cuda-graph-max-bs",
    "2",
    "--kv-reserve-tokens",
    "98304",
    "--max-seq-len-override",
    "98304",
    "--max-prefill-length",
    "4096",
    "--enable-cache-report",
    "--enable-special-token-ckpt",
    "--tool-call-parser",
    "qwen3_coder",
    "--reasoning-parser",
    "qwen3",
    "--prefill-layer-major",
    "--mamba-host-slots",
    "0"
]

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
