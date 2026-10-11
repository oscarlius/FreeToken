"""Exercise the generated wrapper, real spawn and real observer together."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

DEV = Path(__file__).parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name.removesuffix('.py'), DEV / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLI = '''
import json, multiprocessing as mp, os, sys, time
from pathlib import Path
from types import SimpleNamespace

def worker(ready, stop, uid):
    from freetoken.engine.engine import Engine
    from freetoken.scheduler.scheduler import Scheduler
    from freetoken.scheduler.io import SchedulerIOMixin
    from freetoken.message.backend import UserMsg, DetokenizeMsg
    root = Path(os.environ['R046C_T06_OBSERVER_DIR']) / 'workers' / str(os.getpid())
    if os.environ.get('R061_CPU_RESIDUE'):
        root.mkdir(parents=True); (root / 'residue').write_text('old')
    Engine()
    Scheduler()._process_one_msg(UserMsg(uid))
    SchedulerIOMixin()._reply_tokenizer_rank0([DetokenizeMsg(uid)])
    import __main__
    (root / 'spawn_main.json').write_text(json.dumps({'pid': os.getpid(),
        'main': __main__.__file__}))
    ready.set()
    assert stop.wait(8)

def main():
    context = mp.get_context('spawn')
    def start(uid):
        ready, stop = context.Event(), context.Event()
        process = context.Process(target=worker, args=(ready, stop, uid),
            name='freetoken-TP0-scheduler')
        process.start()
        deadline = time.monotonic() + 6
        while not ready.wait(.02):
            if process.exitcode is not None or time.monotonic() > deadline:
                if process.is_alive(): process.terminate()
                process.join()
                raise RuntimeError('CPU worker failed before readiness')
        return SimpleNamespace(processes=[process], stop=stop)
    from freetoken.server import supervisor
    supervisor.run_backend_supervisor(start(0), restart_backend=lambda: start(2))
'''


def package(tmp_path, version, residue=False):
    module = load(f'r061_oom_fault_prepare_v{version}.py')
    base, _ = module.runtime()
    run = tmp_path / ('v' + str(version))
    run.mkdir()
    boot = module.backend_startup_writer(base.write_fault_startup)(run)
    stub = run / 'stub'
    files = {
        'freetoken/engine/engine.py': 'class Engine:\n def __init__(self): pass\n',
        'freetoken/scheduler/scheduler.py': 'class Scheduler:\n def _process_one_msg(self,msg): return msg\n',
        'freetoken/scheduler/io.py': 'class SchedulerIOMixin:\n def _reply_tokenizer_rank0(self,msg): return msg\n',
        'freetoken/message/backend.py': '''class UserMsg:
 def __init__(self,uid): self.uid=uid;self.input_ids=[1,2]
class DetokenizeMsg:
 def __init__(self,uid):
  self.uid=uid;self.next_token=99;self.finished=True;self.finish_reason='stop'
''',
        'freetoken/server/supervisor.py': '''def retire(handle):
 handle.stop.set()
 for process in handle.processes:
  process.join(8)
  assert process.exitcode==0
def run_backend_supervisor(handle, restart_backend):
 retire(handle)
 retire(restart_backend())
''',
        'freetoken/cli.py': CLI,
    }
    for name, source in files.items():
        path = stub / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
        for parent in (path.parent, *path.parent.parents):
            if parent == stub:
                break
            (parent / '__init__.py').touch()
    observer = run / 'ordinary_observer'
    (observer / 'backend_handles').mkdir(parents=True)
    (observer / 'backend_handles' / 'historical.json').write_text('{}')
    env = {**os.environ, 'CUDA_VISIBLE_DEVICES': '',
           'R046C_T06_OBSERVER_DIR': str(observer),
           'PYTHONPATH': str(stub) + os.pathsep + os.environ.get('PYTHONPATH', '')}
    if residue:
        env['R061_CPU_RESIDUE'] = '1'
    result = subprocess.run([sys.executable, boot['startup']], cwd=run,
                            env=env, capture_output=True, text=True, timeout=22)
    return result, observer, boot


@pytest.mark.skipif(sys.platform != 'linux', reason='actual observer binds Linux /proc births')
def test_actual_wrapper_two_worker_epochs_preserve_physical_observer_paths(tmp_path):
    result, observer, boot = package(tmp_path, 7)
    assert result.returncode == 0, result.stdout + result.stderr
    workers = list((observer / 'workers').iterdir())
    assert len(workers) == 2
    assert not (observer / 'inputs.jsonl').exists()
    uids = []
    for worker in workers:
        row = json.loads((worker / 'inputs.jsonl').read_text())
        token = json.loads((worker / 'tokens.jsonl').read_text())
        spawn = json.loads((worker / 'spawn_main.json').read_text())
        assert spawn['main'] == boot['startup']
        assert str(spawn['pid']) == worker.name
        assert row['worker_birth']['pid'] == spawn['pid']
        assert Path(row['input_ids_path']).parent == worker
        assert token['uid'] == row['uid'] and token['next_token'] == 99
        uids.append(row['uid'])
    assert sorted(uids) == [0, 2]
    for epoch in (0, 1):
        handle = json.loads((observer / 'backend_handles' / f'epoch-{epoch}.json').read_text())
        assert handle['epoch'] == epoch and len(handle['workers']) == 1
        assert str(handle['workers'][0]['pid']) in {p.name for p in workers}


@pytest.mark.skipif(sys.platform != 'linux', reason='actual observer binds Linux /proc births')
def test_old_writer_reproduces_nonempty_root_failure(tmp_path):
    result, _, _ = package(tmp_path, 5)
    assert result.returncode != 0
    assert 'T06 observer directory is not empty' in result.stderr


@pytest.mark.skipif(sys.platform != 'linux', reason='actual observer binds Linux /proc births')
def test_new_writer_still_rejects_residue_in_its_own_worker_directory(tmp_path):
    result, _, _ = package(tmp_path, 7, residue=True)
    assert result.returncode != 0
    assert 'T06 observer directory is not empty' in result.stderr


