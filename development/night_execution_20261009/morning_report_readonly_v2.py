#!/usr/bin/env python3
"""Root-only 09:00 reader/writer.  No production, HTTP, model, fetch, or push action."""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,os,re,subprocess
from pathlib import Path
from urllib.parse import urlsplit,urlunsplit
HERE=Path(__file__).resolve().parent; INPUTS=HERE/'MORNING_REPORT_INPUTS_V2.json'; BASE='184c965964b5f79deaecf1b1e3e0eda3187c829d'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def now():return dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
def load():return json.loads(INPUTS.read_text())
def clean_url(v):
 p=urlsplit(v);return urlunsplit((p.scheme,p.hostname or '',p.path,'','')) if p.scheme else re.sub(r'//[^/@]+@','//',v)
def pins(c):
 root=Path(c['night_root']);out={}
 for n,h in c['pinned'].items():
  p=root/n
  if p.is_symlink() or not p.is_file() or sha(p)!=h:raise RuntimeError('pinned input differs: '+n)
  out[n]=h
 return out
def observation(c):
 root=Path(c['production_root']); d=root/'overnight_observation'; term=d/'terminal.json'; samples=d/'samples.jsonl'; start=d/'start.json'; owner=root/'owner.json'
 if any(p.is_symlink() or not p.is_file() for p in (term,samples,start,owner)):raise RuntimeError('actual terminal/source is absent')
 t=json.loads(term.read_text()); rows=[json.loads(x) for x in samples.read_text().splitlines() if x.strip()]; s=json.loads(start.read_text());o=json.loads(owner.read_text())
 if now()<dt.datetime.fromisoformat(c['not_before']):raise RuntimeError('09:00 wall-time guard has not opened')
 if t.get('classification') not in ('requires_review','completed_requires_review') or t.get('eligible_to_request_push_approval') is not False or t.get('push_approved') is not False or t.get('push_executed') is not False:raise RuntimeError('terminal does not preserve requires_review/ineligible state')
 if t.get('until')!=c['not_before'] or t.get('until_epoch')!=1791594000 or not isinstance(t.get('at'),(int,float)) or t['at']<t['until_epoch']:raise RuntimeError('terminal timestamp/window does not close at 09:00')
 if t.get('samples')!=len(rows) or t.get('final')!=rows[-1]:raise RuntimeError('terminal sample count/final row differs from actual samples')
 if s.get('source_run')!=str(root) or s.get('until')!=c['not_before'] or s.get('generation_requests')!=0 or s.get('service_mutations')!=0:raise RuntimeError('observation source/window differs')
 for role in ('supervisor','service'):
  if [o.get(role,{}).get('pid'),o.get(role,{}).get('start_ticks')]!=c['expected_owner'][role]:raise RuntimeError('owner identity differs: '+role)
 bad={'unhealthy':0,'owner_mismatches':0,'stale':0,'alerts':0,'epochs':set(),'restarts':set()}
 for r in rows:
  bad['unhealthy']+=r.get('watchdog_latest',{}).get('healthy') is not True;bad['owner_mismatches']+=r.get('active_owner_matches') is not True;bad['stale']+=r.get('watchdog_fresh') is not True;bad['alerts']+=int(r.get('alerts_count',0));bad['epochs'].add(r.get('backend_epoch'));bad['restarts'].add(r.get('restart_attempts'))
 return term,t,rows,bad
def git(c):
 def g(*a):
  try:p=subprocess.run(['git','-C',c['release_worktree'],*a],text=True,capture_output=True,timeout=30);return p.returncode,p.stdout.strip()
  except subprocess.TimeoutExpired:return 124,'UNKNOWN_TIMEOUT'
 _,head=g('rev-parse','HEAD');cs,dirty=g('status','--porcelain','-uno');_,stat=g('diff','--shortstat',BASE+'..HEAD');_,count=g('rev-list','--count',BASE+'..HEAD');cr,remote=g('remote','get-url','origin');lr,heads=g('ls-remote','--heads','origin','refs/heads/release/e2')
 return {'head':head,'tracked_dirty':None if cs else bool(dirty),'shortstat':stat,'commits':count,'origin':clean_url(remote) if cr==0 else 'UNKNOWN','remote_head':heads if lr==0 else 'UNKNOWN'}
