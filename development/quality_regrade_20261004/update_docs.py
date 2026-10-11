"""Merge verified quality/D0 policy and namespace declarations into current docs."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
rules=next((ROOT/'plan').glob('00_*.md'))
text=rules.read_text(encoding='utf-8')
first='- **历史比较**（2026-10-04 补充交接）：每个封存轮次的结果文件开头 3 行必须给出与同类历史数据的比较；不可比较时写明原因、缺少的来源或不同口径。\n'
anchor='- 本地结果写完后，在 `plan/README.md`'
if first not in text:text=text.replace(anchor,first+anchor,1)
new='''16. **质量判卷标准（含离线重判）**：规范判卷器为 `_shared/evaluator.py`，SHA256 `39f10fa8ddab2c1b076862eb827d903be945243bb2e2422ec448e8560646e330`；60题语料 SHA256 `bde77ab02bb11539f6ee69861dc441ea3670ed6796d4d27226af1f89f74f9cad`。服务器标准位置 `/data2/_shared/evaluator.py`。质量轮次 `round.json` 及逐题记录必须绑定 `evaluator_sha256`、语料、实际客户端／重判脚本 SHA、Python 版本和原始回答 SHA；客户端必须实际调用经 SHA 校验的判卷器，哈希不符或 `EVALUATOR_ERROR` 立即停止。只比较同判卷器、同语料和同测试协议的分数；离线重判注明原始回答来源，不当新生成成绩。历史38/60保留其原始判分字段，不以当时目录内存在的判卷器文件替代实际执行来源；47/60只引用 `E2-R009-regrade` 的显式重判工件。
17. **D0 解码用途**：开启 `FT_DEV_D0` 的解码数据只作诊断；T07约−3.5%与R022约−10%的差异尚未唯一归因，在同树、匹配首枪政策、交替顺序和重复样本的复测闭合前，不作为生产性能数、性能收益或回归判据。未启用 timeline 的测量不得把开销归因于 `FT_DEV_D0_TIMELINE_STEPS`。
18. **分数来源与展示**：每个质量分数注明原始判分或离线重判、轮次、判卷器 SHA及语料 SHA；看板／论文引用数值时绑定数据发布版本及其子结论状态。封存轮次按第4节在结果开头3行比较同类历史数据；保留不可比较的原因，不能只选一个未标来源的数字。
'''
if '16. **质量判卷标准' not in text:
 boundary=text.rfind('\n---\n',0,text.index('## 7.'))
 if boundary<0:raise ValueError('rule boundary changed')
 text=text[:boundary]+'\n'+new+text[boundary:]
rules.write_text(text,encoding='utf-8')
readme=ROOT/'plan/README.md';text=readme.read_text(encoding='utf-8')
mechanisms='''机制 D12–D14 的数字与当前卡号也不同，按卡片标题中的显式声明对应：

| 机制代号 | 含义 | 当前计划卡 | 当前处理 |
|---|---|---|---|
| 机制 D12 | 锚点切段与快照策略 | D01（第一步）；后续触发点见 D09 | D01已交付；后续按各卡依赖验收 |
| 机制 D13 | 短后缀按需搬运 | D12 | 后置／冻结，待T06和批准 |
| 机制 D14 | 错相位重叠解码 | D10 | 后置／冻结，待T05时间线 |
| 无机制号声明 | 层优先快照计划与前缀续算修复 | **卡 D14** | R022默认门已过，R023命中续算未过；不是机制D14 |

'''
anchor='`M1`–`M6`'
if '机制 D12–D14 的数字' not in text:text=text.replace(anchor,mechanisms+anchor,1)
text=text.replace('| M1 | `../reports/REPORT_E1_20261003.md` 中的论文编辑器验收；无当前开发卡绑定 | 未知（不得外推为机制映射） |','| M1 | 机制定义／当前卡绑定未声明；报告中的同名M1为编辑验收条目 | 未知；不得据报告条目外推机制映射 |')
text=text.replace('T01…T16_*.md','T01…T18_*.md').replace('D01…D13_*.md','D01…D14_*.md')
lines=text.splitlines()
for i,line in enumerate(lines):
 if line.startswith('| T07 |'):
  parts=line.split('|');parts[2]=' R003 kept；T07/R022 D0解码差值已对账，唯一原因未定 ';parts[3]=' [E2-R003结果](01_测试与调研/results/T07-E2-R003_20261004.md)、[核对](01_测试与调研/results/T07-E2-R003_20261004_r2.md) ';parts[4]=' 32K约−3.49%对门约−10.14%；均未开timeline，首枪/样本/顺序不同；D0解码仅作诊断 ';lines[i]='|'.join(parts)
 if line.startswith('| D07 |'):
  parts=line.split('|');parts[2]=' R024默认四臂门已独立复核封存kept；G3/G4/T06待 ';parts[4]=' fefb19c，直接父D06@0369263；CPU28PASS/1CUDA SKIP；R024完整128-token全文一致、13预填，尚不授予T17或业务接受 ';lines[i]='|'.join(parts)
 if line.startswith('| T16 |'):
  line=line.replace('D00/D01/D02/D03/D06/D14','D00/D01/D02/D03/D06/D07/D14').replace('R020/R022四臂','R020/R022/R024四臂');lines[i]=line
readme.write_text('\n'.join(lines)+'\n',encoding='utf-8')
d0=next((ROOT/'plan').glob('01_*/results/T07-E2-R003_20261004_r2.md'))
text=d0.read_text(encoding='utf-8').replace('`E2-R003/{A_d0on_p1,p2,p3;B_d0off_p1,p2,p3}/c_32052_r{1,2}.json`','`E2-R003/A_d0on_p{1,2,3}/c_32052_r{1,2}.json`及对应\n`B_d0off_p{1,2,3}/c_32052_r{1,2}.json`')
d0.write_text(text,encoding='utf-8')
rootreadme=ROOT/'README.md';text=rootreadme.read_text(encoding='utf-8')
tools='''- 规范质量判卷与离线重判：`development/quality_regrade_20261004/regrade.py`／`stage.py`绑定判卷器、语料、输入和逐题来源，CPU重判保留历史工件。`close_stage.py --receipt close_cpu_receipt_r2.json --close`使用冻结闭包；`close.py`／`publication.py`通过身份journal、flock及Linux `renameat2(RENAME_NOREPLACE)`同步标准并追加E0更正，中断后先读回实际状态。`test_regrade.py`、`test_benchmark_standard.py`、`test_publication.py`覆盖判分与并发恢复。共享 `_shared/benchmark_client.py` 直接调用校验后的规范判卷器，逐题和汇总写入判卷器／语料／客户端SHA；生成预算仍为768。历史内置 `grade_response` 不作为新轮次计分路径。
- R024 D07收尾：`development/t16_r024_d04_close.sh`及 `{inspect,evidence,verify}.sh`保留准确本轮审核／D04封存入口；只证明父D06与候选D07默认四臂等价，不代替T17、G3/G4或T06。
'''
if '- 规范质量判卷与离线重判：' not in text:
 anchor='- [判卷器独立复核]'
 if anchor not in text:raise ValueError('README evidence anchor changed')
 text=text.replace(anchor,tools+anchor,1)
rootreadme.write_text(text,encoding='utf-8')
print('Merged rules, namespace declarations, D0/D07 status and tool documentation.')
