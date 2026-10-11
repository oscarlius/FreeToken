"""Current-evidence report authorized by the user's 07:55 revision."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path('/data2/FreeToken')
NIGHT = ROOT / 'development/night_execution_20261009'
PLAN = ROOT / 'plan'


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    module = import_file('morning', NIGHT / 'morning_report_readonly_v3.py')
    cfg = module.load()
    module.pins(cfg)
    git = module.git(cfg)
    prod = ROOT / 'runs/production/RESTORE481-NIGHT-20261009-01'
    obs = prod / 'overnight_observation'
    rows = [json.loads(x) for x in (obs / 'samples.jsonl').read_text().splitlines() if x.strip()]
    start = json.loads((obs / 'start.json').read_text())
    if (obs / 'terminal.json').exists():
        raise RuntimeError('Current report expects an unfinished observation; read actual terminal instead')
    stamp = datetime.datetime.now().astimezone().isoformat()
    summary = module.summarize(rows)
    scope = 'PENDING_USER_APPROVAL_OBSERVATION_IN_PROGRESS' if git['scope_matches'] else 'BLOCKED_OR_UNKNOWN'
    receipt = {'at': stamp, 'scope': 'current evidence, not09terminal', 'new_observation_status': 'in_progress', 'start': start['at'], 'samples': len(rows), 'summary': summary, 'last_sample': rows[-1], 'git': git, 'source_pins': cfg['pinned'], 'user_directive_sha256': hashlib.sha256((PLAN / 'MORNING_REVIEW_20261010_0745.md').read_bytes()).hexdigest(), 'push_approved': False, 'push_executed': False}
    table = import_file('oldtable', NIGHT / 'morning_report_readonly_v1.py').TABLE.replace('S1/S2retry1 parallel=1, no MTP', 'S1 MTP OFF; S2retry1 MTP ON; parallel=1 queued')
    report = f'''# 2026-10-10 当前证据早报

真实写入：{stamp}。按用户07:55修订立即出报，不等待09:00。早报等待程序已按精确PID/出生时间停止；原观察暂继续，首个CPU独审通过项目就绪后停481并如实截断。尚无最终观察终态。

{table}
## 新解释与下一轮

依照07:45主会话核查记录，R067d-retry1原formal not_met保持，但热种子512+7681与冷donor8193一段的切分不同，donate边界36层状态已不同；不能作为短尾机制/C3被否定的证据。retry2复刻真实种子切分，并先比较donor@P状态哈希，相异则failed_harness停止。

D10原formal FAILED_HARNESS保持；5.855077/1.064367来自每步清空lane缓存的缺陷原型，不能否定错相位重叠机制。持久化/ownership epoch修复后复测；论文/README/claim map同步更正。在R067retry2和D10复测出结果之前不出PDF、不投稿。

R047/T03b修复64页对齐快照；R052a差128记H-bug，D05排查。R044旧三轮failed_harness不改判，CPU别名表复审仅诊断，R044b为新轮。Strata S4验证parallel2+真实batch-MTP opt-in；S3没有此opt-in。

## 生产与观察

481于04:49:08完成唯一首次冷SDK冒烟，17字段逐项匹配df77cb1471d199b527e671d4a9f3e36b5e37e3ce2bb965df9180c560aa6f9d97，无184回滚。新观察当前{len(rows)}样本，状态in_progress；实际统计={json.dumps(summary, ensure_ascii=False)}。首条窗口前50.99秒loading快照保留，不改为clean PASS。原观察17:35:56→22:41:20为truncated，306样本0issues，不能称隔夜通过。

Strata同v0.1.41同构建：S1无MTP冷32K61.4–63.35/短60.44–66.31；S2开MTP冷/短均值77.17/79.06，原提示聚合64.6189（S1为48.4182，parallel1排队）；S3两路20.6089/40.5569、聚合35.4811，未达两路均>30。ignore_eos固定256不支持，52/60仅R001历史。D09/D10 T16 kept均只是默认关闭门，启用路径不提前认定通过。

## 准备时间线

A R067d-retry2 CPU独审预计08:40；B S4 08:20/R044b09:00；C D10 lane缓存11:00；D T03b首版12:00；E D09-T17启动修复09:00/D05排查10:00。偏差>30分钟更新。GPU取首个已独审项串行接入，无可跑项时恢复481。13:00为状态与下午时间线汇报点，不是截止。

并发>2、持续负载>30分钟或打满CPU/内存/PCIe/磁盘均属于压力测试，必须预先报告范围、并发、时长、影响，用户知悉之后执行。当前各项预期<=2并发，仍逐项核对时长和影响。

## 推送与证据

状态{scope}。未获批准，未推送；目标仅origin release/e2精确481，不含D09/D10/R047调试代码、夜间工装或论文。实时Git={json.dumps(git, ensure_ascii=False)}。

证据快照：development/night_execution_20261009/MORNING_REPORT_CURRENT_EVIDENCE.json。旧轮原始字节、manifest、独审、终态保留，修正追加，不重复出同结论V2/V3文件。英文全文历史V9来源独审通过，当前解释更正后需要重新核对来源；无PDF、无arXiv提交，多卡仍DERIVED/PROPOSED。GitHub MTP查询见_shared/research/GITHUB_MTP_SCHEMES_20261010.md。
'''
    proposal = f'''# 2026-10-10 当前推送申请

真实写入：{stamp}；状态{scope}；未批准、未执行推送。

拟推送https://github.com/FlashML-org/FreeToken.git的refs/heads/release/e2，仅SHA481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9。相对184c965964b5f79deaecf1b1e3e0eda3187c829d为40提交/91文件/+11964/-129；实时scope_matches={git['scope_matches']}，远端ref={git['remote_head']!r}，查询成功={git['remote_read_success']}。不使用force；排除D09/D10/R047调试树、夜间包、论文。

原新观察在进行中，没有原09:00终态，首条旧loading需复核；本早报由07:55新指令授权提前生成，不把in_progress写成通过。请用户另行裁决观察条件并明确批准以上精确范围；本申请不自动豁免门。

证据：plan/MORNING_REPORT_20261010.md、development/night_execution_20261009/MORNING_REPORT_CURRENT_EVIDENCE.json；首次冷根回读SHAb6f2e4dd1f4dbc7c95b95bd80f5481069b7b7ec4cac1c0e0c87110e93805d21e。
'''
    targets = [(NIGHT / 'MORNING_REPORT_CURRENT_EVIDENCE.json', json.dumps(receipt, ensure_ascii=False, indent=2) + '\n'), (PLAN / 'MORNING_REPORT_20261010.md', report), (PLAN / 'PUSH_APPLICATION_20261010.md', proposal)]
    if any(p.exists() for p, _ in targets):
        raise RuntimeError('Current report exists; append corrections instead of overwrite')
    for p, text in targets:
        with p.open('x', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
    event = {'at': datetime.datetime.now().astimezone().isoformat(), 'event': 'MORNING_REPORT_NOW_WRITTEN', 'observation_status': 'in_progress', 'samples': len(rows), 'report_sha256': hashlib.sha256(targets[1][0].read_bytes()).hexdigest(), 'proposal_sha256': hashlib.sha256(targets[2][0].read_bytes()).hexdigest(), 'push_approved': False, 'push_executed': False}
    with (NIGHT / 'COORDINATION_LOG.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(event, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    print(json.dumps(event, ensure_ascii=False))


if __name__ == '__main__':
    main()
