"""Merge only the final verified quality row and provenance note."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
readme=ROOT/'plan/README.md'
text=readme.read_text(encoding='utf-8');lines=text.splitlines()
for i,line in enumerate(lines):
 if line.startswith('| T08 |'):
  parts=line.split('|');parts[2]=' P1/P2已封存；三批规范离线重判已封存kept；两路待D06 '
  if '标准重判' not in parts[3]:parts[3]=parts[3].rstrip()+'、[标准重判](01_测试与调研/results/T08-E2-R009-regrade_20261004.md) '
  parts[4]=' 原始生成38/60保留；同39f10fa8判卷器重判E0/R004/R009均47/60、逐题状态相同；原冷/soak测量有效，重判不授予D14输出接受 '
  lines[i]='|'.join(parts)
 if line.startswith('| D07 |') and '[R024门]' not in line:
  parts=line.split('|');parts[3]=parts[3].rstrip()+'、[R024门](01_测试与调研/results/T16-E2-R024-gate-D07_20261004.md) ';lines[i]='|'.join(parts)
 if line.startswith('| T16 |'):
  parts=line.split('|')
  if '[D07 R024]' not in parts[3]:parts[3]=parts[3].rstrip()+'、[D07 R024](01_测试与调研/results/T16-E2-R024-gate-D07_20261004.md) '
  parts[4]=parts[4].replace('共同工装39PASS','共同工装55PASS');lines[i]='|'.join(parts)
 if line.startswith('| Q6 |'):
  parts=line.split('|');parts[2]=' `agent_trace.py` 本地与远端md5差异仍需按实际批次绑定；判卷器/质量客户端已统一，原38/60执行SHA未留存 '
  parts[3]=' 标准39f10fa8已同步；E2-R009-regrade三批47/60，E0原值与来源更正均保留；以后记录实际执行客户端及判卷器SHA '
  lines[i]='|'.join(parts)
text='\n'.join(lines)+'\n'
if '| T18 |' not in text:
 anchor='| T17 |';start=text.find(anchor);end=text.find('\n',start)
 if start<0:raise ValueError('T17 status row absent')
 text=text[:end+1]+'| T18 | 后置配置调研，未启动 | [卡片](01_测试与调研/T18_质量输出与思考预算配置调研.md) | 同判卷器比较生成预算与思考截断；不改变当前主线测试配置 |\n'+text[end+1:]
readme.write_text(text,encoding='utf-8')
rootreadme=ROOT/'README.md';text=rootreadme.read_text(encoding='utf-8')
line='- 规范质量判卷与离线重判：'
start=text.index(line);end=text.index('\n',start)
if '`finalize.py`只通过' not in text[start:end]:
 text=text[:end]+' `finalize.py`只通过冻结D04工具追加独立审核与离线分析kept判定，初次pending快照和原manifest保留；[结果](plan/01_测试与调研/results/T08-E2-R009-regrade_20261004.md)。'+text[end:]
rootreadme.write_text(text,encoding='utf-8')
for path in [ROOT/'development/d07_progress.md',next((ROOT/'plan').glob('02_*/D07_*\u4ea4\u4ed8*.md'))]:
 text=path.read_text(encoding='utf-8')
 if 'R024默认四臂门（追加）' not in text:
  text+='\n\n### R024默认四臂门（追加）\n\n2026-10-04：E2-R024-gate-D07已独立复算并D04封存kept，父D06与候选D07四臂128-token全文一致，13预填事件包含就绪请求。当前round SHA `27c30ef5bfc2aa1e0cb5e4ecc8e2bbe78fbdbe60003609492f4477448a935ae4`，manifest SHA `54401ae6c0bca5709c01b46bfc14e84e3619ae1f01e6ce54ed79d4868199610f`。仅默认等价门通过；G3/G4/T06及T17接受仍待各自验证，不授予E2-base.1接受。完整结果为 `plan/01_测试与调研/results/T16-E2-R024-gate-D07_20261004.md`。\n'
  path.write_text(text,encoding='utf-8')
print('Final quality status/provenance and postposed T18 card linked.')
