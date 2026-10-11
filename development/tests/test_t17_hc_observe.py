import importlib.util
import pickle
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


PATH = Path(__file__).parents[1] / "t17_hc_observe.py"
SPEC = importlib.util.spec_from_file_location("t17_hc_observe", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Tensor:
    def __init__(self, rows): self.rows = [list(row) for row in rows]
    @property
    def shape(self): return len(self.rows), len(self.rows[0])
    @property
    def dtype(self): return "fake16"
    def stride(self): return len(self.rows[0]), 1
    def __getitem__(self, rows): return Tensor([self.rows[row] for row in rows])
    def detach(self): return self
    def to(self, *_a, **_kw): return self
    def clone(self): return Tensor(self.rows)
    def fill_(self, value): self.rows = [[value for _ in row] for row in self.rows]; return self
    def add(self, value): return Tensor([[item + value for item in row] for row in self.rows])


class FakeTorch:
    @staticmethod
    def save(value, destination):
        pickle.dump(value.rows, destination)


@contextmanager
def fake_torch():
    prior = sys.modules.get("torch")
    sys.modules["torch"] = FakeTorch
    try:
        yield
    finally:
        if prior is None: sys.modules.pop("torch", None)
        else: sys.modules["torch"] = prior


class Op:
    def __init__(self, add): self.add, self.calls, self.last_args, self.last_result = add, 0, None, None
    def forward(self, value, *args, **kwargs):
        self.calls += 1; self.last_args = (value, args, kwargs); self.last_result = value.add(self.add)
        return self.last_result


class HC:
    def __init__(self):
        self.input_mix_weight_down = Op(2); self.input_mix_weight_up = Op(3); self.calls = 0
    def _down(self, norm):
        whole = self.input_mix_weight_down.forward(norm)
        return whole, None
    def mix(self, hidden):
        self.calls += 1
        down, _ = self._down(hidden.add(1))
        up = self.input_mix_weight_up.forward(down.add(4))
        return up.add(5), None


class GDN:
    def __init__(self): self._split_in_proj = False; self.in_proj = Op(7)


class Layer:
    _is_linear = True
    def __init__(self, layer_id, ple=None):
        self._layer_id, self.ple, self.attn_hyper_connection, self.linear_attn = layer_id, ple, HC(), GDN()


class PLE:
    def __init__(self, layer_id): self.layer_id = layer_id


class Model:
    def __init__(self):
        self.embed_tokens = Op(1)
        self.layers = SimpleNamespace(op_list=[Layer(0), Layer(1, PLE(1)), Layer(2)])
        self._config = SimpleNamespace(qwen4_args=SimpleNamespace(ple_layer_ids=(1,)))


def batch(cached=4608, device=8257, *, uid=41, slot=8, decode=False, extra=False):
    request = SimpleNamespace(uid=uid, linear_slot_idx=slot, cached_len=cached,
                              device_len=device, extend_len=device - cached)
    reqs = [request]
    if extra: reqs.append(SimpleNamespace(uid=99, linear_slot_idx=9, cached_len=0, device_len=2, extend_len=2))
    return SimpleNamespace(reqs=reqs, is_decode=decode), request


def rows(count): return Tensor([[row, row + 1] for row in range(count)])


def execute(model, active, *, marker=None):
    value = model.embed_tokens.forward(rows(active.reqs[0].extend_len), marker, flag="x")
    mixed, _ = model.layers.op_list[0].attn_hyper_connection.mix(value)
    output = model.layers.op_list[0].linear_attn.in_proj.forward(mixed, marker, flag="q")
    return value, mixed, output


def finish(observer, uid):
    with fake_torch(): return observer.finalize(uid)


@pytest.mark.parametrize("device,expected_m", [(8193, 3585), (8257, 3649)])
def test_captures_exact_first_64_rows_and_preserves_actual_m(tmp_path, device, expected_m):
    model = Model(); active, request = batch(device=device); token = object()
    request_before = dict(request.__dict__)
    observer = MODULE.install(model, lambda: active, output_dir=tmp_path)
    value, mixed, output = execute(model, active, marker=token)
    receipt = finish(observer, request.uid)
    assert receipt["extend_tokens"] == expected_m and receipt["positions"] == list(range(4608, 4672))
    assert set(receipt["roles"]) == set(MODULE.ROLES)
    assert all(meta["shape"][0] == 64 and meta["extend_tokens"] == expected_m
               for meta in receipt["roles"].values())
    assert model.embed_tokens.last_args[1] == (token,)
    assert model.layers.op_list[0].linear_attn.in_proj.last_args[1] == (token,)
    assert value is model.embed_tokens.last_result and output is model.layers.op_list[0].linear_attn.in_proj.last_result
    assert request.__dict__ == request_before
    hc = model.layers.op_list[0].attn_hyper_connection
    assert (model.embed_tokens.calls, hc.calls, hc.input_mix_weight_down.calls,
            hc.input_mix_weight_up.calls, model.layers.op_list[0].linear_attn.in_proj.calls) == (1, 1, 1, 1, 1)
    assert receipt["selection"]["gdn"]["decoder_index"] == 0
    assert receipt["selection"]["ple"]["decoder_index"] == 1


def test_capture_is_immediate_cpu_copy_and_leaf_metadata_does_not_copy_weight(tmp_path):
    model = Model(); active, request = batch(); observer = MODULE.install(model, lambda: active, output_dir=tmp_path)
    value, _mixed, _output = execute(model, active)
    value.fill_(-1)
    captured, meta = observer.captures["embedding_output"]
    assert captured.rows[0] == [1, 2]
    leaf = observer.captures["hc_down_output"][1]["leaf_operator"]
    assert leaf["weight"] == "unknown" and leaf["quant_method_class"] is None
    finish(observer, request.uid)


def test_decode_first_child_later_hit_and_non_target_are_ignored_before_coordinates(tmp_path):
    for active, request in (
        batch(4608, 8257, decode=True),
        batch(512, 4608),
        batch(8192, 8257),
    ):
        model = Model(); observer = MODULE.install(model, lambda active=active: active, output_dir=tmp_path / str(request.cached_len))
        execute(model, active)
        assert observer.identity is None and observer.errors == [] and observer.captures == {}
        with pytest.raises(ValueError, match="never observed"):
            finish(observer, request.uid)


def test_target_uid_isolation_singleton_and_duplicate_missing_are_fail_closed(tmp_path):
    model = Model(); active, request = batch(); observer = MODULE.install(model, lambda: active, output_dir=tmp_path / "uid")
    execute(model, active)
    with pytest.raises(ValueError, match="terminal UID"):
        finish(observer, 999)

    model = Model(); active, request = batch(extra=True); observer = MODULE.install(model, lambda: active, output_dir=tmp_path)
    execute(model, active)
    with pytest.raises(ValueError, match="singleton"): finish(observer, request.uid)

    model = Model(); active, request = batch(); observer = MODULE.install(model, lambda: active, output_dir=tmp_path / "duplicate")
    execute(model, active); execute(model, active)
    with pytest.raises(ValueError, match="duplicate"): finish(observer, request.uid)

    model = Model(); active, request = batch(); observer = MODULE.install(model, lambda: active, output_dir=tmp_path / "missing")
    observer.capture("embedding_output", rows(3649), active, model.embed_tokens, "forward")
    with pytest.raises(ValueError, match="missing HC observation"): finish(observer, request.uid)


def test_exclusive_snapshot_rejects_racing_writer_without_overwrite(tmp_path, monkeypatch):
    model = Model(); active, request = batch(); observer = MODULE.install(model, lambda: active, output_dir=tmp_path); execute(model, active)
    target = tmp_path / "hc_41_embedding_output.pt"; original_open = Path.open
    def raced_open(path, mode="r", *args, **kwargs):
        if path == target and mode == "xb":
            with original_open(target, "wb") as stream: stream.write(b"signed-zero:\x80")
        return original_open(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", raced_open)
    with pytest.raises(ValueError, match="refusing to replace HC snapshot"):
        finish(observer, request.uid)
    assert target.read_bytes() == b"signed-zero:\x80"


def test_structure_requires_decoder_zero_and_mapped_ple_one(tmp_path):
    model = Model(); model.layers.op_list[1].ple = None; model.layers.op_list[2].ple = PLE(2)
    active, _ = batch()
    with pytest.raises(ValueError, match="PLE decoder 1"):
        MODULE.install(model, lambda: active, output_dir=tmp_path)
    model = Model(); model._config.qwen4_args.ple_layer_ids = (2,)
    with pytest.raises(ValueError, match="mapped PLE"):
        MODULE.install(model, lambda: active, output_dir=tmp_path)
