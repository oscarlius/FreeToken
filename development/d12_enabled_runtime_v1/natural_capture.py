"""D12's bounded natural-terminal policy over the existing D16 capture.

Only delivery completion semantics and artifact names differ. Native admission,
sampler snapshots, physical send observation and shutdown remain D16-owned.
"""
from __future__ import annotations

import json
from pathlib import Path

from equiv_suite.service_capture import ServiceCaptureAdapter, ServiceCaptureError, _raw, _sha, _token_sha, _uid
from equiv_suite.sampler_capture import read_logits_receipt


MODE = "natural-terminal-v1"
POLICY_SCHEMA = "ft_d12_natural_capture_policy/v1"
REPORT_SCHEMA = "ft_d12_natural_service_capture/v1"
POLICY_FILE = "d12_natural_capture_policy.json"
REPORT_FILE = "d12_natural_service_delivery.json"


def make_policy(binding, max_captures, max_bytes):
    if any(type(n) is not int or n <= 0 for n in (max_captures, max_bytes)):
        raise ValueError("D12 natural capture requires positive explicit budgets")
    requests = []
    for row in binding["requests"]:
        if type(row["uid"]) is not int or type(row["max_tokens"]) is not int or not 0 < row["max_tokens"] <= 2048:
            raise ValueError("D12 natural request UID or generation limit is invalid")
        requests.append({"uid": row["uid"], "logical_label": f"G_seed12k/round-{row['uid']:02d}",
            "max_tokens": row["max_tokens"], "temperature": row["temperature"],
            "input_ids_json_sha256": row["input_ids_json_sha256"], "payload_sha256": row["payload_sha256"]})
    if [row["uid"] for row in requests] != [0, 1, 2]:
        raise ValueError("D12 natural capture requires all three frozen requests")
    return {"schema": POLICY_SCHEMA, "mode": MODE, "bundle_sha256": binding["bundle_sha256"],
            "requests": requests, "max_physical_captures": max_captures, "max_serialized_bytes": max_bytes,
            "terminal_source": "native DetokenizeMsg.finished after successful send_result",
            "output_equivalence_verified": False}


class NaturalServiceCapture(ServiceCaptureAdapter):
    def __init__(self, destination, *, binding, max_captures, max_bytes, process_identity=None):
        self.policy = make_policy(binding, max_captures, max_bytes)
        # These immutable internal rows are upper bounds, not exact output
        # expectations. They are never published as D16 expected_deliveries.
        bounds = [{"uid": row["uid"], "generation_index": index, "logical_label": row["logical_label"]}
                  for row in self.policy["requests"] for index in range(row["max_tokens"])]
        super().__init__(destination, expected_queries=bounds, max_captures=max_captures,
                         max_bytes=max_bytes, process_identity=process_identity)
        self._natural_terminal = set()
        self.destination.mkdir(parents=True, exist_ok=True)
        if self.destination.is_symlink() or (self.destination / "service_delivery.json").exists():
            raise ValueError("D12 natural capture cannot share a fixed D16 report destination")
        with (self.destination / POLICY_FILE).open("xb") as output:
            output.write(_raw(self.policy))

    def observe_detokenize(self, message):
        uid = _uid(getattr(message, "uid", None))
        if uid in self._natural_terminal:
            self.record_observer_error("D12 delivery occurred after terminal generation")
            raise ServiceCaptureError("D12 delivery occurred after terminal generation")
        super().observe_detokenize(message)
        if message.finished:
            self._natural_terminal.add(uid)

    def _delivery_extras(self):
        extras = []
        for uid, upper_bound in self._expected_by_uid.items():
            rows = [row for row in self.deliveries if row["uid"] == uid]
            if not 1 <= len(rows) <= len(upper_bound):
                raise ServiceCaptureError("D12 natural delivery is missing or exceeds the frozen limit")
            if (uid not in self._natural_terminal or rows[-1]["finished"] is not True
                    or any(row["generation_index"] != i or row["finished"] is not False
                           for i, row in enumerate(rows[:-1]))):
                raise ServiceCaptureError("D12 natural delivery lacks one final terminal")
            sampled = self.registry.get(uid)["sampled_tokens"]
            if len(sampled) < len(rows):
                raise ServiceCaptureError("D12 physical sampler history is shorter than delivery")
            extras.extend({"uid": uid, "generation_index": index, "sampled_token_id": token,
                           "delivered": False, "reason": "physical sample after delivered terminal generation"}
                          for index, token in enumerate(sampled[len(rows):], start=len(rows)))
        return extras

    def _report(self, terminal, error, extras):
        report = super()._report(terminal, error, extras)
        report.pop("expected_deliveries")
        report.update(schema=REPORT_SCHEMA, policy_sha256=_sha(_raw(self.policy)),
                      scope="bounded natural-terminal capture only; no output equivalence acceptance",
                      output_equivalence_verified=False)
        return report

    def _write_report(self, document):
        # Base finalize dispatches here on both complete and failed paths. No
        # legacy service_delivery.json exists for the fixed-generation reader.
        with (self.destination / REPORT_FILE).open("xb") as output:
            output.write(_raw(document))


