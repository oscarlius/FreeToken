import importlib.util
import pickle
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

try:
    import torch as REAL_TORCH
except ModuleNotFoundError:
    REAL_TORCH = None


class Tensor:
    def __init__(self, values):
        self.values = [list(row) if isinstance(row, list) else row for row in values]
    @property
    def shape(self):
        return (len(self.values), len(self.values[0])) if self.values and isinstance(self.values[0], list) else (len(self.values),)
    @property
    def dtype(self): return "fake"
    def __getitem__(self, key):
        if isinstance(key, list): return Tensor([self.values[index] for index in key])
        return Scalar(self.values[key])
    def detach(self): return self
    def to(self, *_args, **_kwargs): return self
    def clone(self): return Tensor(self.values)
    def fill_(self, value):
        self.values = [[value for _ in row] if isinstance(row, list) else value for row in self.values]
        return self
    def add(self, amount):
        return Tensor([[item + amount for item in row] if isinstance(row, list) else row + amount for row in self.values])


class Scalar:
    def __init__(self, value): self.value = value
    def item(self): return self.value


class FakeTorch:
    @staticmethod
    def save(value, destination):
        if hasattr(destination, "write"):
            pickle.dump(value.values, destination)
        else:
            with open(destination, "wb") as stream: pickle.dump(value.values, stream)
    @staticmethod
    def load(path, **_kwargs):
        with open(path, "rb") as stream: return Tensor(pickle.load(stream))


@contextmanager
def fake_torch_module():
    previous = sys.modules.get("torch")
    sys.modules["torch"] = FakeTorch
    try:
        yield
    finally:
        if previous is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = previous


def finalize_stub(observer, uid):
    with fake_torch_module():
        return observer.finalize(uid)


