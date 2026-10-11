#!/usr/bin/env python3
"""Spawn-safe R067 cold-service entrypoint; never use for hot release/e2 services."""
from __future__ import annotations

import hashlib
import os
import sys

from r067_cold_hook import ids_sha256, install, install_token_receipts, load_manifest
from r067_wire import R067ExactIdsMsg, R067UserMsg, register_wire_types


def install_wire() -> None:
    """Install in parent and spawn children before FreeToken launches workers."""
    from freetoken.scheduler.scheduler import Scheduler
    from freetoken.scheduler.io import SchedulerIOMixin
    from freetoken.tokenizer.tokenize import TokenizeManager
    manifest = os.environ.get("R067_COLD_SCHEDULE_MANIFEST")
    if not manifest:
        raise ValueError("R067 cold schedule manifest is required")
    schedules = load_manifest(__import__("pathlib").Path(manifest))
    original = TokenizeManager.tokenize
    register_wire_types()

    def tokenize(self, messages):
        ordinary = [message for message in messages if not isinstance(message, R067ExactIdsMsg)]
        output = original(self, ordinary) if ordinary else []
        for message in messages:
            if not isinstance(message, R067ExactIdsMsg):
                continue
            values = message.input_ids_exact
            actual = ids_sha256(values)
            record = schedules.get(message.schedule_id)
            if record is None or record["input_ids_sha256"] != actual:
                raise ValueError("R067 request schedule/input differs from frozen manifest")
            import torch
            output.append(R067UserMsg(uid=message.uid, input_ids=torch.tensor(values, dtype=torch.int32),
                                      sampling_params=message.sampling_params, epoch=message.epoch,
                                      r067_cold={"uid": message.uid, "schedule_id": message.schedule_id,
                                                 "input_ids_sha256": actual}))
        return output

    TokenizeManager.tokenize = tokenize
    install(Scheduler, schedules)
    receipt_dir = os.environ.get("R067_COLD_TOKEN_RECEIPTS")
    if not receipt_dir:
        raise ValueError("R067 cold token receipt directory is required")
    install_token_receipts(SchedulerIOMixin, __import__("pathlib").Path(receipt_dir))


def install_api() -> None:
    from fastapi import HTTPException
    from pydantic import BaseModel
    from freetoken.core import SamplingParams
    from freetoken.server import api_server as api

    @api.app.post("/internal/r067/cold-exact-ids")
    async def cold_exact_ids(request: R067Request):
        if request.max_tokens != 128 or not request.input_ids:
            raise HTTPException(400, "R067 requires nonempty IDs and max_tokens=128")
        state = api.get_global_state()
        uid = state.new_user()
        await state.send_one(R067ExactIdsMsg(uid=uid, input_ids_exact=request.input_ids,
                             schedule_id=request.schedule_id, sampling_params=SamplingParams(
                                 max_tokens=128, temperature=0, top_p=1, ignore_eos=True)))
        text, tokens, cached, prompt, completion = "", [], 0, 0, 0
        async for ack in state.wait_for_ack(uid):
            if ack.error:
                raise HTTPException(400, ack.error)
            text += ack.incremental_output
            tokens.extend(getattr(ack, "token_ids", []))
            cached += ack.cached_tokens; prompt += ack.prompt_tokens_delta; completion += ack.completion_tokens_delta
            if ack.finished:
                break
        receipt = __import__("pathlib").Path(os.environ["R067_COLD_TOKEN_RECEIPTS"]) / f"{uid}.json"
        if not receipt.is_file():
            raise HTTPException(500, "R067 sampled-token receipt missing")
        token_ids = __import__("json").loads(receipt.read_text(encoding="utf-8"))["token_ids"]
        return {"uid": uid, "text": text, "token_ids": token_ids,
                "input_ids_sha256": ids_sha256(request.input_ids),
                "usage": {"cached_tokens": cached, "prompt_tokens": prompt, "completion_tokens": completion}}


class R067Request(__import__("pydantic").BaseModel):
    input_ids: list[int]
    schedule_id: str
    max_tokens: int = 128


def cpu_probe(inbox, queue) -> None:
    from freetoken.tokenizer.tokenize import TokenizeManager
    from freetoken.scheduler.scheduler import Scheduler
    from freetoken.message.tokenizer import BaseTokenizerMsg
    message = BaseTokenizerMsg.decoder(inbox.get(timeout=30))
    output = TokenizeManager.__new__(TokenizeManager).tokenize([message])[0]
    queue.put({"backend_type": type(output).__name__, "scheduler_hook": Scheduler._process_one_msg.__name__, "uid": output.uid, "marker": output.r067_cold,
               "input_ids_sha256": ids_sha256(output.input_ids), "cuda_initialized": __import__("torch").cuda.is_initialized()})


if __name__ in ("__main__", "__mp_main__"):
    install_wire()
if __name__ == "__main__":
    if sys.argv[1:] == ["--cpu-startup-probe"]:
        import json
        import multiprocessing
        from freetoken.core import SamplingParams
        from freetoken.message.tokenizer import BaseTokenizerMsg
        register_wire_types()
        source = R067ExactIdsMsg(uid=41, text="", input_ids_exact=[100, 1], schedule_id="t1",
                                 sampling_params=SamplingParams(max_tokens=128, temperature=0, top_p=1, ignore_eos=True))
        context = multiprocessing.get_context("spawn"); inbox = context.Queue(); queue = context.Queue()
        inbox.put(BaseTokenizerMsg.encoder(source)); child = context.Process(target=cpu_probe, args=(inbox, queue)); child.start()
        proof = queue.get(timeout=60); child.join(60)
        assert child.exitcode == 0 and proof["backend_type"] == "R067UserMsg" and proof["scheduler_hook"] == "rearming_process" and proof["uid"] == 41 and not proof["cuda_initialized"]
        print(json.dumps({"schema": "ft_r067_cold_spawn_wire/v1", "gpu_started": False, "proof": proof}, sort_keys=True))
    else:
        install_api()
        from freetoken.cli import main
        sys.argv = ["ft", *sys.argv[1:]]
        main()
