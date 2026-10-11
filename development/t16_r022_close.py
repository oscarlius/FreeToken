"""Seal the exact independently reviewed R022 four-arm measurement."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path('/data2/FreeToken')
ROUNDS=Path('/data2/_shared/runs/ft_rounds')
RID='E2-R022-gate-D14'
BATCH=50
REVIEW_SHA='d212243e709d521ad93c91893103eb202ae9497c736c38692480c340e68662ec'
WRITER_SHA='67c36b2fe91400372e3e470caa443afeefde8ac53bb7aff515e32d407a4d48ff'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(data)


def encoded(value):
    return (json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()


def close():
    source=Path(__file__).with_name('t16_r022_review.py')
    if source.is_symlink() or sha(source)!=REVIEW_SHA:raise ValueError('reviewer source changed')
    spec=importlib.util.spec_from_file_location('ft_r022_review_for_close',source)
    reviewer=importlib.util.module_from_spec(spec);spec.loader.exec_module(reviewer)
    directory=reviewer.guarded(ROUNDS/RID)
    result=reviewer.audit(allow_review=True)
    review_path=directory/'review_batch50.json'
    if reviewer.load(review_path)!=result:raise ValueError('independent review no longer recomputes')
    before={p.relative_to(directory).as_posix():sha(p) for p in directory.rglob('*') if p.is_file()}
    receipt_path=ROOT/'runs/dev_D14'/('launch_'+RID+'.json')
    receipt=reviewer.load(receipt_path)
    frozen=Path(receipt['frozen_runner']).parent
    stage=Path(receipt['source_stage'])
    tools={name:(ROOT/'scripts'/name).read_bytes() for name in ('round_json_append.py','round_close.py','round_close.sh')}
    if hashlib.sha256(tools['round_json_append.py']).hexdigest()!=WRITER_SHA:raise ValueError('D04 writer changed')
    for name,data in tools.items():
        if data!=(Path(__file__).parent/name).read_bytes():raise ValueError('D04 local/server bytes differ: '+name)
    for origin,target in ((frozen,'runtime_source'),(stage,'cpu_source')):
        for path in origin.rglob('*'):
            if path.is_symlink():raise ValueError('source archive symlink')
            if path.is_file():write(directory/'source_tools'/target/path.relative_to(origin),path.read_bytes())
    for path in (Path(__file__),source,receipt_path,ROOT/'scripts/serve_args_diff.py',
                 ROOT/'scripts/cold_eq.py',ROOT/'scripts/ft_probe_ckpt_tax.py'):
        write(directory/'source_tools'/path.name,path.read_bytes())
    for name,data in tools.items():write(directory/name,data)
    write(directory/'batch.sh',(directory/'batch50.sh').read_bytes())
    log=ROUNDS/'batch50.log'
    arms={name:{'owned_service_pid':pid} for name,pid in result['service_pids'].items()}
    metadata={'schema':'ft_round/v2','round_id':RID,'epoch':2,'card':'T16','title':'D14 exact four-arm default-path gate',
              'parent':'E2-pre-gate-D00','base':{'commit':reviewer.PARENT,'code_version':'E2-base@23f2e2c','worktree':'/data2/FreeToken/wt/e2base'},
              'experimental':{'candidate_commit':reviewer.CANDIDATE,'worktree':'/data2/FreeToken/wt/e2d14'},
              'serve':{'arms':arms},'design':{'batch':BATCH,'serve_order':list(reviewer.ARMS)},
              'independent_review_sha256':sha(review_path),
              'diagnostics':{'gate_sha256':result['gate_sha256'],'independent_review_sha256':sha(review_path),
                             'reviewer_source_sha256':REVIEW_SHA,'original_raw_files':before,
                             'cpu_stage_sha256':receipt['cpu_stage_sha256']},
              'results':result['recomputed'],
              'acceptance_limits':['Cold default-path T16 only; prefix-hit T17 and corrected T10 remain pending.',
                                   'Service PID start ticks were not retained; terminal process proof is bounded.'],
              'proposed_verdict':'kept','verdict':'pending_review','verdict_history':[],'retractions':[],
              'batch_logs':[{'path':str(log),'sha256':sha(log)}]}
    write(directory/'round.json',encoded(metadata))
    subprocess.run(['bash',str(directory/'round_close.sh'),RID,'--round-root',str(ROUNDS)],
                   env={**os.environ,'FT_ROUND_PYTHON':sys.executable},check=True)
    subprocess.run([sys.executable,str(directory/'round_json_append.py'),str(directory),'verdict',
                    '--new','kept','--reason','Four-arm raw GPU measurement independently recomputed: full 128-token text, PID-only parameters, 13/13 complete prefill transfer rows. Measurement accepted; T17/T10 and D14 baseline acceptance remain pending.',
                    '--evidence','review_batch50.json','gate_batch50.json',
                    '--by','Codex mainline under CODEX_HANDOFF_20261004b'],check=True)
    subprocess.run([sys.executable,str(directory/'round_json_append.py'),str(directory),'check'],check=True)
    if any(sha(directory/name)!=digest for name,digest in before.items()):raise ValueError('original raw bytes changed')
    if any(p.stat().st_mode&0o222 for p in (directory,*directory.rglob('*'))):raise ValueError('closure not read-only')
    return {'rid':RID,'batch':BATCH,'verdict':'kept','round_sha256':sha(directory/'round.json'),
            'manifest_sha256':sha(directory/'MANIFEST.sha256'),'review_sha256':sha(review_path),
            'original_raw_files_verified':len(before)}


if __name__=='__main__':
    if sys.platform!='linux':raise SystemExit('actual Linux evidence host required')
    print(json.dumps(close(),sort_keys=True))