def read_natural_delivery(capture, *, expected_policy, process_identity, logits_probe, logits_probe_sha256):
    """Verify a stopped capture against caller-owned policy and worker identity.

The existing D16 reader validates all sampler bytes and histories once. This
adds the natural terminal/admission cross-check, never a model-value verdict.
"""
    root = Path(capture).absolute()
    if root.resolve() != root or root.is_symlink() or not root.is_dir():
        raise ServiceCaptureError("D12 capture must be a physical directory")

    def read(relative):
        path = root / relative
        if path.resolve() != path or path.is_symlink() or not path.is_file():
            raise ServiceCaptureError("D12 capture file is unavailable: " + relative)
        raw = path.read_bytes()
        return raw, json.loads(raw)

    policy_raw, policy = read(POLICY_FILE)
    report_raw, report = read(REPORT_FILE)
    if (policy_raw != _raw(expected_policy) or policy.get("schema") != POLICY_SCHEMA
            or policy.get("mode") != MODE or report.get("schema") != REPORT_SCHEMA
            or report.get("terminal") != "complete" or report.get("admitted") is not False
            or report.get("output_equivalence_verified") is not False or report.get("errors") != []
            or report.get("policy_sha256") != _sha(policy_raw) or "expected_deliveries" in report
            or report.get("process_identity") != process_identity
            or (root / "service_delivery.json").exists()):
        raise ServiceCaptureError("D12 natural capture policy, identity or terminal differs")
    limits = {row["uid"]: row for row in policy["requests"]}
    admissions = report["admission_receipts"]
    if [item["uid"] for item in admissions] != list(limits):
        raise ServiceCaptureError("D12 admissions do not match the frozen UID order")
    admitted = {}
    for seq, item in enumerate(admissions, start=1):
        uid = item["uid"]
        if item["admission_seq"] != seq or item["receipt_path"] != f"admissions/admission-{seq:06d}.json":
            raise ServiceCaptureError("D12 admission sequence/path differs")
        raw, document = read(item["receipt_path"])
        spec = limits[uid]
        if (_sha(raw) != item["receipt_sha256"] or document["uid"] != uid
                or document["physical_event_identity"] != item["physical_event_identity"]
                or document["process_identity"] != process_identity or document["admission_seq"] != seq
                or document["logical_label"] != spec["logical_label"] or item["logical_label"] != spec["logical_label"]
                or _sha(json.dumps(document["input_ids"], separators=(",", ":")).encode()) != spec["input_ids_json_sha256"]
                or _token_sha(document["input_ids"]) != document["input_ids_sha256"]):
            raise ServiceCaptureError("D12 admission does not bind the frozen worker inputs")
        sampling = document["sampling_fields"]
        if (sampling["max_tokens"] != spec["max_tokens"] or sampling["temperature"] != spec["temperature"]
                or sampling["ignore_eos"] is not False or sampling["stop_strs"] != []
                or _sha(_raw(sampling)) != document["sampling_fields_sha256"]):
            raise ServiceCaptureError("D12 admission sampling differs from frozen inputs")
        admitted[uid] = document

    manifest_raw, manifest = read("sampler/manifest.json")
    if not manifest.get("captures"):
        raise ServiceCaptureError("D12 has no retained physical samples")
    entry = manifest["captures"][-1]
    verified = read_logits_receipt(root / "sampler", capture_id=entry["id"], receipt_sha256=entry["receipt_sha256"],
                                   logits_probe=logits_probe, logits_probe_sha256=logits_probe_sha256)
    if verified.get("verdict") != "recorded":
        raise ServiceCaptureError("D12 native sampler verification failed: " + str(verified.get("error")))
    physical = {uid: [] for uid in limits}
    for entry in manifest["captures"]:
        raw, document = read("sampler/" + entry["id"] + "/receipt.json")
        if _sha(raw) != entry["receipt_sha256"] or document["process_identity"] != process_identity:
            raise ServiceCaptureError("D12 sampler receipt changed or has a different worker identity")
        for row in document["rows"]:
            uid = row["uid"]
            if (uid not in admitted or row["generation_index"] != len(physical[uid])
                    or row["original_prompt_ids"] != admitted[uid]["input_ids"]
                    or row["event_identity"] != admitted[uid]["physical_event_identity"]):
                raise ServiceCaptureError("D12 sampler history differs from actual admissions")
            physical[uid].append(row["sampled_token_id"])
    if (sum(map(len, physical.values())) > policy["max_physical_captures"]
            or manifest["serialized_bytes"] > policy["max_serialized_bytes"]):
        raise ServiceCaptureError("D12 physical capture exceeded its frozen budget")
    delivered = {uid: [] for uid in limits}
    for row in report["deliveries"]:
        uid, index = row["uid"], row["generation_index"]
        if uid not in limits or type(index) is not int:
            raise ServiceCaptureError("D12 delivery UID/generation is undeclared")
        history = delivered[uid]
        if (index != len(history) or index >= limits[uid]["max_tokens"] or index >= len(physical[uid])
                or (history and history[-1]["finished"]) or row["delivered"] is not True
                or type(row["finished"]) is not bool or row["next_token"] != physical[uid][index]
                or row["sampled_token_id"] != physical[uid][index]
                or row["physical_event_identity"] != admitted[uid]["physical_event_identity"]
                or row["logical_label"] != limits[uid]["logical_label"]):
            raise ServiceCaptureError("D12 delivery differs from the bounded physical sampler history")
        history.append(row)
    extras = []
    for uid, history in delivered.items():
        if not history or history[-1]["finished"] is not True:
            raise ServiceCaptureError("D12 declared request lacks a delivered terminal")
        extras.extend({"uid": uid, "generation_index": i, "sampled_token_id": token, "delivered": False,
                       "reason": "physical sample after delivered terminal generation"}
                      for i, token in enumerate(physical[uid][len(history):], start=len(history)))
    if report["un_delivered_samples"] != extras or read("sampler/manifest.json")[0] != manifest_raw:
        raise ServiceCaptureError("D12 undelivered physical samples or sealed manifest differ")
    return {"capture_complete": True, "output_equivalence_verified": False,
            "report_sha256": _sha(report_raw), "policy_sha256": _sha(policy_raw),
            "sampler_manifest_sha256": _sha(manifest_raw), "process_identity": process_identity,
            "delivered_counts": {str(uid): len(rows) for uid, rows in delivered.items()},
            "undelivered_physical_samples": len(extras)}
