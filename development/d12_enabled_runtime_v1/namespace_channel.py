"""Private, bounded host/PID-1 control pipes for the D12 namespace owner.

This transport grants no launch authority. Its caller must validate the original
outer birth before START, and close the parent copies of both child descriptors
after Popen. A PID-1 watchdog exits on control EOF even while its main thread is
busy, so kernel namespace teardown can remove all descendant process groups.
"""
from __future__ import annotations

import fcntl
import json
import os
import queue
import re
import select
import stat
import threading
import time


SCHEMA = "ft_d12_namespace_pipe/v1"
MAX_FRAME = 4096


class ChannelClosed(RuntimeError):
    pass


class Endpoint:
    def __init__(self, read_fd, write_fd, binding):
        if re.fullmatch(r"[0-9a-f]{64}", binding) is None:
            raise ValueError("namespace pipe needs an external SHA256 binding")
        identities = []
        for fd, mode in ((read_fd, os.O_RDONLY), (write_fd, os.O_WRONLY)):
            if type(fd) is not int or fd <= 2:
                raise ValueError("namespace channel requires dedicated descriptors")
            info = os.fstat(fd)
            if not stat.S_ISFIFO(info.st_mode) or fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_ACCMODE != mode:
                raise ValueError("namespace channel requires separate read/write pipe ends")
            if os.fpathconf(fd, "PC_PIPE_BUF") < MAX_FRAME:
                raise ValueError("namespace pipe atomic-write bound is too small")
            identities.append((info.st_dev, info.st_ino))
            os.set_inheritable(fd, False)
            os.set_blocking(fd, False)
        if identities[0] == identities[1]:
            raise ValueError("namespace command and event pipes must differ")
        self.read_fd, self.write_fd, self.binding = read_fd, write_fd, binding
        self.next_in = self.next_out = 0
        self.buffer = b""

    def send(self, kind, data=None, timeout=5):
        if not isinstance(kind, str) or not kind or (data is not None and not isinstance(data, dict)):
            raise ValueError("invalid namespace frame kind or payload")
        raw = (json.dumps({"schema": SCHEMA, "binding": self.binding, "sequence": self.next_out,
                           "kind": kind, "data": {} if data is None else data},
                          sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
        if len(raw) > MAX_FRAME:
            raise ValueError("namespace frame exceeds pipe bound")
        if not select.select([], [self.write_fd], [], timeout)[1]:
            raise TimeoutError("namespace send timeout")
        # Frames fit PIPE_BUF. A nonblocking pipe write is atomic or fails;
        # never retry a partially published command as a second command.
        if os.write(self.write_fd, raw) != len(raw):
            raise RuntimeError("partial namespace frame publication")
        self.next_out += 1

    def receive(self, timeout):
        deadline = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.read_fd], [], [], remaining)[0]:
                raise TimeoutError("namespace receive timeout")
            raw = os.read(self.read_fd, MAX_FRAME)
            if not raw:
                raise ChannelClosed("namespace control/event pipe reached EOF")
            self.buffer += raw
            if len(self.buffer.split(b"\n", 1)[0]) >= MAX_FRAME:
                raise ValueError("namespace frame exceeds pipe bound")
        raw, self.buffer = self.buffer.split(b"\n", 1)
        row = json.loads(raw)
        if (not isinstance(row, dict) or set(row) != {"schema", "binding", "sequence", "kind", "data"}
                or row["schema"] != SCHEMA or row["binding"] != self.binding
                or type(row["sequence"]) is not int or row["sequence"] != self.next_in
                or not isinstance(row["kind"], str) or not row["kind"] or not isinstance(row["data"], dict)):
            raise ValueError("namespace frame binding/sequence/payload differs")
        self.next_in += 1
        return row

    def close(self):
        for name in ("read_fd", "write_fd"):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)


class HostChannel:
    def __init__(self, binding):
        read_command, write_command = os.pipe2(os.O_CLOEXEC)
        try:
            read_event, write_event = os.pipe2(os.O_CLOEXEC)
        except BaseException:
            os.close(read_command)
            os.close(write_command)
            raise
        try:
            self.endpoint = Endpoint(read_event, write_command, binding)
        except BaseException:
            for fd in (read_command, write_command, read_event, write_event):
                os.close(fd)
            raise
        self.child_fds = (read_command, write_event)

    def child_started(self):
        for fd in self.child_fds:
            os.close(fd)
        self.child_fds = ()

    def close_control(self):
        if self.endpoint.write_fd is not None:
            os.close(self.endpoint.write_fd)
            self.endpoint.write_fd = None

    def close(self):
        self.child_started()
        self.endpoint.close()


class InitChannel:
    def __init__(self, read_fd, write_fd, binding):
        if os.getpid() != 1:
            raise ValueError("namespace watchdog must execute in namespace PID 1")
        self.endpoint = Endpoint(read_fd, write_fd, binding)
        self.commands = queue.Queue(maxsize=4)
        self.finished = threading.Event()
        self.thread = threading.Thread(target=self._watch, name="d12-control-eof", daemon=True)
        self.thread.start()

    def _watch(self):
        try:
            while not self.finished.is_set():
                try:
                    message = self.endpoint.receive(.1)
                except TimeoutError:
                    continue
                self.commands.put_nowait(message)
        except BaseException:
            # This must work while the controller's main thread is in health,
            # HTTP collection, or another blocking operation. No success receipt
            # is emitted. PID-1 exit lets the kernel kill its descendants.
            os._exit(125)

    def receive(self, timeout):
        try:
            return self.commands.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("namespace command timeout") from exc

    def send(self, kind, **data):
        self.endpoint.send(kind, data)

    def close_after_cleanup(self):
        """Call only once all owned services are stopped or none were started."""
        self.finished.set()
        self.thread.join(timeout=1)
        if self.thread.is_alive():
            raise RuntimeError("namespace control watchdog did not stop")
        self.endpoint.close()
