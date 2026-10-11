from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


DEV = Path(__file__).parents[1]


def load(name: str):
    path = DEV / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


RUNNER = load('t10_raw_phase1_r017.py')


def digest(values):
    return hashlib.sha256(struct.pack(f'<{len(values)}i', *values)).hexdigest()


def replay_row(index, *, reason='length', tools=None, tokens=2, error=None, dry=False):
    return {'round': index, 'messages_sha': f'row-{index}', 'error': error, 'dry_run': dry,
            'finish_reason': reason, 'tool_calls': ([] if tools is None else tools),
            'completion_tokens': tokens, 'prompt_tokens': 2}


def replay_document(rows):
    return {'meta': {'params': {'max_tokens': 200}}, 'rounds': rows}


def token_record(uid, pid, prompt, generated, finish):
    return {'schema': 'ft_dev_tokens/v1', 'uid': uid, 'pid': pid,
            'prompt_ids': prompt, 'generated_ids': generated, 'prompt_length': len(prompt),
            'finish_reason': finish, 'prompt_ids_sha256_int32le': digest(prompt),
            'generated_ids_sha256_int32le': digest(generated),
            'input_ids_sha256_int32le': digest(prompt + generated)}


def test_r017_permits_real_tool_calls_only_as_engine_stop():
    rows = [replay_row(index, reason='tool_calls', tools=['read_file']) if index < 6
            else replay_row(index, reason='length') for index in range(12)]
    assert RUNNER.validate_replay_rows(replay_document(rows)) == rows
    assert RUNNER.expected_engine_finish_reason(rows[0]) == 'stop'
    assert RUNNER.expected_engine_finish_reason(rows[-1]) == 'length'


@pytest.mark.parametrize('mutate', [
    lambda rows: rows.__setitem__(0, replay_row(0, reason='unknown')),
    lambda rows: rows.__setitem__(0, replay_row(0, reason='tool_calls', tools=[])),
    lambda rows: rows.__setitem__(0, replay_row(0, reason='tool_calls', tools=[''])),
    lambda rows: rows.__setitem__(0, replay_row(0, reason='tool_calls', tools=['\t\n'])),
    lambda rows: rows.__setitem__(0, replay_row(0, reason='tool_calls', tools=['   '])),
    lambda rows: rows.__setitem__(0, replay_row(0, reason='tool_calls', tools='read_file')),
    lambda rows: rows.__setitem__(0, replay_row(0, reason='tool_calls', tools=[1])),
    lambda rows: rows.__setitem__(0, replay_row(0, error='HTTP 500')),
    lambda rows: rows.__setitem__(0, replay_row(0, dry=True)),
    lambda rows: rows.__setitem__(0, replay_row(0, tokens=0)),
    lambda rows: rows.__setitem__(0, replay_row(0, tokens=201)),
    lambda rows: rows.__setitem__(0, replay_row(0, tokens=True)),
    lambda rows: rows.pop(),
])
def test_r017_rejects_any_nonterminal_or_malformed_http_row(mutate):
    rows = [replay_row(index) for index in range(12)]
    mutate(rows)
    with pytest.raises(ValueError):
        RUNNER.validate_replay_rows(replay_document(rows))


def test_r017_bind_keeps_prompt_uid_pgid_and_engine_finish_contract(tmp_path, monkeypatch):
    arm = tmp_path / 'B1'; logits = arm / 'logits'; logits.mkdir(parents=True)
    pid, pgid = 9_109_001, 9_109_777
    (arm / 'owned_process.json').write_text(json.dumps({'pid': pid, 'pgid': pgid}))
    expected, rows = {}, []
    for index in range(12):
        key, prompt = f'row-{index}', [100 + index, 200 + index]
        tool = index < 6
        http_reason, engine_reason = ('tool_calls', 'stop') if tool else ('length', 'length')
        row = replay_row(index, reason=http_reason, tools=['read_file'] if tool else [], tokens=2)
        rows.append(row)
        expected[key] = {'messages_sha': key, 'prompt_length': len(prompt),
                         'prompt_ids': prompt, 'prompt_ids_sha256_int32le': digest(prompt)}
        path = logits / f'tokens_uid{index}_pid{pid}.json'
        path.write_text(json.dumps(token_record(index, pid, prompt, [7, 8], engine_reason)))
    monkeypatch.setattr(RUNNER.os, 'getpgid', lambda value: pgid, raising=False)
    bound = object.__new__(RUNNER.Run).bind(arm, rows, expected, set())
    assert len(bound) == 12
    assert bound['row-0']['http_finish_reason'] == 'tool_calls'
    assert bound['row-0']['engine_finish_reason'] == 'stop'
    assert bound['row-6']['http_finish_reason'] == 'length'
    assert bound['row-6']['engine_finish_reason'] == 'length'


@pytest.mark.parametrize('fault', ('engine_length', 'wrong_prompt', 'foreign_pgid', 'duplicate_uid', 'missing_row'))
def test_r017_bind_rejects_engine_or_identity_relaxation(tmp_path, monkeypatch, fault):
    arm = tmp_path / 'B1'; logits = arm / 'logits'; logits.mkdir(parents=True)
    pid, pgid = 9_110_001, 9_110_777
    (arm / 'owned_process.json').write_text(json.dumps({'pid': pid, 'pgid': pgid}))
    expected, rows = {}, []
    for index in range(12):
        key, prompt = f'row-{index}', [100 + index, 200 + index]
        rows.append(replay_row(index, reason='tool_calls', tools=['read_file'], tokens=2))
        expected[key] = {'messages_sha': key, 'prompt_length': 2, 'prompt_ids': prompt,
                         'prompt_ids_sha256_int32le': digest(prompt)}
        record = token_record(index, pid, prompt, [7, 8], 'stop')
        if fault == 'engine_length' and index == 0:
            record['finish_reason'] = 'length'
        if fault == 'wrong_prompt' and index == 0:
            record = token_record(index, pid, [999, 200], [7, 8], 'stop')
        if fault == 'duplicate_uid' and index == 1:
            record = token_record(0, pid, prompt, [7, 8], 'stop')
        (logits / f"tokens_uid{record['uid']}_pid{pid}.json").write_text(json.dumps(record))
    if fault == 'missing_row':
        (logits / f'tokens_uid11_pid{pid}.json').unlink()
    monkeypatch.setattr(RUNNER.os, 'getpgid', lambda value: pgid + 1 if fault == 'foreign_pgid' else pgid, raising=False)
    with pytest.raises(ValueError):
        object.__new__(RUNNER.Run).bind(arm, rows, expected, set())


