from __future__ import annotations

import asyncio
from types import SimpleNamespace

import torch

from freetoken.core import Req, SamplingParams
from freetoken.message import DetokenizeMsg, PromptAdmittedMsg, TokenizeMsg, UserMsg, UserReply
from freetoken.scheduler.prefill import PrefillManager
from freetoken.server.accounting import AdmissionClosedError
from freetoken.server import api_server
from freetoken.server.api_server import FrontendManager
from freetoken.tokenizer.server import _prompt_admitted_reply, _sampled_reply
from freetoken.tokenizer.tokenize import TokenizeManager


class _AsyncQueue:
    def __init__(self) -> None:
        self.q: asyncio.Queue = asyncio.Queue()

    async def get(self):
        return await self.q.get()

    async def put(self, item) -> None:
        await self.q.put(item)


class _Tokenizer:
    def encode(self, text, return_tensors=None, add_special_tokens=True):
        assert text == "epoch prompt"
        return torch.tensor([[11, 12]], dtype=torch.long)


def test_tokenizer_scheduler_and_detokenizer_preserve_epoch() -> None:
    tokenized = TokenizeManager(_Tokenizer()).tokenize([
        TokenizeMsg(uid=7, text="epoch prompt", sampling_params=SamplingParams(), epoch=9)
    ])[0]
    assert tokenized.epoch == 9

    # The actual scheduler intake stores the UserMsg epoch on PendingReq; the final Req
    # carries that same value to scheduler DetokenizeMsg construction.
    manager = object.__new__(PrefillManager)
    manager.pending_list = []
    PrefillManager.add_one_req(manager, tokenized)
    pending = manager.pending_list[0]
    assert pending.epoch == 9
    req = Req(
        input_ids=tokenized.input_ids, table_idx=0, cached_len=0, output_len=1,
        uid=tokenized.uid, sampling_params=tokenized.sampling_params, cache_handle=object(), epoch=pending.epoch,
    )
    detokenize = DetokenizeMsg(uid=req.uid, next_token=13, finished=True, epoch=req.epoch)
    assert _sampled_reply(detokenize, "x").epoch == 9
    assert _prompt_admitted_reply(PromptAdmittedMsg(uid=7, prompt_tokens=2, epoch=9)).epoch == 9


def test_default_epoch_is_protocol_compatible() -> None:
    msg = TokenizeMsg(uid=1, text="epoch prompt", sampling_params=SamplingParams())
    assert msg.epoch == 0
    assert UserReply(uid=1, incremental_output="", finished=False).epoch == 0


def test_frontend_drops_stale_epoch_before_current_stream_terminal() -> None:
    async def scenario() -> None:
        recv, send = _AsyncQueue(), _AsyncQueue()
        state = FrontendManager(
            config=SimpleNamespace(served_model_name="test"), send_tokenizer=send,
            recv_tokenizer=recv, maintenance_state="serving",
        )
        state._create_listener_once()
        old_uid = await state.new_user()
        assert state.request_epoch(old_uid) == 0

        # This is the replacement worker generation. UID remains monotonic and must only
        # accept epoch=1 replies even if an old IPC sender emits the same UID.
        state.backend_epoch = 1
        new_uid = await state.new_user()
        assert state.request_epoch(new_uid) == 1
        await recv.put(UserReply(uid=new_uid, incremental_output="stale", finished=True, epoch=0))
        await asyncio.sleep(0)
        assert state.ack_map[new_uid] == []
        await recv.put(UserReply(uid=new_uid, incremental_output="fresh", finished=True, epoch=1))
        stream = state.wait_for_ack(new_uid)
        reply = await anext(stream)
        assert reply.incremental_output == "fresh"
        assert reply.finished is True
        await stream.aclose()
        assert new_uid not in state.ack_map
        assert new_uid not in state.request_epochs

        # OOM terminalization belongs to the original epoch and happens once per dispatched UID.
        state.fail_dispatched_for_oom("out of memory")
        state.fail_dispatched_for_oom("out of memory again")
        await asyncio.sleep(0)
        assert len([reply for reply in state.ack_map[old_uid] if reply.finished]) == 1
        old_stream = state.wait_for_ack(old_uid)
        terminal = await anext(old_stream)
        assert terminal.finished and terminal.error_code == "insufficient_workspace"
        assert terminal.epoch == 0
        await old_stream.aclose()
        assert old_uid not in state.request_epochs
        for task in asyncio.all_tasks():
            if task is not asyncio.current_task() and task.get_coro().__name__ == "listen":
                task.cancel()
    asyncio.run(scenario())


def test_frontend_restart_wait_queue_bounds_timeout_cancel_and_failed_wakeup(monkeypatch) -> None:
    async def scenario() -> None:
        recv, send = _AsyncQueue(), _AsyncQueue()
        state = FrontendManager(
            config=SimpleNamespace(served_model_name="test"), send_tokenizer=send,
            recv_tokenizer=recv, maintenance_state="restarting",
        )
        # This is the same FrontendManager readiness state used by the supervisor callback;
        # no listener/IPC is required to exercise bounded admission itself.
        state._loop = asyncio.get_running_loop()
        state._ready_event = asyncio.Event()
        monkeypatch.setattr(api_server, "RESTART_READY_TIMEOUT_S", 0.01)
        with __import__("pytest").raises(AdmissionClosedError, match="timed out"):
            await state.new_user()
        assert state._restart_waiters == 0

        state._restart_waiters = api_server.RESTART_QUEUE_MAX
        with __import__("pytest").raises(AdmissionClosedError, match="queue is full"):
            await state.new_user()
        state._restart_waiters = 0

        waiter = asyncio.create_task(state.new_user())
        await asyncio.sleep(0)
        assert state._restart_waiters == 1
        waiter.cancel()
        with __import__("pytest").raises(asyncio.CancelledError):
            await waiter
        assert state._restart_waiters == 0

        waiter = asyncio.create_task(state.new_user())
        await asyncio.sleep(0)
        state.maintenance_state = "failed"
        state.wake_failed_restart_waiters()
        with __import__("pytest").raises(AdmissionClosedError, match="failed"):
            await waiter
        assert state._restart_waiters == 0
    asyncio.run(scenario())
