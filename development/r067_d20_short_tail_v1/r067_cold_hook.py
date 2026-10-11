"""R067-only cold-request schedule rearming hook.

The hook runs only in a D20 cold service's spawned scheduler process.  It
changes no FreeToken source and never handles ordinary ``UserMsg`` objects.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

_ACTIVE_UIDS: set[int] = set()
_TOKENS: dict[int, list[int]] = {}


def ids_sha256(ids: Any) -> str:
    values = ids.tolist() if hasattr(ids, "tolist") else list(ids)
    if not values or any(type(value) is not int for value in values):
        raise ValueError("R067 requires nonempty integer input ids")
    return hashlib.sha256(struct.pack("<%di" % len(values), *values)).hexdigest()


def load_manifest(path: Path, *, parse_schedule=None) -> dict[str, dict[str, Any]]:
    """Load only regular, hash-bound schedules frozen by the R067 FILEdry."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("R067 schedule manifest must be a regular file")
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError("R067 cold manifest must contain exactly four schedules")
    loaded: dict[str, dict[str, Any]] = {}
    if parse_schedule is None:
        from freetoken.scheduler.dev_prefill_schedule import parse as parse_schedule
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "path", "sha256", "input_ids_sha256"}:
            raise ValueError("R067 schedule manifest row differs")
        key, source, expected, input_sha = row["id"], Path(row["path"]), row["sha256"], row["input_ids_sha256"]
        if not isinstance(key, str) or key in loaded or not isinstance(input_sha, str) or len(input_sha) != 64:
            raise ValueError("R067 schedule identity differs")
        if source.is_symlink() or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise ValueError("R067 schedule source differs")
        loaded[key] = {"schedule": parse_schedule(source.read_text(encoding="utf-8")), "input_ids_sha256": input_sha,
                       "path": str(source), "sha256": expected}
    return loaded


def install(scheduler_type: type, schedules: dict[str, dict[str, Any]]) -> None:
    """Install the narrow hook before multiprocessing spawn starts schedulers."""
    original_init = scheduler_type.__init__
    original = scheduler_type._process_one_msg

    def initialized(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original_init(self, *args, **kwargs)
        # The launcher deliberately supplies the first frozen schedule through
        # FT_DEV_PREFILL_SCHEDULE so stock initialization computes its model
        # alignment.  Do not let that one-shot value bypass this hook.
        initial = self.prefill_manager.dev_prefill_schedule
        if initial is not None:
            known = [record["schedule"] for record in schedules.values()]
            if initial not in known:
                raise ValueError("R067 initial environment schedule is not frozen")
            self.prefill_manager.dev_prefill_schedule = None
        return result

    def rearming_process(self: Any, message: Any) -> Any:
        marker = getattr(message, "r067_cold", None)
        if marker is None:
            return original(self, message)
        if not isinstance(marker, dict) or set(marker) != {"uid", "schedule_id", "input_ids_sha256"}:
            raise ValueError("R067 cold marker differs")
        if marker["uid"] != getattr(message, "uid", None):
            raise ValueError("R067 cold UID differs")
        record = schedules.get(marker["schedule_id"])
        if record is None or marker["input_ids_sha256"] != record["input_ids_sha256"]:
            raise ValueError("R067 cold schedule/input binding differs")
        if ids_sha256(message.input_ids) != record["input_ids_sha256"]:
            raise ValueError("R067 cold actual input differs")
        manager = self.prefill_manager
        if (manager.dev_prefill_schedule is not None or manager.pending_list
                or self.decode_manager.runnable or self._last_data is not None):
            raise RuntimeError("R067 schedule rearm requires an idle drained scheduler")
        # This is the only state transition: recreate the parsed immutable schedule
        # for this verified cold request, then leave original admission unchanged.
        manager.dev_prefill_schedule = record["schedule"]
        _ACTIVE_UIDS.add(message.uid)
        _TOKENS[message.uid] = []
        return original(self, message)

    scheduler_type.__init__ = initialized
    scheduler_type._process_one_msg = rearming_process


def install_token_receipts(io_type: type, directory: Path) -> None:
    """Persist actual sampled IDs for only verified cold UIDs, at terminal reply."""
    directory.mkdir(parents=True, exist_ok=True)
    original = io_type._reply_tokenizer_rank0

    def observed_reply(self: Any, messages: Any) -> Any:
        for message in messages:
            uid = getattr(message, "uid", None)
            if uid not in _ACTIVE_UIDS or type(getattr(message, "next_token", None)) is not int:
                continue
            _TOKENS[uid].append(message.next_token)
            if getattr(message, "finished", False):
                target = directory / f"{uid}.json"
                if target.exists():
                    raise RuntimeError("R067 token receipt already exists")
                payload = {"uid": uid, "token_ids": _TOKENS.pop(uid), "finished": True}
                target.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
                _ACTIVE_UIDS.remove(uid)
        return original(self, messages)

    io_type._reply_tokenizer_rank0 = observed_reply
