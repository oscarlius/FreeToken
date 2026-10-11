"""Merge sealed R031 evidence and the current plan into the existing D14 row."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
path = ROOT / 'development/development_status.json'
before = path.read_bytes()
value = json.loads(before)
if value['revision'] != 59:
    raise ValueError('status changed; merge from fresh revision')
row = next(row for row in value['development'] if row['card'] == 'D14')
if row['candidate_commit'] != 'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42':
    raise ValueError('D14 candidate changed')
now = datetime.now(timezone.utc).isoformat()
row.update(status='R031诊断kept；R023历史not_met保留；新T17同结构参照待开发',
           updated_at=now,
           next_step='按20261005权威任务书实现卡D14默认关闭调度参数与D0字段，再交付卡D16自动同结构参照、CPU夹具、T16和新T17；不修改生产数值内核。',
           blockers=[
               'FT_DEV_PREFILL_SCHEDULE、D0四结构字段及卡D16自动参照尚未交付。',
               '供体8193计算超过捐赠8192；参照必须保留真实计算形状并恢复8192快照，不能裁去lookahead。',
               '新T17状态硬门、双进程同结构参照和输出比较未完成；卡D17集成仍等待。',
           ])
additions = [
    ('development/t17_gemm_cpu_e1154756dd3c.json', 'Linux13项重放和10项原门PASS；真实CPU融合BF16权重及原kernel导入，CUDAfalse，17源冻结'),
    ('development/t17_gemm_E2-R031-diagnostic-T17_read.json', '12份输出实际CPU复算；M3585复现暖，M3649／4096复现冷，三重复均一致'),
    ('development/t17_gemm_close_E2-R031-diagnostic-T17_closure_receipt.json', '诊断kept独立封存；18原始文件不变，68清单项／v001v002历史／只读检查通过'),
    ('development/t17_r031_panel_receipt.json', '完整封存元数据POST及API／持久化回读一致，封存源未变'),
    ('plan/01_测试与调研/results/T17-E2-R031-diagnostic-T17_20261005.md', '首三行历史比较、真实BF16算子重放与证据限制；不授予新T17或性能接受'),
    ('plan/PLAN_20261005_重新规划.md', '当前总负责人权威计划：三层新T17、卡D14调度参数、卡D16、卡D17集成与卡D18；MTP冻结、TP原计划'),
]
for name, summary in additions:
    if any(item['path'] == name for item in row['evidence']):
        raise ValueError('R031 evidence already recorded')
    row['evidence'].append({'path': name, 'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), 'summary': summary})
value.update(revision=60, updated_at=now, updated_by='Codex sealed R031 and current 20261005 plan')
payload = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
temporary = path.with_name(path.name + '.r031-update.tmp')
with temporary.open('xb') as stream:
    stream.write(payload)
if path.read_bytes() != before:
    raise ValueError('concurrent status update; preserved temporary merge')
os.replace(temporary, path)
print(json.dumps({'revision': 60, 'updated_card': 'D14', 'sha256': hashlib.sha256(payload).hexdigest()}))
