"""CAS the exact revision-60 tracker with the committed schedule CPU evidence."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
path = ROOT / 'development/development_status.json'
before = path.read_bytes()
value = json.loads(before)
if value['revision'] != 60:
    raise ValueError('tracker changed; merge from a fresh revision')
now = datetime.now(timezone.utc).isoformat()
candidate = 'e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7'
row = next(item for item in value['development'] if item['card'] == 'D14')
if row['candidate_commit'] != 'e4f32022a5aa4d8734d87d9f6eb15e98c1edde42':
    raise ValueError('previous D14 candidate differs')
row['prior_candidate_commit'] = row['candidate_commit']
row.update(candidate_commit=candidate, candidate_git_tree='09068014ec70359cb20919669be43e2dc56c9cba',
           status='新调度候选已提交同步；Linux70CPU PASS；新T16/T17待执行', updated_at=now,
           next_step='交付准确门候选绑定的T16默认路径门和卡D16新版T17批次，再执行双独立同结构参照；卡D17仍等待。',
           blockers=['新候选仅有CPU证明，尚无GPU T16默认路径或新版T17接受。',
                     '卡D16实测执行器、双参照、普通包络及批次脚本仍待交付。'])
def evidence(name, summary):
    return {'path': name, 'sha256': hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), 'summary': summary}
additions = [
    evidence('development/d14_schedule_cpu_6454d1109e8d.json', '准确门候选Linux70CPU PASS，日志、源、Git tree和扩展绑定保留'),
    evidence('development/d14_schedule_cpu_bb164dfb4193.json', '原始CPU失败夹具保留只读；22调度/14Engine PASS，1夹具FAIL'),
    evidence('development/d16_historical_replay_20261005.json', 'R019/R021各臂13事件无误判；R023四恢复PASS但同结构参照缺失，indeterminate'),
    evidence('development/D14_schedule_progress_20261005.md', '完整候选实现、历史提交、真实CPU结果和后续门边界'),
]
row['evidence'].extend(additions)
if any(item['card']=='D16' for item in value['development']):
    raise ValueError('D16 row already exists; merge explicitly')
value['development'].append({'card':'D16','title':'同结构冷参照与等价测试套件','candidate_commit':candidate,
    'status':'CPU读者与调度生成器已提交；21Linux工具测试PASS；实测执行器待交付',
    'updated_at':now,'next_step':'复用共用服务生命周期，交付T17命中/双参照/包络批次及批槽、停靠、缓存、交错运行器。',
    'blockers':['没有新版T17实测或T20全套接受。'], 'evidence':additions[::2]})
value.update(revision=61,updated_at=now,updated_by='Codex schedule candidate and actual Linux CPU stage')
payload=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
temporary=path.with_name(path.name+'.schedule-update.tmp')
with temporary.open('xb') as stream:stream.write(payload)
if path.read_bytes()!=before:raise ValueError('concurrent tracker mutation; merge left intact')
os.replace(temporary,path)
print(json.dumps({'revision':61,'candidate':candidate,'sha256':hashlib.sha256(payload).hexdigest()}))