def exclusive(p,text):
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w',encoding='utf-8') as f:f.write(text);f.flush();os.fsync(f.fileno())
def main():
 a=argparse.ArgumentParser();a.add_argument('--file-dry-run',action='store_true');a.add_argument('--run',action='store_true');x=a.parse_args();c=load();pins(c);term,t,rows,bad=observation(c)
 if x.file_dry_run or not x.run:print(json.dumps({'ready':True,'writes':False,'samples':len(rows)}));return
 plan=HERE.parents[1]/'plan';report=plan/'NIGHT_EXECUTION_20261010_0900_REPORT.md';proposal=plan/'PUSH_APPLICATION_20261010_0900.md'
 if report.exists() or proposal.exists():raise RuntimeError('report/proposal already exists; no overwrite')
 g=git(c);bad['epochs']=sorted(bad['epochs']);bad['restarts']=sorted(bad['restarts']);state='MANUAL_REVIEW_REQUIRED' if g['head']==c['expected_head'] and g['tracked_dirty'] is False and g['origin']=='https://github.com/FlashML-org/FreeToken.git' else 'BLOCKED_OR_UNKNOWN';stamp=now().isoformat()
 table='Strata S1 MTP OFF; S2 retry1 MTP ON, parallel=1; S3 parallel=2 without batch-MTP opt-in. R044 retry1 failed_harness 1/24 missing19 intermediate captures; retry2 failed_harness 1/24 captureerror0+19 chunk receipts; no third retry. D10 prototype FAILED_HARNESS 1/2, TPS5.855077/1.064367, outputs46/58, observational only. D09 retry1 kept 8/100 default-off only; enabled T17/T03b/T2 pending.'
 report_text=f'# 2026-10-10 09:00 夜间报告\n\n真实写入：{stamp}；terminal `{term}` SHA `{sha(term)}`，terminal.at `{t["at"]}`，samples={len(rows)}。classification=`{t.get("classification")}`，eligible=`{t.get("eligible_to_request_push_approval")}`。异常汇总={json.dumps(bad,ensure_ascii=False)}；不称 clean PASS。\n\n{table}\n\n原观察306 samples/0 issues为TRUNCATED 17:35:56–22:41:20，非隔夜通过。恢复官方SDK first-cold 17字段全匹配：`b6f2e4dd1f4dbc7c95b95bd80f5481069b7b7ec4cac1c0e0c87110e93805d21e`；无184回滚。闭环证据由 `{INPUTS}` 的 {len(c["pinned"])} 项SHA pins完整绑定。\n\nGit：{json.dumps(g,ensure_ascii=False)}。论文中文仅§8/C5；英文V9 source-ready/PDF-unbuilt，无PDF/arXiv。\n'
 prop=f'# Push application — 2026-10-10 09:00\n\nState: **{state}**。需人工异常裁决与用户明确 scope approval；绝不自动推送。origin `refs/heads/release/e2`，expected481 `{c["expected_head"]}`；当前Git={json.dumps(g,ensure_ascii=False)}。scope仅release/e2，排除D09/D10/R047调试树、night packets与论文。\n'
 exclusive(report,report_text);exclusive(proposal,prop)
 log=HERE/'COORDINATION_LOG.jsonl';line=json.dumps({'at':stamp,'event':'MORNING_REPORT_V2_WRITTEN','terminal_sha256':sha(term),'push_state':state},sort_keys=True)+'\n'
 with log.open('a',encoding='utf-8') as f:f.write(line);f.flush();os.fsync(f.fileno())
 print(json.dumps({'written':True,'state':state}))
if __name__=='__main__':main()
