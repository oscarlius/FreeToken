import ast
import importlib.util
import io
import json
from pathlib import Path
import urllib.error

import pytest

from test_r055b_owned_launch import load as load_owner, install_fake_product, exec_observer, message


def load_fix():
    path = Path(__file__).parents[1] / 'r055b_pause_harness_v2.py'
    spec = importlib.util.spec_from_file_location('pause_harness_v2', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_api_timeout_receipt_is_preserved(monkeypatch):
    tool = load_fix()
    receipt = {'status': 'timeout', 'request_id': 'cancel-2', 'error': None}

    def answer(request, timeout):
        assert request.full_url == 'http://127.0.0.1:51449/dev/pause'
        assert json.loads(request.data) == {'seconds': 30.0, 'timeout': 0.05}
        raise urllib.error.HTTPError(request.full_url, 504, 'Gateway Timeout', {},
                                     io.BytesIO(json.dumps(receipt).encode()))

    monkeypatch.setattr(tool.urllib.request, 'urlopen', answer)
    assert tool.pause_request(51449, 30.0, 0.05) == {**receipt, 'http_status': 504}


@pytest.mark.parametrize('code,body,expected', [
    (500, b'{}', urllib.error.HTTPError),
    (504, b'not-json', RuntimeError),
    (504, b'{"status":"accepted","request_id":"x"}', RuntimeError),
    (504, b'{"status":"timeout","request_id":""}', RuntimeError),
    (504, b'{"status":"timeout","request_id":"x","error":"cancel enqueue failed"}', RuntimeError),
])
def test_other_http_failures_are_not_accepted(monkeypatch, code, body, expected):
    tool = load_fix()

    def answer(request, timeout):
        raise urllib.error.HTTPError(request.full_url, code, 'failure', {}, io.BytesIO(body))

    monkeypatch.setattr(tool.urllib.request, 'urlopen', answer)
    with pytest.raises(expected):
        tool.pause_request(51449, 30.0, 0.05)


def test_observer_uses_candidate_message_boundary(monkeypatch, tmp_path):
    tool, owner = load_fix(), load_owner()
    scheduler = Path(__file__).parents[1] / 'e2r046_pausefix/python/freetoken/scheduler/scheduler.py'
    if not scheduler.exists():
        scheduler = Path('/data2/FreeToken/wt/e2base1-p1/python/freetoken/scheduler/scheduler.py')
    assert scheduler.is_file(), 'actual candidate scheduler source required'
    tree = ast.parse(scheduler.read_text(encoding='utf-8'))
    receiver = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == '_process_one_msg')
    classes = {node.args[1].id for node in ast.walk(receiver)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == 'isinstance' and len(node.args) == 2
               and isinstance(node.args[1], ast.Name)}
    assert 'UserMsg' in classes and 'InputTokenizedMsg' not in classes
    original = owner.PAUSE_OBSERVER
    owner.PAUSE_OBSERVER = tool.corrected_observer(owner)
    assert original != owner.PAUSE_OBSERVER
    monkeypatch.setenv('R055B_MODEL_MEMORY', str(tmp_path / 'cuda.jsonl'))
    monkeypatch.setenv('R055_PAUSE_OBSERVATIONS', str(tmp_path / 'pause.jsonl'))
    Scheduler, IO, Engine = install_fake_product(monkeypatch)
    exec_observer(owner)
    Engine()
    Scheduler()._process_one_msg(message('UserMsg', uid=41))
    IO()._reply_tokenizer_rank0([message('DetokenizeMsg', uid=41, finished=True, next_token=7)])
    rows = [json.loads(line) for line in (tmp_path / 'cuda.jsonl').read_text().splitlines()]
    assert [row['event'] for row in rows] == ['model_loaded', 'request_before', 'request_after']
    assert rows[1]['uid'] == rows[2]['uid'] == '41'


def test_repairs_bind_actual_owner_call_path_without_launch():
    tool, owner = load_fix(), load_owner()
    old_rid = owner.RID
    tool.install(owner)
    assert owner._legacy().pause_request is tool.pause_request
    assert 'elif name=="UserMsg":' in owner.PAUSE_OBSERVER
    assert 'r055b_pause_harness_v2.py' in owner.SOURCE_DEPENDENCIES
    assert owner.RID == old_rid  # A new retry RID still requires user disposition.
    with pytest.raises(RuntimeError, match='already installed'):
        tool.install(owner)