PATH = Path(__file__).parents[1] / "t17_projection_observe.py"
SPEC = importlib.util.spec_from_file_location("t17_projection_observe", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Op:
    def __init__(self, add=0): self.add, self.calls = add, 0
    def forward(self, value, *args, **kwargs):
        self.calls += 1
        return value.add(self.add)


class PLE(Op):
    def __init__(self):
        super().__init__(7); self.value_proj, self.short_conv_calls = Op(3), 0
    def _short_conv(self, value, meta, states):
        self.short_conv_calls += 1
        return value.add(4)
    def forward(self, value, batch):
        self.calls += 1
        projected = self.value_proj.forward(value)
        self._short_conv(projected, None, None)
        return value.add(7)


class GDN:
    def __init__(self): self._split_in_proj, self.in_proj = False, Op(5)


class Layer:
    _is_linear = True
    def __init__(self, layer_id, *, with_ple=False):
        self._layer_id = layer_id
        self.ple, self.linear_attn = (PLE() if with_ple else None), GDN()
        if self.ple is not None:
            self.ple.layer_id = layer_id


class Model:
    def __init__(self):
        self.embed_tokens = Op(1)
        self.layers = SimpleNamespace(op_list=[Layer(0), Layer(1, with_ple=True), Layer(2)])
        self._config = SimpleNamespace(qwen4_args=SimpleNamespace(ple_layer_ids=(1,)))


def make_batch(*, cached, device, uid=41, slot=3, extra=False):
    req = SimpleNamespace(uid=uid, linear_slot_idx=slot, cached_len=cached,
                          device_len=device, extend_len=device - cached)
    reqs = [req]
    if extra:
        reqs.append(SimpleNamespace(uid=99, linear_slot_idx=4, cached_len=0, device_len=7, extend_len=7))
    return SimpleNamespace(reqs=reqs), req


def rows(count): return Tensor([[index, index, index] for index in range(count)])


def execute(model, batch):
    hidden = model.embed_tokens.forward(rows(batch.reqs[0].extend_len))
    qkv_out = model.layers.op_list[0].linear_attn.in_proj.forward(hidden)
    model.layers.op_list[1].ple.forward(hidden, batch)
    return hidden, qkv_out


@pytest.mark.parametrize("cached,device,first_row", [(8192, 8257, 1), (4608, 8257, 3585)])
def test_selects_absolute_rows_for_warm_and_cold_internal_chunk(tmp_path, cached, device, first_row):
    model = Model(); batch, req = make_batch(cached=cached, device=device)
    observer = MODULE.install(model, lambda: batch, output_dir=tmp_path, source_ple_layer_ids=(1,))
    hidden, qkv_out = execute(model, batch)
    receipt = finalize_stub(observer, req.uid)
    assert sys.modules.get("torch") is REAL_TORCH
    gdn, ple_owner = model.layers.op_list[0], model.layers.op_list[1]
    assert [model.embed_tokens.calls, ple_owner.ple.calls, ple_owner.ple.value_proj.calls, ple_owner.ple.short_conv_calls, gdn.linear_attn.in_proj.calls] == [1, 1, 1, 1, 1]
    assert qkv_out.shape == hidden.shape and receipt["cached_tokens"] == cached
    assert receipt["positions"] == list(range(8192, 8257))
    assert set(receipt["roles"]) == {"embedding_output", "ple_input", "ple_value_projection_output", "ple_conv_output", "gdn_qkv_input", "gdn_qkv_output"}
    embedding = FakeTorch.load(tmp_path / receipt["roles"]["embedding_output"]["file"])
    assert embedding.shape == (65, 3) and embedding[0].value[0] == first_row
    conv_binding = receipt["roles"]["ple_conv_output"]["module_binding"]
    assert conv_binding["method"] == "_short_conv" and conv_binding["source_sha256"]
    assert receipt["selection"] == {"gdn": {"decoder_index": 0, "decoder_layer_id": 0, "decoder_class": "Layer"},
                                    "ple": {"decoder_index": 1, "decoder_layer_id": 1, "decoder_class": "Layer"},
                                    "ple_layer_id": 1}


def test_return_req_and_state_are_unmodified_and_terminal_is_unique(tmp_path):
    model = Model(); batch, req = make_batch(cached=8192, device=8257); before = dict(req.__dict__)
    observer = MODULE.install(model, lambda: batch, output_dir=tmp_path)
    hidden, qkv = execute(model, batch)
    assert req.__dict__ == before and qkv.shape == hidden.shape
    finalize_stub(observer, 41)
    with pytest.raises(ValueError, match="more than one terminal"): observer.finalize(41)


def test_non_target_donor_and_decode_are_ignored_before_coordinate_validation(tmp_path):
    model = Model(); batch, req = make_batch(cached=0, device=8193)
    observer = MODULE.install(model, lambda: batch, output_dir=tmp_path); execute(model, batch)
    assert observer.identity is None and observer.captures == {} and observer.errors == []
    with pytest.raises(ValueError, match="never observed"): finalize_stub(observer, req.uid)

    model = Model(); decode, req = make_batch(cached=8192, device=8257)
    decode.is_decode = True
    req.extend_len = -1  # Deliberately incoherent: decode must be ignored before coordinate checks.
    observer = MODULE.install(model, lambda: decode, output_dir=tmp_path / "decode")
    execute(model, decode)
    assert observer.identity is None and observer.captures == {} and observer.errors == []
    with pytest.raises(ValueError, match="never observed"): finalize_stub(observer, req.uid)


def test_target_multi_request_and_partial_range_fail_closed(tmp_path):
    model = Model(); batch, _ = make_batch(cached=8192, device=8257, extra=True)
    observer = MODULE.install(model, lambda: batch, output_dir=tmp_path); execute(model, batch)
    with pytest.raises(ValueError, match="singleton"): finalize_stub(observer, 41)
    model = Model(); partial, req = make_batch(cached=8193, device=8257)
    observer = MODULE.install(model, lambda: partial, output_dir=tmp_path); execute(model, partial)
    with pytest.raises(ValueError, match="partially"): finalize_stub(observer, req.uid)


def test_missing_role_rejects_and_capture_is_an_immediate_cpu_copy(tmp_path):
    model = Model(); batch, req = make_batch(cached=8192, device=8257)
    observer = MODULE.install(model, lambda: batch, output_dir=tmp_path)
    value = rows(65); observer.capture("embedding_output", value, batch, model.embed_tokens); value.fill_(-1)
    copied, _ = observer.captures["embedding_output"]
    assert copied[0].value[0] == 0
    with pytest.raises(ValueError, match="missing target projection capture"): finalize_stub(observer, req.uid)


def test_duplicate_capture_is_retained_as_error(tmp_path):
    model = Model(); batch, req = make_batch(cached=8192, device=8257)
    observer = MODULE.install(model, lambda: batch, output_dir=tmp_path); value = rows(65)
    observer.capture("embedding_output", value, batch, model.embed_tokens)
    observer.capture("embedding_output", value, batch, model.embed_tokens)
    with pytest.raises(ValueError, match="duplicate target capture"): finalize_stub(observer, req.uid)


def test_snapshot_create_is_exclusive_against_a_postcheck_writer(tmp_path, monkeypatch):
    model = Model(); batch, req = make_batch(cached=8192, device=8257)
    observer = MODULE.install(model, lambda: batch, output_dir=tmp_path)
    execute(model, batch)
    target = tmp_path / "projection_41_embedding_output.pt"
    original_open = Path.open

    def raced_open(path, mode="r", *args, **kwargs):
        if path == target and mode == "xb":
            with original_open(target, "wb") as writer:
                writer.write(b"other-writer-bytes")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", raced_open)
    with pytest.raises(ValueError, match="refusing to replace projection snapshot"):
        finalize_stub(observer, req.uid)
    assert target.read_bytes() == b"other-writer-bytes"


def test_requires_the_source_backed_second_decoder_ple_owner(tmp_path):
    model = Model()
    model.layers.op_list[1].ple = None
    model.layers.op_list[2].ple = PLE()
    model.layers.op_list[2].ple.layer_id = 2
    batch, _ = make_batch(cached=8192, device=8257)
    with pytest.raises(ValueError, match="decoder index 1"):
        MODULE.install(model, lambda: batch, output_dir=tmp_path)

    model = Model()
    model.layers.op_list[1].ple = None
    with pytest.raises(ValueError, match="exactly one PLE"):
        MODULE.install(model, lambda: batch, output_dir=tmp_path)

    model = Model()
    model._config.qwen4_args.ple_layer_ids = (2,)
    with pytest.raises(ValueError, match="source config PLE layer ids"):
        MODULE.install(model, lambda: batch, output_dir=tmp_path, source_ple_layer_ids=model._config.qwen4_args.ple_layer_ids)


@pytest.mark.skipif(REAL_TORCH is None, reason="PyTorch is unavailable on this host")
def test_real_torch_cpu_serialization_when_available(tmp_path):
    model = Model(); batch, req = make_batch(cached=8192, device=8257)
    observer = MODULE.install(model, lambda: batch, output_dir=tmp_path)
    hidden = model.embed_tokens.forward(REAL_TORCH.arange(65 * 2, dtype=REAL_TORCH.float32).reshape(65, 2))
    model.layers.op_list[0].linear_attn.in_proj.forward(hidden)
    model.layers.op_list[1].ple.forward(hidden, batch)
    receipt = observer.finalize(req.uid)
    loaded = REAL_TORCH.load(tmp_path / receipt["roles"]["embedding_output"]["file"], weights_only=True)
    assert tuple(loaded.shape) == (65, 2) and loaded.device.type == "cpu"


