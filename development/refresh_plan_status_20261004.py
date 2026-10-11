"""Merge verified R022/R023 and release status into the existing local board."""
import datetime
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
rows={
 'T01':'| T01 | FTD-20261004-1已发布 | [发布结果](01_测试与调研/results/T01-FTD-20261004-1_20261004.md)、[勘误](data_releases/FTD-20261004-1-erratum-1.json) | 21轮：13 kept/8 failed_harness；两端清单逐字节一致、只读；受影响输出hypothesis已登记 |',
 'T05':'| T05 | 待D06 GPU自检及E2-base.1 | — | R020默认门已独立复核封存kept；G3/G4先前客户端分词停滞，无实际GPU结果；P0后新基线验证T05 |',
 'T10':'| T10 | 历史测量封存、R013分类完成；D14重跑待T17 | [R017](01_测试与调研/results/T10-E2-R017_20261004.md)、[R013](01_测试与调研/results/T10-E2-R013_20261004.md)、[分类](../development/p0_r013_classification.md) | 旧冷热33/36不同；11分叉位置3/5/3；R013的11对FP32逐位相同、restore proof均null，只证明预热前缀协议可复现；修复版3进程×12轮和机制归因仍待 |',
 'T16':'| T16 | D00/D01/D02/D03/D06/D14默认门通过 | [D14 R022](01_测试与调研/results/T16-E2-R022-gate-D14_20261004.md)、[R021失败](01_测试与调研/results/T16-E2-R021-gate-D14_20261004.md)、[D03](01_测试与调研/results/T16-E2-R002-gate-D03_20261004.md) | R020/R022四臂独立复核封存kept；R019/R021真实夹具、共同工装39PASS；T16不代替命中续算T17 |',
 'T17':'| T17 | R023/b51真实GPU执行中 | [工具](../development/t17_d14_README.md)、[核查要求](../development/T17_gpu_review_blockers.md)、[初始状态影响](../development/D14_initial_state_impact.md) | 准确Linux14+10+3PASS、正常spawn四观察器及signed-zero字节负对照PASS，14源文件冻结；四边界donor2、短/长各128token与独立cold，尚无GPU接受结论 |',
 'D04':'| D04 | 收尾、正式判定及FTD-20261004-1已发布 | [工具记录](../development/d04_design_notes.md)、[发布结果](01_测试与调研/results/T01-FTD-20261004-1_20261004.md) | 新数据版13 kept/8 failed_harness；测量判定与输出/归因hypothesis分开；R022随后独立封存，未原地改数据版 |',
 'D06':'| D06 | 候选及R020默认门通过；G3/G4/T05待 | [交付](02_开发任务/D06_交付记录_20261004.md)、[进展](../development/d06_progress.md) | 0369263准确Linux69PASS；R019失败保留，R020四臂独立复核封存kept；G3/G4先前分词停滞已清理所属进程，无实际GPU结果；P0后新基线验证 |',
 'D14':'| D14 | 候选及R022默认门通过；T17运行中，T10待 | [交付](02_开发任务/D14_交付记录_20261004.md)、[P0进展](../development/p0_ngram_progress.md) | e4f3202；CPU13 failed→13 passed、387PASS/2已有FAIL/14SKIP；R021 failed_harness保留，R022独立复核封存kept；未合入E2-base.1 |',
 'Q1':'| Q1 | 已解决：R021/R022所属进程停止后已释放锁；R023/b51通过资源门，持有自己的T17锁 | 每臂重新核验GPU/8095/源码/所属PID；不移除其他轮次或陈旧锁 |',
}
path=ROOT/'plan/README.md';original=path.read_bytes();source=original.decode('utf-8')
for card,row in rows.items():
 source,count=re.subn(r'(?m)^\| '+card+r' \|[^\r\n]*',lambda _:row,source)
 if count!=1:raise ValueError('exact one current status row required: '+card)
if path.read_bytes()!=original:raise ValueError('plan changed during merge')
path.write_bytes(source.encode('utf-8'))
path=ROOT/'development/development_status.json';original=path.read_bytes();doc=json.loads(original)
stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
doc['revision']+=1;doc['updated_at']=stamp
card=next(x for x in doc['development'] if x['card']=='D14')
card.update(status='T16通过；T17验证中',updated_at=stamp,
 next_step='R022默认四臂门已独立复核D04封存kept；R023/b51实际命中续算T17执行中。通过T17及D07默认门后合成E2-base.1，再T10和同判卷器60题。',
 blockers=['T17和修复版T10无接受结论；D07默认门及E2-base.1合入仍待，不标D14完成。'])
for name,summary in [('development/t16_r022_close_receipt.json','R022四臂独立复算PASS，74原始文件未变，D04kept只读封存'),
                     ('development/t17_d14_cpu_receipt.json','Linux14+10+3PASS，四wrapper正常spawn CUDAfalse及uint8 signed-zero负对照PASS，14源文件冻结'),
                     ('development/t17_d14_E2-R023-gate-T17_launch_receipt.json','R023/b51实际启动，PID/PGID300919；尚无GPU接受结论')]:
 item={'path':name,'sha256':hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),'summary':summary}
 card['evidence']=[x for x in card['evidence'] if x['path']!=name]+[item]
if path.read_bytes()!=original:raise ValueError('status changed during merge')
path.write_bytes((json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode())
print(json.dumps({'revision':doc['revision'],'updated_at':stamp}))
