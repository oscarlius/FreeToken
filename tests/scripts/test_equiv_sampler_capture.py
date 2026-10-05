import hashlib
import json
import os
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from equiv_suite.sampler_capture import QueryRegistry, SamplerCapture, read_logits_receipt
from equiv_suite.gate import token_sha

TOOL = Path(os.environ.get("FT_D16_D03_TOOL", Path(__file__).resolve().parents[3] / "e2d03" / "scripts" / "logits_probe.py"))


def test_prompt_hash_uses_existing_int32_le_contract():
    registry = QueryRegistry()
    registry.bind_query("a", [1, 2, 3], "event-a")
    assert registry.get("a")["prompt_sha256"] == token_sha([1, 2, 3])
    with pytest.raises(ValueError, match="int32"):
        registry.bind_query("b", [2**31], "event-b")


class Req:
    def __init__(self, uid, ids, device_len=None, dtype=torch.int32):
        self.uid = uid
        self.input_ids = torch.tensor(ids, dtype=dtype)
        self.device_len = len(ids) if device_len is None else device_len


class Batch:
    def __init__(self, reqs): self.reqs = reqs


class Sampler:
    def __init__(self, fail=False, mutate=False): self.calls, self.fail, self.last, self.mutate = 0, fail, None, mutate
    def sample(self, logits, args):
        self.calls += 1
        if self.fail: raise RuntimeError("native sampler failure")
        self.last = logits.argmax(-1)
        if self.mutate: logits.zero_()
        return self.last


class Engine:
    def __init__(self, sampler): self.sampler, self.forward_calls = sampler, 0
    def forward_batch(self, batch, logits):
        self.forward_calls += 1
        # This mirrors complete_one: capture must retain the pre-forward device length.
        for req in batch.reqs: req.device_len += 1
        return self.sampler.sample(logits, None)


def registry():
    result = QueryRegistry()
    result.bind_query("a", [1, 2, 3], "event-a")
    result.bind_query("b", [4, 5, 6], "event-b")
    return result


def observer(tmp_path, *, max_captures=4, max_bytes=100_000):
    return SamplerCapture(tmp_path / "capture", registry=registry(),
                          process_identity={"pid": 101, "start_ticks": 202, "execution_id": "worker-a"},
                          max_captures=max_captures, max_bytes=max_bytes)


def receipt(tmp_path):
    return json.loads((tmp_path / "capture" / "capture-000001" / "receipt.json").read_text())


def test_explicit_attach_freezes_precomplete_rows_and_keeps_native_result(tmp_path):
    engine, sampler = Engine(Sampler()), Sampler()
    # Use the same sampler object, making original-call count observable.
    engine.sampler = sampler
    batch = Batch([Req("a", [1, 2, 3, 7, 999], 4), Req("b", [4, 5, 6, 8, 999], 4)])
    logits = torch.tensor([[.1, .2, .9], [.5, .4, .3]], dtype=torch.float16)
    before = batch.reqs[0].input_ids.clone()
    capture = observer(tmp_path).attach(engine)
    output = engine.forward_batch(batch, logits)
    assert sampler.calls == 1 and output is sampler.last
    assert torch.equal(batch.reqs[0].input_ids, before)  # observer did not mutate input IDs
    data = receipt(tmp_path)
    assert data["admitted"] is False and data["sbatch_coverage"] is True
    assert [row["generation_index"] for row in data["rows"]] == [1, 1]
    assert data["rows"][0]["context_ids"] == [1, 2, 3, 7]  # padded tail was not captured
    assert data["rows"][0]["native_dtype"] == "torch.float16"
    assert capture.errors == []
    saved = torch.load(tmp_path / "capture" / "capture-000001" / "logits_fp32.pt", weights_only=True)
    assert saved.dtype == torch.float32 and saved.shape == (2, 3)


def test_default_is_inert_and_scheduled_single_is_not_sbatch(tmp_path):
    engine = Engine(Sampler())
    batch = Batch([Req("a", [1, 2, 3, 8], 4)])
    engine.forward_batch(batch, torch.ones(1, 3))
    assert not (tmp_path / "capture").exists()
    engine = Engine(Sampler())
    observer(tmp_path).attach(engine)
    engine.forward_batch(Batch([Req("a", [1, 2, 3, 8], 4)]), torch.ones(1, 3))
    assert receipt(tmp_path)["sbatch_coverage"] is False


