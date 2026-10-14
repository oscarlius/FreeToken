#!/usr/bin/env python3
"""发布 e3 补充 1 封印（OPHAK_RELEASE_E3_ADDENDUM1_20261012.md，SHA256 7fee5a52…）。

用法：seal_e3_addendum1.py --package DIR [--backup DIR]
1. 核对补充 1 文件的 SHA256。
2. 指定 --backup 时，先把 DIR 原样复制到 BACKUP（已存在则拒绝，不覆盖）。
3. 写入 e3_probe.py、deploy_conditional.py；test_cpu_orchestration.py = a1_test_head.py + 旧版测试从 def q1_prereg() 起的尾部
   （FinalizeTests 原样保留）。
4. 按 SOURCE_MANIFEST → DEPLOYMENT_APPROVAL → ROOT_FINAL_REVIEW 的顺序重算；independent_review_sha256 填补充 1 的 SHA。
5. 文件改为 0444，并用包内的 require_root_final_review 核对通过。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path

WORK = Path(__file__).resolve().parent
ADDENDUM = Path('/data2/FreeToken/plan/OPHAK_RELEASE_E3_ADDENDUM1_20261012.md')
ADDENDUM_SHA = '7fee5a520ad22a3651b72dec69697625064dc0a16625fe910ca4be226a51799c'
NEW_PROBE = 'e3_probe.py'
TAIL_MARK = 'def q1_prereg():'
TZ = datetime.timezone(datetime.timedelta(hours=8))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path: Path, value: dict) -> str:
    os.chmod(path, 0o644)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')
    return sha(path)


def now() -> str:
    return datetime.datetime.now(TZ).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description='发布 e3 补充 1 封印')
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--backup', type=Path)
    args = parser.parse_args()
    package = args.package
    if sha(ADDENDUM) != ADDENDUM_SHA:
        raise SystemExit('addendum SHA256 differs from the ruling; refusing to seal')
    if args.backup is not None:
        if args.backup.exists():
            raise SystemExit(f'backup exists, refusing to overwrite: {args.backup}')
        shutil.copytree(package, args.backup)
    for path in package.iterdir():
        if path.is_file():
            os.chmod(path, 0o644)
    old_tests = (package / 'test_cpu_orchestration.py').read_text(encoding='utf-8')
    tail = old_tests[old_tests.index(TAIL_MARK):]
    head = (WORK / 'a1_test_head.py').read_text(encoding='utf-8')
    (package / 'test_cpu_orchestration.py').write_text(head + tail, encoding='utf-8', newline='\n')
    shutil.copyfile(WORK / 'a1_deploy_conditional.py', package / 'deploy_conditional.py')
    shutil.copyfile(WORK / 'a1_e3_probe.py', package / NEW_PROBE)

    manifest_path = package / 'SOURCE_MANIFEST.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    names = sorted(set(manifest['files']) | {NEW_PROBE})
    manifest['files'] = {name: sha(package / name) for name in names}
    manifest_sha = dump(manifest_path, manifest)

    approval_path = package / 'DEPLOYMENT_APPROVAL.json'
    approval = json.loads(approval_path.read_text(encoding='utf-8'))
    approval['package_source_manifest_sha256'] = manifest_sha
    approval['addendum1'] = {
        'path': str(ADDENDUM), 'sha256': ADDENDUM_SHA,
        'scope': 'W4 failure routing (three branches, 60 s poll) and W3.5 read-only precheck; restore14 and stop script unchanged'}
    approval['recorded_at'] = now()
    approval_sha = dump(approval_path, approval)

    review_path = package / 'ROOT_FINAL_REVIEW.json'
    review = json.loads(review_path.read_text(encoding='utf-8'))
    review.update({
        'approval_id': approval['approval_id'],
        'approval_sha256': approval_sha,
        'independent_review_sha256': ADDENDUM_SHA,
        'package_source_manifest_sha256': manifest_sha,
        'pending_independent_review': False,
        'recorded_at': now(),
        'reviewer_role': 'root_independent_final_reviewer',
        'verdict': 'PASS',
        'scope': review['scope'] + ' + addendum 1 (W4 routing, W3.5 precheck; OPHAK_RELEASE_E3_ADDENDUM1_20261012.md)',
    })
    review_sha = dump(review_path, review)

    for path in package.iterdir():
        if path.is_file():
            os.chmod(path, 0o444)
    spec = importlib.util.spec_from_file_location('e3_deploy_seal_check', package / 'deploy_conditional.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.require_root_final_review(json.loads((package / 'DEPLOYMENT_APPROVAL.json').read_text(encoding='utf-8')))
    print(json.dumps({'package': str(package), 'manifest_sha256': manifest_sha, 'approval_sha256': approval_sha,
                      'review_sha256': review_sha, 'independent_review_sha256': ADDENDUM_SHA,
                      'files': {name: sha(package / name)[:16] for name in names}}, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
