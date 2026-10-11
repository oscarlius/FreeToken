"""Instance-scoped D16 sampler evidence for a real Engine forward path.

This is a new R040d tool.  It deliberately has no server launcher and only
wraps the supplied Engine instance while a test harness explicitly attaches it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class CaptureError(ValueError):
    """The physical sampler stream cannot prove the declared request stream."""


def _uid(value: object) -> str | int:
    if type(value) not in (str, int):
        raise CaptureError("request UID must be a string or integer")
    return value


def _integer_rows(value: object) -> list[int]:
    """Accept the native sampler's 1-D tensor result without importing torch."""
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, list) or any(type(token) is not int for token in value):
        raise CaptureError("sampler result is not a one-dimensional integer row")
    return value


@dataclass(frozen=True)
class PhysicalRow:
    uid: str | int
    generation_index: int
    row_index: int
    sampled_token_id: int


class SamplerCapture:
    """Bind every actual ``forward_batch`` sampler row to a UID/generation.

    ``device_len`` is read from the scheduler request immediately before the
    engine's native forward.  Each sampler result must have exactly one row per
    actual request in that same forward; a partial batch is invalid evidence.
    """

    def __init__(self) -> None:
        self._prompt_lengths: dict[str | int, int] = {}
        self._history: dict[str | int, list[int]] = {}
        self._current: list[tuple[str | int, int, int]] | None = None
        self._attached = False
        self.captures: list[list[PhysicalRow]] = []

    def bind_query(self, uid: str | int, prompt_length: int) -> None:
        uid = _uid(uid)
        if uid in self._prompt_lengths or type(prompt_length) is not int or prompt_length <= 0:
            raise CaptureError("query binding requires a unique UID and positive prompt length")
        self._prompt_lengths[uid] = prompt_length
        self._history[uid] = []

    def history(self, uid: str | int) -> tuple[int, ...]:
        return tuple(self._history[_uid(uid)])

    def _before_forward(self, batch: object) -> None:
        reqs = getattr(batch, "reqs", None)
        if not isinstance(reqs, (list, tuple)) or not reqs:
            raise CaptureError("physical forward has no request rows")
        rows: list[tuple[str | int, int, int]] = []
        seen: set[str | int] = set()
        for index, req in enumerate(reqs):
            uid = _uid(getattr(req, "uid", None))
            device_len = getattr(req, "device_len", None)
            if uid in seen or uid not in self._prompt_lengths or type(device_len) is not int:
                raise CaptureError("physical forward UID/device length binding differs")
            generation = device_len - self._prompt_lengths[uid]
            if generation < 0 or generation != len(self._history[uid]):
                raise CaptureError("physical sampler history is missing or out of order")
            seen.add(uid)
            rows.append((uid, generation, index))
        self._current = rows

    def _after_sample(self, sampled: object) -> None:
        rows = self._current
        self._current = None
        if rows is None:
            raise CaptureError("sampler ran without an immediately preceding physical forward")
        values = _integer_rows(sampled)
        if len(values) != len(rows):
            raise CaptureError("sampler result rows do not equal physical forward rows")
        capture = [PhysicalRow(uid=uid, generation_index=generation, row_index=index,
                               sampled_token_id=values[index])
                   for uid, generation, index in rows]
        # No history changes until the whole native sampler result is known valid.
        for row in capture:
            self._history[row.uid].append(row.sampled_token_id)
        self.captures.append(capture)

    def attach(self, engine: object) -> "SamplerCapture":
        if self._attached:
            raise CaptureError("capture is already attached")
        sampler = getattr(engine, "sampler", None)
        forward = getattr(engine, "forward_batch", None)
        sample = getattr(sampler, "sample", None)
        if not callable(forward) or not callable(sample):
            raise CaptureError("attach requires an Engine forward_batch and sampler.sample")

        def forward_wrapper(batch: object, *args: object, **kwargs: object):
            self._before_forward(batch)
            try:
                return forward(batch, *args, **kwargs)
            except BaseException:
                self._current = None
                raise

        def sample_wrapper(logits: object, args: object):
            sampled = sample(logits, args)
            self._after_sample(sampled)
            return sampled

        engine.forward_batch = forward_wrapper
        sampler.sample = sample_wrapper
        self._attached = True
        return self

    def finish(self, expected: dict[str | int, int]) -> None:
        """Seal the old capture interface's cardinality contract in memory."""
        if not self._attached or set(expected) != set(self._history):
            raise CaptureError("sampler finish UID set differs")
        if any(type(count) is not int or len(self._history[uid]) != count for uid, count in expected.items()):
            raise CaptureError("sampler finish history count differs")


def install(engine: object) -> SamplerCapture:
    """Compatibility entry point for a source capsule's native sampler role."""
    return SamplerCapture().attach(engine)
