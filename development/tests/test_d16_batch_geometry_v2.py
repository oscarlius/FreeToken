"""CPU regression for D16 geometry observation at the real scheduler boundary."""
from __future__ import annotations

import ast
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / name)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


V1 = _load('d16_exact_service_startup.py')
V2 = _load('d16_exact_service_startup_v2.py')
SCHEDULER_SOURCE = ROOT / 'e2base1' / 'python' / 'freetoken' / 'scheduler' / 'scheduler.py'


class _Registry:
    def get(self, uid):
        return {'prompt_sha256': f'prompt-{uid}'}


class _Adapter:
    def __init__(self):
        self.registry = _Registry()
        self.scheduler_batches = []
        self.errors = []

    def record_observer_error(self, message):
        self.errors.append(message)

    def observe_scheduler_batch(self, batch):
        def row(req):
            return {'uid': req.uid, 'input_ids_sha256': f'live-{req.uid}'}
        self.scheduler_batches.append({
            'scheduler_sequence': len(self.scheduler_batches) + 1,
            'phase': 'prefill', 'requests': [row(req) for req in batch.reqs],
            'padded_requests': [row(req) for req in batch.reqs],
            'active_table_idx': None,
        })


class _Batch:
    def __init__(self):
        self.reqs = [SimpleNamespace(uid=11, cached_len=2, device_len=5, extend_len=3)]
        self.is_prefill = False


class _Tensor:
    shape = (1, 3)


class _Engine:
    def __init__(self, failure=None):
        self.calls = []
        self.failure = failure
        self.result = SimpleNamespace(next_tokens_gpu='native-next-tokens')

    def forward_batch(self, batch, *args, **kwargs):
        self.calls.append((batch, args, kwargs))
        if self.failure is not None:
            raise self.failure
        return self.result


def _production_forward():
    tree = ast.parse(SCHEDULER_SOURCE.read_text(encoding='utf-8'))
    scheduler = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Scheduler')
    method = next(node for node in scheduler.body if isinstance(node, ast.FunctionDef) and node.name == '_forward')
    assigned = next(
        index for index, statement in enumerate(method.body)
        if isinstance(statement, ast.Assign)
        and isinstance(statement.targets[0], ast.Attribute)
        and isinstance(statement.targets[0].value, ast.Name)
        and statement.targets[0].value.id == 'batch'
        and statement.targets[0].attr == 'input_ids'
    )
    forwarded = next(
        index for index, statement in enumerate(method.body)
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'forward_batch'
            for node in ast.walk(statement)
        )
    )
    assert assigned < forwarded
    method = copy.deepcopy(method)
    method.decorator_list = []
    method.returns = None
    for argument in (*method.args.posonlyargs, *method.args.args, *method.args.kwonlyargs):
        argument.annotation = None
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace = {}
    exec(compile(module, str(SCHEDULER_SOURCE), 'exec'), namespace)
    return namespace['_forward']


class _TokenPool:
    def __init__(self, tensor):
        self.tensor = tensor
        self.writes = []

    def __getitem__(self, mapping):
        assert mapping == 'input_mapping'
        return self.tensor

    def __setitem__(self, mapping, value):
        self.writes.append((mapping, value))


class _ForwardInput(tuple):
    def __new__(cls, batch):
        return super().__new__(cls, (batch, 'sample_args', 'input_mapping', 'output_mapping'))

    @property
    def batch(self):
        return self[0]


def _run_actual_product_forward(batch, engine):
    scheduler = SimpleNamespace(
        token_pool=_TokenPool(_Tensor()), toolcall_anchor_id=None,
        engine=engine, cache_manager=SimpleNamespace(),
        decode_manager=SimpleNamespace(filter_reqs=lambda reqs: None),
    )
    result = _production_forward()(scheduler, _ForwardInput(batch))
    assert scheduler.token_pool.writes == [('output_mapping', result.next_tokens_gpu)]
    return result


