"""Frozen input drift and actual native admission checks; no model execution."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

import replay_binding


BUNDLE_SHA = "282ec437c54b0ba341aac5a0bc31e996ca0d53343d0f48d5b8fa488523ca00e2"
BUNDLE = Path(os.environ.get("FT_D12_TEST_INPUT_BUNDLE", Path(__file__).parent.parent / "d12_enabled_inputs_20261008"))


def test_frozen_requests_preserve_original_tools_and_actual_input_ids():
    binding = replay_binding.load_replay_binding(BUNDLE, BUNDLE_SHA)
    assert [r["uid"] for r in binding["requests"]] == [0, 1, 2]
    assert [len(r["input_ids"]) for r in binding["requests"]] == [12660, 12905, 12987]
    assert all(r["max_tokens"] == 2048 and r["temperature"] == 0 for r in binding["requests"])
    # No historical output length becomes a new service completion criterion.
    assert all("api_completion_tokens" not in r for r in binding["requests"])


@pytest.mark.parametrize("fault", ["manifest", "payload", "ids", "order", "escape"])
def test_bundle_drift_is_rejected_before_admission(tmp_path, fault):
    root = tmp_path / "bundle"
    # Corrupt only a fresh copy. The sealed Linux source is read-only; copyfile
    # intentionally does not carry those file modes into these fault fixtures.
    shutil.copytree(BUNDLE, root, copy_function=shutil.copyfile)
    digest = BUNDLE_SHA
    if fault == "manifest":
        digest = "0" * 64
    elif fault in ("payload", "ids"):
        path = root / ("G_seed12k/round-00.payload.json" if fault == "payload" else "G_seed12k/ordinary_observer/input-0.json")
        path.write_bytes(path.read_bytes() + b" ")
    else:
        path = root / "binding.json"
        value = json.loads(path.read_bytes())
        if fault == "order":
            value["selected_history"].reverse()
        else:
            value["selected_history"][0]["input_ids_path"] = "../outside.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        replay_binding.load_replay_binding(root, digest)


def test_launcher_requires_both_binding_inputs(monkeypatch):
    monkeypatch.delenv("FT_D12_REPLAY_INPUT_DIR", raising=False)
    monkeypatch.delenv("FT_D12_REPLAY_INPUT_SHA256", raising=False)
    assert replay_binding.load_from_env() is None
    with pytest.raises(ValueError):
        replay_binding.load_from_env(required=True)
    monkeypatch.setenv("FT_D12_REPLAY_INPUT_DIR", str(BUNDLE))
    with pytest.raises(ValueError):
        replay_binding.load_from_env()


@pytest.mark.parametrize("fault", [None, "tokens", "uid", "limit", "temperature", "ignore_eos", "stop", "duplicate"])
def test_real_native_admission_and_failure_evidence(tmp_path, monkeypatch, fault):
    source = os.environ.get("FT_D12_NATIVE_SOURCE")
    if not source:
        pytest.skip("requires Linux candidate and product torch environment")
    monkeypatch.syspath_prepend(str(Path(source) / "scripts"))
    monkeypatch.syspath_prepend(str(Path(source) / "python"))
    import torch
    from equiv_suite.service_capture import ServiceCaptureAdapter, ServiceCaptureError
    from freetoken.core import SamplingParams
    from freetoken.message import UserMsg

    binding = replay_binding.load_replay_binding(BUNDLE, BUNDLE_SHA)
    expected = [{"uid": i, "generation_index": 0, "logical_label": f"fixture-{i}"} for i in range(3)]
    adapter = ServiceCaptureAdapter(tmp_path / "capture", expected_queries=expected,
        max_captures=8, max_bytes=1000000, process_identity={"pid": 1, "start_ticks": 2, "execution_id": "cpu-test"})
    original = adapter.admit_user_msg
    restore = replay_binding.install_admission_guard(adapter, binding)
    expected_before = copy.deepcopy(adapter.expected_queries)
    row = binding["requests"][0]
    ids = list(row["input_ids"])
    params = {"max_tokens": 2048, "temperature": 0}
    uid = 0
    if fault == "tokens": ids[-1] += 1
    if fault == "uid": uid = 1
    if fault == "limit": params["max_tokens"] = 140
    if fault == "temperature": params["temperature"] = 0.5
    if fault == "ignore_eos": params["ignore_eos"] = True
    if fault == "stop": params["stop_strs"] = ["premature"]
    msg = UserMsg(uid=uid, input_ids=torch.tensor(ids, dtype=torch.int32), sampling_params=SamplingParams(**params))
    if fault == "duplicate": adapter.admit_user_msg(msg)
    if fault is not None:
        with pytest.raises(ServiceCaptureError): adapter.admit_user_msg(msg)
        assert adapter.errors and "D12 frozen input binding failed" in adapter.errors[-1]
        assert len(adapter._bound) == (1 if fault == "duplicate" else 0)
    else:
        adapter.admit_user_msg(msg)
        for row in binding["requests"][1:]:
            adapter.admit_user_msg(UserMsg(uid=row["uid"], input_ids=torch.tensor(row["input_ids"], dtype=torch.int32),
                                          sampling_params=SamplingParams(max_tokens=2048, temperature=0)))
        assert len(adapter._bound) == 3 and not adapter.errors
        for row in binding["requests"]:
            assert adapter.registry.get(row["uid"])["prompt_ids"] == row["input_ids"]
    assert adapter.expected_queries == expected_before
    restore()
    assert adapter.admit_user_msg == original
    assert torch.cuda.is_initialized() is False
