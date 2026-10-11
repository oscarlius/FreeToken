"""Restore the approved production candidate immediately after owned test cleanup."""
import json
from pathlib import Path
import subprocess
import time

HERE=Path(__file__).resolve().parent
RAW=Path('/data2/FreeToken/runs/dev_R067/E2-R067c-d20-short-tail-retry2')
PY='/data2/FreeToken/venv/bin/python'

def main():
    while not (RAW/'terminal.json').exists():
        time.sleep(5)
    terminal=json.loads((RAW/'terminal.json').read_text())
    assert terminal['rid']==RAW.name and terminal['actual_services']<=10
    assert terminal['actual_generation_calls']<=14
    assert not terminal['cleanup_errors'] and terminal['GPU_lock_released']
    assert terminal['verdict'] in ('PASS','not_met','failed_harness')
    deadline=time.monotonic()+120
    while Path('/data2/_shared/gpu.lock').exists():
        assert time.monotonic()<deadline,'test cleanup lock still present'
        time.sleep(1)
    assert not Path('/data2/FreeToken/run/production.active.json').exists()
    print(json.dumps({'event':'test_terminal_restoring_production','terminal':terminal,'at':time.time()}),flush=True)
    start=subprocess.run([PY,'-u',str(HERE/'start_approved_release.py')],capture_output=True,text=True)
    print(start.stdout,flush=True)
    assert start.returncode==0,start.stderr
    with (HERE/'RESTORE_WAIT.log').open('xb') as f:
        wait=subprocess.Popen(['nohup',PY,'-u',str(HERE/'wait_release_and_smoke.py')],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    print(json.dumps({'event':'production_restore_started','approval':'RESTORE481-E2-R067c-20261009-03','wait_pid':wait.pid,'at':time.time()}),flush=True)

if __name__=='__main__':main()
