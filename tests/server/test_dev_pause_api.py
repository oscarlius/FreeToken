"""HTTP registration tests for the opt-in D06 development pause endpoint."""

from __future__ import annotations

import importlib
import asyncio
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient


def test_dev_pause_route_is_absent_by_default_and_validates_when_enabled(monkeypatch):
    import freetoken.server.api_server as api_server

    monkeypatch.delenv("FT_DEV_PAUSE_ENDPOINT", raising=False)
    api_server = importlib.reload(api_server)
    assert TestClient(api_server.app).post("/dev/pause", json={"seconds": 1}).status_code == 404

    monkeypatch.setenv("FT_DEV_PAUSE_ENDPOINT", "1")
    api_server = importlib.reload(api_server)
    response = TestClient(api_server.app).post("/dev/pause", json={"seconds": 0})
    assert response.status_code == 422
    assert response.json()["status"] == "rejected"

    monkeypatch.delenv("FT_DEV_PAUSE_ENDPOINT", raising=False)
    importlib.reload(api_server)


def test_dispatch_dev_pause_sends_the_scheduler_control_message():
    from freetoken.message import DevPauseMsg
    from freetoken.server.api_server import dispatch_dev_pause

    sent = []
    state = SimpleNamespace(dev_pause_futures={})

    async def send_one(msg):
        sent.append(msg)
        asyncio.get_running_loop().call_soon(
            state.dev_pause_futures[msg.request_id].set_result,
            {"request_id": msg.request_id, "status": "accepted", "error": None},
        )

    state.send_one = send_one
    result = asyncio.run(dispatch_dev_pause(state, seconds=1.0, timeout=1.0))
    assert result["status"] == "accepted"
    assert len(sent) == 1 and isinstance(sent[0], DevPauseMsg)
    assert sent[0].seconds == 1.0
    assert sent[0].expires_monotonic_s > 0.0


def test_dispatch_timeout_cancels_a_late_pause_request():
    from freetoken.message import DevPauseCancelMsg, DevPauseMsg
    from freetoken.server.api_server import dispatch_dev_pause

    sent = []
    state = SimpleNamespace(dev_pause_futures={})

    async def send_one(msg):
        sent.append(msg)

    state.send_one = send_one
    result = asyncio.run(dispatch_dev_pause(state, seconds=1.0, timeout=0.001))
    assert result["status"] == "timeout"
    assert isinstance(sent[0], DevPauseMsg)
    assert isinstance(sent[1], DevPauseCancelMsg)
    assert sent[0].expires_monotonic_s > 0.0


def test_initial_send_hang_is_bounded_by_the_total_deadline():
    from freetoken.message import DevPauseCancelMsg
    from freetoken.server.api_server import dispatch_dev_pause

    sent = []
    state = SimpleNamespace(dev_pause_futures={})
    never = asyncio.Event()

    async def send_one(msg):
        sent.append(msg)
        if not isinstance(msg, DevPauseCancelMsg):
            await never.wait()

    state.send_one = send_one
    started = time.monotonic()
    result = asyncio.run(dispatch_dev_pause(state, seconds=1.0, timeout=0.02))
    assert result["status"] == "timeout"
    assert time.monotonic() - started < 0.20


def test_cancel_enqueue_hang_is_bounded_and_reported():
    from freetoken.message import DevPauseCancelMsg
    from freetoken.server.api_server import dispatch_dev_pause

    state = SimpleNamespace(dev_pause_futures={})
    never = asyncio.Event()

    async def send_one(msg):
        if isinstance(msg, DevPauseCancelMsg):
            await never.wait()

    state.send_one = send_one
    started = time.monotonic()
    result = asyncio.run(dispatch_dev_pause(state, seconds=1.0, timeout=0.005))
    elapsed = time.monotonic() - started
    assert result["status"] == "timeout"
    assert "cancel enqueue timed out" in result["error"]
    assert 0.20 <= elapsed < 0.60


def test_slow_initial_send_consumes_the_reply_deadline():
    from freetoken.message import DevPauseCancelMsg
    from freetoken.server.api_server import dispatch_dev_pause

    state = SimpleNamespace(dev_pause_futures={})

    async def send_one(msg):
        if not isinstance(msg, DevPauseCancelMsg):
            await asyncio.sleep(0.02)

    state.send_one = send_one
    started = time.monotonic()
    result = asyncio.run(dispatch_dev_pause(state, seconds=1.0, timeout=0.03))
    # A second full timeout after send would take roughly 50ms; only the remaining budget waits.
    assert result["status"] == "timeout"
    assert time.monotonic() - started < 0.045


def test_dispatch_cancellation_while_sending_cleans_up_and_reraises():
    from freetoken.message import DevPauseCancelMsg, DevPauseMsg
    from freetoken.server.api_server import dispatch_dev_pause

    sent = []
    state = SimpleNamespace(dev_pause_futures={})

    async def send_one(msg):
        sent.append(msg)
        if isinstance(msg, DevPauseMsg):
            raise asyncio.CancelledError

    state.send_one = send_one
    try:
        asyncio.run(dispatch_dev_pause(state, seconds=1.0, timeout=1.0))
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancellation was swallowed")
    assert state.dev_pause_futures == {}
    assert isinstance(sent[-1], DevPauseCancelMsg)


def test_dispatch_cancellation_while_waiting_cleans_up_and_reraises():
    from freetoken.message import DevPauseCancelMsg, DevPauseMsg
    from freetoken.server.api_server import dispatch_dev_pause

    sent = []
    state = SimpleNamespace(dev_pause_futures={})

    async def send_one(msg):
        sent.append(msg)

    state.send_one = send_one

    async def run():
        task = asyncio.create_task(dispatch_dev_pause(state, seconds=1.0, timeout=10.0))
        while not sent:
            await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return
        raise AssertionError("cancellation was swallowed")

    asyncio.run(run())
    assert state.dev_pause_futures == {}
    assert isinstance(sent[0], DevPauseMsg)
    assert isinstance(sent[-1], DevPauseCancelMsg)
