"""Append-only recovery of window02's exact dead owner, then approved Restore06."""
import importlib.util
import json
from pathlib import Path
import subprocess
import time

import gpu_window as master
from hybrid_service import alive_members, idle, load_d07
from window_measure import write

def execute():
    # Fixed target; no discovery or modification of original terminal artifacts.
    root = Path('/data2/FreeToken/runs/dev_D08_D10_20261011/window02')
    events = [json.loads(row) for row in (root/'events.jsonl').read_text().splitlines()]
    start = next(row for row in events if row['event'] == 'window_started')
    deadline = start['deadline_epoch']
    owner = json.loads((root/'hybrid_service/owner.json').read_text())
    d07 = load_d07()
    for pid in (owner['birth']['pid'], start['master_identity']['pid']):
        if d07.process_identity(pid) is not None or alive_members(pid):
            raise RuntimeError('original owned process or group still present')
    if time.time() >= deadline-600:
        raise RuntimeError('insufficient original window recovery budget')
    idle(d07)
    recovery = root/'root_owned_recovery'
    recovery.mkdir(exist_ok=False)
    write(recovery/'cleanup_proof.json', {
        'at': time.time(), 'dead_hybrid': owner['birth'],
        'dead_master': start['master_identity'], 'owner': owner['gpu_owner'],
        'no_compute_process': True, 'gpu_memory_below_1000_mib': True,
        'ports_bindable': True, 'original_terminal_preserved': True,
    })
    # The helper validates exact token, inode and device again before unlink.
    d07.release_d07_gpu_lock(owner['gpu_owner'])
    spec = importlib.util.spec_from_file_location('restore06_recovery',master.RESTORE/'deploy_conditional.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.require_root_final_review(module.load())
    release_deadline = deadline-600
    started = master.bounded_restore_command(master.command('start_approved_release.py'), recovery,
                                            'restore_start', release_deadline, 90)
    smoke = master.bounded_restore_command(master.command('wait_release_and_smoke.py'), recovery,
                                          'restore_smoke', release_deadline, 900) if started.returncode == 0 else None
    if started.returncode or smoke.returncode:
        def runner(argv):
            name = Path(argv[-1]).stem
            return master.bounded_restore_command(argv,recovery,'recovery_'+name,deadline-5,
                                                  150 if name == 'stop_approved_restore' else 240)
        code = module.recover_after_restore_failure(runner)
        write(recovery/'terminal.json',{'rollback184': True,'code':code,
                                      'all_later_gpu_stopped':True,'at':time.time()})
        return
    with (recovery/'observer.log').open('xb') as handle:
        observer = subprocess.Popen(master.command('post_night_observer.py'),stdout=handle,
                                    stderr=subprocess.STDOUT,start_new_session=True)
    write(recovery/'terminal.json', {'rollback184':False,'smoke_passed':True,
                                   'observer_parent_pid':observer.pid,'observation_still_open':True,
                                   'at':time.time(),'deadline_exceeded':time.time()>deadline})


if __name__ == '__main__':
    execute()
