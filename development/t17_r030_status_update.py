"""Record independently sealed R030 without changing other development rows."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
path = ROOT / 'development/development_status.json'
before = path.read_bytes()
value = json.loads(before)
if value['revision'] != 58:
    raise ValueError('status changed; merge against its fresh revision')
row = next(row for row in value['development'] if row['card'] == 'D14')
if row['candidate_commit'] != 'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42':
    raise ValueError('D14 candidate changed')
now = datetime.now(timezone.utc).isoformat()
row.update(status='T17 not_met；R029／R030诊断独立封存；真实GDN算子重放准备中',
           updated_at=now,
           next_step='修正并冻结GDN重放工装，验证真实权重融合、PID／锁和CPU输入后运行单GPU诊断；保留原T17／E2-base.1／T10门。')
additions = [
    ('development/t17_hc_close_E2-R030-diagnostic-T17_closure_receipt.json', 'R030诊断kept独立封存；98原始文件未变，清单、历史和只读检查通过；不授予原T17接受'),
    ('development/t17_r030_panel_receipt.json', '8098 API和持久化元数据回读与封存源一致；源文件哈希不变'),
    ('development/t17_hc_E2-R030-diagnostic-T17_read.json', '实际CPU逐位复算：八类上游角色相同，GDN输出789字节不同；四类恢复相同，输出fork36'),
    ('plan/01_测试与调研/results/T17-E2-R030-diagnostic-T17_20261005.md', '首三行历史比较、真实BF16 TorchLinearKernel路径与诊断限制；cuBLAS唯一因果未证明'),
]
for name, summary in additions:
    digest = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    if any(item['path'] == name for item in row['evidence']):
        raise ValueError('R030 status evidence already exists')
    row['evidence'].append({'path': name, 'sha256': digest, 'summary': summary})
value.update(revision=59, updated_at=now, updated_by='Codex R030 independent closure and CPU readback')
payload = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
temporary = path.with_name(path.name + '.r030-update.tmp')
with temporary.open('xb') as stream:
    stream.write(payload)
if path.read_bytes() != before:
    raise ValueError('concurrent status change; preserved temporary merge for review')
os.replace(temporary, path)
print(json.dumps({'revision': 59, 'updated_card': 'D14', 'sha256': hashlib.sha256(payload).hexdigest()}))
