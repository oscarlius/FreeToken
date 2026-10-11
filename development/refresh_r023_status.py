"""Merge only verified R023 failure and T10 preparation into the live local board."""
import datetime
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
receipt = json.loads((ROOT / 'development/t17_r023_close_receipt.json').read_text(encoding='utf-8'))
if receipt.get('rid') != 'E2-R023-gate-T17' or receipt.get('verdict') != 'not_met' or receipt.get('original_raw_files_verified') != 76:
    raise ValueError('exact sealed R023 receipt required')
rows = {
    'T17': '| T17 | R023实际输出/计算态不等，封存not_met；继续诊断 | [R023结果](01_测试与调研/results/T17-E2-R023-gate-T17_20261004.md)、[诊断](../development/t17_r023_computation_diagnosis.md) | 同一8257 IDs、warm缓存8192/cold0、各128token，index36分叉；四角色恢复字节PASS，8256三个浮点计算态不等；76原始文件未变，后三边界未测 |',
    'D14': '| D14 | R022默认门通过；R023 T17 not_met，继续诊断 | [交付](02_开发任务/D14_交付记录_20261004.md)、[T17结果](01_测试与调研/results/T17-E2-R023-gate-T17_20261004.md) | e4f3202；CPU13 failed→13 passed；R022 kept；R023真实测量不等，非failed_harness；未合入E2-base.1 |',
    'T10': '| T10 | 历史判定已封存；新准备9PASS，实际重跑待T17接受 | [R017](01_测试与调研/results/T10-E2-R017_20261004.md)、[R013分类](../development/p0_r013_classification.md)、[新准备](../development/t10_d14_prepare.md) | SSH9新鲜只读复核：冷/冷36/36、热/热36/36相同，冷/热3/36相同=33/36不同；3进程×12轮协议与双trace SHA已锁定；新GPU未启动 |',
    'Q1': '| Q1 | 已解决：R023所属batch/两服务已停止、所属锁释放，现场GPU4MiB | 每新轮重查GPU/8095/源码/所属PID与start ticks；不清理其他或陈旧锁 |',
}
path = ROOT / 'plan/README.md'
original = path.read_bytes()
source = original.decode('utf-8')
for card, row in rows.items():
    source, count = re.subn(r'(?m)^\| ' + card + r' \|[^\r\n]*', lambda _: row, source)
    if count != 1:
        raise ValueError('exact one status row required: ' + card)
if path.read_bytes() != original:
    raise ValueError('plan changed during row merge')
path.write_bytes(source.encode('utf-8'))
path = ROOT / 'development/development_status.json'
original = path.read_bytes()
doc = json.loads(original)
stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
doc['revision'] += 1
doc['updated_at'] = stamp
card = next(x for x in doc['development'] if x['card'] == 'D14')
card.update(status='T16通过；T17 not_met，继续诊断', updated_at=stamp,
            next_step='R023已独立not_met封存；新轮对齐分块并捕获8192前缀/8256续算状态，定位数值路径。E2-base.1、T10实际重跑及60题仍待接受门。',
            blockers=['同一8257输入首次采样分叉index36，三浮点计算態不等；恢复字节正确不代替等价门。',
                      '剩余三边界未测；D07默认门、E2-base.1及修复版T10仍待。'])
items = [
    ('development/t17_r023_close_receipt.json', 'not_met只读封存；76原始文件哈希保持，清单和历史检查通过'),
    ('development/t17_r023_close_cpu_receipt.json', 'Linux封存23PASS/20subtests；原始counterexample独立CPU复算'),
    ('plan/01_测试与调研/results/T17-E2-R023-gate-T17_20261004.md', '首fork36，四角色恢复字节PASS与三浮点计算态不等分列'),
    ('development/t17_r023_computation_diagnosis.md', '分块路径解释与8192/8256边界新轮诊断；不是新GPU结果'),
    ('development/t10_d14_prepare.md', 'SSH9刷新旧cold/cold36/36、warm/warm36/36、cold/warm3/36；新准备CPU9PASS'),
]
for name, summary in items:
    item = {'path': name, 'sha256': hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), 'summary': summary}
    card['evidence'] = [x for x in card['evidence'] if x['path'] != name] + [item]
for item in card['evidence']:
    if item['path'] == 'development/t17_d14_E2-R023-gate-T17_launch_receipt.json':
        item['summary'] = 'R023/b51实际启动回执；现已终止并独立封存not_met'
d07 = next(x for x in doc['development'] if x['card'] == 'D07')
d07['next_step'] = 'D06 R020已通过；D07准确提交CPU28PASS和独立复核完成，实际GPU默认门与T06尚待。新轮使用共同完整尾段工装。'
if path.read_bytes() != original:
    raise ValueError('status changed during evidence merge')
path.write_bytes((json.dumps(doc, ensure_ascii=False, indent=2) + '\n').encode())
print(json.dumps({'revision': doc['revision'], 'updated_at': stamp, 'R023': 'not_met'}))
