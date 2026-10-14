"""Actual spawn/import CPU proof using real message and queue seams; no generation."""
import json
import multiprocessing
import os
from pathlib import Path
from types import SimpleNamespace


def child():
    from freetoken.message import DetokenizeMsg, PromptAdmittedMsg
    from freetoken.scheduler.io import SchedulerIOMixin

    assert SchedulerIOMixin._reply_tokenizer_rank0.__module__ == "native_observer"

    class Queue:
        def put(self, message):
            self.message = message

    state = SimpleNamespace(_send_into_tokenizer=Queue())
    SchedulerIOMixin._reply_tokenizer_rank0(state, [PromptAdmittedMsg(77, 32012, 0)])
    SchedulerIOMixin._reply_tokenizer_rank0(state, [DetokenizeMsg(77, 100, False)])
    SchedulerIOMixin._reply_tokenizer_rank0(state, [DetokenizeMsg(77, 101, True, "length")])


if __name__ == "__main__":
    process = multiprocessing.get_context("spawn").Process(target=child)
    process.start()
    process.join(60)
    if process.is_alive():
        process.terminate()
        process.join(5)
        raise RuntimeError("CPU spawn proof exceeded deadline")
    assert process.exitcode == 0, process.exitcode
    records = list(Path(os.environ["FT_UPSTREAM_NATIVE_IDS"]).glob("native_ids_*.jsonl"))
    assert len(records) == 1, records
    result = json.loads(records[0].read_text())
    assert result["native_token_ids"] == [100, 101]
    assert result["prompt_tokens"] == 32012 and result["cached_tokens"] == 0
    print("SPAWN_OBSERVER_CPU_PASS")
