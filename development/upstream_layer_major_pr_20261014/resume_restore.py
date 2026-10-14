"""Complete the already approved, not-yet-started E3 restore after CUDA release."""
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ops',HERE.parent/'r067c_retry2_production_control_20261009/ssh_ops.py')
ops=importlib.util.module_from_spec(spec);spec.loader.exec_module(ops)
client=ops.connect()
try:
    ops.run(client,r'''
import json, os, pathlib, subprocess
root=pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
code=r"""
import json, pathlib, subprocess, sys, time
root=pathlib.Path('/data2/FreeToken/development/upstream_layer_major_pr_20261014')
sys.path.insert(0,str(root));import gpu_window_ready as window
auth=json.loads((root/'WINDOW_AUTHORIZATION_SEALED.json').read_text())
original=json.loads((root/'GPU_WINDOW_TERMINAL.json').read_text())
assert len(original['arms'])==3 and all(x['classification']=='kept' for x in original['arms'])
assert not original['restored'] and not pathlib.Path('/data2/FreeToken/run/production.active.json').exists()
assert not (root/'restore_start.log').exists()
events=[json.loads(line) for line in (root/'window_events.jsonl').read_text().splitlines()]
deadline=events[0]['window_deadline'];window.remaining(deadline)
helper=window.load(pathlib.Path(auth['frozen_ops']['path']).parent/'d07_g3g4_prepare.py','recovery_helper')
helper.require_gpu_idle();lifecycle=helper.load_owned_lifecycle()
assert not helper.LOCK.exists()
record={'at':time.time(),'original_terminal_unchanged':True,'gpu_released_before_resume':True,
        'reason':'post-exit CUDA memory release lag; no compute process and4MiB at read-only followup',
        'measurement_rerun':False,'sdk_calls':2,'restored':False}
try:
    for name,log in (('start_approved_release.py','restore_start.log'),('wait_release_and_smoke.py','restore_smoke.log')):
        with (root/log).open('xb') as f:
            process=subprocess.Popen(['/data2/FreeToken/venv/bin/python',str(root/'restore_e3'/name)],
                stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            rc=process.wait(timeout=window.remaining(deadline))
            assert rc==0,(name,rc)
        finally:lifecycle.stop_owned_process(process,10,5)
    record['restored']=True
    window.log('production_restored_after_release_wait',sdk_calls=2,
               approval_id=json.loads((root/'restore_e3/DEPLOYMENT_APPROVAL.json').read_text())['approval_id'])
except BaseException as exc:record['error']=repr(exc)
record['finished_at']=time.time()
with (root/'GPU_WINDOW_RECOVERY.json').open('x') as f:json.dump(record,f,indent=2)
print(json.dumps(record),flush=True)
"""
with (root/'restore_resume_supervisor.log').open('xb') as f:
    p=subprocess.Popen(['/data2/FreeToken/venv/bin/python','-u','-c',code],cwd=root,
        env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONPATH=str(root),PYTHONDONTWRITEBYTECODE='1'),
        stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print('Approved restoration resume controller PID',p.pid)
''')
finally:client.close()
