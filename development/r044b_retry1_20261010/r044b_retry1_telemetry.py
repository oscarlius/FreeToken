"""Retry1 telemetry stop adapter for the retained R044b runner.

The predecessor's ``OwnedTelemetry.stop`` can leave later sidecars running when
one earlier sidecar's terminate/wait/close operation raises.  This mixin keeps
the retained telemetry contract but attempts every task-owned sidecar and
records the aggregate failure so the caller preserves the GPU lock for recovery.
"""
from __future__ import annotations

import json
import subprocess
from typing import Any

RETRY1_RID = 'E2-R044b-retry1-20261010'


def _error(row: dict[str, Any], stage: str, exc: BaseException) -> dict[str, str]:
    return {"name": str(row["name"]), "stage": stage, "error": repr(exc)}


class ReliableTelemetryStopMixin:
    """Drop-in mixin for R044b's task-owned ``OwnedTelemetry`` instance."""

    def _stop_one_sidecar(self, row: dict[str, Any], errors: list[dict[str, str]]) -> None:
        process = row["process"]
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=self._remaining_stop())
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=self._remaining_stop())
            if process.poll() is None:
                errors.append({"name": str(row["name"]), "stage": "post_wait", "error": "process still alive"})
        except BaseException as exc:
            errors.append(_error(row, "terminate_wait", exc))
        finally:
            try:
                row["handle"].close()
            except BaseException as exc:
                errors.append(_error(row, "close_handle", exc))

    def stop(self) -> None:
        if self.stopped:
            return
        errors: list[dict[str, str]] = []
        self.stop_event.set()
        if self.thread is not None:
            try:
                self.thread.join(timeout=self._remaining_stop())
                if self.thread.is_alive():
                    errors.append({"name": "proc_diskstats", "stage": "join", "error": "thread remains after stop"})
            except BaseException as exc:
                errors.append({"name": "proc_diskstats", "stage": "join", "error": repr(exc)})
        # Deliberately do not raise here: every process is a separately owned sidecar.
        for row in self.processes:
            self._stop_one_sidecar(row, errors)
        for name, handle in (("proc_diskstats", self._disk_handle), ("service_bindings", self._bindings_handle)):
            try:
                handle.close()
            except BaseException as exc:
                errors.append({"name": name, "stage": "close_handle", "error": repr(exc)})
        if errors:
            receipt = self.raw / "telemetry_cleanup_errors.json"
            with receipt.open("x", encoding="utf-8") as handle:
                json.dump({"schema": "ft_r044b_retry1_telemetry_cleanup_errors/v1", "rid": getattr(self, "rid", RETRY1_RID), "stopped_at": self._stamp(), "sidecars_stopped": False, "errors": errors}, handle, indent=2)
                handle.write("\n")
            raise RuntimeError("telemetry cleanup incomplete; preserve GPU lock for recovery: " + json.dumps(errors, sort_keys=True))
        for path in [self.diskstats, self.bindings, *[self.raw / row["name"] for row in self.processes]]:
            path.chmod(0o444)
        if not self.manifest.exists():
            self._write_manifest("stopped")
        with self.terminal.open("x", encoding="utf-8") as handle:
            json.dump({"schema": "ft_r044b_owned_telemetry_terminal/v1", "rid": getattr(self, "rid", RETRY1_RID), "stopped_at": self._stamp(), "sidecars_stopped": True, "diskstats_thread_alive": False}, handle, indent=2)
            handle.write("\n")
        self.manifest.chmod(0o444)
        self.terminal.chmod(0o444)
        self.stopped = True


def retry1_telemetry_class(base: type) -> type:
    """Compose the repair with the frozen telemetry class without editing it."""
    return type("R044bRetry1OwnedTelemetry", (ReliableTelemetryStopMixin, base), {})