def test_duplicate_or_bad_prompt_is_indeterminate_without_partial_capture(tmp_path):
    engine = Engine(Sampler()); capture = observer(tmp_path).attach(engine)
    engine.forward_batch(Batch([Req("a", [1, 2, 3]), Req("a", [1, 2, 3, 8])]), torch.ones(2, 3))
    assert not (tmp_path / "capture").exists()
    assert "duplicate UID" in capture.errors[-1]
    engine = Engine(Sampler()); capture = observer(tmp_path).attach(engine)
    engine.forward_batch(Batch([Req("a", [9, 2, 3])]), torch.ones(1, 3))
    assert "does not begin" in capture.errors[-1]


def test_float_ids_and_same_original_prompt_with_different_prefix_are_rejected(tmp_path):
    engine = Engine(Sampler()); capture = observer(tmp_path).attach(engine)
    engine.forward_batch(Batch([Req("a", [1., 2., 3.], dtype=torch.float32)]), torch.ones(1, 3))
    assert "integer CPU" in capture.errors[-1]
    registry_with_same_prompt = QueryRegistry()
    registry_with_same_prompt.bind_query("a", [1, 2, 3], "event-a")
    registry_with_same_prompt.bind_query("b", [1, 2, 3], "event-b")
    capture = SamplerCapture(tmp_path / "same", registry=registry_with_same_prompt,
                             process_identity={"pid": 101, "start_ticks": 202, "execution_id": "worker-a"},
                             max_captures=4, max_bytes=100_000)
    engine = Engine(Sampler()); capture.attach(engine)
    engine.forward_batch(Batch([Req("a", [1, 2, 3, 7]), Req("b", [1, 2, 3, 8])]), torch.ones(2, 3))
    assert "equal original prompts" in capture.errors[-1]


def test_original_sampler_failure_and_budget_do_not_publish(tmp_path):
    engine = Engine(Sampler(fail=True)); capture = observer(tmp_path).attach(engine)
    with pytest.raises(RuntimeError, match="native sampler failure"):
        engine.forward_batch(Batch([Req("a", [1, 2, 3])]), torch.ones(1, 3))
    assert not (tmp_path / "capture").exists() and capture.errors == []
    engine = Engine(Sampler()); capture = observer(tmp_path, max_bytes=1).attach(engine)
    engine.forward_batch(Batch([Req("a", [1, 2, 3])]), torch.ones(1, 3))
    # A rejected first write may leave an empty exclusive root, but it has no
    # terminal manifest and therefore cannot be read as a retained capture.
    assert not (tmp_path / "capture" / "manifest.json").exists() and "budget" in capture.errors[-1]
    engine = Engine(Sampler()); capture = observer(tmp_path / "row-budget", max_captures=1).attach(engine)
    engine.forward_batch(Batch([Req("a", [1, 2, 3])]), torch.ones(1, 3))
    # A new generation index makes this a distinct attempted capture but exceeds the lifetime cap.
    engine.forward_batch(Batch([Req("a", [1, 2, 3, 9])]), torch.ones(1, 3))
    assert "budget" in capture.errors[-1]


def test_multiple_successful_samples_get_distinct_manifest_bound_capture_ids(tmp_path):
    engine = Engine(Sampler()); capture = observer(tmp_path).attach(engine)
    engine.forward_batch(Batch([Req("a", [1, 2, 3])]), torch.ones(1, 3))
    engine.forward_batch(Batch([Req("a", [1, 2, 3, 8])]), torch.ones(1, 3))
    manifest = json.loads((tmp_path / "capture" / "manifest.json").read_text())
    assert [entry["id"] for entry in manifest["captures"]] == ["capture-000001", "capture-000002"]
    assert manifest["serialized_bytes"] == sum(entry["serialized_bytes"] for entry in manifest["captures"])


def test_pre_sample_snapshot_survives_native_inplace_mutation_and_cumulative_byte_failure_is_terminal(tmp_path):
    engine = Engine(Sampler(mutate=True)); capture = observer(tmp_path, max_bytes=1_000_000).attach(engine)
    logits = torch.tensor([[1., 2., 3.]])
    engine.forward_batch(Batch([Req("a", [1, 2, 3])]), logits)
    saved = torch.load(tmp_path / "capture" / "capture-000001" / "logits_fp32.pt", weights_only=True)
    assert saved.tolist() == [[1., 2., 3.]] and logits.tolist() == [[0., 0., 0.]]
    first = json.loads((tmp_path / "capture" / "manifest.json").read_text())["serialized_bytes"]
    engine = Engine(Sampler()); capture = observer(tmp_path / "budget", max_bytes=first + 1).attach(engine)
    engine.forward_batch(Batch([Req("a", [1, 2, 3])]), torch.ones(1, 3))
    engine.forward_batch(Batch([Req("a", [1, 2, 3, 9])]), torch.ones(1, 3))
    with pytest.raises(ValueError, match="incomplete"):
        capture.finalize([{"uid": "a", "generation_index": 0, "event_identity": "event-a"},
                          {"uid": "a", "generation_index": 1, "event_identity": "event-a"}])
    assert json.loads((tmp_path / "budget" / "capture" / "manifest.json").read_text())["terminal"] == "failed"


