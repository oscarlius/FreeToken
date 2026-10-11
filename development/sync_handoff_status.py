"""Refresh only the current handoff status from verified receipts and known gaps."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
status_path = ROOT / 'development/development_status.json'
before = status_path.read_bytes()
data = json.loads(before)
cards = {item['card']: item for item in data['development']}
now = datetime.now(timezone.utc).isoformat()
cards['D14'].update(
    status='已交付待验证',
    candidate_commit='e4f32022a5aa4d8734d87d9f6eb15e98c1edde42', updated_at=now,
    next_step='R021已判failed_harness并原样封存；R022/batch50四臂已通过独立复核并封存。执行T17后合成E2-base.1；再跑T10与60题。',
    blockers=['T17和T10重跑尚未完成，不标D14最终接受；D07默认门未过，尚未合成E2-base.1。'],
)
for name, description in (
    ('development/D14_initial_state_impact.md', '相对坐标会触发实际GDN/conv/PLE fresh分支；源码证据与GPU接受分列。'),
    ('development/t16_r021_failed_close_receipt.json', '原始43工件哈希保持；R021封存为failed_harness。'),
):
    path = ROOT / name
    if path.is_file() and not any(row.get('path') == name for row in cards['D14']['evidence']):
        cards['D14']['evidence'].append({'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'summary': description})
cards['D04'].update(
    status='发布完成；后续轮次继续追加', updated_at=now,
    next_step='FTD-20261004-1与不可变勘误均已发布；保持后续轮次、判定和数据版本分列。', blockers=[],
)
cards['D07']['blockers'] = ['D07实际GPU默认门与T06业务验收未执行；D06 R020已通过，CPU通过不替代D07证据。']
data['revision'] = int(data['revision']) + 1
data['updated_at'] = now
data['updated_by'] = 'Codex mainline verified handoff follow-up'
data['baseline']['known_defects'] = {
    'reference': 'development/D14_initial_state_impact.md',
    'candidate_commit': cards['D14']['candidate_commit'],
    'affected_claims': 'Prefix-hit continuation outputs, warm replay text and multi-turn quality remain hypothesis.',
    'baseline_successor': 'E2-base.1 not accepted; D14 T16/T17 and D07 default gate remain prerequisites.',
}
if status_path.read_bytes() != before:
    raise RuntimeError('status changed concurrently; reload before applying')
status_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

readme_path = ROOT / 'plan/README.md'
before = readme_path.read_bytes()
text = before.decode('utf-8').replace('\r\n', '\n').replace('\r', '')
text = text.replace('E2-R021-gate-D14 / batch49，不标GPU门通过',
                    'R021/batch49因共享工装口径判failed_harness并封存；R022/batch50四臂重跑中，不标GPU门通过')
if '| T17 |' not in text:
    marker = '| D00 | 构建与T00基线立项通过'
    rows = (
        '| T17 | 工装CPU验证中；真实模型门待T16 | [初始状态影响](../development/D14_initial_state_impact.md)、[门核查要求](../development/T17_gpu_review_blockers.md) | 短尾段与>4096尾段分别覆盖；真实采样ID、四角色恢复和首子块状态均需原始证据 |\n'
        '| P0判定/发布 | 已发布；缺陷影响以勘误逐项标hypothesis | [FTD-20261004-1](data_releases/FTD-20261004-1.json)、[erratum-1](data_releases/FTD-20261004-1-erratum-1.json) | 13 kept（测量有效）、8 failed_harness；冷时延/冷输出保留，8条输出层结论hypothesis；服务器/本地字节一致并只读 |\n'
        '| R013分类 | 分叉分类完成，修复后T10仍待 | [P0分类记录](../development/p0_r013_fork_classification.md) | 11分叉：首token3、早期5、晚期3；top-2差0–1.875，同路径新进程logits逐位相同；确定性路径差异不等于D14后分歧已消失 |\n'
    )
    if marker not in text:
        raise RuntimeError('README status insertion marker changed')
    text = text.replace(marker, rows + marker, 1)
text = text.replace('../development/p0_logits_progress.md', '../development/p0_r013_fork_classification.md')
text = text.replace('R022/batch50四臂重跑中，不标GPU门通过', 'R022/batch50四臂独立复核PASS并封存；T17/T10仍待，E2-base.1未接受')
if '| Q11 |' not in text:
    text += ('\n| Q11 | E2-base已知缺陷：符合层优先条件的命中续算会走错误fresh初始状态；捐赠快照问题也可能影响短尾段 | '
             '[影响说明](../development/D14_initial_state_impact.md)、[勘误](data_releases/FTD-20261004-1-erratum-1.json)；冷测量保留，暖输出/多轮质量hypothesis，待统一E2-base.1复测 |\n')
if readme_path.read_bytes() != before:
    raise RuntimeError('README changed concurrently; reload before applying')
readme_path.write_text(text, encoding='utf-8', newline='\n')
print('Updated current handoff fields; GPU acceptance remains pending.')