def test_v1_reads_input_ids_during_schedule_but_v2_records_actual_forward_shape():
    batch = _Batch()
    old_adapter = _Adapter()
    V1.install_batch_geometry(old_adapter)
    try:
        old_adapter.observe_scheduler_batch(batch)
    except AttributeError as error:
        assert 'input_ids' in str(error)
    else:
        raise AssertionError('v1 must reproduce the pre-forward missing input_ids defect')

    batch = _Batch()
    adapter = _Adapter()
    engine = _Engine()
    V2.install_batch_geometry(adapter, engine)
    adapter.observe_scheduler_batch(batch)
    assert 'input_shape' not in adapter.scheduler_batches[0]
    native_result = _run_actual_product_forward(batch, engine)
    assert native_result is engine.result
    event = adapter.scheduler_batches[0]
    assert event['input_shape'] == [1, 3]
    assert event['geometry_input_source'] == 'Scheduler._forward:batch.input_ids'
    assert len(event['geometry_event_identity']) == 64
    assert adapter.errors == []


def test_v2_duplicate_missing_and_bad_shape_are_evidence_failures_not_forward_failures():
    adapter = _Adapter()
    engine = _Engine()
    V2.install_batch_geometry(adapter, engine)
    batch = _Batch()
    adapter.observe_scheduler_batch(batch)
    adapter.observe_scheduler_batch(batch)
    assert len(adapter.scheduler_batches) == 1
    assert adapter.errors == ['D16 geometry batch binding duplicated']
    batch.input_ids = _Tensor()
    expected = engine.forward_batch(batch, 'sample_args')
    assert expected is engine.result

    unbound = _Batch()
    unbound.input_ids = _Tensor()
    expected = engine.forward_batch(unbound, 'sample_args')
    assert expected is engine.result
    assert 'no matching scheduled batch binding' in adapter.errors[-1]

    class BadTensor:
        @property
        def shape(self):
            raise RuntimeError('shape unavailable')

    bad = _Batch()
    adapter.observe_scheduler_batch(bad)
    bad.input_ids = BadTensor()
    expected = engine.forward_batch(bad, 'sample_args')
    assert expected is engine.result
    assert 'shape unavailable' in adapter.errors[-1]

    changed = _Batch()
    adapter.observe_scheduler_batch(changed)
    adapter.scheduler_batches[-1]['requests'][0]['input_ids_sha256'] = 'tampered'
    changed.input_ids = _Tensor()
    expected = engine.forward_batch(changed, 'sample_args')
    assert expected is engine.result
    assert 'event identity changed' in adapter.errors[-1]


def test_v2_keeps_pending_batch_matching_within_capture_budget():
    adapter = _Adapter()
    adapter._max_captures = 1
    engine = _Engine()
    V2.install_batch_geometry(adapter, engine)
    adapter.observe_scheduler_batch(_Batch())
    adapter.observe_scheduler_batch(_Batch())
    assert len(adapter.scheduler_batches) == 1
    assert adapter.errors == ['D16 geometry batch binding exceeds capture budget']


def test_v2_preserves_native_forward_exception_and_records_capture_write_failure():
    adapter = _Adapter()
    adapter._max_bytes = 100
    adapter._scheduler_batch_bytes = 0
    engine = _Engine(failure=RuntimeError('native forward marker'))
    V2.install_batch_geometry(adapter, engine)
    batch = _Batch()
    adapter.observe_scheduler_batch(batch)
    batch.input_ids = _Tensor()
    try:
        engine.forward_batch(batch, 'sample_args')
    except RuntimeError as error:
        assert str(error) == 'native forward marker'
    else:
        raise AssertionError('native forward error was swallowed')
    assert any('capture bytes budget' in error for error in adapter.errors)

    class WriteFailAdapter(_Adapter):
        def observe_scheduler_batch(self, batch):
            raise OSError('receipt write failed')

    failed = WriteFailAdapter()
    healthy_engine = _Engine()
    V2.install_batch_geometry(failed, healthy_engine)
    unbound = _Batch()
    failed.observe_scheduler_batch(unbound)
    unbound.input_ids = _Tensor()
    result = healthy_engine.forward_batch(unbound, 'sample_args')
    assert result is healthy_engine.result
    assert 'receipt write failed' in failed.errors[0]
