"""Exercise the real one-shot launch transaction under cancellation/failure."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def transaction(tmp_path, mode):
    script = (Path(__file__).parents[1] / 'd06_selfcheck_195aa332_launch.sh').read_text()
    tree = ast.parse(script.split("<<'PY'\n", 1)[1].rsplit('\nPY\n', 1)[0])
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'launch_owned')
    handlers = {2:'previous-int',15:'previous-term'}
    events = []
    def register(signum, handler):
        previous = handlers[signum]
        handlers[signum] = handler
        return previous
    signals = SimpleNamespace(SIGINT=2, SIGTERM=15, SIG_IGN=0, signal=register)
    proc = SimpleNamespace(pid=123)
    def spawn(*_args, **_kwargs):
        assert _kwargs['env']['CUDA_VISIBLE_DEVICES'] == '0'
        events.append('spawn')
        if mode == 'signal':
            handlers[15](15, None)
        return proc
    class Helper:
        def write_exclusive(self, path, value):
            with path.open('x') as stream:json.dump(value, stream)
        def publish_receipt(self, path, identity, value):
            assert identity == (path.stat().st_dev, path.stat().st_ino)
            events.append('publish')
            if mode == 'publication-failure':raise OSError('fixture publish failed')
            path.write_text(json.dumps(value))
        def stop_owned_process(self, actual):
            assert actual is proc
            assert handlers[2] == handlers[15] == signals.SIG_IGN
            events.append('stop')
            if mode == 'cleanup-failure':raise RuntimeError('fixture cleanup failed')
    if mode == 'cleanup-failure':
        def fail_publication(*_):raise OSError('fixture publish failed')
        Helper.publish_receipt = fail_publication
    scope = {'signal':signals,'os':SimpleNamespace(environ={'CUDA_VISIBLE_DEVICES':''}),'subprocess':SimpleNamespace(Popen=spawn,DEVNULL=-1,STDOUT=-2)}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual-launch-transaction>', 'exec'), scope)
    receipt, log = tmp_path/'receipt.json', tmp_path/'launch.log'
    record = {'state':'reserved','argv':['fixture']}
    return scope['launch_owned'], (['fixture'],log,receipt,record,Helper(),tmp_path), handlers, events


@pytest.mark.parametrize('mode', ['signal','publication-failure','cleanup-failure'])
def test_owned_child_cleanup_and_failure_evidence_on_interruption(tmp_path, mode):
    launch, args, handlers, events = transaction(tmp_path, mode)
    with pytest.raises((InterruptedError,OSError)):
        launch(*args)
    assert 'stop' in events
    failure = json.loads((tmp_path/'receipt.json.failure.json').read_text())
    assert failure['pid'] == failure['pgid'] == 123
    assert failure['state'] == ('cleanup_failure' if mode == 'cleanup-failure' else 'launch_failed_owned_stopped')
    assert handlers == {2:'previous-int',15:'previous-term'}


def test_success_returns_published_owned_receipt(tmp_path):
    launch, args, handlers, events = transaction(tmp_path, 'success')
    result = launch(*args)
    assert result['state'] == 'launched' and result['pid'] == 123
    assert events == ['spawn','publish']
    assert handlers == {2:'previous-int',15:'previous-term'}
