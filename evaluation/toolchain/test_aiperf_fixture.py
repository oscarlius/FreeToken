"""AIPerf CLI smoke against the owned loopback streaming fixture only."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from http.server import ThreadingHTTPServer

from test_openai_fixture import _Handler


TOOLCHAIN = Path(__file__).resolve().parent
AIPERF = TOOLCHAIN / "venv-aiperf" / "bin" / "aiperf"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stop_owned_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def _metric_sections(value: object) -> list[dict[str, object]]:
    if isinstance(value, dict):
        sections = [value] if {"time_to_first_token", "time_to_first_output_token"}.issubset(value) else []
        for item in value.values():
            sections.extend(_metric_sections(item))
        return sections
    if isinstance(value, list):
        return [section for item in value for section in _metric_sections(item)]
    return []


def test_aiperf_streaming_cli_smoke() -> None:
    _Handler.request_count = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    process: subprocess.Popen[str] | None = None
    try:
        run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:12]}"
        run_dir = TOOLCHAIN / "smoke-runs" / run_id
        artifacts = run_dir / "artifacts"
        run_dir.mkdir(parents=True, exist_ok=False)
        command = [
            str(AIPERF), "profile", "--model", "mock-model", "--url", f"http://127.0.0.1:{server.server_port}",
            "--streaming", "--tokenizer", "builtin", "--no-server-metrics", "--no-gpu-telemetry",
            "--request-count", "2", "--concurrency", "1", "--request-timeout-seconds", "5",
            "--ui", "none", "--isl", "8", "--osl", "4",
            "--output-artifact-dir", str(artifacts),
        ]
        env = os.environ.copy()
        for name in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
            env.pop(name, None)
        env.update({"CUDA_VISIBLE_DEVICES": "", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "NO_PROXY": "127.0.0.1,localhost"})
        process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=45)
        except subprocess.TimeoutExpired:
            _stop_owned_process_group(process)
            stdout, stderr = process.communicate()
            (run_dir / "stdout.log").write_text(stdout, encoding="utf-8")
            (run_dir / "stderr.log").write_text(stderr, encoding="utf-8")
            raise AssertionError(f"AIPerf smoke exceeded 45 seconds; evidence retained in {run_dir}")
        (run_dir / "stdout.log").write_text(stdout, encoding="utf-8")
        (run_dir / "stderr.log").write_text(stderr, encoding="utf-8")
        assert process.returncode == 0, f"AIPerf failed ({process.returncode}); evidence retained in {run_dir}"
        json_files = sorted(artifacts.rglob("*.json"))
        parsed = [(path, json.loads(path.read_text(encoding="utf-8"))) for path in json_files]
        metric_sections = [section for _, data in parsed for section in _metric_sections(data)]
        assert _Handler.request_count == 2
        assert len(metric_sections) == 1
        metrics = metric_sections[0]
        assert metrics["request_count"]["avg"] == 2.0
        assert metrics["error_summary"] == []
        assert metrics["time_to_first_token"]["count"] == 2
        assert metrics["time_to_first_output_token"]["count"] == 2
        receipt = {
            "command": command,
            "request_count": _Handler.request_count,
            "stdout_sha256": _sha256(run_dir / "stdout.log"),
            "stderr_sha256": _sha256(run_dir / "stderr.log"),
            "source_sha256": _sha256(Path(__file__)),
            "artifact_sha256": {str(path.relative_to(run_dir)): _sha256(path) for path in sorted(artifacts.rglob("*")) if path.is_file()},
            "metric_summary": {
                "error_summary": metrics["error_summary"],
                "request_count": metrics["request_count"]["avg"],
                "ttft_count": metrics["time_to_first_token"]["count"],
                "ttfo_count": metrics["time_to_first_output_token"]["count"],
            },
        }
        receipt_path = run_dir / "receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        latest = {"run": str(run_dir.relative_to(TOOLCHAIN)), "receipt_sha256": _sha256(receipt_path)}
        (TOOLCHAIN / "aiperf-smoke-latest.json").write_text(json.dumps(latest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        if process is not None and process.poll() is None:
            _stop_owned_process_group(process)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
