#!/usr/bin/env python3
"""发布 e3 finalize（指令 §2.4，窗口内机械执行，≤ 2 分钟）。

输入：Q1 的 cold_smoke.json（格式与 test_smoke_live.test_release_smoke 的 payload 相同）。
步骤：
1. 逐项核对预登记 PREREG_RELEASE_E3.json 的 q1_cold_smoke：短请求行结构 [512]、usage、finish_reason、SHA 为 e2 参考值；
   长请求行结构 [8257]、usage、finish_reason；长请求 SHA 只报告，不判定。任何一项不符即抛 ValueError，不写任何审批。
2. 写入 e3 参考值文件 expected_reference.json，以及 first_cold_baseline（cold_baseline.json，格式同 cold_smoke.json）。
3. 重生成存档 evidence/source_manifest.json（与 v8 同一规则：排除 __pycache__），再更新发布包的
   DEPLOYMENT_APPROVAL.json（frozen_ops.source_manifest_sha256、first_cold_baseline 与其 SHA、recorded_at），
   重算审批 SHA，并更新 ROOT_FINAL_REVIEW.json 的 approval_sha256。
4. 自检：用本包的 deploy_conditional.require_root_final_review 核对通过。

用法：finalize_e3.py --q1 PATH_TO_cold_smoke.json [--archive DIR] [--package DIR] [--prereg FILE]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

PACKAGE = Path(__file__).resolve().parent
ARCHIVE = Path('/data2/FreeToken/runs/dev_release/release_e3_ops_v1_20261012')
PREREG = Path('/data2/FreeToken/development/release_e3_accounting_20261012/PREREG_RELEASE_E3.json')
REF_DIR_REL = Path('source/development/release_e3_reference_20261012')
E2_SHORT_SHA = 'fd11a31559daaafb889b8a80f29a412470e0635caae631971a0a31e948a9dfdd'
COMMIT = '9db0ee776c25afa8d2719ab700b2de7ccc606142'
APPROVAL_ID = 'RELEASE-E3-20261012-02'
TZ = datetime.timezone(datetime.timedelta(hours=8))


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_writable(path: Path) -> None:
    if path.exists():
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)


def seal(path: Path) -> None:
    os.chmod(path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def validate_q1(payload: dict[str, Any], prereg: dict[str, Any]) -> dict[str, str]:
    """逐项核对 q1_cold_smoke；返回报告用的数值（长请求 SHA 只报告）。任何判定失败抛 ValueError。"""
    spec = prereg['q1_cold_smoke']
    problems: list[str] = []
    results = payload.get('results', {})
    for key in ('short', 'long'):
        if key not in results:
            raise ValueError(f'Q1 结果缺少 {key} 请求')
    short, long_ = results['short'], results['long']
    want_short, want_long = spec['short'], spec['long']
    if short['backend_cache_rows'] != want_short['backend_cache_rows']:
        problems.append(f"短请求行结构 {short['backend_cache_rows']} != {want_short['backend_cache_rows']}")
    if short['usage'] != want_short['usage']:
        problems.append(f"短请求 usage {short['usage']} != {want_short['usage']}")
    if short['finish_reason'] != want_short['finish_reason']:
        problems.append('短请求 finish_reason 不符')
    if short['sha256'] != E2_SHORT_SHA:
        problems.append(f"短请求 SHA {short['sha256']} != e2 参考值 {E2_SHORT_SHA}")
    if long_['backend_cache_rows'] != want_long['backend_cache_rows']:
        problems.append(f"长请求行结构 {long_['backend_cache_rows']} != {want_long['backend_cache_rows']}")
    if long_['usage'] != want_long['usage']:
        problems.append(f"长请求 usage {long_['usage']} != {want_long['usage']}")
    if long_['finish_reason'] != want_long['finish_reason']:
        problems.append('长请求 finish_reason 不符')
    if problems:
        raise ValueError('Q1 核对未通过：' + '；'.join(problems))
    return {'long_sha256_report_only': long_['sha256'],
            'long_e2_sha256_report_only': spec['long']['sha256_report_only']['e2']}


def write_reference(ref_dir: Path, payload: dict[str, Any], q1_sha: str) -> dict[str, str]:
    ref_dir.mkdir(parents=True, exist_ok=True)
    reference = {
        'schema': 'ft_release_e3_expected_reference/v1',
        'purpose': 'Expected outputs for release e3 (measured in the window by Q1, reproduced by the formal smoke).',
        'source_approval': APPROVAL_ID,
        'source_commit': COMMIT,
        'mode': payload['mode'], 'window': payload['window'], 'chunk': payload['chunk'],
        'running': payload['running'], 'graph': payload['graph'],
        'results': payload['results'],
        'source_raw_sha256': {'q1_cold_smoke.json': q1_sha},
    }
    ref_path = ref_dir / 'expected_reference.json'
    cold_path = ref_dir / 'cold_baseline.json'
    for path in (ref_path, cold_path):
        if path.exists():
            raise ValueError(f'{path} 已存在，不覆盖')
    ref_path.write_text(json.dumps(reference, indent=2) + '\n', encoding='utf-8')
    cold_path.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    seal(ref_path)
    seal(cold_path)
    return {'expected_reference': str(ref_path), 'cold_baseline': str(cold_path),
            'cold_baseline_sha256': sha_file(cold_path)}


def regenerate_manifest(archive: Path) -> str:
    """与 v8 同一规则：以 source/ 为根，排除 __pycache__，键为相对路径，值为 SHA256。"""
    source = archive / 'source'
    out: dict[str, str] = {}
    for path in sorted(source.rglob('*')):
        if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts:
            out[path.relative_to(source).as_posix()] = sha_file(path)
    manifest_path = archive / 'evidence' / 'source_manifest.json'
    make_writable(manifest_path)
    manifest_path.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
    seal(manifest_path)
    return sha_file(manifest_path)


def refresh_package(package: Path, archive: Path, cold_path: str, cold_sha: str, manifest_sha: str) -> dict[str, str]:
    approval_path = package / 'DEPLOYMENT_APPROVAL.json'
    review_path = package / 'ROOT_FINAL_REVIEW.json'
    make_writable(approval_path)
    make_writable(review_path)
    approval = json.loads(approval_path.read_text(encoding='utf-8'))
    approval['frozen_ops']['source_manifest_sha256'] = manifest_sha
    approval['first_cold_baseline'] = cold_path
    approval['first_cold_baseline_sha256'] = cold_sha
    approval['recorded_at'] = datetime.datetime.now(TZ).isoformat()
    approval_path.write_text(json.dumps(approval, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
    approval_sha = sha_file(approval_path)
    review = json.loads(review_path.read_text(encoding='utf-8'))
    review['approval_sha256'] = approval_sha
    review_path.write_text(json.dumps(review, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
    seal(approval_path)
    seal(review_path)
    return {'approval_sha256': approval_sha, 'review_sha256': sha_file(review_path)}


def self_check(package: Path) -> None:
    spec = importlib.util.spec_from_file_location('e3_deploy_check', package / 'deploy_conditional.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    approval = json.loads((package / 'DEPLOYMENT_APPROVAL.json').read_text(encoding='utf-8'))
    module.require_root_final_review(approval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='发布 e3 finalize')
    parser.add_argument('--q1', type=Path, required=True)
    parser.add_argument('--archive', type=Path, default=ARCHIVE)
    parser.add_argument('--package', type=Path, default=PACKAGE)
    parser.add_argument('--prereg', type=Path, default=PREREG)
    args = parser.parse_args(argv)
    prereg = json.loads(args.prereg.read_text(encoding='utf-8'))
    payload = json.loads(args.q1.read_text(encoding='utf-8'))
    report = validate_q1(payload, prereg)
    q1_sha = sha_file(args.q1)
    ref = write_reference(args.archive / REF_DIR_REL, payload, q1_sha)
    manifest_sha = regenerate_manifest(args.archive)
    review = refresh_package(args.package, args.archive, ref['cold_baseline'], ref['cold_baseline_sha256'], manifest_sha)
    self_check(args.package)
    out = {'q1_check': 'passed', 'q1_sha256': q1_sha, 'manifest_sha256': manifest_sha, **report, **ref, **review,
           'self_check': 'require_root_final_review passed'}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f'FINALIZE REFUSED: {exc}', file=sys.stderr)
        raise SystemExit(2)
