"""Natural-terminal capture over real D16 components and CPU logits fixtures."""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = os.environ.get("FT_D12_NATIVE_SOURCE")
if not SOURCE:
    pytest.skip("requires Linux candidate and product torch environment", allow_module_level=True)

import torch
from equiv_suite.service_capture import ServiceCaptureError
from freetoken.core import SamplingParams
from freetoken.message import DetokenizeMsg, UserMsg

from natural_capture import NaturalServiceCapture, POLICY_FILE, REPORT_FILE, make_policy, read_natural_delivery
from replay_binding import install_admission_guard, load_replay_binding
from test_replay_binding import BUNDLE, BUNDLE_SHA

IDENTITY = {"pid": 1, "start_ticks": 2, "execution_id": "cpu-natural"}
PROBE = Path(os.environ["FT_D16_D03_TOOL"])
PROBE_SHA = "7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7"


class Engine:
    def __init__(self):
        self.sampler = SimpleNamespace(sample=lambda logits, args: logits.argmax(-1))

    def forward_batch(self, batch):
        for req in batch.reqs:
            req.device_len += 1
        return self.sampler.sample(torch.tensor([[0., 2., 1.]]), SimpleNamespace(temperatures=None))


def setup(tmp_path):
    binding = load_replay_binding(BUNDLE, BUNDLE_SHA)
    # Small explicit upper limits exercise boundaries. The CLI's frozen real
    # payload remains 2048, verified in the separate whole-worker fixture.
    for row in binding["requests"]:
        row["max_tokens"] = row["uid"] + 2
    engine = Engine()
    adapter = NaturalServiceCapture(tmp_path / "capture", binding=binding, max_captures=32,
                                    max_bytes=4000000, process_identity=IDENTITY).attach(engine)
    install_admission_guard(adapter, binding)
    requests = {}
    for row in binding["requests"]:
        message = UserMsg(uid=row["uid"], input_ids=torch.tensor(row["input_ids"], dtype=torch.int32),
                          sampling_params=SamplingParams(max_tokens=row["max_tokens"], temperature=0))
        adapter.admit_user_msg(message)
        requests[row["uid"]] = SimpleNamespace(uid=row["uid"], input_ids=message.input_ids, device_len=len(row["input_ids"]))
    return adapter, engine, requests, binding


def sample(adapter, engine, request, *, finished, deliver=True, wrong_token=False):
    sampled = int(engine.forward_batch(SimpleNamespace(reqs=[request]))[0])
    if deliver:
        adapter.observe_detokenize(DetokenizeMsg(uid=request.uid, next_token=sampled + int(wrong_token), finished=finished))


def complete(tmp_path):
    adapter, engine, requests, binding = setup(tmp_path)
    for uid, request in requests.items():
        for i in range(uid + 1):
            sample(adapter, engine, request, finished=i == uid)
    # The native pipeline may sample once beyond terminal. It is retained as
    # undelivered evidence and never included in an output-equivalence sequence.
    sample(adapter, engine, requests[0], finished=False, deliver=False)
    report = adapter.finalize()
    assert report["terminal"] == "complete" and "expected_deliveries" not in report
    assert not (adapter.destination / "service_delivery.json").exists()
    assert torch.cuda.is_initialized() is False
    return adapter, binding


def read(adapter, binding, **overrides):
    args = {"expected_policy": make_policy(binding, 32, 4000000), "process_identity": IDENTITY,
            "logits_probe": PROBE, "logits_probe_sha256": PROBE_SHA, **overrides}
    return read_natural_delivery(adapter.destination, **args)


def test_natural_terminal_reader_verifies_all_native_samples_without_exact_output_lengths(tmp_path):
    adapter, binding = complete(tmp_path)
    result = read(adapter, binding)
    assert result["capture_complete"] is True and result["output_equivalence_verified"] is False
    assert result["delivered_counts"] == {"0": 1, "1": 2, "2": 3}
    assert result["undelivered_physical_samples"] == 1
    assert hashlib.sha256(PROBE.read_bytes()).hexdigest() == PROBE_SHA


@pytest.mark.parametrize("fault", ["after_terminal", "over_limit", "no_terminal", "wrong_token", "observer"])
def test_natural_terminal_failures_retain_failed_report(tmp_path, fault):
    adapter, engine, requests, _ = setup(tmp_path)
    for uid, request in requests.items():
        sample(adapter, engine, request, finished=not (fault in ("over_limit", "no_terminal") and uid == 0))
    if fault == "after_terminal":
        with pytest.raises(ServiceCaptureError, match="after terminal"):
            sample(adapter, engine, requests[0], finished=True)
    elif fault == "over_limit":
        sample(adapter, engine, requests[0], finished=False)
        with pytest.raises(ServiceCaptureError, match="extra"):
            sample(adapter, engine, requests[0], finished=True)
    elif fault == "wrong_token":
        # A separate unfinished request avoids conflating token mismatch with
        # the already-terminal check exercised above.
        adapter, engine, requests, _ = setup(tmp_path / "wrong")
        with pytest.raises(ServiceCaptureError, match="physical sampler token"):
            sample(adapter, engine, requests[0], finished=True, wrong_token=True)
    elif fault == "observer":
        adapter.record_observer_error("controlled test fault")
    with pytest.raises(ServiceCaptureError):
        adapter.finalize()
    report = json.loads((adapter.destination / REPORT_FILE).read_bytes())
    assert report["terminal"] == "failed" and report["errors"]
    assert not (adapter.destination / "service_delivery.json").exists()
    assert (adapter.destination / "sampler/manifest.json").is_file()


@pytest.mark.parametrize("fault", ["policy", "identity", "report_schema", "fixed_field", "token", "missing_terminal",
                                  "extras", "admission", "snapshot", "missing_uid", "budget", "legacy_file"])
def test_reader_rejects_tampered_or_incomplete_evidence(tmp_path, fault):
    adapter, binding = complete(tmp_path)
    report_path = adapter.destination / REPORT_FILE
    report = json.loads(report_path.read_bytes())
    overrides = {}
    if fault == "policy":
        (adapter.destination / POLICY_FILE).write_text("{}")
    elif fault == "identity":
        overrides["process_identity"] = {**IDENTITY, "start_ticks": 3}
    elif fault == "report_schema": report["schema"] = "ft_equiv_service_capture/v1"
    elif fault == "fixed_field": report["expected_deliveries"] = []
    elif fault == "token": report["deliveries"][0]["next_token"] += 1
    elif fault == "missing_terminal": report["deliveries"][0]["finished"] = False
    elif fault == "extras": report["un_delivered_samples"] = []
    elif fault == "admission":
        path = adapter.destination / report["admission_receipts"][0]["receipt_path"]
        path.write_bytes(path.read_bytes() + b" ")
    elif fault == "snapshot":
        path = next((adapter.destination / "sampler").glob("capture-*/logits_fp32.pt"))
        path.write_bytes(path.read_bytes() + b"corrupted")
    elif fault == "missing_uid": report["admission_receipts"].pop()
    elif fault == "budget":
        overrides["expected_policy"] = make_policy(binding, 1, 100)
    elif fault == "legacy_file": (adapter.destination / "service_delivery.json").write_text("{}")
    report_path.write_text(json.dumps(report))
    with pytest.raises(ServiceCaptureError):
        read(adapter, binding, **overrides)
