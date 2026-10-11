#!/usr/bin/env python3
"""Root-only 09:00 reader/writer.  No production, HTTP, model, fetch, or push action."""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,re,subprocess
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
HERE=Path(__file__).resolve().parent; INPUTS=HERE/'MORNING_REPORT_INPUTS_V3.json'; BASE='184c965964b5f79deaecf1b1e3e0eda3187c829d'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
def load():return json.loads(INPUTS.read_text())
def clean_url(v):
 p=urlsplit(v);return urlunsplit((p.scheme,p.hostname or '',p.path,'','')) if p.scheme else (v.split('@',1)[1] if '@' in v.split(':',1)[0] else re.sub(r'//[^/@]+@','//',v))
def pins(c):
 root=Path(c['night_root']);out={}
 for n,h in c['pinned'].items():
  p=root/n
  if p.is_symlink() or not p.is_file() or sha(p)!=h:raise RuntimeError('pinned input differs: '+n)
  out[n]=h
 return out
def observation(c):
 deadline=dt.datetime.fromisoformat(c['not_before'])
 if now()<deadline:raise RuntimeError('09:00 wall-time guard has not opened')
 root=Path(c['production_root']);d=root/'overnight_observation';term=d/'terminal.json';samples=d/'samples.jsonl';start=d/'start.json';owner=root/'owner.json'
 if any(p.is_symlink() or not p.is_file() for p in (term,samples,start,owner)):raise RuntimeError('actual terminal/source is absent')
 t=json.loads(term.read_text());rows=[json.loads(x) for x in samples.read_text().splitlines() if x.strip()];s=json.loads(start.read_text());o=json.loads(owner.read_text())
 if not rows:raise RuntimeError('actual samples are empty')
 if t.get('classification') not in ('requires_review','clean_observation') or not isinstance(t.get('eligible_to_request_push_approval'),bool) or t.get('push_approved') is not False or t.get('push_executed') is not False:raise RuntimeError('unrecognized actual terminal verdict')
 # Actual observer stores until_epoch only on START, never on terminal.
 if t.get('until')!=c['not_before'] or s.get('until_epoch')!=deadline.timestamp() or s.get('until')!=c['not_before'] or not isinstance(t.get('at'),(int,float)) or t['at']<deadline.timestamp() or rows[-1].get('at',0)<deadline.timestamp():raise RuntimeError('actual observation has not closed at 09:00')
 if t.get('samples')!=len(rows) or t.get('final')!=rows[-1]:raise RuntimeError('terminal sample count/final differs')
 if s.get('source_run')!=str(root) or s.get('generation_requests')!=0 or s.get('service_mutations')!=0 or s.get('at')!=c['observer_start_epoch']:raise RuntimeError('canonical observation source/window differs')
 bad=summarize(rows)
 bad['owner_identity_matches']=all([o.get(role,{}).get('pid'),o.get(role,{}).get('start_ticks')]==c['expected_owner'][role] for role in ('supervisor','service'))
 bad['terminal_verdict_consistent']=bool((t['classification']=='requires_review' and t['eligible_to_request_push_approval'] is False and t.get('issues')) or (t['classification']=='clean_observation' and t['eligible_to_request_push_approval'] is True and not t.get('issues')))
 return term,t,rows,bad

def summarize(rows):
 out={f+'_failures':sum(r.get(f) is not True for r in rows) for f in ('active_owner_matches','supervisor_alive','service_alive','monitor_alive','watchdog_fresh')}
 out['unhealthy']=sum((r.get('watchdog_latest') or {}).get('healthy') is not True for r in rows)
 out['unhealthy_after_first']=sum((r.get('watchdog_latest') or {}).get('healthy') is not True for r in rows[1:])
 out['alerts_max']=max((r.get('alerts_count',0) for r in rows),default=0)
 out['epochs']=sorted({r.get('backend_epoch') for r in rows},key=repr)
 out['restarts']=sorted({r.get('restart_attempts') for r in rows},key=repr)
 out['first_watchdog_age_seconds']=rows[0]['at']-(rows[0].get('watchdog_latest') or {}).get('at',rows[0]['at'])
 return out

