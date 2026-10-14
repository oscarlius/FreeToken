"""Benchmark-only observer of already materialized CPU token replies."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path


def install(io_class, token_message_type, output_dir, prompt_message_type=None):
    """Observe primary-rank replies without GPU reads or synchronization."""
    original = io_class._reply_tokenizer_rank0
    streams = {}
    admissions = {}
    destination = Path(output_dir) / f"native_ids_{os.getpid()}.jsonl"
    destination.parent.mkdir(parents=True, exist_ok=True)

    def reply(self, messages):
        for message in messages:
            if prompt_message_type is not None and isinstance(message, prompt_message_type):
                admissions[message.uid] = {
                    "prompt_tokens": int(message.prompt_tokens),
                    "cached_tokens": int(message.cached_tokens),
                }
            elif isinstance(message, token_message_type):
                tokens = streams.setdefault(message.uid, [])
                tokens.append(int(message.next_token))
                if message.finished:
                    record = {
                        "uid": message.uid,
                        "pid": os.getpid(),
                        "native_token_ids": tokens,
                        "finish_reason": message.finish_reason,
                        "finished_unix_ns": time.time_ns(),
                        "binding": "serial request completion order; HTTP header is not a server UID",
                        **admissions.pop(message.uid, {}),
                    }
                    with destination.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(record, sort_keys=True) + "\n")
                    del streams[message.uid]
        return original(self, messages)

    io_class._reply_tokenizer_rank0 = reply
    return destination
