import importlib.util
from pathlib import Path
import sys
import types

import pytest
torch = pytest.importorskip("torch")


PATH = Path(__file__).parents[1] / "t17_prefix_numeric_observe.py"
spec = importlib.util.spec_from_file_location("prefix_observe", PATH)
observe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observe)


def install_offsets():
    for name in ("freetoken", "freetoken.kernel", "freetoken.kernel.fla"):
        sys.modules.setdefault(name, types.ModuleType(name))
    package = types.ModuleType("freetoken.kernel.fla.index")
    package.prepare_chunk_offsets = lambda cu, size: torch.tensor([0], dtype=torch.int64)
    chunk = types.ModuleType("freetoken.kernel.fla.chunk"); chunk.CHUNK_SIZE = 64
    sys.modules["freetoken.kernel.fla.index"] = package
    sys.modules["freetoken.kernel.fla.chunk"] = chunk


class Target:
    calls = 0
    def _conv_prefill(self, conv, *_args, **_kwargs):
        self.calls += 1
        self.last_result = conv + 1
        return self.last_result


def make_module():
    install_offsets()
    module = types.ModuleType("toy_gdn"); module.__file__ = __file__
    def kernel(q, k, v, g, beta, *args, **kwargs):
        kernel.calls += 1
        kernel.last_args = args
        kernel.last_kwargs = kwargs
        out = q[0]
        if kwargs["return_h"]:
            kernel.last_result = out, torch.arange(60, dtype=torch.float32).reshape(1, 60, 1, 1, 1)
            return kernel.last_result
        kernel.last_result = out
        return kernel.last_result
    kernel.calls = 0
    module.gdn_prefill_chunk_fla = kernel
    Target.__module__ = "toy_gdn"; module.Target = Target; sys.modules["toy_gdn"] = module
    target = Target()
    layer = types.SimpleNamespace(_is_linear=True, linear_attn=target)
    model = types.SimpleNamespace(layers=types.SimpleNamespace(op_list=[layer]))
    return module, target, model, kernel