def test_receipt_reader_rechecks_retained_bytes_and_pinned_metrics_tool(tmp_path):
    engine = Engine(Sampler()); capture = observer(tmp_path).attach(engine)
    engine.forward_batch(Batch([Req("a", [1, 2, 3])]), torch.tensor([[1., 2., 3.]]))
    capture.finalize([{"uid": "a", "generation_index": 0, "event_identity": "event-a"}])
    expected = hashlib.sha256(TOOL.read_bytes()).hexdigest()
    raw = (tmp_path / "capture" / "capture-000001" / "receipt.json").read_bytes()
    result = read_logits_receipt(tmp_path / "capture", capture_id="capture-000001", receipt_sha256=hashlib.sha256(raw).hexdigest(), logits_probe=TOOL, logits_probe_sha256=expected)
    assert result["verdict"] == "recorded" and result["admitted"] is False
    path = tmp_path / "capture" / "capture-000001" / "receipt.json"
    path.write_text(path.read_text().replace("logits_fp32", "tampered_logits"))
    assert read_logits_receipt(tmp_path / "capture", capture_id="capture-000001", receipt_sha256=hashlib.sha256(raw).hexdigest(), logits_probe=TOOL, logits_probe_sha256=expected)["verdict"] == "indeterminate"


def test_reader_rejects_context_or_process_tampering_even_if_manifest_hash_is_rewritten(tmp_path):
    for field in ("context_ids", "process_identity"):
        target = tmp_path / field
        engine = Engine(Sampler()); capture = observer(target).attach(engine)
        engine.forward_batch(Batch([Req("a", [1, 2, 3])]), torch.tensor([[1., 2., 3.]]))
        capture.finalize([{"uid": "a", "generation_index": 0, "event_identity": "event-a"}])
        receipt_path = target / "capture" / "capture-000001" / "receipt.json"
        document = json.loads(receipt_path.read_text())
        if field == "context_ids": document["rows"][0][field] = [8, 9, 10]
        else: del document[field]["pid"]
        raw = (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode(); receipt_path.write_bytes(raw)
        manifest_path = target / "capture" / "manifest.json"; manifest = json.loads(manifest_path.read_text())
        manifest["captures"][0]["receipt_sha256"] = hashlib.sha256(raw).hexdigest()
        manifest["captures"][0]["serialized_bytes"] = len(raw) + (target / "capture" / "capture-000001" / "logits_fp32.pt").stat().st_size
        manifest["serialized_bytes"] = manifest["captures"][0]["serialized_bytes"]
        manifest_path.write_text(json.dumps(manifest))
        tool_sha = hashlib.sha256(TOOL.read_bytes()).hexdigest()
        assert read_logits_receipt(target / "capture", capture_id="capture-000001", receipt_sha256=manifest["captures"][0]["receipt_sha256"], logits_probe=TOOL, logits_probe_sha256=tool_sha)["verdict"] == "indeterminate"


def test_first_byte_budget_failure_can_be_sealed_failed(tmp_path):
    engine = Engine(Sampler()); capture = observer(tmp_path, max_bytes=1).attach(engine)
    engine.forward_batch(Batch([Req("a", [1, 2, 3])]), torch.ones(1, 3))
    with pytest.raises(ValueError):
        capture.finalize([{"uid": "a", "generation_index": 0, "event_identity": "event-a"}])
    manifest = json.loads((tmp_path / "capture" / "manifest.json").read_text())
    assert manifest["terminal"] == "failed" and manifest["captures"] == []


@pytest.mark.parametrize("extra_directory", [False, True])
def test_reader_rejects_unbound_capture_children(tmp_path, extra_directory):
    engine = Engine(Sampler()); capture = observer(tmp_path).attach(engine)
    engine.forward_batch(Batch([Req("a", [1, 2, 3])]), torch.ones(1, 3))
    capture.finalize([{"uid": "a", "generation_index": 0, "event_identity": "event-a"}])
    root = tmp_path / "capture"; child = root / "capture-000001"
    receipt_sha = hashlib.sha256((child / "receipt.json").read_bytes()).hexdigest()
    extra = child / "unbound"
    if extra_directory:
        extra.mkdir()
    else:
        extra.write_bytes(b"unbound")
    result = read_logits_receipt(root, capture_id="capture-000001", receipt_sha256=receipt_sha,
                                 logits_probe=TOOL, logits_probe_sha256=hashlib.sha256(TOOL.read_bytes()).hexdigest())
    assert result["verdict"] == "indeterminate" and "unbound" in result["error"]
