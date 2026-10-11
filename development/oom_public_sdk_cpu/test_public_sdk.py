from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import anthropic
import openai
import pytest


ROOT = Path(__file__).resolve().parent
SERVER_PYTHON = Path(os.environ.get("FT_SDK_SERVER_PYTHON", "/data2/FreeToken/venv/bin/python"))
CANDIDATE = Path(os.environ.get("FT_SDK_CANDIDATE", "/data2/FreeToken/wt/e2oom-protocol-restart"))
ARTIFACTS = Path(os.environ["FT_SDK_ARTIFACT_DIR"])


def _birth(pid: int) -> dict:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": pid, "start_ticks": int(fields[19])}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _http(method: str, url: str) -> dict:
    request = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.loads(response.read())


class _Server:
    def __init__(self, nodeid: str) -> None:
        self.port, self.base, self.nodeid = _free_port(), "", nodeid
        self.base = f"http://127.0.0.1:{self.port}"
        env = {**os.environ, "CUDA_VISIBLE_DEVICES": "", "PYTHONPATH": str(CANDIDATE / "python")}
        self.proc = subprocess.Popen(
            [str(SERVER_PYTHON), str(ROOT / "fixture_server.py"), "--port", str(self.port)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
        )
        self.birth = _birth(self.proc.pid)
        self._wait_ready()

    def _wait_ready(self) -> None:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"fixture exited before readiness: {self.proc.returncode}")
            try:
                if _http("GET", self.base + "/__fixture/status")["maintenance"] == "restarting":
                    return
            except OSError:
                pass
            time.sleep(0.05)
        raise TimeoutError("fixture did not bind loopback")

    def wait_for_waiter(self, client_thread: threading.Thread, result: dict) -> dict:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if not client_thread.is_alive():
                raise RuntimeError(f"SDK request ended before waiter: {result.get('error')!r}")
            status = _http("GET", self.base + "/__fixture/status")
            if status["restart_waiters"] > 0:
                return status
            time.sleep(0.02)
        raise TimeoutError("SDK request did not reach FrontendManager restart waiter")

    def advance(self) -> dict:
        return _http("POST", self.base + "/__fixture/advance")

    def close(self) -> dict:
        if _birth(self.proc.pid) != self.birth:
            raise RuntimeError("fixture PID birth changed; refusing cleanup")
        self.proc.terminate()
        try:
            stdout, stderr = self.proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            stdout, stderr = self.proc.communicate(timeout=10)
        tag = hashlib.sha256(self.nodeid.encode()).hexdigest()[:12]
        (ARTIFACTS / f"server-{tag}.stdout.log").write_text(stdout)
        (ARTIFACTS / f"server-{tag}.stderr.log").write_text(stderr)
        return {"nodeid": self.nodeid, "birth": self.birth, "returncode": self.proc.returncode,
                "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr.encode()).hexdigest()}


@pytest.fixture
def server(request):
    value = _Server(request.node.nodeid)
    try:
        yield value
    finally:
        evidence = value.close()
        tag = hashlib.sha256(request.node.nodeid.encode()).hexdigest()[:12]
        (ARTIFACTS / f"server-{tag}.json").write_text(json.dumps(evidence, sort_keys=True) + "\n")


def _call(kind: str, stream: bool, base: str):
    if kind.startswith("openai"):
        client = openai.OpenAI(base_url=base + "/v1", api_key="fixture", timeout=20)
        if kind == "openai-chat":
            result = client.chat.completions.create(model="fixture", messages=[{"role": "user", "content": "hi"}], max_tokens=4, stream=stream)
            return "".join((chunk.choices[0].delta.content or "") for chunk in result) if stream else result.choices[0].message.content
        if kind == "openai-completions":
            result = client.completions.create(model="fixture", prompt="hi", max_tokens=4, stream=stream)
            return "".join((chunk.choices[0].text or "") for chunk in result) if stream else result.choices[0].text
        result = client.responses.create(model="fixture", input="hi", max_output_tokens=4, stream=stream)
        return "".join(event.delta for event in result if event.type == "response.output_text.delta") if stream else result.output_text
    client = anthropic.Anthropic(base_url=base, api_key="fixture", timeout=20)
    result = client.messages.create(model="fixture", max_tokens=4, messages=[{"role": "user", "content": "hi"}], stream=stream)
    return "".join(event.delta.text for event in result if event.type == "content_block_delta" and hasattr(event.delta, "text")) if stream else result.content[0].text


CASES = [(kind, stream) for kind in ("openai-chat", "openai-completions", "openai-responses", "anthropic-messages") for stream in (False, True)]


@pytest.mark.parametrize("kind,stream", CASES, ids=[f"{kind}-{'stream' if stream else 'full'}" for kind, stream in CASES])
def test_official_sdk_public_route_restarts_through_real_frontend_waiter(server, kind: str, stream: bool):
    result: dict = {}

    def invoke() -> None:
        try:
            result["text"] = _call(kind, stream, server.base)
        except BaseException as exc:
            result["error"] = repr(exc)

    client_thread = threading.Thread(target=invoke, daemon=True)
    client_thread.start()
    before = server.wait_for_waiter(client_thread, result)
    assert before["maintenance"] == "restarting" and before["restart_waiters"] > 0
    after = server.advance()
    assert after == {"maintenance": "serving", "restart_waiters": before["restart_waiters"], "backend_epoch": 1, "initialized": True}
    client_thread.join(timeout=20)
    assert not client_thread.is_alive()
    assert "error" not in result, result.get("error")
    assert result["text"] == "sdk-ok"
    terminal = _http("GET", server.base + "/__fixture/status")
    assert terminal["backend_epoch"] == 1 and terminal["restart_waiters"] == 0
