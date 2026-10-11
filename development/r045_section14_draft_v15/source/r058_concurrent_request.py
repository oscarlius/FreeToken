"""Bounded concurrent request primitives for R058; transport remains caller-owned."""
from __future__ import annotations
from dataclasses import dataclass
import threading
import time
from typing import Callable, Mapping

TIMEOUT_SECONDS = 90

@dataclass(frozen=True)
class RequestSpec:
    name: str
    prompt_tokens: int
    payload: Mapping

def _result(name, entered, completed, *, value=None, error=None, **extra):
    return {'name': name, 'entered_ns': entered, 'completed_ns': completed, 'value': value,
            'error': None if error is None else repr(error), **extra}

def simultaneous(left: RequestSpec, right: RequestSpec, send: Callable[[RequestSpec], object], timeout=TIMEOUT_SECONDS):
    gate, lock, rows = threading.Barrier(3, timeout=timeout), threading.Lock(), []
    def invoke(spec):
        entered = None
        try:
            gate.wait(); entered = time.monotonic_ns(); value = send(spec)
            row = _result(spec.name, entered, time.monotonic_ns(), value=value)
        except BaseException as error:
            gate.abort(); row = _result(spec.name, entered or time.monotonic_ns(), time.monotonic_ns(), error=error)
        with lock: rows.append(row)
    workers = [threading.Thread(target=invoke, args=(item,), name='r058-'+item.name) for item in (left, right)]
    for worker in workers: worker.start()
    try: gate.wait()
    except BaseException: gate.abort()
    for worker in workers: worker.join(timeout)
    if any(worker.is_alive() for worker in workers):
        gate.abort(); raise RuntimeError('R058 simultaneous send did not terminate before timeout')
    if len(rows) != 2 or any(row['error'] for row in rows): raise RuntimeError('R058 simultaneous send failed: '+repr(rows))
    return sorted(rows, key=lambda row: row['name'])

def decode_then_third(left: RequestSpec, right: RequestSpec, third: RequestSpec,
                      stream: Callable[[RequestSpec, Callable[[], None]], object],
                      send: Callable[[RequestSpec], object], timeout=TIMEOUT_SECONDS):
    """Dispatch 64K only after actual tokens in both live decode streams."""
    start, token = threading.Barrier(3, timeout=timeout), [threading.Event(), threading.Event()]
    failed, lock, rows = threading.Event(), threading.Lock(), []
    def decode(index, spec):
        entered = None; first = None
        try:
            start.wait(); entered = time.monotonic_ns()
            def actual_token():
                nonlocal first
                if first is None: first = time.monotonic_ns(); token[index].set()
            value = stream(spec, actual_token)
            if first is None: raise RuntimeError('R058 decode stream ended before actual token')
            terminal = time.monotonic_ns()
            row = _result(spec.name, entered, terminal, value=value, first_token_ns=first, terminal_ns=terminal)
        except BaseException as error:
            failed.set(); start.abort(); terminal = time.monotonic_ns()
            row = _result(spec.name, entered or terminal, terminal, error=error, first_token_ns=first, terminal_ns=terminal)
        with lock: rows.append(row)
    workers = [threading.Thread(target=decode, args=(i, item), name='r058-'+item.name) for i, item in enumerate((left, right))]
    for worker in workers: worker.start()
    try: start.wait()
    except BaseException: failed.set(); start.abort()
    deadline = time.monotonic()+timeout
    while not failed.is_set() and not all(event.is_set() for event in token) and time.monotonic() < deadline: time.sleep(.002)
    with lock: already_finished = bool(rows)
    if failed.is_set() or not all(event.is_set() for event in token) or already_finished:
        for worker in workers: worker.join(timeout)
        raise RuntimeError('R058 decode barrier failed before live dual decode: '+repr(rows))
    entered = time.monotonic_ns()
    try:
        value = send(third)
        dispatch_ns = value.get('dispatch_ns') if isinstance(value,dict) else None
        if not isinstance(dispatch_ns,int): raise RuntimeError('R058 sender receipt lacks dispatch_ns')
        if any(row.get('terminal_ns',dispatch_ns) <= dispatch_ns for row in rows): raise RuntimeError('R058 64K dispatched after decode terminal')
        third_row = _result(third.name, entered, time.monotonic_ns(), value=value, dispatched_while_decoding=True)
    except BaseException as error: failed.set(); third_row = _result(third.name, entered, time.monotonic_ns(), error=error, dispatched_while_decoding=True)
    with lock: rows.append(third_row)
    for worker in workers: worker.join(timeout)
    if any(worker.is_alive() for worker in workers): raise RuntimeError('R058 decode streams did not terminate before timeout')
    if len(rows) != 3 or any(row['error'] for row in rows): raise RuntimeError('R058 decode/64K failed: '+repr(rows))
    return sorted(rows, key=lambda row: row['name'])
