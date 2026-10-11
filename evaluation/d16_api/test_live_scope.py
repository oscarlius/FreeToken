"""The real-service pytest entrypoint; skipped unless the owned controller sets it."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from live_scope import run_service


@pytest.mark.skipif("D16_API_BASE_URL" not in os.environ, reason="requires owned loopback service")
def test_approved_service_sdk_calls_and_writes_all_artifacts():
    result = run_service(os.environ["D16_API_BASE_URL"], os.environ["D16_API_MODEL"],
                         os.environ["D16_API_SERVICE"], Path(os.environ["D16_API_OUTPUT"]))
    assert result and all(value["finish_reason"] == "length" for value in result.values())
