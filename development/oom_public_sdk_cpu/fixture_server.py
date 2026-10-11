#!/usr/bin/env python3
"""CPU-only loopback server using the candidate's real API routes and FrontendManager."""
from __future__ import annotations

import argparse
import asyncio
from types import SimpleNamespace

import uvicorn
from fastapi import FastAPI, HTTPException

from freetoken.message import UserReply
from freetoken.server.anthropic_api import register_anthropic_routes
from freetoken.server.api_server import FrontendManager
from freetoken.server.openai_api import register_openai_routes
from freetoken.server.responses_api import register_responses_routes


class _AsyncQueue:
    def __init__(self) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()

    async def get(self):
        return await self.queue.get()

    async def put(self, item) -> None:
        await self.queue.put(item)


app = FastAPI()
state: FrontendManager | None = None
send: _AsyncQueue | None = None
recv: _AsyncQueue | None = None
backend_task: asyncio.Task | None = None


def _config() -> SimpleNamespace:
    return SimpleNamespace(
        served_model_name="public-sdk-cpu", model_path="/cpu-fixture/no-model",
        mm=SimpleNamespace(text_model_only=True, disabled_encoders=frozenset()),
        tool_call_parser=None, reasoning_parser=None, enable_cache_report=False,
        max_output_tokens=16, served_modalities=frozenset(),
    )


async def _fake_backend() -> None:
    assert send is not None and recv is not None
    while True:
        message = await send.get()
        await recv.put(UserReply(
            uid=message.uid, incremental_output="sdk-ok", finished=True,
            finish_reason="stop", prompt_tokens_delta=3, completion_tokens_delta=2,
            epoch=message.epoch,
        ))


@app.on_event("startup")
async def _startup() -> None:
    global state, send, recv, backend_task
    send, recv = _AsyncQueue(), _AsyncQueue()
    state = FrontendManager(config=_config(), send_tokenizer=send, recv_tokenizer=recv, maintenance_state="restarting")
    state._create_listener_once()
    backend_task = asyncio.create_task(_fake_backend())


@app.on_event("shutdown")
async def _shutdown() -> None:
    if backend_task is not None:
        backend_task.cancel()
        try:
            await backend_task
        except asyncio.CancelledError:
            pass


@app.get("/__fixture/status")
async def _status() -> dict:
    assert state is not None
    return {"maintenance": state.maintenance_state, "restart_waiters": state._restart_waiters,
            "backend_epoch": state.backend_epoch, "initialized": state.initialized}


@app.post("/__fixture/advance")
async def _advance() -> dict:
    assert state is not None
    if state.maintenance_state != "restarting" or state._restart_waiters < 1:
        raise HTTPException(status_code=409, detail="fixture requires a live restarting waiter")
    state.backend_epoch = 1
    state.maintenance_state = "serving"
    assert state._ready_event is not None
    state._ready_event.set()
    return await _status()


register_openai_routes(app, lambda: state, lambda: {})
register_anthropic_routes(app, lambda: state, lambda: {})
register_responses_routes(app, lambda: state, lambda: {})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
