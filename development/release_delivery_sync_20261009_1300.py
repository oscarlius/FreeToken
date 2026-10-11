"""Archive reviewable release documentation and update only the FT root README."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex

import paramiko

FT = Path(__file__).resolve().parents[1]
DEV = FT / 'development'
TARGET = '/data2/FreeToken/runs/dev_release/release_e2_review_packet_20261009_v1'


def main():
    review = {'schema': 'ft_release_cpu_preparation_root_review/v1', 'author': '/root',
        'directive': 'User 2026-10-09 13:00', 'branch_created': True,
        'candidate': '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9',
        'independent_ops_reviewer': '/root/d20_short_tail_cpu',
        'independent_ops_verdict': 'PASS_with_deployment_only_validation_gaps',
        'CPU_local_passed': 20, 'CPU_Linux_passed': 20, 'live_smoke_skipped': 1,
        'final_operations_archive': '/data2/FreeToken/runs/dev_release/release_e2_ops_v3_20261009',
        'production_smoke_executed': False, 'deployment_approved': False, 'push_approved': False,
        'production_activated': False, 'R045': 'pre-reservation dependency block, zero services/calls',
        'R045_independent_metadata_reviewer': '/root/paper_v51_evidence_review',
        'R045_independent_disposition': 'full_gate_blocked; fail-closed enforcement PASS; source/FD PASS retained',
        'D20': 'isolated CPU patch and eight-cell matrix proposal; not merged into481; GPU not approved',
        'Strata22_345_approved': False,
        'remaining_live_validation': ['actual setsid lifecycle and lock/port release',
            'production running/graph2 cold SHA and usage', 'approved real restore smoke',
            'business acceptance and observation'],
        'cold_log_attribution_limit': 'requires exclusive maintenance; backend log has no request ID'}
    path = DEV / 'RELEASE_CPU_PREPARATION_REVIEW_20261009_v1.json'
    with path.open('x', encoding='utf-8') as handle:
        json.dump(review, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    spec = importlib.util.spec_from_file_location('existing_ssh', FT.parent / '_shared/ssh_upload.py')
    settings = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settings)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect('172.16.108.9', username=settings.REMOTE_USER,
                   password=settings.REMOTE_PASS, timeout=20)
    sftp = client.open_sftp()
    rows = {}

    def mkdir(path):
        try:
            sftp.stat(path)
        except FileNotFoundError:
            mkdir(path.rsplit('/', 1)[0])
            sftp.mkdir(path)

    def save(name, blob):
        remote = TARGET + '/' + name
        mkdir(remote.rsplit('/', 1)[0])
        with sftp.open(remote, 'wx') as handle:
            handle.write(blob)
        sftp.chmod(remote, 0o444)
        with sftp.open(remote, 'rb') as handle:
            assert handle.read() == blob
        rows[name] = hashlib.sha256(blob).hexdigest()

    try:
        try:
            sftp.stat(TARGET)
        except FileNotFoundError:
            mkdir(TARGET)
        else:
            raise RuntimeError('Review packet already exists; never overwrite')
        files = ['README.md', 'plan/COORDINATION_LOG.md', 'plan/MORNING_SUMMARY_20261009.md',
            'plan/RELEASE_DIRECTIVE_20261009_1300.md',
            'plan/data_releases/E2_RELEASE_CANDIDATE_DRAFT_20261009.json',
            'development/RELEASE_PROPOSAL_E2_20261009.md',
            'development/DEPLOY_ROLLBACK_E2_DRAFT_20261006.md',
            'development/RELEASE_NOTES_E2_DRAFT_20261006.md',
            'development/RELEASE_E2_BRANCH_CREATION_20261009_v1.json',
            'development/RELEASE_CPU_PREPARATION_REVIEW_20261009_v1.json',
            'development/release_e2_ops_v1/PINNED_HELPERS_CPU_CHECK_20261009.txt',
            'development/d20_short_tail_v1/D20_SHORT_TAIL_CPU_MATRIX.md',
            'development/r045_section14_draft_v18/evidence/R045_V18_PRE_RESERVATION_BLOCK_20261009.json',
            'development/r045_section14_draft_v18/evidence/R045_V18_PRE_RESERVATION_BLOCK_20261009.md']
        files += [p.relative_to(FT).as_posix() for p in (DEV / 'release_e2_ops_v1/evidence_v3').iterdir() if p.is_file()]
        for relative in files:
            save(relative, (FT / relative).read_bytes())
        readme_path = '/data2/FreeToken/README.md'
        with sftp.open(readme_path, 'rb') as handle:
            original = handle.read()
        save('server_before/FreeToken_README.md', original)
        block = ('\n\n## 2026-10-09 release preparation (CPU only; not deployed)\n\n'
            'release/e2 and wt/release-e2 were created at 481d3a7 under the 13:00 approval. '
            'Deployment and push remain unapproved and unexecuted. '
            'Prepared setsid supervisor, shared production GPU lock, inherited-environment cleanup, '
            'internal host 172.16.108.9, rollback49152, and R066 SDK smoke: '
            'FT-venv CPU20 passed; live smoke skipped. Final operations source: '
            '/data2/FreeToken/runs/dev_release/release_e2_ops_v3_20261009/source/development/release_e2_ops_v1. '
            'Review documents: ' + TARGET + '. '
            'D20 isolated CPU24 passed, GPU matrix24 service lifecycles/32 calls unapproved. '
            'R045 stopped before reservation because R040g is failed_harness while the frozen entry '
            'requires measured: zero services/calls/batch/lock/GPU. Strata22/345 unapproved.\n').encode()
        if b'## 2026-10-09 release preparation (CPU only; not deployed)' in original:
            raise RuntimeError('Server README preparation section already exists')
        with sftp.open(readme_path, 'rb') as handle:
            assert handle.read() == original
        with sftp.open(readme_path, 'wb') as handle:
            handle.write(original + block)
        with sftp.open(readme_path, 'rb') as handle:
            assert handle.read() == original + block
        save('server_after/FreeToken_README.md', original + block)
        commands = [
            ['git', '-C', '/data2/FreeToken/wt/release-e2', 'rev-parse', 'HEAD'],
            ['git', '-C', '/data2/FreeToken/wt/release-e2', 'status', '--porcelain', '--untracked-files=all', '--ignored'],
            ['git', '-C', '/data2/FreeToken/src/FreeToken', 'rev-parse', 'HEAD'],
            ['ss', '-H', '-ltn', '( sport = :8095 or sport = :8096 )'],
            ['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'],
            ['nvidia-smi', '--query-gpu=memory.used,utilization.gpu', '--format=csv,noheader,nounits']]
        evidence = []
        for argv in commands:
            _, stdout, stderr = client.exec_command(shlex.join(argv), timeout=20)
            output, error = stdout.read().decode(), stderr.read().decode()
            code = stdout.channel.recv_exit_status()
            assert code == 0, error
            evidence.append({'argv': argv, 'exit_code': code, 'stdout': output})
        assert evidence[0]['stdout'].strip() == review['candidate']
        assert not evidence[1]['stdout'].strip()
        assert evidence[2]['stdout'].strip() == '184c965964b5f79deaecf1b1e3e0eda3187c829d'
        assert not evidence[3]['stdout'].strip() and not evidence[4]['stdout'].strip()
        for target in ('/data2/_shared/gpu.lock', '/data2/FreeToken/run/production.active.json'):
            try:
                sftp.lstat(target)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError('Unexpected active GPU/production ownership')
        final = {'schema': 'ft_release_docs_cpu_delivery/v1', 'remote': TARGET,
            'readback_equal': True, 'files': rows, 'fresh_readonly_evidence': evidence,
            'production_active_absent': True, 'gpu_lock_absent': True,
            'deployment': False, 'push': False, 'model_service_started': False}
        blob = (json.dumps(final, ensure_ascii=False, indent=2) + '\n').encode()
        save('DELIVERY_RECEIPT.json', blob)
        (DEV / 'RELEASE_CPU_DELIVERY_RECEIPT_20261009_v1.json').write_bytes(blob)
        print(json.dumps({'remote': TARGET, 'files_readback': len(rows),
            'receipt_sha256': hashlib.sha256(blob).hexdigest(), 'deployment': False, 'push': False}))
    finally:
        sftp.close()
        client.close()


if __name__ == '__main__':
    main()
