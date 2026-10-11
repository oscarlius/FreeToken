"""Finalize prediction pointers and the current CPU-preparation handoff."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    now = datetime.now(timezone(timedelta(hours=8))).isoformat()
    package = ROOT / 'development/d09_prediction_20261009'
    prediction = package / 'PREDICTION_MANIFEST_v4.json'
    manifest = json.loads(prediction.read_text(encoding='utf-8'))
    seal = json.loads((package / 'SEAL_RECEIPT_v4.json').read_text(encoding='utf-8'))
    canonical_sha = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    assert canonical_sha == seal['canonical_json_sha256']
    assert [r['round'] for r in manifest['eligible_predictions']] == [7, 10]
    assert not subprocess.check_output(['git', '-C', str(ROOT / 'development/e2d09-message-boundary-v1'), 'status', '--porcelain'], text=True).strip()
    refs = {
        'recorded_at': now, 'status': 'SEALED_BEFORE_ACTIVE_ENGINE_IMPLEMENTATION',
        'manifest': prediction.name, 'sha256': sha(prediction), 'canonical_json_sha256': canonical_sha,
        'original_seal': 'SEAL_RECEIPT_v4.json', 'original_sealed_at': seal['sealed_at'],
        'binding_files': {name: sha(package / name) for name in [
            'reproduce_tokenizer_boundaries.py', 'CPU_REPRODUCER_STDOUT_v3.json', 'source/SOURCE_MANIFEST.json']},
        'historical_invalid_manifests': ['PREDICTION_MANIFEST.json', 'PREDICTION_MANIFEST_v2.json', 'PREDICTION_MANIFEST_v3.json'],
        'active_worktree_clean': True, 'engine_integration': 'pending', 'gpu_acceptance': 'pending',
    }
    (package / 'CURRENT_PREDICTION.json').write_text(json.dumps(refs, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for path in [prediction, package / 'SEAL_RECEIPT_v4.json', package / 'CURRENT_PREDICTION.json']:
        path.chmod(stat.S_IREAD)
    card = ROOT / 'plan/02_开发任务/D09_机制D3_基于577的层优先触发点.md'
    with card.open('a', encoding='utf-8') as f:
        f.write(f'''
## 有效预测封存（{now}追加）

有效版本为 `development/d09_prediction_20261009/PREDICTION_MANIFEST_v4.json`，原封存时间 `{seal['sealed_at']}`。

文件字节SHA256：`{refs['sha256']}`；规范JSON SHA256：`{canonical_sha}`。`CURRENT_PREDICTION.json`绑定复现脚本与CPU原始输出，早先v1/v2/v3均已标无效，不可消费。v1曾误用占位时间及LCP，相关初始CPU辅助代码已移入invalid历史，活动D09树干净；此次真实时间封存在后续有效引擎实现之前。

| 历史基线行（0起算） | 前缀token | 到完整prompt末端尾段 | 到生成header尾段 | 基线TTFT s | 预测TTFT s |
|---|---:|---:|---:|---:|---:|
| E1-R003-v4/C_edit round7 | 20282 | 1020 | 1015 | 5.376 | 2.8（情景2.7–2.9） |
| E1-R003-v4/C_edit round10 | 22558 | 197 | 192 | 5.324 | 2.8（情景2.7–2.9） |

旧c721渲染/tokenizer的CPU复算与五个候选实际prompt长度全部相符，采用相邻两个`im_start`的字面消息边界，额外以完整prompt尾段保守筛选。第5/6/8轮尾段1766/4750/1058超限；第9轮已有一遍，仅作控制。以上为历史T2形状上的模型预测，不是481新测量，不追认历史warm正确性；新树三趟回放仍须实测。逐轮将报告实际减2.8秒的残差、遍数与原因。检查点接线、T16/T17/T03b和GPU验收仍待完成。
''')
    for name in ['RELEASE_PROPOSAL_E2_20261009.md', 'RELEASE_NOTES_E2_DRAFT_20261006.md', 'DEPLOY_ROLLBACK_E2_DRAFT_20261006.md']:
        path = ROOT / 'development' / name
        prior = HERE / 'prior_docs/development' / name
        prior.parent.mkdir(parents=True, exist_ok=True)
        if not prior.exists():
            prior.write_bytes(path.read_bytes())
        text = path.read_text(encoding='utf-8')
        banner = '> 10-09晚间更新：D09/D10及X-STRATA-R002-mini已批准，GPU按[新队列](../plan/EVENING_DIRECTIVE_20261009.md)；mini在v0.1.39的无MTP HTTP服务被源码门阻塞，未测。推送仍待10-10 09:00观察报告后的申请与批准。下文“Strata未批”仅是旧状态。\n\n'
        if banner not in text:
            path.write_text(banner + text, encoding='utf-8')
    readme = ROOT / 'README.md'
    text = readme.read_text(encoding='utf-8')
    text = text.replace('独立481开发树已建，GPU按', '独立481开发树已建；D09第7/10轮预测与D10条件区间已封存，机制接线及CUDA原型尚待完成。GPU按', 1)
    readme.write_text(text, encoding='utf-8')
    with (ROOT / 'plan/COORDINATION_LOG.md').open('a', encoding='utf-8') as f:
        f.write(f'\n- {now} root：D09无效预测草案保留并排除；用旧c721实际tokenizer只读CPU复现五候选prompt长度，正式v4仅编辑round7/10合格，预测5.376/5.324→2.8秒；文件SHA {refs["sha256"]}，CURRENT只读绑定。活动D09工作树干净，检查点尚未接线。D10预测不变，7项CPU完整性测试通过；CUDA原型未实现。论文v5.2独审及双视口通过，Strata mini源码门阻塞。快照123样本0告警epoch0restart0，不代表隔夜终态；GPU零启动、无推送。\n')
    receipt = {'recorded_at': now, 'd09_prediction': refs, 'd10_prediction_sha256': sha(ROOT / 'development/d10_staggered_20261009/prediction_manifest.json'),
        'paper_html_sha256': sha(ROOT / 'paper/FreeToken_MultiGPU_CoExec_v5.2.html'),
        'independent_review_sha256': sha(HERE / 'INDEPENDENT_PAPER_REVIEW.json'),
        'render_check_sha256': sha(HERE / 'RENDER_CHECK.json'),
        'd10_cpu_tests': '7 passed', 'cuda_prototype': 'pending', 'd09_checkpoint_integration': 'pending',
        'strata_mini': 'blocked_source_gate', 'gpu_calls': 0, 'service_mutations': 0, 'git_push': False}
    (HERE / 'PREPARATION_HANDOFF.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'recorded_at': now, 'd09_byte_sha256': refs['sha256'], 'd09_canonical_sha256': canonical_sha}, indent=2))


if __name__ == '__main__':
    main()
