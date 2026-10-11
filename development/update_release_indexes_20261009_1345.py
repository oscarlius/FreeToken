"""Refresh release status indexes only; starts no service and performs no SSH."""
import hashlib
import json
from pathlib import Path

FT = Path(__file__).resolve().parents[1]
ARCHIVE = FT / 'development/release_history'
STATUS = ('部署CPU工具v2本地及Linux39 passed、0 skipped；真实冒烟未执行。'
          'H2只读预检：184参数合法、历史68条Prefill正则匹配；ignored文件非空阻断回滚启动，'
          '历史日志无API usage，须后续独占SDK冒烟补证。'
          'R067按13:45获批4格/10服务/14调用，正核对既有T17入口；尚无GPU结果。'
          'R045已完成481+AIPerf两路并发CPU规划（2服务/4调用），部署后另排。'
          '部署、推送与Strata22/345均未批准。')


def preserve(path):
    target = ARCHIVE / (path.stem + '_pre1340_20261009' + path.suffix)
    if not target.exists():
        target.write_bytes(path.read_bytes())


def main():
    ARCHIVE.mkdir(exist_ok=True)
    draft = FT / 'plan/data_releases/E2_RELEASE_CANDIDATE_DRAFT_20261009.json'
    preserve(draft)
    value = json.loads(draft.read_text(encoding='utf-8'))
    value['status'] = 'release_gate_closed_branch_created_CPU39_H2_blocked_no_deployment'
    value['updated_by_directive'] = '2026-10-09 13:40 / 13:45'
    value['release_directive'] = 'plan/RELEASE_DIRECTIVE_20261009_1345.md'
    value['authority']['latest_operations'] = 'plan/RELEASE_DIRECTIVE_20261009_1340.md'
    value['authority']['latest_R067'] = value['release_directive']
    value['code']['worktree'] = '/data2/FreeToken/wt/release-e2'
    value['release_scope']['remaining'] = ['operations review', 'deployment approval', 'push approval']
    value['proposed_runtime_entry']['CPU_archive'] = '/data2/FreeToken/runs/dev_release/release_e2_ops_v4_20261009_1340'
    value['proposed_runtime_entry']['CPU_tests'] = {'local_passed': 39, 'Linux_passed': 39, 'skipped': 0, 'live_smoke_run': False}
    value['rollback']['H2_readonly_preflight'] = {
        'status': 'blocked_dirty_rollback_worktree',
        'git_status_ignored_empty': False,
        'source_modified_or_cleaned': False,
        'exact_argv_help_exit': 0,
        'historical_prefill_regex_matches': 68,
        'historical_API_usage_available': False,
        'evidence': 'development/release_e2_ops_v2/rollback_preflight_evidence/h2_deep_check.json',
        'server_archive': '/data2/FreeToken/runs/dev_release/rollback_preflight_20261009_1340_v1'}
    value['downstream']['R045'] = '481+AIPerf CPU plan complete; proposed 2 fresh services/4 generation calls, deployment-after only; old v18 dependency blocked unchanged'
    value['downstream']['D20'] = 'd50be0f development-schedule-only fix; R067 latest13:45 approved4cells10services14calls; no GPU result yet; original481 hot unchanged'
    value['downstream']['all_GPU'] = 'R067 authorized preparation pending startup admission; R045 CPU only, Strata22/345 unapproved'
    paper = FT / 'paper/FreeToken_MultiGPU_CoExec_v5.1.html'
    value['downstream'].update(paper_version='v5.1', paper_path=paper.relative_to(FT).as_posix(),
        paper_sha256=hashlib.sha256(paper.read_bytes()).hexdigest(),
        paper_final_independent_review='15-item v5.1 textual revision PASS; R067 erratum not applied')
    value['R067_authorized'] = {'rid': 'E2-R067-d20-short-tail', 'prefixes': [8192, 8256],
        'tails': [1, 64], 'cells': 4, 'services_max': 10, 'generation_calls_max': 14,
        'hot_commit': value['code']['commit'], 'cold_commit_short': 'd50be0f',
        'generation_calls_actual': 0, 'service_started': False, 'state': 'preparing_existing_T17_reuse',
        'paper_erratum_applied': False}
    value['remaining'] = ['review corrected operations materials', 'resolve H2 rollback dirty-tree blocker and API-usage evidence gap',
        'execute authorized R067 or report concrete no-code tooling blocker', 'deployment approval', 'push approval',
        'production graph2 cold smoke and live observation after approval']
    draft.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    readme = FT / 'README.md'
    preserve(readme)
    text = readme.read_text(encoding='utf-8')
    start = text.index('## 13:00 发布指令落实（当前状态）')
    end = text.index('## 当前交付', start)
    text = text[:start] + '## 13:40 / 13:45 当前发布状态\n\n' + STATUS + '\n\n[发布方案](development/RELEASE_PROPOSAL_E2_20261009.md) · [H2预检](development/release_e2_ops_v2/rollback_preflight_evidence/H2_DEEP_CHECK_SUMMARY_20261009.md) · [R045新计划](development/r045_aiperf_481_cpu_v1/README.md)。\n\n' + text[end:]
    readme.write_text(text, encoding='utf-8')
    summary = FT / 'plan/MORNING_SUMMARY_20261009.md'
    preserve(summary)
    prior = summary.read_text(encoding='utf-8')
    summary.write_text('# 当前进展摘要（2026-10-09，13:40 / 13:45修订）\n\n' + STATUS +
        '\n\n≤64正确性待证仍保留；仅R067四格实际有效PASS才更新论文C3。源代码发布门已闭合与运维可部署状态分开报告。\n\n以下为历史快照。\n\n' + prior, encoding='utf-8')
    coord = FT / 'plan/COORDINATION_LOG.md'
    with coord.open('a', encoding='utf-8') as handle:
        handle.write('\n\n## 2026-10-09 13:40 / 13:45 修订\n\n' + STATUS + '\n')
    print(json.dumps({'CPU_only': True, 'indexes_updated': 4, 'deployment': False, 'push': False}))


if __name__ == '__main__':
    main()
