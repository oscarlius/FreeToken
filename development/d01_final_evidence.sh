set -eu
test ! -e /data2/_shared/gpu.lock
ss -ltn 'sport = :8095'
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
git -C /data2/FreeToken/wt/e2base status --porcelain --untracked-files=no
git -C /data2/FreeToken/wt/e1r008 status --porcelain --untracked-files=no
/data2/FreeToken/venv/bin/python - <<'PY'
import hashlib
import json
from pathlib import Path
root = Path('/data2/FreeToken/runs/dev_D01')
summary = json.loads((root/'health_ready_check/gpu_selfcheck.json').read_text())
review = {
    'kind': 'D01_development_review_not_formal_acceptance',
    'source': str(root/'health_ready_check/gpu_selfcheck.json'),
    'G3': 'PASS' if summary['G3'] else 'NOT_MET',
    'G4_cached_tokens_equal': summary['cut_on']['cached'] == summary['cut_off']['cached'],
    'G4_snapshot_counts_equal': summary['cut_on']['snapshots'] == summary['cut_off']['snapshots'],
    'G4_snapshot_positive_control': min(summary['cut_on']['snapshots'], summary['cut_off']['snapshots']) > 0,
    'G4_coverage': 'insufficient_positive_control' if min(summary['cut_on']['snapshots'], summary['cut_off']['snapshots']) == 0 else 'assessed',
    'identical_requests': summary['identical_requests'],
    'formal_T16_T03': 'not_run',
    'D02_final_prefill_gap': {},
}
for name in ('cut_on', 'cut_off'):
    arm = root/'health_ready_check'/name
    log = (arm/'serve.log').read_text()
    records = [json.loads(line) for line in (arm/'d0_prefill.jsonl').read_text().splitlines()]
    review['D02_final_prefill_gap'][name] = {'prefill_batches':log.count('Prefill batch,'),
                                          'D0_records':len(records),'D0_seg_logs':log.count('D0 seg:')}
(root/'health_ready_check/gpu_selfcheck_review.json').write_text(json.dumps(review, indent=2))
print(json.dumps(summary, ensure_ascii=False))
print(json.dumps(review, ensure_ascii=False))
lines = []
for path in sorted(root.rglob('*')):
    if path.is_file() and path.name != 'MANIFEST.sha256':
        lines.append(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+str(path.relative_to(root)))
(root/'MANIFEST.sha256').write_text('\n'.join(lines)+'\n')
print('MANIFEST.sha256='+hashlib.sha256((root/'MANIFEST.sha256').read_bytes()).hexdigest())
PY
