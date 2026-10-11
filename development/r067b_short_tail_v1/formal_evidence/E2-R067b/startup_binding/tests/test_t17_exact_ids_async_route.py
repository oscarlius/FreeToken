"""CPU-only execution of the frozen R067b startup route; no HTTP server or GPU."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
STARTUP = ROOT / "tooling" / "t17_d14_startup.py"


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code, self.detail = status_code, detail


class FakeApp:
    def __init__(self):
        self.routes = {}

    def post(self, path):
        def register(fn):
            self.routes[path] = fn
            return fn
        return register


class FakeBaseModel:
    def __init__(self, **fields):
        for name, value in fields.items():
            setattr(self, name, value)


@dataclass
class FakeSamplingParams:
    max_tokens: int = 1024
    temperature: float = 0.0
    top_p: float = 1.0
    ignore_eos: bool = False


@dataclass
class FakeExactIdsMsg:
    uid: int
    text: str
    sampling_params: FakeSamplingParams
    input_ids_exact: list[int]


class FakeWire:
    @staticmethod
    def encoder(msg):
        return {
            "type": type(msg).__name__, "uid": msg.uid, "text": msg.text,
            "sampling": msg.sampling_params.__dict__.copy(),
            "input_ids_exact": msg.input_ids_exact.copy(),
        }

    @staticmethod
    def decoder(data):
        assert data["type"] == "FakeExactIdsMsg"
        return FakeExactIdsMsg(
            uid=data["uid"], text=data["text"],
            sampling_params=FakeSamplingParams(**data["sampling"]),
            input_ids_exact=data["input_ids_exact"],
        )


@dataclass
class Ack:
    incremental_output: str = ""
    cached_tokens: int = 0
    prompt_tokens_delta: int = 0
    completion_tokens_delta: int = 0
    finished: bool = False
    error: str | None = None
    finish_reason: str | None = None


class AsyncFakeFrontend:
    def __init__(self, uid, acks):
        self.uid, self.acks = uid, acks
        self.sent = []

    async def new_user(self):
        return self.uid

    async def send_one(self, msg):
        # The fake wire is deliberately used here: verify the T17 exact-ID message
        # survives the route's enqueue boundary before ACKs are consumed.
        self.sent.append(FakeWire.decoder(FakeWire.encoder(msg)))

    async def wait_for_ack(self, uid):
        assert uid == self.uid and isinstance(uid, int)
        for ack in self.acks:
            yield ack


def load_route(state):
    """Execute the patched startup artifact with only its external dependencies faked."""
    saved = {name: sys.modules.get(name) for name in (
        "fastapi", "pydantic", "freetoken", "freetoken.core",
        "freetoken.message", "freetoken.message.tokenizer", "freetoken.server",
        "freetoken.server.api_server", "freetoken.cli", "t17_d14_exact_ids",
        "t17_d14_observe",
    )}
    fastapi = types.ModuleType("fastapi")
    fastapi.HTTPException = FakeHTTPException
    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = FakeBaseModel
    pkg = types.ModuleType("freetoken"); pkg.__path__ = []
    core = types.ModuleType("freetoken.core"); core.SamplingParams = FakeSamplingParams
    message = types.ModuleType("freetoken.message"); message.__path__ = []
    tokenizer = types.ModuleType("freetoken.message.tokenizer")
    tokenizer.T17ExactIdsMsg = FakeExactIdsMsg
    server = types.ModuleType("freetoken.server"); server.__path__ = []
    api = types.ModuleType("freetoken.server.api_server")
    api.app = FakeApp(); api.get_global_state = lambda: state
    cli = types.ModuleType("freetoken.cli"); cli.main = lambda: None
    exact_ids = types.ModuleType("t17_d14_exact_ids")
    observed = types.ModuleType("t17_d14_observe"); observed.startup = lambda: None
    sys.modules.update({
        "fastapi": fastapi, "pydantic": pydantic, "freetoken": pkg,
        "freetoken.core": core, "freetoken.message": message,
        "freetoken.message.tokenizer": tokenizer, "freetoken.server": server,
        "freetoken.server.api_server": api, "freetoken.cli": cli,
        "t17_d14_exact_ids": exact_ids, "t17_d14_observe": observed,
    })
    original_env = os.environ.get("FT_DEV_STATE_DUMP")
    os.environ["FT_DEV_STATE_DUMP"] = "cpu-test"
    try:
        spec = importlib.util.spec_from_file_location("r067b_startup_under_test", STARTUP)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, saved, original_env
    except BaseException:
        restore_modules(saved)
        raise


def restore_modules(saved):
    for name, old_module in saved.items():
        if old_module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = old_module


class T17ExactIdsAsyncRouteTest(unittest.TestCase):
    def call_route(self, uid, prompt_length, max_tokens):
        state = AsyncFakeFrontend(uid, [
            Ack("first ", cached_tokens=8191, prompt_tokens_delta=prompt_length,
                completion_tokens_delta=1),
            Ack("full text", cached_tokens=65, completion_tokens_delta=1,
                finished=True, finish_reason="length"),
        ])
        module, saved, prior_env = load_route(state)
        try:
            response = asyncio.run(module._t17_exact_ids(
                module._T17Request(input_ids=list(range(prompt_length)), max_tokens=max_tokens)))
        finally:
            restore_modules(saved)
            if prior_env is None:
                os.environ.pop("FT_DEV_STATE_DUMP", None)
            else:
                os.environ["FT_DEV_STATE_DUMP"] = prior_env
        self.assertEqual(response["uid"], uid)
        self.assertIsInstance(response["uid"], int)
        self.assertEqual(response["text"], "first full text")
        self.assertTrue(response["finished"])
        self.assertEqual(response["finish_reason"], "length")
        self.assertEqual(response["usage"], {
            "prompt_tokens": prompt_length, "completion_tokens": 2, "cached_tokens": 8256,
        })
        self.assertEqual(len(state.sent), 1)
        sent = state.sent[0]
        self.assertIsInstance(sent, FakeExactIdsMsg)
        self.assertEqual(sent.uid, uid)
        self.assertIsInstance(sent.uid, int)
        exact_ids = list(range(prompt_length))
        self.assertEqual(sent.input_ids_exact, exact_ids)
        self.assertEqual(
            response["input_ids_sha256"],
            hashlib.sha256(struct.pack(f"<{prompt_length}i", *exact_ids)).hexdigest(),
        )
        self.assertEqual((sent.sampling_params.max_tokens, sent.sampling_params.temperature,
                          sent.sampling_params.top_p, sent.sampling_params.ignore_eos),
                         (max_tokens, 0, 1, True))

    def test_required_and_seed_cpu_cells_call_the_real_async_route(self):
        for uid, prompt_length, max_tokens in (
            # Formal four-cell matrix: request length is P + T, generation cap is 128.
            (8193, 8192 + 1, 128), (8256, 8192 + 64, 128),
            (8257, 8256 + 1, 128), (8320, 8256 + 64, 128),
            # Seed-only cases are distinct: P + 1 exact IDs with a two-token cap.
            (9001, 8192 + 1, 2), (9002, 8256 + 1, 2),
        ):
            with self.subTest(prompt_length=prompt_length, max_tokens=max_tokens):
                self.call_route(uid, prompt_length, max_tokens)

    def test_invalid_inputs_never_allocate_a_user(self):
        state = AsyncFakeFrontend(41, [])
        module, saved, prior_env = load_route(state)
        try:
            for request in (module._T17Request(input_ids=[], max_tokens=1),
                            module._T17Request(input_ids=[1], max_tokens=0)):
                with self.assertRaises(FakeHTTPException) as raised:
                    asyncio.run(module._t17_exact_ids(request))
                self.assertEqual((raised.exception.status_code, raised.exception.detail),
                                 (400, "nonempty IDs and max_tokens required"))
            self.assertEqual(state.sent, [])
        finally:
            restore_modules(saved)
            if prior_env is None: os.environ.pop("FT_DEV_STATE_DUMP", None)
            else: os.environ["FT_DEV_STATE_DUMP"] = prior_env

    def test_ack_error_is_returned_as_http_400(self):
        state = AsyncFakeFrontend(77, [Ack(error="scheduler rejected", finished=True)])
        module, saved, prior_env = load_route(state)
        try:
            with self.assertRaises(FakeHTTPException) as raised:
                asyncio.run(module._t17_exact_ids(module._T17Request(input_ids=[1, 2], max_tokens=2)))
            self.assertEqual((raised.exception.status_code, raised.exception.detail),
                             (400, "scheduler rejected"))
            self.assertEqual(state.sent[0].uid, 77)
        finally:
            restore_modules(saved)
            if prior_env is None: os.environ.pop("FT_DEV_STATE_DUMP", None)
            else: os.environ["FT_DEV_STATE_DUMP"] = prior_env


if __name__ == "__main__":
    unittest.main(verbosity=2)