def batch(uid, cached, device, *, track=False, track_absolute=None):
    row = device - cached
    tracked_at = 8192 if track_absolute is None else track_absolute
    fla = types.SimpleNamespace(cu_seqlens=torch.tensor([0, row]),
        track_boundary_row=torch.tensor([tracked_at - cached]) if track else None,
        track_h_row=torch.tensor([(tracked_at - cached) // 64]) if track else None)
    req = types.SimpleNamespace(uid=uid, cached_len=cached, device_len=device, extend_len=row)
    return types.SimpleNamespace(reqs=[req], is_prefill=True, fla_metadata=fla)


def invoke(target, module, value, tracked):
    conv = target._conv_prefill(value, None, None, None, None)
    q = torch.stack([value]); k = q + 1; v = q + 2
    g = torch.ones((1, value.shape[0], 1)); beta = g + 1
    result = module.gdn_prefill_chunk_fla(q, k, v, g, beta, return_h=tracked)
    return conv, result


def test_install_calls_each_original_once_and_clips_shared_prefix(tmp_path):
    module, target, model, kernel = make_module()
    current = [batch(7, 512, 4608)]
    observer = observe.install(model, object(), output_dir=tmp_path, get_batch=lambda: current[0])
    first = torch.arange(4096 * 2, dtype=torch.float32).reshape(4096, 2)
    conv, result = invoke(target, module, first, False)
    assert target.calls == 1 and kernel.calls == 1
    assert conv is target.last_result and result is kernel.last_result
    assert torch.equal(conv, first + 1) and torch.equal(result, first.unsqueeze(0)[0])
    assert kernel.last_args == () and kernel.last_kwargs == {"return_h": False}
    current[0] = batch(7, 4608, 8193, track=True)
    second = torch.arange(3585 * 2, dtype=torch.float32).reshape(3585, 2)
    invoke(target, module, second, True)
    receipt = observer.finalize(7)
    assert [(x["absolute_start"], x["absolute_end"]) for x in receipt["segments"]] == [(512, 4608), (4608, 8192)]
    assert receipt["h"]["target_boundary_row"] == 3584
    assert receipt["h"]["actual_track_boundary_row"] == 3584
    assert receipt["h"]["actual_track_absolute_boundary"] == 8192
    assert receipt["h"]["actual_track_h_row"] == 56 and receipt["h"]["computed_h_row"] == 56
    assert observer.has_uid(7)


def test_future_tail_is_excluded_and_missing_h_fails_closed(tmp_path):
    module, target, model, _kernel = make_module()
    current = [batch(9, 4608, 8300, track=True, track_absolute=8256)]
    observer = observe.install(model, object(), output_dir=tmp_path, get_batch=lambda: current[0])
    value = torch.arange(3692, dtype=torch.float32).reshape(3692, 1)
    invoke(target, module, value, True)
    segment = observer.by_uid["9"]["segments"][0]
    saved = torch.load(tmp_path / segment["fields"]["q"]["file"], weights_only=True)
    assert saved.shape[1] == 3584 and saved[0, -1, 0].item() == value[3583, 0].item()
    assert not observer.has_uid(9)
    with pytest.raises(ValueError, match="incomplete"):
        observer.finalize(9)


def test_cold_track_beyond_target_still_captures_target_h_row(tmp_path):
    module, target, model, _kernel = make_module()
    current = [batch(12, 512, 4608)]
    observer = observe.install(model, object(), output_dir=tmp_path, get_batch=lambda: current[0])
    invoke(target, module, torch.zeros((4096, 1)), False)
    current[0] = batch(12, 4608, 8257, track=True, track_absolute=8256)
    invoke(target, module, torch.zeros((3649, 1)), True)
    receipt = observer.finalize(12)
    assert receipt["h"]["target_boundary_row"] == 3584
    assert receipt["h"]["actual_track_boundary_row"] == 3648
    assert receipt["h"]["actual_track_absolute_boundary"] == 8256
    assert receipt["h"]["computed_h_row"] == 56
    assert receipt["h"]["actual_track_h_row"] == 57


def test_missing_tuple_for_target_fails_closed(tmp_path):
    module, target, model, _kernel = make_module()
    current = [batch(11, 4608, 8257, track=True)]
    observer = observe.install(model, object(), output_dir=tmp_path, get_batch=lambda: current[0])
    with pytest.raises(ValueError, match="did not return"):
        invoke(target, module, torch.zeros((3649, 1)), False)


def test_target_h_row_does_not_follow_later_track_row(tmp_path):
    module, target, model, _kernel = make_module()
    current = [batch(13, 4608, 8257, track=True)]
    current[0].fla_metadata.track_h_row = torch.tensor([55])
    observer = observe.install(model, object(), output_dir=tmp_path, get_batch=lambda: current[0])
    invoke(target, module, torch.zeros((3649, 1)), True)
    assert observer.by_uid["13"]["h"]["computed_h_row"] == 56
    assert observer.by_uid["13"]["h"]["actual_track_h_row"] == 55
    saved = torch.load(tmp_path / observer.by_uid["13"]["h"]["file"], weights_only=True)
    assert saved[0, 0, 0, 0, 0].item() == 56


def test_segments_are_isolated_by_actual_uid(tmp_path):
    module, target, model, _kernel = make_module()
    current = [batch(21, 512, 4608)]
    observer = observe.install(model, object(), output_dir=tmp_path, get_batch=lambda: current[0])
    invoke(target, module, torch.zeros((4096, 1)), False)
    current[0] = batch(22, 512, 4608)
    invoke(target, module, torch.ones((4096, 1)), False)
    assert set(observer.by_uid) == {"21", "22"}
    assert observer.by_uid["21"]["segments"][0]["fields"]["conv_in"]["file"] != observer.by_uid["22"]["segments"][0]["fields"]["conv_in"]["file"]
    assert not observer.has_uid(21) and not observer.has_uid(22)
