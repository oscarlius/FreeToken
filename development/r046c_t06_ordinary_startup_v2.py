#!/usr/bin/env python3
"""External T06 token observer for ordinary (non-pause) services.

FreeToken replays this module as ``__mp_main__`` in every child.  That entry
only wraps ``Engine.__init__``.  The observer itself is activated in the real
Engine worker and observes Scheduler -> tokenizer DetokenizeMsg objects before
they are sent; it never rewrites a message or emits an ``ft_dev`` ACK.
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import sys
import time
from pathlib import Path


def birth() -> dict:
    fields = (Path("/proc") / str(os.getpid()) / "stat").read_text().rpartition(") ")[2].split()
    ticks = int(fields[19])
    return {"pid": os.getpid(), "start_ticks": ticks, "execution_id": f"{os.getpid()}:{ticks}",
            "pgid": int(fields[2]), "session": int(fields[3])}


class TokenObserver:
    def __init__(self, directory: Path, service_birth: dict):
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.path = directory / "tokens.jsonl"
        self.service_birth, self.worker_birth = service_birth, birth()
        self.counts: dict[int, int] = {}
        self.terminal: set[int] = set()

    def record(self, message) -> None:
        uid = getattr(message, "uid", None)
        token, finished = getattr(message, "next_token", None), getattr(message, "finished", None)
        if type(uid) is not int or uid < 0 or type(token) is not int or type(finished) is not bool:
            raise RuntimeError("T06 observer received malformed DetokenizeMsg")
        if uid in self.terminal:
            raise RuntimeError("T06 observer received token after terminal UID")
        sequence = self.counts.get(uid, 0) + 1
        row = {"schema": "ft_t06_ordinary_token/v2", "uid": uid, "request_seq": sequence,
               "next_token": token, "completion_tokens_delta": 1,
               "completion_tokens_cumulative": sequence, "finished": finished,
               "finish_reason": getattr(message, "finish_reason", None), "time_ns": time.time_ns(),
               "service_birth": self.service_birth, "worker_birth": self.worker_birth}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()
        self.counts[uid] = sequence
        if finished:
            self.terminal.add(uid)

    def flush(self) -> None:
        # Writes are line-flushed; this durable marker proves normal model-worker exit.
        summary = self.path.with_name("shutdown.json")
        if not summary.exists():
            summary.write_text(json.dumps({"schema": "ft_t06_ordinary_shutdown/v2", "worker_birth": self.worker_birth,
                                            "service_birth": self.service_birth, "terminal_uids": sorted(self.terminal)}, sort_keys=True) + "\n",
                               encoding="utf-8")


def install(directory: Path) -> None:
    """Install a lazy Engine hook; tokenizer children do not create observer state."""
    from freetoken.engine.engine import Engine
    from freetoken.scheduler.io import SchedulerIOMixin

    engine_init = Engine.__init__
    enabled = False

    def observed_engine_init(self, *args, **kwargs):
        nonlocal enabled
        if not enabled:
            raw = os.environ.get("R046C_T06_SERVICE_BIRTH")
            if not raw:
                raise RuntimeError("T06 observer lacks service birth binding")
            observer = TokenObserver(directory, json.loads(raw))
            original_reply = SchedulerIOMixin._reply_tokenizer_rank0

            def observed_reply(scheduler, replies):
                for message in replies:
                    if type(message).__name__ == "BatchTokenizerMsg":
                        messages = getattr(message, "data", ())
                    else:
                        messages = (message,)
                    for item in messages:
                        if type(item).__name__ == "DetokenizeMsg":
                            observer.record(item)
                return original_reply(scheduler, replies)

            SchedulerIOMixin._reply_tokenizer_rank0 = observed_reply
            atexit.register(observer.flush)
            enabled = True
        return engine_init(self, *args, **kwargs)

    Engine.__init__ = observed_engine_init


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observer-dir", type=Path, required=True)
    parser.add_argument("ft_args", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    if not options.ft_args or options.ft_args[0] != "--":
        parser.error("pass ft arguments after --")
    os.environ.setdefault("R046C_T06_SERVICE_BIRTH", json.dumps(birth(), sort_keys=True))
    os.environ["R046C_T06_OBSERVER_DIR"] = str(options.observer_dir)
    from freetoken.cli import main as ft_main
    sys.argv = ["ft", *options.ft_args[1:]]
    ft_main()
    return 0


if __name__ == "__mp_main__":
    target = os.environ.get("R046C_T06_OBSERVER_DIR")
    if not target:
        raise RuntimeError("T06 worker lacks observer directory binding")
    install(Path(target))
elif __name__ == "__main__":
    raise SystemExit(main())