def git(c):
 def g(*a):
  try:
   p=subprocess.run(['git','-C',c['release_worktree'],*a],text=True,capture_output=True,timeout=30,env={**os.environ,'GIT_TERMINAL_PROMPT':'0'})
   return p.returncode,p.stdout.strip() if p.returncode==0 else 'UNKNOWN'
  except (subprocess.TimeoutExpired,OSError):return 124,'UNKNOWN'
 ch,head=g('rev-parse','HEAD');cb,branch=g('branch','--show-current');cs,dirty=g('status','--porcelain','-uno');ct,stat=g('diff','--shortstat',BASE+'..HEAD');cc,count=g('rev-list','--count',BASE+'..HEAD');cr,remote=g('remote','get-url','origin');lr,heads=g('ls-remote','--heads','origin','refs/heads/release/e2')
 origin=clean_url(remote) if cr==0 else 'UNKNOWN'
 return {'head':head,'branch':branch,'tracked_dirty':None if cs else bool(dirty),'shortstat':stat,'commits':count,'origin':origin,'remote_head':heads,'remote_read_success':lr==0,'scope_matches':all(x==0 for x in (ch,cb,cs,ct,cc,cr)) and head==c['expected_head'] and branch=='release/e2' and not dirty and stat==c['expected_shortstat'] and count==str(c['expected_commits']) and origin==c['expected_origin']}

