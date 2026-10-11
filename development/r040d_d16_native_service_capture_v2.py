"""R040d sealed native sampler/delivery capture; no server launcher."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from r040d_d16_sampler_capture import CaptureError, SamplerCapture, _uid

SCHEMA = "ft_r040d_d16_service_delivery/v1"


class ServiceCaptureError(ValueError):
    pass


def _ids(value: object) -> list[int]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, list) or not value or any(type(item) is not int for item in value):
        raise ServiceCaptureError("UserMsg input_ids must be a non-empty integer sequence")
    return value


def _expected(value: object) -> dict[str | int, int]:
    if not isinstance(value, list) or not value:
        raise ServiceCaptureError("expected delivery list is empty")
    generations: dict[str | int, list[int]] = {}
    for item in value:
        if not isinstance(item, dict) or set(item) != {"uid", "generation_index", "logical_label"}:
            raise ServiceCaptureError("expected delivery row differs")
        uid, generation = _uid(item["uid"]), item["generation_index"]
        if type(generation) is not int or generation < 0:
            raise ServiceCaptureError("expected delivery generation differs")
        generations.setdefault(uid, []).append(generation)
    result: dict[str | int, int] = {}
    for uid, values in generations.items():
        if sorted(values) != list(range(len(values))):
            raise ServiceCaptureError("expected delivery generations are not contiguous")
        result[uid] = len(values)
    return result


class ServiceCaptureAdapter:
    """Native interface replacement: attach, admit, observe, finalize."""

    def __init__(self, destination: Path | str, *, expected_queries: list[dict[str, Any]], **_limits: Any) -> None:
        self.destination = Path(destination)
        self.expected_rows = list(expected_queries)
        self.expected = _expected(expected_queries)
        self.sampler = SamplerCapture()
        self.deliveries: dict[str | int, list[dict[str, Any]]] = {uid: [] for uid in self.expected}
        self.prepared_batches: list[tuple[str | int, ...]] = []
        self.errors: list[str] = []
        self._sealed = False

    def attach(self, engine: object) -> "ServiceCaptureAdapter":
        self.sampler.attach(engine)
        return self

    def admit_user_msg(self, message: object) -> None:
        uid = _uid(getattr(message, "uid", None))
        if uid not in self.expected:
            raise ServiceCaptureError("UserMsg UID has no expected delivery")
        try:
            self.sampler.bind_query(uid, len(_ids(getattr(message, "input_ids", None))) )
        except CaptureError as error:
            raise ServiceCaptureError(str(error)) from error

    def observe_detokenize(self, message: object) -> None:
        uid, token, finished = _uid(getattr(message, "uid", None)), getattr(message, "next_token", None), getattr(message, "finished", None)
        if uid not in self.expected or type(token) is not int or type(finished) is not bool:
            raise ServiceCaptureError("DetokenizeMsg UID/token/finished differs")
        generation = len(self.deliveries[uid])
        physical = self.sampler.history(uid)
        if generation >= self.expected[uid] or generation >= len(physical):
            raise ServiceCaptureError("DetokenizeMsg lacks a physical sampler row")
        if token != physical[generation]:
            raise ServiceCaptureError("DetokenizeMsg does not match physical sampler token")
        self.deliveries[uid].append({"uid": uid, "generation_index": generation,
                                     "next_token": token, "finished": finished, "delivered": True})

    def observe_prepared_batch(self, batch: object) -> None:
        """Read the real Scheduler ``_prepare_batch`` input without changing it."""
        reqs = getattr(batch, "reqs", None)
        if not isinstance(reqs, (list, tuple)) or not reqs:
            raise ServiceCaptureError("prepared Scheduler batch has no requests")
        uids = tuple(_uid(getattr(req, "uid", None)) for req in reqs)
        if len(set(uids)) != len(uids) or any(uid not in self.expected for uid in uids):
            raise ServiceCaptureError("prepared Scheduler batch UID binding differs")
        self.prepared_batches.append(uids)

    def _first_missing(self) -> dict[str, int] | None:
        for row in self.expected_rows:
            uid, generation = row["uid"], row["generation_index"]
            if len(self.deliveries[uid]) <= generation:
                return {"uid": uid, "generation_index": generation}
        return None

    def _report(self, terminal: str, error: str | None) -> dict[str, Any]:
        deliveries = [row for uid in self.expected for row in self.deliveries[uid]]
        result: dict[str, Any] = {"schema": SCHEMA, "terminal": terminal,
                                  "expected_deliveries": self.expected_rows, "deliveries": deliveries,
                                  "expected_count": len(self.expected_rows), "verified_count": len(deliveries),
                                  "first_missing": self._first_missing(), "errors": self.errors}
        if error is not None:
            result["error"] = error
        return result

    def finalize(self) -> dict[str, Any]:
        if self._sealed:
            raise ServiceCaptureError("service capture is already sealed")
        self._sealed = True
        error = None
        try:
            for uid, count in self.expected.items():
                if len(self.sampler.history(uid)) != count:
                    raise ServiceCaptureError("physical sampler history does not equal expected delivery count")
                if len(self.deliveries[uid]) != count:
                    raise ServiceCaptureError("not every expected query has an actual DetokenizeMsg delivery")
                if any(not row["finished"] for row in self.deliveries[uid][-1:]):
                    raise ServiceCaptureError("final delivery is not terminal")
        except (CaptureError, ServiceCaptureError) as exc:
            error = str(exc)
        report = self._report("complete" if error is None else "failed", error)
        self.destination.mkdir(parents=True, exist_ok=True)
        path = self.destination / "service_delivery.json"
        if path.exists() or path.is_symlink():
            raise ServiceCaptureError("service delivery report path already exists")
        path.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
        if error is not None:
            raise ServiceCaptureError(error)
        return report

    def finish(self) -> dict[str, Any]:
        """Compatibility spelling for retained capture owners."""
        return self.finalize()


def install_from_env(engine: object) -> ServiceCaptureAdapter | None:
    destination = os.environ.get("FT_D16_SERVICE_CAPTURE_DIR")
    if not destination:
        return None
    expected_path = Path(os.environ.get("FT_D16_SERVICE_CAPTURE_EXPECTED_JSON", ""))
    if expected_path.is_symlink() or not expected_path.is_file():
        raise ServiceCaptureError("expected capture file is unavailable")
    try:
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ServiceCaptureError("expected capture file is invalid") from exc
    return ServiceCaptureAdapter(destination, expected_queries=expected).attach(engine)
