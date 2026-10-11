"""Exercise the product supervisor; fake handles replace OS processes only."""
from pathlib import Path
import importlib.util
import os
import queue
import sys

import pytest


SOURCE = Path(os.environ.get('FT_OOM_TEST_WORKTREE',
    Path(__file__).parents[1] / 'e2oom-recovery')) / 'python/freetoken/server/supervisor.py'
spec = importlib.util.spec_from_file_location('oom_actual_supervisor', SOURCE)
supervisor = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = supervisor
spec.loader.exec_module(supervisor)


class Process:
    def __init__(self, name, *, stubborn=False, unkillable=False):
        self.name, self.alive = name, True
        self.stubborn, self.unkillable = stubborn, unkillable
        self.calls = []

    def is_alive(self):
        return self.alive

    def terminate(self):
        self.calls.append('terminate')
        if not self.stubborn:
            self.alive = False

    def join(self, timeout):
        self.calls.append(('join', timeout))

    def kill(self):
        self.calls.append('kill')
        if not self.unkillable:
            self.alive = False


def handle(*processes):
    replies = queue.Queue()
    replies.put('worker ready')
    return supervisor.BackendHandle(replies, list(processes), 1)


def inject_oom(backend):
    backend.ack_queue.put(('error', 'torch.cuda.OutOfMemoryError: injected'))
    backend.processes[0].alive = False


def run(old, restart, ready):
    failures, restarting = [], []
    stopping = [False]
    supervisor.run_backend_supervisor(old, supervisor.LoadProgress(),
        on_ready=lambda: ready(stopping), on_failure=failures.append, poll=0,
        restart_backend=restart, on_restarting=lambda reason, attempt: restarting.append((reason, attempt)),
        is_shutting_down=lambda: stopping[0])
    return failures, restarting


def test_post_ready_oom_retires_every_old_worker_before_replacement():
    old = handle(Process('scheduler'), Process('tokenizer', stubborn=True), Process('detokenizer'))
    fresh = handle(Process('replacement'))
    ready_calls = []

    def restart():
        assert all(not p.is_alive() for p in old.processes)
        assert all(any(isinstance(x, tuple) and x[0] == 'join' for x in p.calls) for p in old.processes)
        assert 'kill' in old.processes[1].calls
        return fresh

    def ready(stopping):
        ready_calls.append(True)
        if len(ready_calls) == 1:
            inject_oom(old)
        else:
            fresh.processes[0].alive = False
            stopping[0] = True

    failures, restarting = run(old, restart, ready)
    assert failures == [] and len(ready_calls) == 2
    assert len(restarting) == 1 and restarting[0][1] == 1


def test_an_old_worker_that_survives_kill_blocks_replacement():
    old = handle(Process('scheduler'), Process('stuck', stubborn=True, unkillable=True))
    factories = []
    failures, _ = run(old, lambda: factories.append(True), lambda _: inject_oom(old))
    assert factories == []
    assert len(failures) == 1 and 'could not be stopped' in failures[0]


def test_replacement_factory_failure_reaches_failure_callback():
    old = handle(Process('scheduler'), Process('tokenizer'))

    def factory():
        raise ValueError('replacement spawn failed')

    failures, _ = run(old, factory, lambda _: inject_oom(old))
    assert len(failures) == 1 and 'replacement spawn failed' in failures[0]
    assert 'oom' in failures[0].lower()
    assert all(not p.is_alive() for p in old.processes)


def test_replacement_loading_failure_cleans_the_replacement_workers():
    old = handle(Process('scheduler'))
    fresh = handle(Process('new scheduler'), Process('new tokenizer'))
    fresh.ack_queue = queue.Queue()
    fresh.ack_queue.put(('error', 'replacement loading failed'))
    failures, _ = run(old, lambda: fresh, lambda _: inject_oom(old))
    assert len(failures) == 1 and 'replacement loading failed' in failures[0]
    assert all(not p.is_alive() for p in fresh.processes)


def test_second_oom_is_bounded_and_releases_all_workers():
    old = handle(Process('scheduler'))
    fresh = handle(Process('new scheduler'), Process('new tokenizer'))
    ready_calls, factories = [], []

    def restart():
        factories.append(True)
        return fresh

    def ready(_):
        ready_calls.append(True)
        inject_oom(old if len(ready_calls) == 1 else fresh)

    failures, restarting = run(old, restart, ready)
    assert len(factories) == 1 and len(restarting) == 1 and len(ready_calls) == 2
    assert len(failures) == 1 and 'OutOfMemoryError' in failures[0]
    assert all(not p.is_alive() for p in fresh.processes)


def test_non_oom_death_preserves_existing_no_restart_behavior():
    old = handle(Process('scheduler'))
    factories = []

    def ready(_):
        old.ack_queue.put(('error', 'ValueError: invalid input'))
        old.processes[0].alive = False

    failures, restarting = run(old, lambda: factories.append(True), ready)
    assert failures == ['ValueError: invalid input'] and restarting == [] and factories == []
