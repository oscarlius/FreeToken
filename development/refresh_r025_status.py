"""Merge the live R025 diagnostic and verified D0 reconciliation into the current board."""
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
process = subprocess.run([sys.executable, str(ROOT / 'development/t17_matched_monitor.py'),
                          'E2-R025-diagnostic-T17'], capture_output=True, check=True)
snapshot = json.loads(process.stdout)
if (snapshot['status']['state'] not in ('loading', 'probing')
        or snapshot['lock']['owner'] != snapshot['rid'] or snapshot['handle']['start_ticks'] != 122229157):
    raise ValueError('exact running R025 diagnostic required; do not publish stale runtime state')
reconciliation = json.loads((ROOT / 'development/d0_decode_reconciliation_20261004.json').read_text(encoding='utf-8'))
if reconciliation.get('gpu_started') is not False or not all(v['manifest_verified'] for v in reconciliation['immutable_inputs'].values()):
    raise ValueError('CPU-only D0 reconciliation with fresh manifest evidence required')
rows = {
    'T17': '| T17 | R023封存not_met；R025同分块诊断运行中 | [R023结果](01_测试与调研/results/T17-E2-R023-gate-T17_20261004.md)、[诊断](../development/t17_r023_computation_diagnosis.md) | R023同一8257输入、128token在index36分叉；R025/b53以FT_LM_CHUNK=7680比较8192前缀及8256计算态，只有诊断资格，不改写原接受门 |',
    'T07': '| T07 | R003 kept；与R022的解码差值已只读对账 | [E2-R003结果](01_测试与调研/results/T07-E2-R003_20261004.md)、[对账](01_测试与调研/results/D0-decode-reconciliation_20261004.md) | 240+116项manifest全PASS；六样本D0解码均值−3.35%～−3.58%，门单样本约−10.1%；首枪/输入/时钟协议不同，因果贡献未确定，门值禁止性能引用 |',
    'Q1': '| Q1 | 单GPU由已授权R025同分块诊断占用，batch53/442080 | 实际birth ticks122229157与冻结源已核对；R023已终止，D07 R024已结束测量；保持单写者，不清理其他锁/进程 |',
}
path = ROOT / 'plan/README.md'
original = path.read_bytes()
source = original.decode('utf-8')
for card, row in rows.items():
    source, count = re.subn(r'(?m)^\| ' + card + r' \|[^\r\n]*', lambda _: row, source)
    if count != 1:
        raise ValueError('one current status row required: ' + card)
if path.read_bytes() != original:
    raise ValueError('board changed during row merge')
path.write_bytes(source.encode('utf-8'))
path = ROOT / 'development/development_status.json'
original = path.read_bytes()
doc = json.loads(original)
stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
doc['revision'] += 1
doc['updated_at'] = stamp
card = next(row for row in doc['development'] if row['card'] == 'D14')
card.update(status='T16通过；T17 not_met，R025诊断中', updated_at=stamp,
            next_step='读取R025同分块8192前缀/8256续算四角色与128token结果并独立复算；R023 not_met保留，E2-base.1和T10仍未接受。')
for name, summary in [
    ('development/t17_matched_E2-R025-diagnostic-T17_launch_receipt.json', 'R025/b53诊断真实启动；FT_LM_CHUNK=7680，16冻结文件，CPU stage7eb1e1d4，非接受门'),
    ('plan/01_测试与调研/results/D0-decode-reconciliation_20261004.md', '历史同类比较已独立复核；门解码值禁止性能引用，因果贡献仍未定'),
    ('development/evaluator_canonical_review.md', '相同E0回答/corpus下250和39均47/60；历史38未pin实际计分源码，不能归因两文件diff'),
]:
    item = {'path': name, 'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), 'summary': summary}
    card['evidence'] = [row for row in card['evidence'] if row['path'] != name] + [item]
if path.read_bytes() != original:
    raise ValueError('status changed during evidence merge')
path.write_bytes((json.dumps(doc, ensure_ascii=False, indent=2) + '\n').encode())
print(json.dumps({'revision': doc['revision'], 'updated_at': stamp, 'R025_state': snapshot['status']['state']}))
