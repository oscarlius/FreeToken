import importlib.util
import pickle
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest


class Tensor:
    def __init__(self, value): self.value = value
    def detach(self): return self
    def to(self, *_args, **_kw): return self
    def clone(self): return Tensor(_clone(self.value))
    @property
    def shape(self): return _shape(self.value)
    @property
    def dtype(self): return 'fake'
    def fill_(self, value): self.value = [value] * len(self.value); return self
    def copy_(self, other): self.value = _clone(other.value); return self


def _clone(x): return list(x) if isinstance(x, list) else x
def _shape(x): return (len(x),) if isinstance(x, list) else ()


class Grid:
    def __init__(self): self.values = {}
    def __getitem__(self, key):
        return self.values.setdefault(tuple(key) if isinstance(key, tuple) else key, Tensor([0, 0]))


class FakeTorch:
    @staticmethod
    def stack(values): return Tensor([_clone(x.value) for x in values])
    @staticmethod
    def save(value, path):
        with open(path, 'wb') as stream: pickle.dump(value.value, stream)
    @staticmethod
    def load(path, **_kw):
        with open(path, 'rb') as stream: return Tensor(pickle.load(stream))


sys.modules['torch'] = FakeTorch
PATH = Path(__file__).parents[1] / 't17_matched_observe.py'
SPEC = importlib.util.spec_from_file_location('matched', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Pool:
    def __init__(self):
        self.num_linear_layers = 2
        self.conv_states, self.recurrent_states = Grid(), Grid()
        self.conv_slot, self.ngram_slot = Grid(), Grid()
    def local_index(self, index): return index
    def slot_state(self, name, _index=None): return self.conv_slot if name == 'ple_conv' else self.ngram_slot


class Layer:
    def __init__(self, index, ple=False):
        self._layer_id, self._is_linear = index, True
        self.linear_attn = SimpleNamespace(layer_id=index)
        self.ple = SimpleNamespace(layer_id=index) if ple else None
        self.calls = 0
    def forward(self, value, batch):
        self.calls += 1; slot = batch.reqs[0].linear_slot_idx
        self.pool.conv_states[self.linear_attn.layer_id, slot].fill_(10 + self._layer_id)
        self.pool.recurrent_states[self.linear_attn.layer_id, slot].fill_(20 + self._layer_id)
        if self.ple:
            self.pool.conv_slot[slot].fill_(30)
            self.pool.ngram_slot[slot].copy_(Tensor([11994, 984]))
        return value + self._layer_id + 1


def setup():
    pool = Pool(); layers = [Layer(0, True), Layer(1)]
    for layer in layers: layer.pool = pool
    model = SimpleNamespace(layers=SimpleNamespace(op_list=layers))
    req = SimpleNamespace(uid=41, linear_slot_idx=1, cached_len=512, device_len=8192, extend_len=7680)
    return pool, model, layers, SimpleNamespace(reqs=[req]), req


def test_original_once_return_req_and_immediate_copy(tmp_path):
    pool, model, layers, batch, req = setup()
    observer = MODULE.install(model, pool, output_dir=tmp_path)
    value = 0
    for layer in layers: value = layer.forward(value, batch)
    pool.ngram_slot[1].copy_(Tensor([88, 99]))
    observer.post_commit(batch)
    receipt = observer.finalize()
    assert [layer.calls for layer in layers] == [1, 1] and value == 3
    assert req.__dict__ == {'uid':41, 'linear_slot_idx':1, 'cached_len':512, 'device_len':8192, 'extend_len':7680}
    pool.conv_states[0, 1].fill_(99)
    assert FakeTorch.load(tmp_path / receipt['roles']['conv_states']['file']).value == [[10, 10], [11, 11]]
    pool.ngram_slot[1].fill_(77)
    assert FakeTorch.load(tmp_path / receipt['roles']['slot:ple_ngram_ctx']['file']).value == [88, 99]


def test_duplicate_rejects(tmp_path):
    pool, model, layers, batch, _ = setup(); observer = MODULE.install(model, pool, output_dir=tmp_path)
    layers[0].forward(0, batch); layers[0].forward(0, batch); layers[1].forward(0, batch)
    with pytest.raises(ValueError, match='duplicate'): observer.finalize()


def test_missing_rejects(tmp_path):
    pool, model, layers, batch, _ = setup(); observer = MODULE.install(model, pool, output_dir=tmp_path)
    layers[0].forward(0, batch)
    with pytest.raises(ValueError, match='missing'): observer.finalize()


def test_non_target_multi_request_batch_is_ignored(tmp_path):
    pool, model, layers, batch, _ = setup(); observer = MODULE.install(model, pool, output_dir=tmp_path)
    batch.reqs.append(SimpleNamespace(uid=42, linear_slot_idx=2, cached_len=0, device_len=7, extend_len=7))
    batch.reqs[0].device_len = 7
    layers[0].forward(0, batch)
    assert observer.errors == [] and observer.identity is None


def test_decoder_order_does_not_define_saved_pool_order(tmp_path):
    pool, model, layers, batch, _ = setup()
    layers[0]._layer_id, layers[0].linear_attn.layer_id = 9, 1
    layers[1]._layer_id, layers[1].linear_attn.layer_id = 3, 0
    observer = MODULE.install(model, pool, output_dir=tmp_path)
    for layer in layers: layer.forward(0, batch)
    observer.post_commit(batch)
    receipt = observer.finalize()
    assert receipt['linear_layers_by_local'] == [
        {'decoder_layer_idx': 3, 'gdn_layer_id': 0, 'local_index': 0},
        {'decoder_layer_idx': 9, 'gdn_layer_id': 1, 'local_index': 1},
    ]
    assert FakeTorch.load(tmp_path / receipt['roles']['conv_states']['file']).value == [[13, 13], [19, 19]]


def test_late_different_decoder_same_local_invalidates_assembled_receipt(tmp_path):
    pool, model, layers, batch, _ = setup()
    observer = MODULE.install(model, pool, output_dir=tmp_path)
    for layer in layers: layer.forward(0, batch)
    observer.post_commit(batch)
    assert observer.receipt is not None
    extra = Layer(9); extra.pool = pool; extra.linear_attn.layer_id = 0
    observer.capture(extra, batch)
    with pytest.raises(ValueError, match='duplicate'):
        observer.finalize()


def test_missing_post_commit_rejects(tmp_path):
    pool, model, layers, batch, _ = setup(); observer = MODULE.install(model, pool, output_dir=tmp_path)
    for layer in layers: layer.forward(0, batch)
    with pytest.raises(ValueError, match='missing PLE'):
        observer.finalize()


def test_commit_wrapper_calls_original_once_then_snapshots_outgoing_context(tmp_path):
    pool, model, layers, batch, _ = setup(); observer = MODULE.install(model, pool, output_dir=tmp_path)
    for layer in layers: layer.forward(0, batch)
    calls = []
    module = SimpleNamespace()
    def commit(meta, fla):
        calls.append((meta, fla)); pool.ngram_slot[1].copy_(Tensor([7, 8])); return 'same-return'
    module.commit_ngram_context = commit
    original = MODULE.wrap_ngram_commit(module, lambda: batch, observer)
    assert module.commit_ngram_context('meta', 'fla') == 'same-return'
    assert original is commit and calls == [('meta', 'fla')]
    receipt = observer.finalize()
    pool.ngram_slot[1].fill_(9)
    assert FakeTorch.load(tmp_path / receipt['roles']['slot:ple_ngram_ctx']['file']).value == [7, 8]
