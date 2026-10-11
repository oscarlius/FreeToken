"""Future shared T16 launcher; policy-free runner selection with pinned stage proof."""
import argparse, hashlib, json, os, re, stat, subprocess, sys, tempfile
from pathlib import Path, PurePosixPath
import t16_process_lifecycle as life

ROOT=Path('/data2/FreeToken'); ROUNDS=Path('/data2/_shared/runs/ft_rounds'); PY=str(ROOT/'venv/bin/python')
RUNNER='t16_candidate_runner_full_tail.py'; BASE='t16_full_tail_base_runner.py'; HELPER_SHA='a3924a63f7ea451972992857e78a2ba7b18c1cd9477e25ddfebb038614359acf'
PINNED={RUNNER:'0451e41128b4d1e0c73f892b375b9fbe70b30a9fbac46bc022500bd3c1b6d8b8',BASE:'379948776d42d5429304afb11dafb0d316e641638caf7cad15fb5b5e6be7340f','t16_process_lifecycle.py':'472a80e65c776803978ff668701c9d40d1f0c895d840e12278c1437862dd02d4'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def receipt(stage):
 stage=Path(stage)
 if sys.platform!='linux' or stage.is_symlink() or not stage.is_dir() or stage.stat().st_uid!=os.geteuid() or stage.stat().st_mode&0o222:raise ValueError('owned read-only Linux stage required')
 p=Path(stage)/'cpu_validation.json'; d=json.loads(p.read_text())
 if p.is_symlink() or p.stat().st_mode&0o222:raise ValueError('CPU receipt not frozen')
 if d.get('schema')!='ft_t16_shared_cpu_stage/v1' or d.get('gpu_started') is not False or d.get('status')!='passed' or type(d.get('passed')) is not int or d['passed']<48:raise ValueError('exact CPU-only shared stage receipt required')
 from t16_candidate_stage_shared import NAMES,TESTS
 if set(d.get('files',{}))!=set(NAMES)|{'t16_legacy_base_runner.py'} or d.get('tests')!=list(TESTS):raise ValueError('CPU proof source/suite binding incomplete')
 for n,h in d['files'].items():
  relative=PurePosixPath(n)
  if relative.is_absolute() or '..' in relative.parts:raise ValueError('unsafe staged source')
  q=Path(stage)/n
  if q.is_symlink() or not q.is_file() or q.stat().st_mode&0o222 or q.stat().st_uid!=os.geteuid() or sha(q)!=h:raise ValueError('staged source changed: '+n)
 if any(d['files'].get(n)!=h for n,h in PINNED.items()):raise ValueError('reviewed shared runtime changed')
 log=stage/'cpu_validation.log'
 if log.is_symlink() or log.stat().st_mode&0o222 or sha(log)!=d.get('log_sha256'):raise ValueError('CPU log changed')
 if re.findall(r'(\d+) passed',log.read_text())!=[str(d['passed'])] or re.search(r'\d+ (failed|skipped|error)',log.read_text()):raise ValueError('CPU log does not prove successful full regression')
 return d
def freeze(stage,report):
 parent=Path('/tmp'); mode=parent.stat().st_mode
 if parent.is_symlink() or not stat.S_ISDIR(mode) or mode&0o022 and not mode&stat.S_ISVTX:raise ValueError('unsafe freeze parent')
 out=Path(tempfile.mkdtemp(prefix='ft-t16-shared-',dir=parent))
 for n,h in report['files'].items():
  target=out/n;target.parent.mkdir(parents=True,exist_ok=True);data=(Path(stage)/n).read_bytes()
  if hashlib.sha256(data).hexdigest()!=h:raise ValueError('stage changed during freeze')
  target.write_bytes(data);target.chmod(0o444)
 for p in sorted(out.rglob('*'),reverse=True):
  if p.is_dir():p.chmod(0o555)
 out.chmod(0o555);return out
def preflight(stage,case):
 report=receipt(stage)
 if Path(__file__).resolve()!=(Path(stage)/Path(__file__).name).resolve() or sha(__file__)!=report['files'].get(Path(__file__).name):raise ValueError('execute launcher from its frozen CPU-tested stage')
 runner=Path(stage)/RUNNER; module=life.verified_module(runner,report['files'][RUNNER],'shared_t16_runner')
 if case not in module.CASES:raise ValueError('case unavailable in shared runtime')
 helper=life.verified_module(ROOT/'runs/plan_batches/e2_launch.py',HELPER_SHA,'shared_t16_helper');number,batch=life.next_round(ROUNDS),helper.next_batch(ROUNDS);cfg=module.CASES[case];rid=f"E2-R{number:03d}-gate-{cfg['card']}";argv=[PY,'-u',str(runner),'--case',case,'--rid',rid,'--batch',str(batch),'--candidate-commit',cfg['new_commit']]
 subprocess.run(argv,check=True,timeout=120)
 if life.next_round(ROUNDS)!=number or helper.next_batch(ROUNDS)!=batch or (ROUNDS/rid).exists():raise ValueError('ledger changed during preflight')
 return report,helper,argv,rid,batch,cfg
def launch(stage,case):
 report,helper,argv,rid,batch,cfg=preflight(stage,case); execution=freeze(stage,report);argv[2]=str(execution/RUNNER);argv.append('--run');path=ROOT/f'runs/dev_{cfg["card"]}'/f'launch_{rid}.json';reserved={'schema':'ft_t16_shared_launch/v1','state':'reserved','rid':rid,'batch':batch,'case':case,'card':cfg['card'],'candidate_commit':cfg['new_commit'],'parent_commit':cfg['parent_commit'],'source_stage':str(stage),'runner_sha256':report['files'][RUNNER],'base_runner_sha256':report['files'][BASE],'cpu_stage_sha256':sha(Path(stage)/'cpu_validation.json'),'frozen_runner':argv[2]};return life.reserve_process(helper,batch,rid,argv,path,reserved)
def main(default_case=None):
 p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);p.add_argument('--case',required=default_case is None,default=default_case);p.add_argument('--launch',action='store_true');a=p.parse_args();print(json.dumps(launch(a.stage,a.case) if a.launch else {'preflight':preflight(a.stage,a.case)[3]}))
if __name__=='__main__':main()
