"""Merge the verified R025 result and next diagnostic tooling without replaying old status."""
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
readme=ROOT/'README.md';text=readme.read_text(encoding='utf-8')
entry='- T17 首层数值诊断：`development/t17_prefix_numeric_{observe,startup,runner,launch,stage,start,monitor}.py` 保留R023默认4096分块，记录第一GDN共享前缀实际入参与原返回h[56]。stage验证Linux CPU及正常spawn，start只启动准确独立审查的冻结源，monitor只读实际进程／源码／结果。见[诊断计划](development/T17_PREFIX_NUMERIC_DIAGNOSTIC_PLAN_20261005.md)及[观察器契约](development/t17_prefix_numeric_observe.md)；只作定位，不授予T17接受，时间不作性能数。\n'
if '- T17 首层数值诊断：' not in text:text=text.replace('- T17 同分块诊断：',entry+'- T17 同分块诊断：',1)
readme.write_text(text,encoding='utf-8')
readme=ROOT/'plan/README.md';text=readme.read_text(encoding='utf-8');lines=text.splitlines()
for i,line in enumerate(lines):
    if line.startswith('| T17 |'):
        lines[i]='| T17 | R023 not_met保留；R025诊断已封存kept，默认分块首层定位准备中 | [R023](01_测试与调研/results/T17-E2-R023-gate-T17_20261004.md)、[R025](01_测试与调研/results/T17-E2-R025-diagnostic-T17_20261004.md)、[下一诊断](../development/T17_PREFIX_NUMERIC_DIAGNOSTIC_PLAN_20261005.md) | R025对齐前缀与8256状态、128输出全字节相同；原接受门仍未过；默认4096观察器准备，新GPU未启动 |'
readme.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Merged exact diagnostic evidence and tool references.')
