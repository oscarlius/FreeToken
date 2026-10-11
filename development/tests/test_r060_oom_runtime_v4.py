"""Exercise the retained native gate's actual owned-lock check on CPU."""
import ast
import importlib.util
import os
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

DEV = Path(__file__).parents[1]


def native_gate(lock):
    source = ast.parse((DEV / 't16_r059_private_port_base_v3.py').read_text())
    cls = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == 'Runner')
    gate = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'gate')
    calls = []

    def command(argv, **kwargs):
        calls.append(argv)
        if argv[0] == 'nvidia-smi':
            return '0\n0\n0\n0'
        if argv[0] == 'ps':
            return 'PID ARGS\n'
        if argv[0] == 'git':
            return 'a' * 40 if 'rev-parse' in argv else ''
        return '/fixture/python/freetoken/__init__.py test test'

    namespace = {'LOCK': lock, 'command': command, 'os': os, 're': re, 'PY': 'cpu-fixture'}
    exec(compile(ast.Module(body=[gate], type_ignores=[]), '<actual-native-gate>', 'exec'), namespace)
    return namespace['gate'], calls


def test_actual_native_gate_reproduces_v3_and_accepts_v4_before_lock_take(tmp_path):
    lock = tmp_path / 'gpu.lock'
    lock.write_text('exact-owner')
    gate, calls = native_gate(lock)
    owner = {'lock_token': 'exact-owner', 'lock_inode': lock.stat().st_ino}
    fixture = SimpleNamespace(token=None, lock_inode=None, environment=lambda tree: {})
    with pytest.raises(RuntimeError, match='foreign GPU lock'):
        gate(fixture, tmp_path, 'a' * 40)
    assert calls == []
    fixture.token, fixture.lock_inode = owner['lock_token'], owner['lock_inode']
    gate(fixture, tmp_path, 'a' * 40)
    assert lock.read_text() == 'exact-owner' and calls
    fixture.lock_inode += 1
    with pytest.raises(RuntimeError, match='foreign GPU lock'):
        gate(fixture, tmp_path, 'a' * 40)


def test_v4_sets_identity_before_retained_execute_and_never_reopens(tmp_path):
    spec = importlib.util.spec_from_file_location('r060b_fixture', DEV / 'r060_oom_owned_launch_v4.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    retained = module.runtime()
    lock = tmp_path / 'gpu.lock'
    lock.write_text('owner')
    owner = {'lock_token': 'owner', 'lock_inode': lock.stat().st_ino}
    gate, _ = native_gate(lock)

    class Runner:
        token = lock_inode = None
        environment = staticmethod(lambda tree: {})
        def execute(self):
            gate(self, tmp_path, 'a' * 40)
            self.lock_take()
            self.lock_release()
            return 'reached-formal-measurement-boundary'

    assert retained.run_owned_runner(Runner(), owner, SimpleNamespace(LOCK=lock)) == 'reached-formal-measurement-boundary'
    assert lock.stat().st_ino == owner['lock_inode'] and lock.read_text() == 'owner'
