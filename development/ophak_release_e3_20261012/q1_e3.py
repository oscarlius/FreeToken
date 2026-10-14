#!/usr/bin/env python3
"""发布 e3 Q1 工装（指令 §2.5）：起一个全新的 e3 服务，跑两条冷冒烟请求，关服，写 cold_smoke.json。

- argv 取自新存档的 release_config.serve_argv('release')，只替换 --host/--port（127.0.0.1:8123）。
- 构建门：同一解释器、同一 PYTHONPATH 导入 freetoken.scheduler.prefill，实际路径必须在 wt/release-e3/python 之下。
- 参数门：Parsed arguments 中 prefill_anchor_cut_min_tokens 必须为 32768。
- 冒烟：不发 warmup，先 short 后 long。断言与 test_smoke_live.test_release_smoke 使用同一套函数。
- real：沿用 task_b_runner 的 oh_window 锁、出生身份与清场（调用与 RealLauncher 相同）。
- stub：stub_e3_server.py 代替 ft serve，不取锁，不碰 8095。只用于演练，结果不是测量。

用法：q1_e3.py --run-dir DIR --mode real|stub [--short-variant A|B] [--long-segments 8257] [--drop-anchor-flag] [--pythonpath ROOT]
DIR 必须不存在。拒绝或失败时不写 cold_smoke.json；退出码见 EXIT_CODES。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

WORK = Path(__file__).resolve().parent
ARCHIVE = Path('/data2/FreeToken/runs/dev_release/release_e3_ops_v1_20261012')
SOURCE = ARCHIVE / 'source' / 'development'
INPUTS = SOURCE / 'r065_d16_discriminate_v1' / 'inputs.json'
TASK_B = Path('/data2/FreeToken/development/ophak_task_b_20261011')
RELEASE_E3_ROOT = '/data2/FreeToken/wt/release-e3/python'
Q1_HOST = '127.0.0.1'
Q1_PORT = 8123
Q1_BASE = f'http://{Q1_HOST}:{Q1_PORT}'
OWNER_NAME = 'OPHAK-RELEASE-E3-Q1'
EXPECTED_MIN_TOKENS = 32768
WINDOW = 98304
CHUNK = 4096
EXIT_CODES = {'passed': 0, 'build_gate_refused': 2, 'param_gate_refused': 3, 'launch_failed': 4,
              'smoke_invalid': 5, 'request_failed': 6, 'cleanup_blocked': 7}


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_modules() -> SimpleNamespace:
    """全部沿用冻结存档与 task_b_runner，本文件不重写任何断言。"""
    return SimpleNamespace(
        tb=load_module('q1_task_b_runner', TASK_B / 'task_b_runner.py'),
        rc=load_module('q1_release_config', SOURCE / 'release_e2_ops_v2' / 'release_config.py'),
        smoke=load_module('q1_test_smoke_live', SOURCE / 'release_e2_ops_v2' / 'test_smoke_live.py'),
        r066=load_module('q1_r066', SOURCE / 'r066_d16_discriminate_v2' / 'sdk_adapter.py'),
        cache=load_module('q1_r066b', SOURCE / 'r066b_canary_v2' / 'sdk_adapter.py'),
    )


def build_argv(rc: Any, drop_anchor_flag: bool) -> tuple[list[str], list[str]]:
    """e3 的 argv，只替换 host/port；drop_anchor_flag 仅供演练 (c) 使用。返回 (Q1 argv, 冻结的生产 argv)。"""
    production = list(rc.serve_argv('release'))
    argv = list(production)
    argv[argv.index('--host') + 1] = Q1_HOST
    argv[argv.index('--port') + 1] = str(Q1_PORT)
    if drop_anchor_flag:
        at = argv.index('--prefill-anchor-cut-min-tokens')
        del argv[at:at + 2]
    return argv, production


def build_env(rc: Any, pythonpath: str, mode: str) -> dict[str, str]:
    env = rc.environment('release')
    env['PYTHONPATH'] = pythonpath
    if mode == 'stub':
        env['CUDA_VISIBLE_DEVICES'] = ''
    return env


def check_build(tb: Any, env: dict[str, str], out_dir: Path) -> dict[str, Any]:
    """构建门（任务 B §3 第 1 条，构建根目录为 release-e3）：导入路径必须落在 wt/release-e3 之下。结果总是写出。"""
    try:
        probe = subprocess.run([tb.FT_PYTHON, '-B', '-c', tb.PROBE_CODE], env=env, capture_output=True,
                               text=True, timeout=300)
        lines = probe.stdout.strip().splitlines()
        imported, returncode, error = (lines[-1] if lines else ''), probe.returncode, probe.stderr[-400:]
    except (OSError, subprocess.SubprocessError) as exc:
        imported, returncode, error = '', None, repr(exc)
    ok = returncode == 0 and imported.startswith(RELEASE_E3_ROOT + '/')
    record = {'build': 'release-e3', 'expected_root': RELEASE_E3_ROOT, 'pythonpath': env.get('PYTHONPATH'),
              'imported': imported, 'returncode': returncode, 'stderr_tail': error, 'ok': ok}
    tb.write_new(out_dir / 'build_gate.json', record)
    if not ok:
        raise tb.BuildGateError(f'构建门不通过：导入 {imported!r}，期望在 {RELEASE_E3_ROOT}/ 之下，返回码 {returncode}')
    return record


def check_params(tb: Any, serve_log: Path, out_dir: Path) -> int | None:
    """参数门（任务 B §3 第 2 条，期望值为 e3 的 32768）：结果总是写出。"""
    try:
        actual = tb.parsed_min_tokens(serve_log)
    except tb.ParamGateError as exc:
        tb.write_new(out_dir / 'param_gate.json', {'expected': EXPECTED_MIN_TOKENS, 'actual': None,
                                                   'error': str(exc), 'ok': False})
        raise
    ok = actual == EXPECTED_MIN_TOKENS
    tb.write_new(out_dir / 'param_gate.json', {'expected': EXPECTED_MIN_TOKENS, 'actual': actual, 'ok': ok})
    if not ok:
        raise tb.ParamGateError(f'参数门不通过：期望 {EXPECTED_MIN_TOKENS}，serve.log 实际 {actual}')
    return actual


def terminate_group(proc: subprocess.Popen) -> bool:
    """只关我方进程组：先 TERM，超时再 KILL。返回是否已退出。"""
    for sig, wait_s in ((signal.SIGTERM, 20), (signal.SIGKILL, 10)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return True
        try:
            proc.wait(timeout=wait_s)
            return True
        except subprocess.TimeoutExpired:
            continue
    return False


class StubLauncher:
    """演练用：stub_e3_server.py 代替 ft serve。不取 GPU 锁，不碰 8095。"""

    def __init__(self, tb: Any, short_variant: str, long_segments: str) -> None:
        self.tb = tb
        self.short_variant, self.long_segments = short_variant, long_segments

    def start(self, argv: list[str], env: dict[str, str], out_dir: Path) -> Any:
        serve_log = out_dir / 'serve.log'
        log_handle = serve_log.open('xb')
        command = [sys.executable, '-B', str(WORK / 'stub_e3_server.py'), '--port', str(Q1_PORT),
                   '--argv-json', json.dumps(argv), '--inputs', str(INPUTS),
                   '--short-variant', self.short_variant, '--long-segments', self.long_segments]
        try:
            proc = subprocess.Popen(command, cwd=str(out_dir), env=env, stdout=log_handle,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as exc:
            log_handle.close()
            raise self.tb.LaunchError(f'stub spawn failed: {exc!r}') from exc
        ready = self.tb.wait_ready(Q1_BASE, timeout_s=self.tb.READY_TIMEOUT_S, proc=proc)
        return self.tb.Handle(OWNER_NAME, 'release', Q1_BASE, serve_log, out_dir, proc=proc, ready=ready,
                              log_handle=log_handle)

    def stop(self, handle: Any) -> bool:
        exited = handle.proc.poll() is not None or terminate_group(handle.proc)
        handle.log_handle.close()
        return exited


class RealLauncher:
    """真实 e3 服务：与 task_b_runner.RealLauncher 相同的 oh_window 锁、出生身份与清场，只换 argv 与构建根目录。"""

    def __init__(self, tb: Any) -> None:
        self.tb = tb
        self.oh = load_module('q1_oh_window', tb.OH_WINDOW_PATH)
        self.d07 = self.oh.load_d07()

    def start(self, argv: list[str], env: dict[str, str], out_dir: Path) -> Any:
        try:
            self.oh.idle(self.d07, [(Q1_HOST, Q1_PORT)])  # 启动前空闲检查；不空闲则抛出，且尚未占锁
        except Exception as exc:  # noqa: BLE001 - 任何非空闲状态都是启动前失败
            raise self.tb.LaunchError(f'启动前检查不通过：{exc!r}') from exc
        owner = self.d07.take_d07_gpu_lock(OWNER_NAME, 0)
        serve_log = out_dir / 'serve.log'
        log_handle = None
        try:
            log_handle = serve_log.open('xb')
            proc = subprocess.Popen(argv, cwd=str(out_dir), env=env, stdout=log_handle,
                                    stderr=subprocess.STDOUT, start_new_session=True)
        except Exception as exc:  # noqa: BLE001 - 任何启动前失败都先释放 GPU 锁
            if log_handle is not None:
                log_handle.close()
            self.d07.release_d07_gpu_lock(owner)
            raise self.tb.LaunchError(f'spawn failed: {exc!r}') from exc
        try:
            birth = self.oh.capture_birth(proc, self.d07)
        except Exception as exc:  # noqa: BLE001 - 取不到身份：只关本次子进程、释放锁
            self.abort(proc, log_handle, owner)
            raise self.tb.LaunchError(f'capture_birth failed: {exc!r}') from exc
        ready = self.tb.wait_ready(Q1_BASE, timeout_s=self.tb.READY_TIMEOUT_S, proc=proc)
        return self.tb.Handle(OWNER_NAME, 'release', Q1_BASE, serve_log, out_dir, proc=proc, ready=ready,
                              birth=birth, owner=owner, log_handle=log_handle)

    def abort(self, proc: subprocess.Popen, log_handle: Any, owner: Any) -> None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
        if log_handle is not None:
            log_handle.close()
        self.d07.release_d07_gpu_lock(owner)

    def stop(self, handle: Any) -> bool:
        ok = self.oh.cleanup(handle.proc, handle.birth, self.d07, handle.out_dir, [(Q1_HOST, Q1_PORT)])
        handle.log_handle.close()
        if ok:
            self.d07.release_d07_gpu_lock(handle.owner)
        return ok


def cold_smoke(mods: SimpleNamespace, run_dir: Path, serve_log: Path) -> dict[str, Any]:
    """与 test_smoke_live.test_release_smoke 相同的断言（同一套函数）。Q1 不是生产服务，因此不做 owner 与身份校验。"""
    smoke, cache, r066 = mods.smoke, mods.cache, mods.r066
    if cache.cached_rows(serve_log.read_text(encoding='utf-8')):
        raise smoke.SmokeInvalid('Prior prefill: the fresh service is not cold')
    offset = serve_log.stat().st_size
    with httpx.Client(trust_env=False, timeout=10) as client:
        response = client.get(Q1_BASE + '/health')
        smoke.validate_health(response.status_code, response.json())
    results: dict[str, Any] = {}
    for key in ('short', 'long'):
        item = r066.inputs()[key]
        with serve_log.open('rb') as handle:
            handle.seek(offset)
            gap = handle.read()
        if cache.cached_rows(gap.decode('utf-8', errors='strict')):
            raise smoke.SmokeInvalid('External prefill between smoke requests')
        offset += len(gap)
        record = r066.collect_one(Q1_BASE, mods.rc.MODEL, key, item, run_dir)
        with serve_log.open('rb') as handle:
            handle.seek(offset)
            window = handle.read()
        (run_dir / f'{key}.serve-window.txt').write_bytes(window)
        rows = cache.cached_rows(window.decode('utf-8', errors='strict'))
        smoke.validate_cold_rows(rows, item['prompt_tokens'], CHUNK)
        assert record['cached_tokens_observation']['value'] in (None, 0)
        results[key] = {'sha256': smoke.valid_projection(record, item['prompt_tokens']),
                        'usage': record['projection']['usage'],
                        'finish_reason': record['projection']['finish_reason'],
                        'api_cached_tokens': record['cached_tokens_observation']['value'],
                        'backend_cache_rows': rows, 'service_log_start_byte': offset}
        offset += len(window)
    return results


def build_payload(mode: str, results: dict[str, Any], argv: list[str]) -> dict[str, Any]:
    return {'schema': 'ft_release_cold_smoke/v1', 'results': results, 'mode': 'release', 'window': WINDOW,
            'chunk': CHUNK, 'running': 2, 'graph': 2, 'q1_mode': mode, 'q1_endpoint': Q1_BASE,
            'actual_supervisor_argv': argv, 'owner_sha256': None, 'exclusive_maintenance_approval': None,
            'historical_private_graph4_SHA_not_used_as_gate': True}


def finish(mods: SimpleNamespace, run_dir: Path, mode: str, classification: str, detail: Any) -> dict[str, Any]:
    result = {'schema': 'ft_q1_e3_result/v1', 'mode': mode, 'classification': classification,
              'exit_code': EXIT_CODES[classification], 'detail': detail, 'at': mods.tb.server_now()}
    mods.tb.write_new(run_dir / 'q1_result.json', result)
    return result


def run_q1(run_dir: Path, mode: str, *, short_variant: str = 'A', long_segments: str = '8257',
           drop_anchor_flag: bool = False, pythonpath: str = RELEASE_E3_ROOT) -> dict[str, Any]:
    if mode not in ('real', 'stub'):
        raise ValueError(f'未知模式：{mode}')
    run_dir.mkdir(parents=True, exist_ok=False)
    mods = load_modules()
    tb = mods.tb
    argv, production = build_argv(mods.rc, drop_anchor_flag)
    env = build_env(mods.rc, pythonpath, mode)
    tb.write_new(run_dir / 'q1_argv.json', {'mode': mode, 'argv': argv, 'production_argv': production,
                                            'pythonpath': env['PYTHONPATH'], 'drop_anchor_flag': drop_anchor_flag,
                                            'at': tb.server_now()})
    try:
        check_build(tb, env, run_dir)
    except tb.BuildGateError as exc:
        return finish(mods, run_dir, mode, 'build_gate_refused', str(exc))
    launcher = RealLauncher(tb) if mode == 'real' else StubLauncher(tb, short_variant, long_segments)
    handle, results = None, None
    classification, detail = 'request_failed', None
    try:
        handle = launcher.start(argv, env, run_dir)
        if not handle.ready:
            classification, detail = 'launch_failed', tb.startup_status(handle.serve_log)
        else:
            check_params(tb, handle.serve_log, run_dir)
            results = cold_smoke(mods, run_dir, handle.serve_log)
            classification = 'passed'
    except tb.ParamGateError as exc:
        classification, detail = 'param_gate_refused', str(exc)
    except tb.LaunchError as exc:
        classification, detail = 'launch_failed', str(exc)
    except mods.smoke.SmokeInvalid as exc:
        classification, detail = 'smoke_invalid', str(exc)
    except Exception as exc:  # noqa: BLE001 - 请求或断言失败：记录后停止，不写 cold_smoke.json
        classification, detail = 'request_failed', repr(exc)
    finally:
        if handle is not None:
            cleaned, cleanup_error = tb.safe_stop(launcher, handle)
            if not cleaned:
                classification, detail = 'cleanup_blocked', cleanup_error or '清场返回失败'
    if classification == 'passed':
        tb.write_new(run_dir / 'cold_smoke.json', build_payload(mode, results, argv))
    return finish(mods, run_dir, mode, classification, detail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='发布 e3 Q1 工装')
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--mode', choices=['real', 'stub'], required=True)
    parser.add_argument('--short-variant', choices=['A', 'B'], default='A')
    parser.add_argument('--long-segments', default='8257')
    parser.add_argument('--drop-anchor-flag', action='store_true')
    parser.add_argument('--pythonpath', default=RELEASE_E3_ROOT)
    args = parser.parse_args(argv)
    result = run_q1(args.run_dir, args.mode, short_variant=args.short_variant, long_segments=args.long_segments,
                    drop_anchor_flag=args.drop_anchor_flag, pythonpath=args.pythonpath)
    print(json.dumps({'classification': result['classification'], 'detail': result['detail']},
                     ensure_ascii=False, indent=1))
    return result['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
