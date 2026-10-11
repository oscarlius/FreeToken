#!/usr/bin/env python3
"""D09 root-reviewed GPU runner. CPU mode only validates immutable bindings.
--run accepts only a root-sealed admission file with an explicit command and exact config hash.
It writes an owned terminal receipt and terminates the process group on every exit path.
"""
import argparse, hashlib, json, os, signal, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
CFG=ROOT/'D09_GPU_CONFIG.json'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load():
    c=json.loads(CFG.read_text()); assert c['candidate']['commit']=='c17b69a46cd512fbf3d127d3879bce92caae457b'; return c
def filedry(c):
    out=ROOT/'FILEDRY.json'; rec={'schema':'freetoken.d09.filedry/v1','at':time.time(),'config_sha256':sha(CFG),'candidate':c['candidate'],'prediction':c['prediction'],'gates':c['gates'],'gpu_started':False,'http_started':False,'compile_started':False}; out.write_text(json.dumps(rec,indent=2)+'\n'); print(out)
def main():
    p=argparse.ArgumentParser(); p.add_argument('--filedry',action='store_true'); p.add_argument('--run',action='store_true'); p.add_argument('--admission',type=Path); a=p.parse_args(); c=load()
    if a.filedry: filedry(c); return
    if not a.run: p.error('choose --filedry or --run')
    assert a.admission and a.admission.is_file(), 'root-sealed admission required'
    ad=json.loads(a.admission.read_text()); assert ad.get('root_approved') is True; assert ad['config_sha256']==sha(CFG); assert ad['rid']==c['rid']; cmd=ad['command']; assert isinstance(cmd,list) and cmd and all(isinstance(x,str) for x in cmd)
    run=Path(c['terminal']['owned_run_root']); assert not run.exists(), 'RID already used'; run.mkdir(parents=True); proc=None; terminal={'rid':c['rid'],'config_sha256':sha(CFG),'admission_sha256':sha(a.admission),'started_at':time.time(),'verdict':'failed_harness'}
    try:
        proc=subprocess.Popen(cmd,cwd=run,start_new_session=True,stdin=subprocess.DEVNULL,stdout=(run/'runner.log').open('xb'),stderr=subprocess.STDOUT); terminal['pid']=proc.pid; rc=proc.wait(); terminal['returncode']=rc; terminal['verdict']='completed' if rc==0 else 'failed_harness'
    finally:
        if proc and proc.poll() is None: os.killpg(proc.pid,signal.SIGTERM); proc.wait(timeout=120)
        terminal['ended_at']=time.time(); (run/'terminal.json').write_text(json.dumps(terminal,indent=2)+'\n')
    if terminal['verdict']!='completed': raise SystemExit(1)
if __name__=='__main__': main()
