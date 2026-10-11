"""Refresh the local handoff snapshot from one bounded host observation."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def atomic_json(path, value):
    payload = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    captured = subprocess.run([sys.executable, 'development/remote.py',
                               'development/d03_consumer_observe.sh'], cwd=ROOT,
                              check=True, capture_output=True, text=True, encoding='utf-8')
    observed = json.loads(captured.stdout)
    path = ROOT / 'development/dashboard_handoff/snapshot.json'
    snapshot = json.loads(path.read_text(encoding='utf-8'))
    snapshot.update(observed_at=observed['observed_at'], revision=snapshot['revision'] + 1)
    d03 = next(row for row in snapshot['development'] if row['card'] == 'D03')
    failed = observed['status'].get('state') == 'error'
    d03.update(updated_at=observed['observed_at'], next_step=('T16 已复核封存；T04 恢复臂异常退出，正在核对真实恢复证据。' if failed
               else 'T16 已复核封存；T04 阶段2正在测量，随后执行 T10。'),
               blockers=['T04/T10 业务验收仍待，正式 verdict 单独维护。'])
    report_path = 'plan/01_测试与调研/results/T16-E2-R002-gate-D03_20261004.md'
    d03['evidence'] = [row for row in d03['evidence'] if row['path'] != report_path]
    d03['evidence'].append({'path': report_path,
                            'summary': 'T16 独立复核 PASS，历史链及只读清单校验通过',
                            'sha256': observed['t16_manifest_sha256']})
    t16 = next(row for row in snapshot['tests'] if row['rid'] == 'E2-R002-gate-D03')
    t16.update(stage='已封存待判定', execution_status='已结束', pid_alive=False,
               status_updated_at=observed['t16_closed_at'], review_status='独立01复核 PASS', sealed=True,
               formal_verdict=observed['t16_formal_verdict'], process_observer='D04 封存及历史链校验')
    snapshot['tests'] = [row for row in snapshot['tests'] if row['rid'] != observed['rid']]
    measured = observed['status'].get('state') == 'complete_measurements_pending_review'
    stage = '异常' if failed else ('测量结束待复核' if measured else ('测试中' if observed['pid_alive'] and observed['identity_verified'] else '进程状态未知'))
    snapshot['tests'].insert(0, {'card': 'T04', 'rid': observed['rid'], 'batch': observed['batch'],
        'stage': stage, 'execution_status': stage, 'batch_pid': observed['batch_pid'],
        'pid_alive': observed['pid_alive'], 'identity_verified': observed['identity_verified'],
        'process_observer': '宿主机 SSH 只读 /proc 身份观察，' + observed['observed_at'],
        'status_updated_at': None, 'elapsed_s': None, 'progress': None,
        'review_status': '待独立复核', 'sealed': False, 'formal_verdict': None,
        'evidence': [{'path': '/data2/_shared/runs/ft_rounds/E2-R014/',
                      'summary': '已存在 capture.json 的臂：' + ', '.join(observed['captured_arms'])}]})
    t11, status11 = observed['t11'], observed['t11']['status']
    snapshot['tests'] = [row for row in snapshot['tests'] if row['rid'] != 'E2-R011']
    proof11 = t11['sealed_proof']
    stage11 = ('已封存待判定' if proof11 else '异常' if status11['state'] == 'failed' else '测量结束待复核' if status11['state'] == 'complete'
               else '测试中' if t11['pid_alive'] and t11['identity_verified'] else '进程状态未知')
    snapshot['tests'].insert(0, {'card': 'T11', 'rid': 'E2-R011', 'batch': 40, 'stage': stage11,
        'execution_status': stage11, 'batch_pid': 2569357, 'pid_alive': t11['pid_alive'],
        'identity_verified': t11['identity_verified'], 'process_observer': '宿主机 SSH 只读 /proc 身份观察，' + observed['observed_at'],
        'status_updated_at': status11.get('updated_at'), 'elapsed_s': None, 'progress': None,
        'review_status': '独立01复核 PASS；写回科学分类未解决', 'sealed': True, 'formal_verdict': proof11['formal_verdict'],
        'evidence': [{'path': '/data2/_shared/runs/ft_rounds/E2-R011/',
                      'summary': '11次真实恢复；目标命中13376/续算56；历史11长度44张量逐位一致，目标写回归因待定',
                      'sha256': proof11['manifest_sha256']}]})
    snapshot['tests'] = [row for row in snapshot['tests'] if row['rid'] != 'E2-R012']
    snapshot['tests'].insert(0, {'card': 'T10', 'rid': 'E2-R012', 'batch': 41, 'stage': '异常',
        'execution_status': '加载前异常退出', 'batch_pid': 2628647, 'pid_alive': observed['t10_failed']['pid_alive'],
        'identity_verified': False, 'process_observer': '宿主机只读 /proc，' + observed['observed_at'],
        'status_updated_at': None, 'elapsed_s': None, 'progress': None,
        'review_status': '启动环境错误已确认；无科学测量', 'sealed': False, 'formal_verdict': None,
        'evidence': [{'path': '/data2/_shared/runs/ft_rounds/E2-R012/',
                      'summary': '启动包装将GPU设为不可见，原失败工件保留；R016随后完成12条后因HTTP终止原因校验失败'}]})
    snapshot['errors'] = ([{'source': 'T04 E2-R014 batch39', 'message': 'T04 恢复臂未证明实际恢复，测量已异常退出；失败工件保留，正在核对恢复条件。'}]
                          if failed else [])
    snapshot['errors'].append({'source': 'T10 E2-R012 batch41', 'message': '启动环境未暴露GPU，测量未开始；原失败证据保留。'})
    retry = observed['t10_retry']
    retry_state = retry['status']['state']
    retry_stage = ('异常' if retry_state == 'error' else '测量结束待复核' if retry_state == 'complete_measurements_pending_review'
                   else ('加载' if retry['loading'] else '测试中') if retry['pid_alive'] and retry['identity_verified'] else '进程状态未知')
    snapshot['tests'] = [row for row in snapshot['tests'] if row['rid'] != 'E2-R016']
    snapshot['tests'].insert(0, {'card': 'T10', 'rid': 'E2-R016', 'batch': 42, 'stage': retry_stage,
        'execution_status': retry_stage, 'batch_pid': 2672941, 'pid_alive': retry['pid_alive'],
        'identity_verified': retry['identity_verified'], 'process_observer': '宿主机只读 /proc 身份观察，' + observed['observed_at'],
        'status_updated_at': None, 'elapsed_s': None,
        'progress': {'done': retry['terminal_records'], 'total': retry['terminal_records_total'], 'label': '实际引擎终端记录'},
        'review_status': '待独立复核', 'sealed': False, 'formal_verdict': None,
        'evidence': [{'path': '/data2/_shared/runs/ft_rounds/E2-R016/',
                      'summary': '实际终端记录计数；R016已因HTTP tool_calls与engine stop映射校验错误停止，原工件保留' if retry_state == 'error'
                                 else '源码已复核冻结；Linux CPU10PASS，CUDA环境已修正，真实72记录测量'}]})
    if retry_state == 'error':
        snapshot['errors'].append({'source': 'T10 E2-R016 batch42',
                                  'message': '12/72条后异常：HTTP工具终止tool_calls未按引擎stop校验；新R017已复核、Linux28PASS并冻结后启动。'})
    retry15 = observed['t04_retry']
    state15 = retry15['status']['state']
    stage15 = ('异常' if state15 == 'error' else '测量结束待复核' if state15 == 'complete_measurements_pending_review'
               else ('加载' if retry15['loading'] else '测试中') if retry15['pid_alive'] and retry15['identity_verified'] else '进程状态未知')
    snapshot['tests'] = [row for row in snapshot['tests'] if row['rid'] != 'E2-R015']
    snapshot['tests'].insert(0, {'card': 'T04', 'rid': 'E2-R015', 'batch': 43, 'stage': stage15,
        'execution_status': stage15, 'batch_pid': 2749339, 'pid_alive': retry15['pid_alive'],
        'identity_verified': retry15['identity_verified'], 'process_observer': '宿主机只读 /proc 身份观察，' + observed['observed_at'],
        'status_updated_at': None, 'elapsed_s': None,
        'progress': {'done': len(retry15['captured_arms']), 'total': retry15['capture_total'], 'label': '完成capture的实际臂'},
        'review_status': '工装独立复核和Linux20PASS；测量待复核', 'sealed': False, 'formal_verdict': None,
        'evidence': [{'path': '/data2/_shared/runs/ft_rounds/E2-R015/',
                      'summary': '已完成臂：' + ', '.join(retry15['captured_arms'])}]})
    if state15 == 'error':
        snapshot['errors'].append({'source': 'T04 E2-R015 batch43', 'message': '实际host恢复12416，与预定12672不符；工装严格拒绝，检查请求历史和实际分块边界。'})
    bridge = observed['t10_bridge_retry']
    bridge_state = bridge['status']['state']
    bridge_stage = ('异常' if bridge_state == 'error' else '测量结束待复核' if bridge_state == 'complete_measurements_pending_review'
                    else ('加载' if bridge['loading'] else '测试中') if bridge['pid_alive'] and bridge['identity_verified'] else '进程状态未知')
    snapshot['tests'] = [row for row in snapshot['tests'] if row['rid'] != 'E2-R017']
    snapshot['tests'].insert(0, {'card': 'T10', 'rid': 'E2-R017', 'batch': 44, 'stage': bridge_stage,
        'execution_status': bridge_stage, 'batch_pid': 2786369, 'pid_alive': bridge['pid_alive'],
        'identity_verified': bridge['identity_verified'], 'process_observer': '宿主机只读 /proc 身份观察，' + observed['observed_at'],
        'status_updated_at': None, 'elapsed_s': None,
        'progress': {'done': bridge['terminal_records'], 'total': bridge['terminal_records_total'], 'label': '实际引擎终端记录'},
        'review_status': '工装独立复核、Linux28PASS；测量待复核', 'sealed': False, 'formal_verdict': None,
        'evidence': [{'path': '/data2/_shared/runs/ft_rounds/E2-R017/', 'summary': '严格HTTP tool_calls→engine stop映射，其余原始token绑定保持'}]})
    proof17 = bridge.get('sealed_proof')
    if proof17:
        row17 = next(row for row in snapshot['tests'] if row['rid'] == 'E2-R017')
        row17.update(stage='已封存待判定', execution_status='测量已结束',
                     status_updated_at=proof17['closed_at'], review_status='原始测量及元数据独立复核PASS；11个分叉待阶段2定位',
                     sealed=True, formal_verdict=proof17['formal_verdict'])
        row17['evidence'].append({'path': '/data2/_shared/runs/ft_rounds/E2-R017/MANIFEST.sha256',
                                  'summary': '三进程冷/热各自36/36一致；冷热3/36一致、33/36不同；11实际token分叉，D04历史及只读清单通过',
                                  'sha256': proof17['manifest_sha256']})
    if bridge_state == 'error':
        snapshot['errors'].append({'source': 'T10 E2-R017 batch44', 'message': bridge['status'].get('error', '测量异常，待诊断')})
    d03.update(next_step=('T10 R017异常，检查实际证据；T04分块边界请求历史诊断中。' if bridge_state == 'error'
                         else 'T10 R017测量结束待复核；T04分块边界请求历史诊断中。' if bridge_state == 'complete_measurements_pending_review'
                         else 'T10 R017测量中；T04 R015实际恢复长度不符，诊断分块边界请求历史。'))
    if proof17:
        d03['next_step'] = 'T10 R017已复核封存，11个实际token分叉等待双新进程K1定位；T04边界构造CPU验证及新GPU门待完成。'
    fix_path = 'development/d03_continuation_fix.md'
    fix_file = ROOT / fix_path
    if fix_file.is_file():
        import hashlib
        d03['evidence'] = [row for row in d03['evidence'] if row['path'] != fix_path]
        d03['evidence'].append({'path': fix_path, 'summary': '普通分块诊断修复已独立复核、旧源447PASS/2原有FAIL/6SKIP；f506准确Git blob已在独立Linux26PASS，新GPU门待验证',
                                'sha256': hashlib.sha256(fix_file.read_bytes()).hexdigest()})
        d03['next_step'] += ' 普通分块诊断修复已有CPU证据，边界构造及新GPU门仍待。'

    d03['candidate_commit'] = 'f5067bbe05da51d5f78185213435a8be095a684a'
    d03['blockers'] = ['新修复候选f506已在独立服务器CPU26PASS，默认GPU门及实际12672恢复尚未验证；原c30的门不替代新门。', 'T04/T10业务验收及正式verdict仍待；T10 R013实测使用原c30。']
    stage2 = observed['t10_stage2']
    state2 = stage2['status']['state']
    stage2_label = ('异常' if state2 == 'error' else '测量结束待复核'
        if state2 == 'complete_measurements_pending_review' else
        ('加载' if stage2['loading'] else '测试中') if stage2['pid_alive'] and stage2['identity_verified']
        else '进程状态未知')
    snapshot['tests'] = [row for row in snapshot['tests'] if row['rid'] != 'E2-R013']
    snapshot['tests'].insert(0, {'card': 'T10-P2', 'rid': 'E2-R013', 'batch': 45,
        'stage': stage2_label, 'execution_status': stage2_label, 'batch_pid': 2977969,
        'pid_alive': stage2['pid_alive'], 'identity_verified': stage2['identity_verified'],
        'process_observer': '宿主机 SSH 只读 /proc 身份观察，' + observed['observed_at'],
        'status_updated_at': None, 'elapsed_s': None,
        'progress': {'done': stage2['capture_count'], 'total': stage2['capture_total'], 'label': '实际K1 capture'},
        'review_status': '工装独立复核PASS、Linux18PASS；测量待复核',
        'sealed': False, 'formal_verdict': None,
        'evidence': [{'path': '/data2/_shared/runs/ft_rounds/E2-R013/',
                      'summary': '已有成对比较摘要 ' + str(stage2['comparison_count']) + '/11；'
                        '11实际token分叉、每点两个新进程、K1 FP32全词表；探针先预热前缀再采集，科学分类待定'},
                     {'path': '/data2/FreeToken/runs/dev_D03/launch_E2-R013.json',
                      'summary': '由已封存R017输入启动的b45；完整源SHA和父轮工件绑定',
                      'sha256': stage2['receipt_sha256']}]})
    if state2 == 'error':
        snapshot['errors'].append({'source': 'T10 E2-R013 batch45',
                                  'message': stage2['status'].get('error', '阶段2测量异常，原工件保留')})
    if stage2.get('progress_errors'):
        snapshot['errors'].append({'source': 'T10 E2-R013进度观察',
                                  'message': '; '.join(stage2['progress_errors'])})
    import hashlib
    cpu_path = 'development/t04_boundary_cpu_prediction.json'
    cpu_sha = '57bf608c7cc752e061dd3dbdd5010dba2af84103529f498a35ba035275699610'
    if hashlib.sha256((ROOT / cpu_path).read_bytes()).hexdigest() != cpu_sha:
        raise ValueError('Linux CPU boundary prediction changed')
    d03['evidence'] = [row for row in d03['evidence'] if row['path'] != cpu_path]
    d03['evidence'].append({'path': cpu_path, 'sha256': cpu_sha,
        'summary': '真实Linux CPU10PASS；Y96归档12416、Y122归档12608、Y129预测归档12672；不等于GPU实际归档/恢复证明'})
    d03['next_step'] = ('T10 R013/b45已启动，实际采集 ' + str(stage2['capture_count']) + '/22，'
        '成对比较摘要 ' + str(stage2['comparison_count']) + '/11，全部完成后独立复核；'
        'T04 Y129已过真实CPU构造门，修复f506已提交并在独立服务器CPU26PASS，待新默认GPU门及新RID实际恢复验证。')
    raw_review_path = ROOT / 'development/t10_r013_raw_review.json'
    if raw_review_path.is_file() and state2 == 'complete_measurements_pending_review':
        raw_review = json.loads(raw_review_path.read_text(encoding='utf-8'))
        if (raw_review.get('rid'), raw_review.get('batch'), raw_review.get('verdict')) != ('E2-R013', 45, 'PASS'):
            raise ValueError('R013 independent raw review identity is invalid')
        if raw_review['integrity']['RUN_MANIFEST.sha256'] != stage2.get('run_manifest_sha256'):
            raise ValueError('R013 independent raw review does not bind the observed producer manifest')
        row13 = next(row for row in snapshot['tests'] if row['rid'] == 'E2-R013')
        row13['review_status'] = '原始FP32数据独立复核PASS；元数据复核和D04封存待完成'
        row13['evidence'].append({'path': 'development/t10_r013_raw_review.json',
            'sha256': hashlib.sha256(raw_review_path.read_bytes()).hexdigest(),
            'summary': '22个实际FP32 [1,248320]全有限；11对逐位一致/top1=1/KL=0。仅预热前缀后K1场景，科学归因待判断。'})
        d03['next_step'] = ('T10 R013已完成22/22采样和11/11比较，原始数据独立复核PASS；'
            '待元数据独立复核/D04封存，科学归因单列。T04新GPU门与实际恢复仍待；'
            '新T16 adapter服务器CPU16PASS，启动器冻结源执行和回执预约问题正在修正，尚未启动新GPU轮次。')
    proof13 = stage2.get('sealed_proof')
    if proof13:
        row13 = next(row for row in snapshot['tests'] if row['rid'] == 'E2-R013')
        row13.update(stage='已封存待判定', execution_status='测量已结束',
            status_updated_at=proof13['closed_at'], sealed=True,
            formal_verdict=proof13['formal_verdict'],
            review_status='原始测量与元数据独立复核PASS；科学归因待判断')
        row13['evidence'].append({'path': '/data2/_shared/runs/ft_rounds/E2-R013/MANIFEST.sha256',
            'sha256': proof13['manifest_sha256'],
            'summary': '父轮R017；D04封存、历史链和只读清单PASS。11对预热前缀K1 logits逐位一致，恢复证明null。'})
        d03['next_step'] = ('T10 R013已独立复核并D04封存，正式判定pending_review；'
            'T04修复f506的新T16 GPU门及实际恢复仍待，科学归因单列。')
    d06 = next((row for row in snapshot['development'] if row['card'] == 'D06'), None)
    if d06 is None:
        d06 = {'card': 'D06', 'title': '多会话测量工装与开发暂停端点', 'evidence': []}
        snapshot['development'].append(d06)
    d06.update(status='进行中', updated_at=observed['observed_at'],
        candidate_commit=None, next_step='源码及CPU检查完成后再冻结候选、排GPU门。',
        blockers=['T16/GPU自检/T05尚未执行。'])
    d06['evidence'] = [{'path': 'development/e2d06/',
        'summary': '独立工作树exp/e2d06，父树E2-base@23f2e2c'}]
    candidate_path = ROOT / 'development/d06_candidate_server.json'
    commit_path = ROOT / 'development/d06_candidate_commit.json'
    if candidate_path.is_file() and commit_path.is_file():
        cpu_report = json.loads(candidate_path.read_text(encoding='utf-8'))
        committed = json.loads(commit_path.read_text(encoding='utf-8'))
        if cpu_report['candidate_commit'] != committed['candidate_commit']:
            raise ValueError('D06 CPU report and committed candidate differ')
        if cpu_report['git_blob_files'] != committed['git_blob_files']:
            raise ValueError('D06 CPU report source hashes differ from commit')
        if cpu_report['returncode'] == 0 and cpu_report['tokenizer_proof']['state'] == 'passed':
            d06.update(status='已交付待验证', candidate_commit=cpu_report['candidate_commit'],
                next_step='源码候选0369263已安装独立服务器树、准确Git blob CPU69PASS；等待GPU串行队列执行T16默认门、G3/G4与T05。',
                blockers=['T16/G3/G4及T05均未执行，CPU通过不替代GPU或业务验收。',
                          'GPU任务串行执行；候选尚未完成业务验收。'])
            d06['evidence'].append({'path': 'development/d06_candidate_server.json',
                'summary': '准确提交Linux69PASS/6.32s；实际Qwen输入4000/32000/32052逐ID一致，左右前缀4 token；旧失败报告保留',
                'sha256': hashlib.sha256(candidate_path.read_bytes()).hexdigest()})
    for relative, summary in (
        ('development/d06_progress.md', '开发/CPU已完成、源码独立复核无剩余阻塞；GPU门和正式验收仍待'),
        ('plan/02_开发任务/D06_交付记录_20261004.md', '源码候选交付、完整父树和commit、需01验证的门及字段说明'),
    ):
        evidence_path = ROOT / relative
        if evidence_path.is_file():
            d06['evidence'].append({'path': relative, 'summary': summary,
                'sha256': hashlib.sha256(evidence_path.read_bytes()).hexdigest()})
    d07_path = ROOT / 'development/d07_progress.json'
    if d07_path.is_file():
        if d07_path.is_symlink() or d07_path.stat().st_size > 1024 * 1024:
            raise ValueError('D07 owner status must be a bounded regular JSON file')
        d07 = json.loads(d07_path.read_text(encoding='utf-8'))
        if d07.get('card') != 'D07' or d07.get('status') not in ('进行中','已交付待验证'):
            raise ValueError('D07 owner status is invalid')
        if d07['status'] == '进行中' and d07.get('candidate_commit') is not None:
            raise ValueError('D07 uncommitted status requires an explicit source scope')
        if d07['status'] == '已交付待验证':
            committed07 = json.loads((ROOT/'development/d07_candidate_commit.json').read_text(encoding='utf-8'))
            server07 = json.loads((ROOT/'development/d07_candidate_server.json').read_text(encoding='utf-8'))
            if (d07.get('candidate_commit') != committed07['candidate_commit']
                    or server07['candidate_commit'] != committed07['candidate_commit']
                    or server07['git_blob_files'] != committed07['git_blob_files']
                    or server07['returncode'] != 0 or server07['gpu_started'] is not False):
                raise ValueError('D07 delivered candidate and exact-source CPU proof differ')
        snapshot['development'] = [row for row in snapshot['development'] if row['card'] != 'D07']
        snapshot['development'].append(d07)
    candidate_gate = observed.get('t16_candidate')
    if candidate_gate:
        receipt, candidate_status = candidate_gate['receipt'], candidate_gate['status']
        state = candidate_status['state']
        label = ('异常' if state in ('error','failed') else '测量结束待复核'
            if state == 'complete_measurements_pending_review' else
            ('加载' if state == 'loading' else '测试中')
            if candidate_gate['pid_alive'] and candidate_gate['identity_verified'] else '进程状态未知')
        snapshot['tests'] = [row for row in snapshot['tests'] if row['rid'] != receipt['rid']]
        snapshot['tests'].insert(0, {'card':'T16','rid':receipt['rid'],'batch':receipt['batch'],
            'stage':label,'execution_status':label,'batch_pid':receipt['batch_pid'],
            'pid_alive':candidate_gate['pid_alive'],'identity_verified':candidate_gate['identity_verified'],
            'process_observer':'宿主机 SSH 只读 /proc 身份观察，'+observed['observed_at'],
            'status_updated_at':candidate_status.get('updated_at'),'elapsed_s':None,
            'progress':{'done':len(candidate_gate['measured_arms']),'total':candidate_gate['arm_total'],
                'label':'已生成测量摘要臂（非验收）'},
            'review_status':'工装最终源独立复核及Linux32PASS；测量待复核',
            'sealed':False,'formal_verdict':None,
            'evidence':[{'path':'/data2/FreeToken/runs/dev_D03/launch_'+receipt['rid']+'.json',
                'sha256':candidate_gate['receipt_sha256'],
                'summary':'c30父树→f506候选；当前臂 '+str(candidate_status.get('arm'))+'；8臂串行默认门'}]})
        d03['next_step'] = ('f506候选T16 '+receipt['rid']+'/b'+str(receipt['batch'])+'：'+label+
            '，当前臂 '+str(candidate_status.get('arm'))+'。待测量完成后独立复核；T04实际恢复仍待。')
        if candidate_gate.get('sealed_proof'):
            proof18 = candidate_gate['sealed_proof']
            row18 = next(row for row in snapshot['tests'] if row['rid'] == receipt['rid'])
            row18.update(stage='已封存待判定',execution_status='测量已结束',sealed=True,
                review_status='原始测量与元数据独立复核PASS；D04封存检查通过',
                status_updated_at=proof18['closed_at'],formal_verdict=proof18['formal_verdict'])
            row18['evidence'].append({'path':'/data2/_shared/runs/ft_rounds/'+receipt['rid']+'/MANIFEST.sha256',
                'sha256':proof18['manifest_sha256'],'summary':'8臂、6对全文/参数/序列及搬运计数复核；正式判定单列'})
            d03['next_step']='f506新T16已复核封存，正式pending_review；G3实际CPU复现已过，G4/G5开发自检和T04真实恢复待完成。'
            d03['blockers']=['G4/G5开发GPU自检及T04实际12672恢复尚待；正式verdict单独维护。',
                'T10已封存测量的科学归因未解决；现有T10原始测量使用c30。']
        if state in ('error','failed'):
            snapshot['errors'].append({'source':receipt['rid'],
                'message':candidate_status.get('error','候选门异常，保留失败工件')})
    gate06 = observed.get('t16_d06_candidate')
    if gate06:
        receipt06, status06 = gate06['receipt'], gate06['status']
        state06 = status06['state']
        label06 = ('异常' if state06 in ('failed','error') else '测量结束待复核'
            if state06 == 'complete_measurements_pending_review' else
            ('加载' if state06 == 'loading' else '测试中')
            if gate06['pid_alive'] and gate06['identity_verified'] else '进程状态未知')
        snapshot['tests'] = [row for row in snapshot['tests'] if row['rid'] != receipt06['rid']]
        snapshot['tests'].insert(0, {'card':'T16','rid':receipt06['rid'],'batch':receipt06['batch'],
            'stage':label06,'execution_status':label06,'batch_pid':receipt06['batch_pid'],
            'pid_alive':gate06['pid_alive'],'identity_verified':gate06['identity_verified'],
            'process_observer':'宿主机 SSH 只读 /proc 身份观察，'+observed['observed_at'],
            'status_updated_at':status06.get('updated_at'),'elapsed_s':None,
            'progress':{'done':len(gate06['measured_arms']),'total':gate06['arm_total'],
                'label':'已生成测量摘要臂（非验收）'},
            'review_status':'准确工装Linux32PASS；测量待独立复核',
            'sealed':False,'formal_verdict':None,
            'evidence':[{'path':'/data2/FreeToken/runs/dev_D03/launch_'+receipt06['rid']+'.json',
                'sha256':gate06['receipt_sha256'],
                'summary':'E2-base23f2父树→D06候选0369263；当前臂 '+str(status06.get('arm'))+'；4臂串行默认门'}]})
        d06['next_step'] = 'T16 '+receipt06['rid']+'/b'+str(receipt06['batch'])+'：'+label06+'。G3/G4及T05仍待。'
        d06['blockers'] = ['T16测量及独立复核尚待；G3/G4和T05未执行，CPU通过不替代业务验收。']
        if state06 in ('failed','error'):
            d06['next_step']='R019/b47在父预填充计数处失败；完整13条被旧包装器按12条判读，正在修复工装并准备新RID重跑。G3/G4及T05仍待。'
            d06['blockers']=['T16工装口径修复及新轮次独立复核待完成；G3/G4与T05未执行。']
            full_tail_path=ROOT/'development/t16_full_tail_launcher_7e1c05a_289327f_cpu.json'
            if full_tail_path.is_file():
                full_tail=json.loads(full_tail_path.read_text(encoding='utf-8'))
                expected={'t16_candidate_launch_full_tail.py':'7e1c05a79b856b6a99c3f8d9422afd7013b9ef0215c78e17427d205f78384dcf',
                    't16_candidate_runner_full_tail.py':'d29f639ea1559dff92588d8d8da25190a32ebf77f44f5cfd9618d302145f57f1',
                    't16_full_tail_base_runner.py':'66f0dce3c5bdcc885f2e19267110e7a3a74798e7e87936b27faa122a28ae2125'}
                if (any(full_tail['files'].get(name)!=digest for name,digest in expected.items())
                    or any(step['returncode'] for step in full_tail['steps'])
                    or full_tail['gpu_started'] is not False
                    or full_tail['log_sha256']!='6d70cd37dcaedef1cfdfac0ffe72fa484353c889da62578bc67bd0be7a237e1f'):
                    raise ValueError('full-tail Linux source proof differs')
                d06['next_step']='R019原失败工件保留；新完整尾段工装/启动器准确Linux45PASS、独立复核通过，等待GPU空闲后新RID重跑，随后G3/G4/T05。'
                d06['blockers']=['新轮次T16/G3/G4及T05尚待；CPU及工装复核不替代实际GPU门。']
                d06['evidence'].append({'path':str(full_tail_path.relative_to(ROOT)).replace('\\','/'),
                    'sha256':hashlib.sha256(full_tail_path.read_bytes()).hexdigest(),
                    'summary':'准确新源码Linux45PASS；完整13条tail口径，缺事件/搬运不同仍拒绝，GPU未启动'})
            snapshot['errors'].append({'source':receipt06['rid'],
                'message':status06.get('error','候选门异常，保留失败工件')})
    retry06=observed.get('t16_d06_retry')
    if retry06:
        receipt20,status20=retry06['receipt'],retry06['status'];state20=status20['state']
        label20=('异常' if state20 in ('failed','error') else '测量结束待复核'
            if state20=='complete_measurements_pending_review' else
            ('加载' if state20=='loading' else '测试中')
            if retry06['pid_alive'] and retry06['identity_verified'] else '进程状态未知')
        snapshot['tests']=[row for row in snapshot['tests'] if row['rid']!=receipt20['rid']]
        snapshot['tests'].insert(0,{'card':'T16','rid':receipt20['rid'],'batch':receipt20['batch'],
            'stage':label20,'execution_status':label20,'batch_pid':receipt20['batch_pid'],
            'pid_alive':retry06['pid_alive'],'identity_verified':retry06['identity_verified'],
            'process_observer':'宿主机 SSH 只读 /proc 身份观察，'+observed['observed_at'],
            'status_updated_at':status20.get('updated_at'),'elapsed_s':None,
            'progress':{'done':len(retry06['measured_arms']),'total':4,'label':'已生成测量摘要臂（非验收）'},
            'review_status':'新完整尾段工装和启动器Linux45PASS及独立复核通过；GPU测量待复核',
            'sealed':False,'formal_verdict':None,
            'evidence':[{'path':'/data2/FreeToken/runs/dev_D06/launch_'+receipt20['rid']+'.json',
                'sha256':retry06['receipt_sha256'],'summary':'23f2父树→0369263候选；新base66f0/adapterd29f，保留R019失败工件'}]})
        d06['next_step']='新完整尾段T16 '+receipt20['rid']+'/b'+str(receipt20['batch'])+'：'+label20+'，当前臂 '+str(status20.get('arm'))+'。G3/G4及T05仍待。'
        sealed20=retry06.get('sealed_proof')
        if sealed20:
            row20=next(row for row in snapshot['tests'] if row['rid']==receipt20['rid'])
            row20.update(stage='已封存待判定',execution_status='测量已结束',
                review_status='四臂实际raw和准确归档CPU重算独立PASS；真实D04封存已校验',
                sealed=True,formal_verdict=sealed20['formal_verdict'],status_updated_at=sealed20['closed_at'])
            row20['evidence'].append({'path':'/data2/_shared/runs/ft_rounds/'+receipt20['rid']+'/MANIFEST.sha256',
                'sha256':sealed20['manifest_sha256'],'summary':'四臂各13条完整预填充事件；生成全文、H2D/D2D及分段一致'})
            d06['next_step']='R020/b48已复核并于'+sealed20['closed_at']+'真实封存，正式pending_review；继续G3/G4开发自检和T05。'
            d06['blockers']=['G3/G4实际GPU开发自检和T05业务验收尚待；默认门已封存不等于D06完成。']
        if state20 in ('failed','error'):
            snapshot['errors'].append({'source':receipt20['rid'],'message':status20.get('error','新默认门异常，工件保留')})
    selfcheck = observed.get('d03_f506_selfcheck')
    if selfcheck:
        phase=selfcheck['phase']; record=selfcheck['receipt']
        label=('异常' if phase=='failed' else '测量结束待复核' if phase=='complete_measurements_pending_review'
            else ('加载' if phase=='loading' else '测试中')
            if selfcheck['pid_alive'] and selfcheck['identity_verified'] else '进程状态未知')
        identity='D03-f506-G4-G5-selfcheck'
        snapshot['tests']=[row for row in snapshot['tests'] if row['rid']!=identity]
        snapshot['tests'].insert(0,{'card':'D03开发自检','rid':identity,'batch':None,
            'stage':label,'execution_status':label,'batch_pid':record['pid'],
            'pid_alive':selfcheck['pid_alive'],'identity_verified':selfcheck['identity_verified'],
            'process_observer':'宿主机 SSH 只读进程身份观察，'+observed['observed_at'],
            'status_updated_at':None,'elapsed_s':None,'progress':None,
            'review_status':'工装/source/input独立复核PASS；GPU结果待独立复核',
            'sealed':False,'formal_verdict':None,
            'evidence':[{'path':record['output'],'summary':'当前臂 '+str(selfcheck['active_arm'])+'；开发自检，不是正式验收轮次'},
                {'path':'development/d03_f506_selfcheck_launch_receipt.json','sha256':selfcheck['receipt_sha256'],
                 'summary':'21,976个实际Qwen token；c30父树→f506候选，固定G4边界与G5两进程逐位比较'}]})
        d03['next_step']='f506 T16已独立复核并封存；G4/G5开发自检：'+label+'，当前臂 '+str(selfcheck['active_arm'])+'。T04实际恢复仍待。'
        if selfcheck['error']:
            snapshot['errors'].append({'source':identity,'message':selfcheck['error'].get('error','开发自检失败，工件保留')})
        review_path = ROOT / 'development/d03_f506_r018_independent_review.json'
        if review_path.is_file() and phase == 'complete_measurements_pending_review':
            review = json.loads(review_path.read_text(encoding='utf-8'))
            if (review.get('reviewer') != '/root/d06_server_review'
                    or review.get('recommendation') != 'APPROVE'
                    or review.get('candidate_commit') != record['candidate_commit']
                    or review.get('f506', {}).get('selfcheck_sha256') != hashlib.sha256(
                        (ROOT / 'development/d03_f506_gpu_selfcheck_raw.json').read_bytes()).hexdigest()
                    or review['f506']['g5']['bitwise_equal'] != 64):
                raise ValueError('f506 independent development review differs from actual source or measurements')
            row_check = next(row for row in snapshot['tests'] if row['rid'] == identity)
            row_check.update(stage='开发自检已复核', execution_status='测量已结束',
                review_status='实际原始工件独立复核PASS；七边界完整，G5双进程64/64逐位相同')
            row_check['evidence'].append({'path':str(review_path.relative_to(ROOT)).replace('\\','/'),
                'sha256':hashlib.sha256(review_path.read_bytes()).hexdigest(),
                'summary':'完整MANIFEST校验通过；G4开发比较74点/0合法包络，不作为T04科学验收'})
            d03['next_step']='f506 T16已复核封存，G3/G4/G5开发自检已复核通过；正在准备Y129新轮次，仍须证明T04实际恢复12672。'
            d03['blockers']=['T04新轮次尚待实际12672 host恢复与FP32对比；开发自检不替代科学验收。',
                'T10已封存测量的科学归因仍待，现有T10使用c30；正式verdict单独维护。']
    selfcheck06=observed.get('d06_selfcheck')
    if selfcheck06:
        receipt06=selfcheck06['receipt'];phase06=selfcheck06['phase']
        label06=('异常' if phase06=='failed' else '测量结束待复核' if phase06=='complete_measurements_pending_review'
            else '测试中' if selfcheck06['pid_alive'] and selfcheck06['identity_verified'] else '进程状态未知')
        identity06='D06-03692633-G3-G4-selfcheck'
        snapshot['tests']=[row for row in snapshot['tests'] if row['rid']!=identity06]
        snapshot['tests'].insert(0,{'card':'D06开发自检','rid':identity06,'batch':None,
            'stage':label06,'execution_status':phase06,'batch_pid':receipt06['pid'],
            'pid_alive':selfcheck06['pid_alive'],'identity_verified':selfcheck06['identity_verified'],
            'process_observer':'宿主机 SSH 只读 /proc 身份观察，'+observed['observed_at'],
            'status_updated_at':None,'elapsed_s':None,'progress':None,'review_status':'准确源Linux11PASS及启动器独立APPROVE；实际GPU结果待复核',
            'sealed':False,'formal_verdict':None,
            'evidence':[{'path':receipt06['output'],'summary':'32K同提示双路ACK计时、真实idle无批次；开发自检，非T05正式验收'},
                {'path':'development/d06_selfcheck_launch_receipt.json','sha256':selfcheck06['receipt_sha256'],'summary':'准确源195aa332；专用GPU队列8095，启动前资源预检通过'}]})
        d06['next_step']='R020/b48已复核封存；G3/G4开发GPU自检：'+label06+'，阶段：'+phase06+'。随后T05。'
        if selfcheck06['error']:
            snapshot['errors'].append({'source':identity06,'message':selfcheck06['error'].get('error','开发自检异常，工件保留')})
    # Current formal verdicts are archival states, not GPU admission or acceptance.
    d03['next_step'] = ('D14 CPU13 baseline failure has a source fix and PASS regression; '
                        'GPU T16/T17 and T10 rerun remain pending. T04 Y129 is P2.')
    d03['blockers'] = ['D14 needs GPU-gate evidence before T16/T17/T10 rerun; '
                       'D04 measurement verdicts do not admit a GPU gate.']
    d06['next_step'] = ('R020 is archived as measurement kept. The D06 tokenizer selfcheck stalled '
                        'before G3/G4 evidence; retry is P1 after P0, followed by T05.')
    d06['blockers'] = ['G3/G4 are not passed because the original tokenizer-stall selfcheck did not '
                       'produce their evidence; T05 remains pending.']
    snapshot['development'] = [row for row in snapshot['development'] if row['card'] != 'D14']
    snapshot['development'].insert(0, {
        'card': 'D14',
        'title': 'Layer-major snapshot context and prefix continuation repair',
        'status': 'CPU regression fixed; GPU gates pending',
        'candidate_commit': 'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42',
        'updated_at': observed['observed_at'],
        'next_step': 'Run GPU T16/T17, then rerun T10 against the repaired candidate.',
        'blockers': ['CPU13 baseline failed before the repair and passed after it; GPU T16/T17/T10 evidence is still required.'],
        'evidence': [{
            'path': 'development/p0_ngram_semantic_proof.json',
            'sha256': hashlib.sha256((ROOT / 'development/p0_ngram_semantic_proof.json').read_bytes()).hexdigest(),
            'summary': 'CPU13 baseline regression: FAIL before the D14 repair and PASS after it; no GPU admission implied.'
        }]
    })
    for test_row in snapshot['tests']:
        if test_row.get('formal_verdict') == 'kept':
            test_row['stage'] = 'measurement kept (not GPU admission)'
            test_row['execution_status'] = 'measurements complete; archival verdict kept'
            test_row['review_status'] = 'Formal verdict is measurement-only kept; GPU admission and acceptance remain separate.'

    snapshot['priority_note'] = (
        'Formal archives: 14 measurement-only kept verdicts and 7 failed_harness verdicts; '
        'FTD04 has not been published. P0: D14 GPU gates, then T16/T17 and T10. '
        'P1: D06/T05 and D07/T06. P2: T04/T09. D08-D13 and TP are frozen.'
    )
    snapshot['source_note'] = '本地交接快照，非实时；T04/T11/T10/T16及开发自检PID仅在 observed_at 由宿主机只读观察。开发状态日期是维护时间；未返回的阶段事件时间不推测。'
    comparison = next(row for row in snapshot['comparisons'] if row['metric'] == 'D03 当前门结果')
    comparison.update(reason='T16 默认路径门已复核封存；未将单次门计时当作性能验收。', scientific_status='T04/T10 业务验收待测量和复核')
    atomic_json(path, snapshot)
    status = {'schema': 'ft_development_status/v1', 'revision': snapshot['revision'],
              'updated_at': observed['observed_at'], 'updated_by': 'mainline_owner',
              'baseline': snapshot['baseline'], 'development': snapshot['development'],
              'source_note': '本地主线负责人维护的开发状态；不包含实时 PID 采集器。'}
    atomic_json(ROOT / 'development/development_status.json', status)
    atomic_json(ROOT / 'development/d03_latest_observation.json', observed)
    print(json.dumps({'revision': snapshot['revision'], 'observed_at': observed['observed_at'],
                      't04_retry_pid_alive': retry15['pid_alive'], 't04_retry_stage': stage15,
                      'captured_arms': retry15['captured_arms'], 't10_stage2_captures': stage2['capture_count'],
                      't10_stage2_comparisons': stage2['comparison_count'], 'd06_status': d06['status']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
