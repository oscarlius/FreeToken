"""Publish the CPU/document review snapshot; no model/service/runtime mutation."""
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath

import paramiko

FT = Path(__file__).resolve().parents[1]
REMOTE = '/data2/FreeToken/runs/dev_release/release_e2_review_packet_20261009_v2'


def main():
    spec = importlib.util.spec_from_file_location('existing_ssh_settings', FT.parent / '_shared/ssh_upload.py')
    settings = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settings)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(settings.REMOTE_HOST, username=settings.REMOTE_USER, password=settings.REMOTE_PASS, timeout=20)
    sftp = client.open_sftp()

    def mkdir(path):
        try:
            sftp.stat(path)
        except FileNotFoundError:
            mkdir(str(PurePosixPath(path).parent))
            sftp.mkdir(path)

    def read(path):
        with sftp.open(path, 'rb') as handle:
            return handle.read()

    files = [FT / name for name in (
        'README.md', 'plan/COORDINATION_LOG.md', 'plan/MORNING_SUMMARY_20261009.md',
        'plan/RELEASE_DIRECTIVE_20261009_1340.md', 'plan/RELEASE_DIRECTIVE_20261009_1345.md',
        'plan/data_releases/E2_RELEASE_CANDIDATE_DRAFT_20261009.json',
        'development/RELEASE_PROPOSAL_E2_20261009.md', 'development/DEPLOY_ROLLBACK_E2_DRAFT_20261006.md',
        'development/RELEASE_NOTES_E2_DRAFT_20261006.md',
        'development/release_e2_ops_v2/OPS_CPU_INDEPENDENT_REVIEW_20261009.json',
        'development/release_e2_ops_v2/DOCS_ROOT_CHECK_20261009.json',
        'development/release_e2_ops_v2/ROOT_READONLY_RESOURCE_CHECK_20261009_1348.json',
        'development/r067_d20_short_tail_v1/R067_V2_10SERVICE_14CALL_PLAN.json',
        'development/r067_d20_short_tail_v1/R067_V2_exact_inputs.json',
        'development/r067_d20_short_tail_v1/R067_V2_EXISTING_TOOL_LAUNCH_PACKET.json')]
    for subdir in ('development/release_e2_ops_v2/evidence_v4',
                   'development/release_e2_ops_v2/rollback_preflight_evidence',
                   'development/r045_aiperf_481_cpu_v1', 'development/release_history/pre1340'):
        files.extend(p for p in (FT / subdir).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts)
    blobs = {p.relative_to(FT).as_posix(): p.read_bytes() for p in set(files)}
    manifest = {}

    def save(name, data):
        target = REMOTE + '/' + name
        mkdir(str(PurePosixPath(target).parent))
        with sftp.open(target, 'wx') as handle:
            handle.write(data)
        sftp.chmod(target, 0o444)
        assert read(target) == data
        manifest[name] = hashlib.sha256(data).hexdigest()

    try:
        try:
            sftp.stat(REMOTE)
        except FileNotFoundError:
            mkdir(REMOTE)
        else:
            raise RuntimeError('Review snapshot already exists; never overwrite')
        for name, blob in sorted(blobs.items()):
            save(name, blob)
        server_readme = '/data2/FreeToken/README.md'
        before = read(server_readme)
        save('server_before/FreeToken_README.md', before)
        marker = '\n\n## 2026-10-09 13:40 / 13:45 CPU发布材料修订\n'
        if marker.encode() in before:
            raise RuntimeError('Server README marker exists; do not append twice')
        after = before + (marker +
            '\nOPSv2 CPU39 passed/0 skipped，真实生产冒烟未运行。H2回滚树ignored非空，历史日志无API usage，保持阻断。'
            '部署与推送未批准。当前完整发布/回滚手册、argv及环境diff、独立CPU审查与R045新481+AIPerf CPU计划已只读归档：`' + REMOTE + '`. '
            'R067按13:45获批4格/最多10服务14调用，准备实际启动准入；≤64结论尚未更新。Strata22/345未批准。'
            '\n这是一份CPU/文档审阅快照；R067后续终态以其新封存回执为准。\n').encode()
        with sftp.open(server_readme, 'wb') as handle:
            handle.write(after)
        assert read(server_readme) == after
        save('server_after/FreeToken_README.md', after)
        receipt = {'schema': 'ft_release_ops_CPU_docs_delivery/v2', 'remote': REMOTE,
            'files': manifest, 'readback_equal': True, 'production_service_started': False,
            'GPU_started_by_this_sync': False, 'deployment_approval': False, 'push_approval': False,
            'R067_snapshot_only': True, 'H2': 'blocked_dirty_rollback_worktree_and_historical_API_usage_gap'}
        receipt_bytes = (json.dumps(receipt, ensure_ascii=False, indent=2) + '\n').encode()
        save('DELIVERY_RECEIPT.json', receipt_bytes)
        (FT / 'development/RELEASE_CPU_DELIVERY_RECEIPT_20261009_v2.json').write_bytes(receipt_bytes)
        print(json.dumps({'remote': REMOTE, 'files': len(manifest), 'readback_equal': True,
            'production_service_started': False, 'GPU_started_by_this_sync': False}))
    finally:
        sftp.close()
        client.close()


if __name__ == '__main__':
    main()
