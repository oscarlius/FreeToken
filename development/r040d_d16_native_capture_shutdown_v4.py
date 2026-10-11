"""R040d sealed delivery reader with arm-local failure diagnostics."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


class NativeCaptureShutdownError(RuntimeError):
    pass


def _failure(arm: Path, delivery: Path, document: dict[str, Any] | None, reason: str) -> NativeCaptureShutdownError:
    expected = document.get("expected_count", len(document.get("expected_deliveries", []))) if document else 0
    verified = document.get("verified_count", len(document.get("deliveries", []))) if document else 0
    missing = document.get("first_missing") if document else None
    first = "none" if not isinstance(missing, dict) else f"uid={missing.get('uid')},generation={missing.get('generation_index')}"
    return NativeCaptureShutdownError(f"D16 harness failure arm={arm} delivery={delivery} reason={reason} expected={expected} verified={verified} first_missing={first}")


def read_sealed_service_delivery(arm: str | os.PathLike[str]) -> dict[str, Any]:
    arm_path = Path(arm)
    delivery = arm_path / "capture" / "service_delivery.json"
    if delivery.is_symlink() or not delivery.is_file():
        raise _failure(arm_path, delivery, None, "service_delivery_not_sealed")
    try:
        document = json.loads(delivery.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _failure(arm_path, delivery, None, "service_delivery_invalid") from exc
    if not isinstance(document, dict) or document.get("terminal") != "complete":
        raise _failure(arm_path, delivery, document if isinstance(document, dict) else None,
                       str(document.get("error", "service_delivery_incomplete")) if isinstance(document, dict) else "service_delivery_invalid")
    return document