def exclusive(p,text):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(text);f.flush();os.fsync(f.fileno())
def main():
 a=argparse.ArgumentParser();a.add_argument('--file-dry-run',action='store_true');a.add_argument('--run',action='store_true');x=a.parse_args();c=load();pins(c);term,t,rows,bad=observation(c)
 if x.file_dry_run or not x.run:print(json.dumps({'ready':True,'writes':False,'samples':len(rows)}));return
 plan=HERE.parents[1]/'plan';report=plan/'NIGHT_EXECUTION_20261010_0900_REPORT.md';proposal=plan/'PUSH_APPLICATION_20261010_0900.md'
 if report.exists() or proposal.exists():raise RuntimeError('report/proposal already exists; no overwrite')
 g=git(c);state='MANUAL_REVIEW_REQUIRED' if g['scope_matches'] and g['remote_read_success'] and not g['remote_head'] and bad['owner_identity_matches'] and bad['terminal_verdict_consistent'] and bad['unhealthy_after_first']==0 and bad['alerts_max']==0 and bad['epochs']==[0] and bad['restarts']==[0] and not any(bad[f+'_failures'] for f in ('active_owner_matches','supervisor_alive','service_alive','monitor_alive','watchdog_fresh')) else 'BLOCKED_OR_UNKNOWN';stamp=now().isoformat()
 table='Strata S1 MTP OFF; S2 retry1 MTP ON, parallel=1; S3 parallel=2 without batch-MTP opt-in. R044 retry1 failed_harness 1/24 missing19 intermediate captures; retry2 failed_harness 1/24 captureerror0+19 chunk receipts; no third retry. D10 prototype FAILED_HARNESS 1/2, TPS5.855077/1.064367, outputs46/58, observational only. D09 retry1 kept 8/100 default-off only; enabled T17/T03b/T2 pending.'
 report_text=f'# 2026-10-10 09:00 夜间报告\n\n真实写入：{stamp}；terminal `{term}` SHA `{sha(term)}`，terminal.at `{t["at"]}`，samples={len(rows)}。classification=`{t.get("classification")}`，eligible=`{t.get("eligible_to_request_push_approval")}`。异常汇总={json.dumps(bad,ensure_ascii=False)}；不称 clean PASS。\n\n{table}\n\n原观察306 samples/0 issues为TRUNCATED 17:35:56–22:41:20，非隔夜通过。恢复官方SDK first-cold 17字段全匹配：`b6f2e4dd1f4dbc7c95b95bd80f5481069b7b7ec4cac1c0e0c87110e93805d21e`；无184回滚。闭环证据由 `{INPUTS}` 的 {len(c["pinned"])} 项SHA pins完整绑定。\n\nGit：{json.dumps(g,ensure_ascii=False)}。论文中文仅§8/C5；英文V9 source-ready/PDF-unbuilt，无PDF/arXiv。\n'
 prop=f'# Push application — 2026-10-10 09:00\n\nState: **{state}**。需人工异常裁决与用户明确 scope approval；绝不自动推送。origin `refs/heads/release/e2`，expected481 `{c["expected_head"]}`；当前Git={json.dumps(g,ensure_ascii=False)}。scope仅release/e2，排除D09/D10/R047调试树、night packets与论文。\n'
 report_text += '\n\n## 逐轮实测与边界\n\n| Round / scope | factual state | service / calls | boundary |\n|---|---|---:|---|\n| Old observer | TRUNCATED | 306 / 0 issues | 17:35:56–22:41:20; not an overnight pass |\n| R067 original | user reclassified failed_harness | 3 / 7 | 6 hot valid |\n| R047/T03b; R052a; R044 original | not_met; not_met; failed_harness | 6/24; 1/9; 1/0 | R052a cache13376 vs floor13504/full13554 |\n| Strata S1; S2 original; S2 retry1 | valid subset; failed_harness; valid subset | 1/11; 1/0; 1/11 | S1 MTP OFF / S2retry1 MTP ON; parallel=1 queued |\n| D09 original; R067 retry1; D09 retry1 | failed_harness; not_met; kept | 4/48; 4/8; 8/100 | R067 hot39/cold248046 A=B cold cache0; D09 default-off only |\n| R047 diagnostic; Strata S3; D10 T16 | failed post-exec; valid subset; kept | 1/3; 1/11; 8/100 | R047 missing d0_decode/alignment3/mismatch60; S3 parallel=2, cap4 used |\n| R044 retry1; retry2 | failed_harness; failed_harness | 1/24; 1/24 | retry1 missing19 intermediate captures; retry2 captureerror0+19 chunk receipts, strict args reader missing max_prefill_length; no third retry |\n| D10 prototype formal | FAILED_HARNESS | 1/2 | completion TPS 5.855077/1.064367, outputs46/58; observational negative only; profiles1–3 not run |\n| RESTORE481 smoke | passed | official SDK 2 prompts | 512/8257 each128, cache0; 17 fields match frozen first-cold baseline; no rollback184 |\n\nStrata同一v0.1.41构建fb58e0dbc8399662c0e47c76578c6e878b14f6cf，binary a1f4bc961395b8d347e3e73d48a35c372000006a42ca9c3ea8abd09fb46aa7a0；构建在计时前完成，无资产下载/prepare。总4服务已用完。S1冷32K61.4–63.35/短60.44–66.31；S2retry1均值77.17/79.06；原提示聚合S1 48.4181687/S2 64.6189210约+33.46%，parallel=1排队，不是两路解码或纯MTP因果实验。S3两路20.6089121/40.5569274，聚合35.4811359，没有两路均>30；未显式启用batch-MTP。ignore_eos固定256不支持；52/60仅R001历史，未重测。\n\nR067d retry1产品not_met，D12触发条件未满足。D09启用T17/T03b/T2未完成，<=64尾段结论以R067d为准，不能推为通过。R047原not_met保持；诊断3调用后缺d0_decode，cached mismatch60与unaligned3不能确证竞态/token ID根因；不能称cached mismatch恒成立。D10理想41.67、按实测修正33.1–40预测未改，首组5.855077/1.064367为有实际完成路径证据的观察性负结果，formal FAILED_HARNESS保持；后续组含fixed256未跑，未取得正式开发资格。\n\n新观察首条读取窗口前loading记录，实际年龄与后续异常从samples派生统计；首条及原terminal均不改写、不豁免。生产04:49:08首冷通过，原基准df77cb1471d199b527e671d4a9f3e36b5e37e3ce2bb965df9180c560aa6f9d97，原观察为截断。GitHub MTP查询归档_shared/research/GITHUB_MTP_SCHEMES_20261010.md。多卡仍DERIVED/PROPOSED；未新增KT/llama.cpp基线。\n'
 report_text += '\n\n实际原issues：'+json.dumps(t.get('issues'),ensure_ascii=False)+'\n自动资格：'+str(t.get('eligible_to_request_push_approval'))+'\n\n冻结证据逐项：\n'+'\n'.join('- '+str(HERE/n)+' SHA '+h for n,h in c['pinned'].items())+'\nInputs SHA '+sha(INPUTS)+'\n原samples SHA '+sha(term.parent/'samples.jsonl')+'\n原start SHA '+sha(term.parent/'start.json')+'\n'
 prop += '\n\n拟推送仓库 https://github.com/FlashML-org/FreeToken.git 的 refs/heads/release/e2，仅精确481 SHA。基线184c965964b5f79deaecf1b1e3e0eda3187c829d，40提交/91文件/+11964/-129，必须与实时scope_matches核对；远端ref非空或查询失败均需额外裁决。请分别裁决首条窗口前loading例外及批准确定推送范围；自动资格 '+str(t.get('eligible_to_request_push_approval'))+' 不改写、不自动豁免。不使用force，未批准前不执行。完整报告：'+str(report)+'；terminal SHA '+sha(term)+'。\n'
 exclusive(report,report_text);exclusive(proposal,prop)
 log=HERE/'COORDINATION_LOG.jsonl';line=json.dumps({'at':stamp,'event':'MORNING_REPORT_V3_WRITTEN','terminal_sha256':sha(term),'report_sha256':sha(report),'proposal_sha256':sha(proposal),'push_state':state,'push_approved':False,'push_executed':False},sort_keys=True)+'\n'
 with log.open('a',encoding='utf-8') as f:f.write(line);f.flush();os.fsync(f.fileno())
 print(json.dumps({'written':True,'state':state}))
if __name__=='__main__':main()
