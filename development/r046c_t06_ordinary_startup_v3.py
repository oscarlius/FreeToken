#!/usr/bin/env python3
"""T06 v3 worker-side input and token observer; product messages remain unchanged."""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import sys
import time
from pathlib import Path

INPUT_SCHEMA = "ft_t06_ordinary_input/v3"
TOKEN_SCHEMA = "ft_t06_ordinary_token/v3"


def birth() -> dict:
    fields = (Path("/proc") / str(os.getpid()) / "stat").read_text().rpartition(") ")[2].split()
    ticks = int(fields[19])
    return {"pid": os.getpid(), "start_ticks": ticks, "execution_id": f"{os.getpid()}:{ticks}",
            "pgid": int(fields[2]), "session": int(fields[3])}


def canonical_input_ids(value) -> tuple[list[int], bytes, str]:
    """Return full-token count and stable SHA over an ASCII JSON integer array."""
    ids = value.tolist() if hasattr(value, "tolist") else value
    if not isinstance(ids, list) or any(type(token) is not int for token in ids):
        raise RuntimeError("T06 observer received non-canonical UserMsg.input_ids")
    encoded = json.dumps(ids, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return ids, encoded, hashlib.sha256(encoded).hexdigest()


class WorkerObserver:
    def __init__(self, directory: Path, service_birth: dict):
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.directory = directory
        self.inputs = directory / "inputs.jsonl"
        self.tokens = directory / "tokens.jsonl"
        self.service_birth, self.worker_birth = service_birth, birth()
        self.input_uids: set[int] = set()
        self.token_counts: dict[int, int] = {}
        self.terminal: set[int] = set()

    def _append(self, path: Path, row: dict) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            handle.flush()

    def record_input(self, message) -> None:
        uid = getattr(message, "uid", None)
        if type(uid) is not int or uid < 0 or uid in self.input_uids:
            raise RuntimeError("T06 observer received duplicate or malformed UserMsg UID")
        ids, encoded, digest = canonical_input_ids(getattr(message, "input_ids", None))
        ids_path = self.directory / f"input-{uid}.json"
        try:
            with ids_path.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
        except FileExistsError as error:
            raise RuntimeError("T06 observer input receipt path already exists") from error
        self._append(self.inputs, {"schema": INPUT_SCHEMA, "uid": uid, "input_tokens": len(ids),
            "canonical_encoding": "utf8-json-int-array-separators=,:", "input_ids_sha256": digest,
            "input_ids_path": str(ids_path), "input_ids_file_sha256": digest,
            "source": "Scheduler._process_one_msg(UserMsg)", "time_ns": time.time_ns(),
            "service_birth": self.service_birth, "worker_birth": self.worker_birth})
        self.input_uids.add(uid)

    def record_token(self, message) -> None:
        uid, token, finished = getattr(message, "uid", None), getattr(message, "next_token", None), getattr(message, "finished", None)
        if type(uid) is not int or uid not in self.input_uids or type(token) is not int or type(finished) is not bool:
            raise RuntimeError("T06 observer received token without matching worker input")
        if uid in self.terminal:
            raise RuntimeError("T06 observer received token after terminal UID")
        sequence = self.token_counts.get(uid, 0) + 1
        self._append(self.tokens, {"schema": TOKEN_SCHEMA, "uid": uid, "request_seq": sequence,
            "next_token": token, "completion_tokens_delta": 1, "completion_tokens_cumulative": sequence,
            "finished": finished, "finish_reason": getattr(message, "finish_reason", None), "time_ns": time.time_ns(),
            "service_birth": self.service_birth, "worker_birth": self.worker_birth})
        self.token_counts[uid] = sequence
        if finished:
            self.terminal.add(uid)

    def flush(self) -> None:
        path = self.directory / "shutdown.json"
        if not path.exists():
            path.write_text(json.dumps({"schema": "ft_t06_ordinary_shutdown/v3", "service_birth": self.service_birth,
                "worker_birth": self.worker_birth, "terminal_uids": sorted(self.terminal)}, sort_keys=True) + "\n", encoding="utf-8")


def install(directory: Path) -> None:
    """Lazy-install only when the real Engine worker constructs its Engine."""
    from freetoken.engine.engine import Engine
    from freetoken.message.backend import UserMsg
    from freetoken.scheduler.io import SchedulerIOMixin
    from freetoken.scheduler.scheduler import Scheduler

    engine_init, enabled = Engine.__init__, False

    def observed_engine_init(self, *args, **kwargs):
        nonlocal enabled
        if not enabled:
            raw = os.environ.get("R046C_T06_SERVICE_BIRTH")
            if not raw:
                raise RuntimeError("T06 observer lacks service birth binding")
            observer = WorkerObserver(directory, json.loads(raw))
            original_process, original_reply = Scheduler._process_one_msg, SchedulerIOMixin._reply_tokenizer_rank0

            def observed_process(scheduler, msg):
                if isinstance(msg, UserMsg):
                    observer.record_input(msg)
                return original_process(scheduler, msg)

            def observed_reply(scheduler, replies):
                for message in replies:
                    for item in getattr(message, "data", (message,)):
                        if type(item).__name__ == "DetokenizeMsg":
                            observer.record_token(item)
                return original_reply(scheduler, replies)

            Scheduler._process_one_msg = observed_process
            SchedulerIOMixin._reply_tokenizer_rank0 = observed_reply
            atexit.register(observer.flush)
            enabled = True
        return engine_init(self, *args, **kwargs)

    Engine.__init__ = observed_engine_init


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--observer-dir", type=Path, required=True); parser.add_argument("ft_args", nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    if not options.ft_args or options.ft_args[0] != "--":
        parser.error("pass ft arguments after --")
    os.environ.setdefault("R046C_T06_SERVICE_BIRTH", json.dumps(birth(), sort_keys=True))
    os.environ["R046C_T06_OBSERVER_DIR"] = str(options.observer_dir)
    from freetoken.cli import main as ft_main
    sys.argv = ["ft", *options.ft_args[1:]]; ft_main(); return 0


if __name__ == "__mp_main__":
    target = os.environ.get("R046C_T06_OBSERVER_DIR")
    if not target:
        raise RuntimeError("T06 worker lacks observer directory binding")
    install(Path(target))
elif __name__ == "__main__":
    raise SystemExit(main())
