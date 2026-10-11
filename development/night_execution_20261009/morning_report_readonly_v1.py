#!/usr/bin/env python3
"""Root-only, read-only 09:00 report writer.  It never controls production or Git."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, re, subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

HERE=Path(__file__).resolve().parent
INPUTS=HERE/'MORNING_REPORT_INPUTS_V1.json'
TABLE='''| Round / scope | factual state | service / calls | boundary |
|---|---|---:|---|
| Old observer | TRUNCATED | 306 / 0 issues | 17:35:56–22:41:20; not an overnight pass |
| R067 original | user reclassified failed_harness | 3 / 7 | 6 hot valid |
| R047/T03b; R052a; R044 original | not_met; not_met; failed_harness | 6/24; 1/9; 1/0 | R052a cache13376 vs floor13504/full13554 |
| Strata S1; S2 original; S2 retry1 | valid subset; failed_harness; valid subset | 1/11; 1/0; 1/11 | S1/S2retry1 parallel=1, no MTP |
| D09 original; R067 retry1; D09 retry1 | failed_harness; not_met; kept | 4/48; 4/8; 8/100 | R067 hot39/cold248046 A=B cold cache0; D09 default-off only |
| R047 diagnostic; Strata S3; D10 T16 | failed post-exec; valid subset; kept | 1/3; 1/11; 8/100 | R047 missing d0_decode/alignment3/mismatch60; S3 parallel=2, cap4 used |
| R044 retry1; retry2 | failed_harness; failed_harness | 1/24; 1/24 | retry1 missing19 intermediate captures; retry2 captureerror0+19 chunk receipts, strict args reader missing max_prefill_length; no third retry |
| D10 prototype formal | FAILED_HARNESS | 1/2 | completion TPS 5.855077/1.064367, outputs46/58; observational negative only; profiles1–3 not run |
| RESTORE481 smoke | passed | official SDK 2 prompts | 512/8257 each128, cache0; 17 fields match frozen first-cold baseline; no rollback184 |
'''

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def now()->dt.datetime:return dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
def load()->dict:return json.loads(INPUTS.read_text())
def safe_url(value:str)->str:
 p=urlsplit(value); return urlunsplit((p.scheme,p.hostname or '',p.path,'','')) if p.scheme else re.sub(r'//[^/@]+@','//',value)
def read_pins(cfg:dict)->dict:
 root=Path(cfg['night_root']); rows={}
 for name,want in cfg['pinned'].items():
  path=root/name
  if path.is_symlink() or not path.is_file() or sha(path)!=want: raise RuntimeError(f'pinned input differs: {name}')
  rows[name]=want
 return rows
def terminal(cfg:dict)->tuple[Path,dict,list[dict]]:
 root=Path(cfg['production_root']); term=root/cfg['terminal']; samples=root/'overnight_observation/samples.jsonl'; start=root/'overnight_observation/start.json'; owner=root/'owner.json'
 if term.is_symlink() or not term.is_file():raise RuntimeError('actual overnight terminal is absent')
 if any(p.is_symlink() or not p.is_file() for p in (samples,start,owner)):raise RuntimeError('actual overnight source files are absent')
 data=json.loads(term.read_text()); rows=[json.loads(x) for x in samples.read_text().splitlines() if x.strip()]
 if not rows or not isinstance(data,dict):raise RuntimeError('terminal/samples are incomplete')
 begin=json.loads(start.read_text()); live=json.loads(owner.read_text()); expected=cfg['expected_owner']
 if begin.get('source_run')!=str(root) or begin.get('until')!=cfg['not_before'] or begin.get('generation_requests')!=0 or begin.get('service_mutations')!=0:raise RuntimeError('observation source/window is not read-only canonical')
 for role in ('supervisor','service'):
  actual=live.get(role,{})
  if [actual.get('pid'),actual.get('start_ticks')]!=expected[role]:raise RuntimeError(f'observation {role} identity differs')
 if any(row.get('active_owner_matches') is not True for row in rows):raise RuntimeError('observation samples have an owner mismatch')
 return term,data,rows
def guard(cfg:dict)->tuple[Path,dict,list[dict]]:
 if now()<dt.datetime.fromisoformat(cfg['not_before']):raise RuntimeError('09:00 wall-time guard has not opened')
 term,data,rows=terminal(cfg)
 if data.get('classification') not in {'requires_review','completed_requires_review'}:raise RuntimeError('terminal classification is not requires_review')
 if data.get('eligible_to_request_push_approval') is not False:raise RuntimeError('terminal improperly claims push eligibility')
 return term,data,rows
def git_snapshot(cfg:dict)->dict:
 wd=cfg['release_worktree']
 def run(*args):
  p=subprocess.run(['git','-C',wd,*args],text=True,capture_output=True,check=False);return p.returncode,p.stdout.strip()
 code,head=run('rev-parse','HEAD'); code2,status=run('status','--porcelain'); code3,remotes=run('remote','-v')
 remote_rows=[]
 for line in remotes.splitlines():
  parts=line.split(); remote_rows.append({'name':parts[0],'url':safe_url(parts[1])} if len(parts)>=2 else {'raw':'malformed'})
 code4,heads=run('ls-remote','--heads','origin','release/e2'); code5,shortstat=run('diff','--shortstat','184c965964b5f79deaecf1b1e3e0eda3187c829d..HEAD'); code6,commits=run('rev-list','--count','184c965964b5f79deaecf1b1e3e0eda3187c829d..HEAD')
 return {'head':head if code==0 else None,'tracked_dirty':bool(status) if code2==0 else None,'remotes':remote_rows,'ls_remote_release_e2':heads if code4==0 else 'UNKNOWN','ls_remote_ok':code4==0,'diff_shortstat':shortstat if code5==0 else 'UNKNOWN','commit_count':commits if code6==0 else 'UNKNOWN'}
def write_new(path:Path,text:str)->None:
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8') as f:f.write(text)
def run_report(cfg:dict)->None:
 pins=read_pins(cfg); term,data,samples=guard(cfg); git=git_snapshot(cfg); stamp=now().isoformat()
 state='MANUAL_REVIEW_REQUIRED' if git['head']==cfg['expected_head'] and git['tracked_dirty'] is False else 'BLOCKED_OR_UNKNOWN'
 report=f'''# 2026-10-10 09:00 夜间报告\n\n真实写入：{stamp}。此报告由已终止的实际 observation 生成；classification 保持 `{data.get("classification")}`，不将观察或冒烟称为 clean PASS。\n\n{TABLE}\n## 生产观察\n\nterminal：`{term}` SHA `{sha(term)}`；samples={len(samples)}。首条 watchdog loading 50.99 秒发生在窗口前，后续健康；仍需人工原因审查。\n\n## Strata 与研究\n\n同一构建 `fb58e0dbc8399662c0e47c76578c6e878b14f6cf`，binary `a1f4bc...7a0`，22:48 前完成且无资产下载。S1 cold61.4–63.4/short60.4–66.3；S2 cold77.17/short79.06，original per-request104.8604/102.9456、aggregate64.6189（parallel=1 queued）；S3 parallel=2 cold69.525/short71.80、per-route20.6089/40.5569、aggregate35.4811，不能称两路均>30。ignore_eos fixed256 不支持；quality52/60仅R001历史，未重跑且无MTP因果声明。研究查询见 `_shared/research/GITHUB_MTP_SCHEMES_20261010.md`。\n\n## 论文与推送\n\n中文仅§8/C5；多GPU仍 DERIVED/PROPOSED。英文V9独审 source-ready/PDF-unbuilt，未PDF或arXiv提交。D09 enabled未测量；D10理想41.67、修正33.1–40预测未改，实际首组低于区间。\n\nGit HEAD=`{git["head"]}`，tracked_dirty=`{git["tracked_dirty"]}`，remotes={json.dumps(git["remotes"],ensure_ascii=False)}，ls-remote={git["ls_remote_release_e2"]!r}。\n'''
 proposal=f'''# Push application — 2026-10-10 09:00\n\nState: **{state}**. User explicit approval is still required. The initial watchdog exception requires manual review; this writer neither waives it nor pushes.\n\nScope is release/e2 only: expected HEAD `{cfg["expected_head"]}` versus 184 baseline, 40 commits/91 files/+11964/-129. D09/D10/R047 debug trees, night packets and paper work are excluded.\n\nEvidence: terminal `{term}` SHA `{sha(term)}`; first-cold readback `b6f2e4dd1f4dbc7c95b95bd80f5481069b7b7ec4cac1c0e0c87110e93805d21e`; pinned scope `c918bab5fd0b8c93ff283f0391099618da906d0d0cd6c614145dc76de4692107`.\n'''
 plan=HERE.parents[1]/'plan'; write_new(plan/'NIGHT_EXECUTION_20261010_0900_REPORT.md',report); write_new(plan/'PUSH_APPLICATION_20261010_0900.md',proposal)
 with (plan/'COORDINATION_LOG.md').open('a',encoding='utf-8') as f:f.write(f'\n| {stamp} | R | 09:00 readonly report written | {state} | terminal {sha(term)} |\n')
 print(json.dumps({'written':True,'terminal_sha256':sha(term),'pins':len(pins),'samples':len(samples),'push_state':state}))
def main():
 p=argparse.ArgumentParser();p.add_argument('--file-dry-run',action='store_true');p.add_argument('--run',action='store_true');a=p.parse_args()
 cfg=load(); read_pins(cfg)
 if a.file_dry_run or not a.run: guard(cfg); print(json.dumps({'ready':True,'writes':False})); return
 run_report(cfg)
if __name__=='__main__':main()
