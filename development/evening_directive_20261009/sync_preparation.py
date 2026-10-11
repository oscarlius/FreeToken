"""Publish only FT preparation/docs, preserving remote prior bytes and log rows."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'development/r067c_retry2_production_control_20261009'))
import ssh_ops


def mkdirs(sftp, path):
    current = PurePosixPath('/')
    for part in PurePosixPath(path).parts[1:]:
        current /= part
        try:
            sftp.stat(str(current))
        except FileNotFoundError:
            sftp.mkdir(str(current))


def read_if_exists(sftp, path):
    try:
        with sftp.open(path, 'rb') as f:
            return f.read()
    except FileNotFoundError:
        return None


def main():
    now = datetime.now(timezone(timedelta(hours=8))).isoformat()
    files = [ROOT / p for p in [
        'README.md', 'paper/README.md', 'plan/ROOT_EXECUTION_DIRECTIVE_20261009.md',
        'plan/EVENING_DIRECTIVE_20261009.md', 'plan/MORNING_20261010_REPORT_PREPARATION.md',
        'plan/02_开发任务/D09_机制D3_基于577的层优先触发点.md',
        'plan/02_开发任务/D10_机制D14_错相位重叠解码可行性原型.md',
        'paper/src/body_v52.html', 'paper/src/build_v52.py',
        'paper/FreeToken_MultiGPU_CoExec_v5.2.html', 'paper/ARXIV_ENGLISH_OUTLINE_20261009.md',
        'development/RELEASE_PROPOSAL_E2_20261009.md',
        'development/RELEASE_NOTES_E2_DRAFT_20261006.md',
        'development/DEPLOY_ROLLBACK_E2_DRAFT_20261006.md',
    ]]
    for folder in [HERE, ROOT / 'development/d09_prediction_20261009', ROOT / 'development/d10_staggered_20261009']:
        files.extend(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts
            and '.pytest_cache' not in p.parts and 'prior_remote' not in p.parts
            and p.name != 'REMOTE_SYNC_RECEIPT.json')
    files = sorted(set(files))
    client = ssh_ops.connect()
    results = []
    try:
        sftp = client.open_sftp()
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            target = '/data2/FreeToken/' + rel
            data = path.read_bytes()
            old = read_if_exists(sftp, target)
            if old == data:
                results.append({'path': rel, 'state': 'same', 'sha256': hashlib.sha256(data).hexdigest()})
                continue
            if old is not None:
                prior = HERE / 'prior_docs' / path.relative_to(ROOT)
                if not prior.exists() or old != prior.read_bytes():
                    results.append({'path': rel, 'state': 'remote_diff_preserved_not_overwritten', 'remote_sha256': hashlib.sha256(old).hexdigest()})
                    continue
                archived = '/data2/FreeToken/development/evening_directive_20261009/prior_remote/' + rel
                mkdirs(sftp, str(PurePosixPath(archived).parent))
                existing = read_if_exists(sftp, archived)
                if existing is None:
                    ssh_ops.put_new(sftp, archived, old)
                else:
                    assert existing == old
            mkdirs(sftp, str(PurePosixPath(target).parent))
            temp = target + '.evening-preparation-new'
            assert read_if_exists(sftp, temp) is None
            ssh_ops.put_new(sftp, temp, data)
            sftp.posix_rename(temp, target)
            assert read_if_exists(sftp, target) == data
            if rel.startswith('development/d09_prediction_20261009/') and path.name in [
                'PREDICTION_MANIFEST_v4.json', 'SEAL_RECEIPT_v4.json', 'CURRENT_PREDICTION.json']:
                sftp.chmod(target, 0o444)
            if rel.startswith('development/d10_staggered_20261009/') and path.name in ['prediction_manifest.json', 'PREDICTION_SEAL.json']:
                sftp.chmod(target, 0o444)
            results.append({'path': rel, 'state': 'written_verified', 'sha256': hashlib.sha256(data).hexdigest()})
        # Append only this turn's new rows; never replace another agent's log.
        remote_log = '/data2/FreeToken/plan/COORDINATION_LOG.md'
        log = read_if_exists(sftp, remote_log) or b''
        local_lines = (ROOT / 'plan/COORDINATION_LOG.md').read_text(encoding='utf-8').splitlines()
        additions = [line for line in local_lines if ('root：归档晚间六项用户决定' in line or 'root：D09无效预测草案保留并排除' in line)
                     and line.encode('utf-8') not in log]
        with sftp.open(remote_log, 'ab') as f:
            for line in additions:
                f.write(('\n' + line + '\n').encode('utf-8'))
        results.append({'path': 'plan/COORDINATION_LOG.md', 'state': 'append_only', 'rows_added': len(additions)})
    finally:
        client.close()
    receipt = {'written_at': now, 'scope': 'FT_docs_and_CPU_preparation_only', 'files': results,
        'release_worktree_mutated': False, 'gpu_calls': 0, 'service_actions': 0}
    (HERE / 'REMOTE_SYNC_RECEIPT.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'total': len(results), 'written_verified': sum(x['state'] == 'written_verified' for x in results),
        'preserved_remote_differences': [x['path'] for x in results if x['state'] == 'remote_diff_preserved_not_overwritten']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
