"""Development-only raw MoE route trace export.

Nothing in this module is constructed until ``FT_DEV_ROUTE_TRACE`` is set and a
real engine forward begins.  The collector deliberately takes its snapshot at
the router boundary, before the offload cache rewrites expert ids to slots.
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time
from pathlib import Path

import numpy as np
import torch


_ENV = "FT_DEV_ROUTE_TRACE"
_QUEUE_SIZE = 8
_collector = None


def route_trace_enabled() -> bool:
    return bool(os.environ.get(_ENV))


def get_route_tracer():
    global _collector
    if not route_trace_enabled():
        return None
    if _collector is None:
        _collector = RouteTraceCollector(Path(os.environ[_ENV]))
    return _collector


class RouteTraceCollector:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._queue = queue.Queue(maxsize=_QUEUE_SIZE)
        self._failed = None
        self._seq = 0
        self._current = None
        self._layer_ids = None
        # Owns captures rejected before the writer accepts them, including a
        # failed event synchronization: dropping such a pinned destination while
        # CUDA is still copying into it is unsafe.
        self._retired = []
        self._closed = False
        self._thread = threading.Thread(target=self._writer, name="ft-route-trace", daemon=True)
        self._thread.start()

    def begin(self, batch) -> None:
        if self._closed:
            raise RuntimeError("route trace collector is closed")
        if self._failed:
            raise RuntimeError("route trace writer failed") from self._failed
        if self._current is not None:
            raise RuntimeError("nested route trace forward")
        reqs = []
        for req in batch.reqs:
            n = req.extend_len if batch.is_prefill else 1
            if n <= 0:
                raise RuntimeError("route trace saw non-positive request token count")
            reqs.append({"rid": int(req.uid), "n_tokens": int(n)})
        self._current = {"seq": self._seq, "phase": batch.phase, "t": sum(x["n_tokens"] for x in reqs), "reqs": reqs, "layers": {}}
        self._seq += 1

    def capture(self, layer_id: int | None, ids: torch.Tensor) -> None:
        if self._closed:
            raise RuntimeError("route trace collector is closed")
        cur = self._current
        if cur is None:
            return
        if layer_id is None:
            raise RuntimeError("route trace requires a MoE layer id")
        if ids.ndim != 2 or ids.shape[1] != 10:
            raise RuntimeError(f"route trace requires [token,10] ids, got {tuple(ids.shape)}")
        t = cur["t"]
        if ids.shape[0] < t:
            raise RuntimeError("route trace ids shorter than real batch token layout")
        if layer_id in cur["layers"]:
            raise RuntimeError(f"route trace duplicated layer {layer_id}")
        # Slice away CUDA-graph padding before starting D2H.  The detached copy is
        # independent of the cache's later in-place expert-id -> slot rewrite.
        # The D2H copy is enqueued before the caller's cache rewrite on the same
        # stream.  Its event fences the writer, so this is both a snapshot of raw
        # ids and an asynchronous transfer; cloning the destination here would
        # race the unfinished non-blocking copy.
        raw = ids[:t].detach()
        data = None
        event = None
        # CPU `.to(cpu)` may alias raw; retain a separate immutable snapshot there.
        try:
            if ids.is_cuda:
                # Keep the destination owned by this forward before scheduling
                # D2H.  If event creation/recording fails, the fallback stream
                # fence below retains it until that copy is no longer in flight.
                data = torch.empty(raw.shape, dtype=torch.int16, device="cpu", pin_memory=True)
                cur["layers"][int(layer_id)] = (data, None)
                data.copy_(raw, non_blocking=True)
                event = torch.cuda.Event()
                event.record()
                cur["layers"][int(layer_id)] = (data, event)
            else:
                data = raw.to(dtype=torch.int16).clone()
                cur["layers"][int(layer_id)] = (data, None)
        except BaseException as exc:
            if data is not None:
                self._retired.append((data, event))
            if ids.is_cuda:
                try:
                    torch.cuda.current_stream().synchronize()
                except BaseException as fence_exc:
                    self._failed = fence_exc
                    raise RuntimeError("async route trace capture cleanup failed") from fence_exc
            self._failed = exc
            raise

    def end(self) -> None:
        if self._closed:
            raise RuntimeError("route trace collector is closed")
        cur, self._current = self._current, None
        if cur is None:
            return
        layers = cur.pop("layers")
        if self._failed:
            self._retire(layers.values())
            raise RuntimeError("route trace writer failed") from self._failed
        if not layers:
            return
        # Models may place MoE blocks at non-contiguous transformer layer ids.  The
        # trace layer axis is therefore ordered by those real ids, and layer_count
        # names the captured MoE layers rather than pretending dense numbering.
        ordered = sorted(layers)
        if self._layer_ids is None:
            self._layer_ids = ordered
        elif self._layer_ids != ordered:
            self._retire(layers.values())
            raise RuntimeError("route trace MoE layer mapping changed across forwards")
        cur["layer_count"] = len(ordered)
        cur["layer_ids"] = ordered
        cur["file"] = f"route-{cur['seq']:08d}.npz"
        try:
            self._queue.put_nowait((cur, [layers[i] for i in ordered]))
        except queue.Full as exc:
            self._retire(layers.values())
            self._failed = exc
            raise RuntimeError("route trace queue is full") from exc

    def abort(self) -> None:
        cur, self._current = self._current, None
        if cur is not None:
            self._retire(cur.get("layers", {}).values())

    def _retire(self, copied) -> None:
        """Synchronize rejected D2H captures before their owner can disappear."""
        copied = list(copied)
        try:
            for _, event in copied:
                if event is not None:
                    event.synchronize()
        except BaseException as exc:
            self._retired.extend(copied)
            self._failed = exc
            raise RuntimeError("async route trace cleanup failed") from exc

    def _writer(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                self._queue.task_done()
                return
            record, copied = item
            try:
                for _, event in copied:
                    if event is not None:
                        event.synchronize()
                arr = np.stack([tensor.numpy().copy() for tensor, _ in copied])
                np.savez_compressed(self.directory / record["file"], expert_ids=arr)
                (self.directory / f"route-{record['seq']:08d}.json").write_text(
                    json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8"
                )
            except BaseException as exc:
                # Do not release a destination if the event cannot establish
                # that its asynchronous D2H has finished.
                self._retired.extend(copied)
                self._failed = exc
            finally:
                self._queue.task_done()

    def flush(self) -> None:
        """Block until all accepted records have reached disk or fail loudly."""
        deadline = time.monotonic() + 5.0
        while self._queue.unfinished_tasks:
            if self._failed:
                raise RuntimeError("route trace writer failed") from self._failed
            if time.monotonic() >= deadline:
                raise RuntimeError("route trace writer flush timed out")
            time.sleep(0.01)
        if self._failed:
            raise RuntimeError("route trace writer failed") from self._failed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        error = None
        try:
            self.abort()
        except BaseException as exc:
            error = exc
        try:
            self.flush()
        except BaseException as exc:
            if error is None:
                error = exc
        try:
            self._queue.put(None, timeout=5.0)
        except queue.Full:
            if error is None:
                error = RuntimeError("route trace writer close timed out")
        self._thread.join(timeout=5.0)
        if self._thread.is_alive() and error is None:
            error = RuntimeError("route trace writer close timed out")
        if error is not None:
            raise error
