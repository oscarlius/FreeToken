import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gpu_client import BenchmarkError, _bind_native_receipt, _parse_sse, check_service, invoke, run_arm


class ParseSSETests(unittest.TestCase):
    def test_interleaved_terminal_and_usage(self):
        raw = io.BytesIO()
        outcome = _parse_sse(
            [
                b'data: {"choices":[{"text":"a","finish_reason":null}]}\n', b'\n',
                b'data: {"choices":[{"text":"","finish_reason":"length"}]}\n', b'\n',
                b'data: {"choices":[],"usage":{"cached_tokens":77}}\n', b'\n', b'data: [DONE]\n', b'\n',
            ], raw, 0,
        )
        self.assertEqual(outcome.text, "a")
        self.assertEqual(outcome.finish_reason, "length")
        self.assertEqual(outcome.usage["cached_tokens"], 77)
        self.assertTrue(raw.getvalue())

    def test_missing_usage_fails(self):
        with self.assertRaisesRegex(BenchmarkError, "without usage"):
            _parse_sse([b'data: {"choices":[{"text":"","finish_reason":"stop"}]}\n', b'\n'], io.BytesIO(), 0)

    def test_chat_delta_event_fails(self):
        with self.assertRaisesRegex(BenchmarkError, "not a completion event"):
            _parse_sse(
                [b'data: {"choices":[{"delta":{"content":"a"},"finish_reason":null}]}\n', b'\n'],
                io.BytesIO(), 0,
            )

    def test_maintenance_health_is_refused(self):
        with patch("gpu_client._get_json", return_value={"status": "ok", "maintenance": "rebuilding"}):
            with self.assertRaisesRegex(BenchmarkError, "not serving"):
                check_service("http://unused", "model")

    def test_missing_native_record_is_refused(self):
        receipt = {"started_unix_ns": 1, "usage": {"prompt_tokens": 32012}}
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(BenchmarkError, "no native_ids"):
                _bind_native_receipt(receipt, directory, "cold")

    def test_native_cache_mismatch_is_refused(self):
        receipt = {
            "started_unix_ns": 1,
            "usage": {"prompt_tokens": 32012, "prompt_tokens_details": {"cached_tokens": 77}},
        }
        record = {"uid": 4, "finished_unix_ns": 2, "native_token_ids": list(range(128)), "prompt_tokens": 32012, "cached_tokens": 76, "pid": 1, "finish_reason": "length"}
        with patch("gpu_client._native_terminal", return_value=record):
            with self.assertRaisesRegex(BenchmarkError, "cached_tokens differ"):
                _bind_native_receipt(receipt, "unused", "continuation")

    def test_omitted_api_cache_is_allowed_when_native_cache_is_zero(self):
        receipt = {"started_unix_ns": 1, "usage": {"prompt_tokens": 32012}}
        record = {"uid": 4, "finished_unix_ns": 2, "native_token_ids": list(range(128)), "prompt_tokens": 32012, "cached_tokens": 0, "pid": 1, "finish_reason": "length"}
        receipt["finish_reason"] = "length"
        with patch("gpu_client._native_terminal", return_value=record):
            _bind_native_receipt(receipt, "unused", "cold")
        self.assertEqual(receipt["native_cached_tokens"], 0)
        self.assertEqual(receipt["native_uid"], 4)

    def test_failing_warmup_stops_before_next_call(self):
        calls = []

        def invoke(_base, _model, _input, label, _output, **_ignored):
            calls.append(label)
            return {"label": label, "finish_reason": "stop", "usage": {"prompt_tokens": 512, "completion_tokens": 1}}

        with tempfile.TemporaryDirectory() as directory, patch("gpu_client.check_service"), patch("gpu_client.invoke", side_effect=invoke):
            with self.assertRaisesRegex(BenchmarkError, "completion_tokens"):
                run_arm("http://unused", "model", self._inputs(directory), Path(directory) / "out", "main", directory, 9_999_999_999)
        self.assertEqual(calls, ["warmup-short512-1"])

    def test_failing_cold_stops_before_continuation(self):
        calls = []

        def invoke(_base, _model, _input, label, _output, **_ignored):
            calls.append(label)
            prompt = 512 if "short512" in label else 32012
            return {
                "label": label,
                "finish_reason": "length",
                "usage": {
                    "prompt_tokens": prompt,
                    "completion_tokens": 128,
                    "prompt_tokens_details": {"cached_tokens": 1 if "cold" in label else 0},
                },
                "native_cached_tokens": 1 if "cold" in label else 0,
            }

        with tempfile.TemporaryDirectory() as directory, patch("gpu_client.check_service"), patch("gpu_client.invoke", side_effect=invoke):
            with self.assertRaisesRegex(BenchmarkError, "cold cached_tokens"):
                run_arm("http://unused", "model", self._inputs(directory), Path(directory) / "out", "main", directory, 9_999_999_999)
        self.assertEqual(calls, ["warmup-short512-1", "warmup-short512-2", "short512", "long1-cold32012"])

    def test_expired_deadline_does_not_open_transport(self):
        with tempfile.TemporaryDirectory() as directory, patch("gpu_client.urllib.request.urlopen") as urlopen:
            with self.assertRaisesRegex(BenchmarkError, "deadline has expired"):
                invoke("http://unused", "model", "prompt", "expired", directory, deadline_unix=0)
        urlopen.assert_not_called()

    def test_deadline_caps_http_timeout(self):
        response = [
            b'data: {"choices":[{"text":"x","finish_reason":null}]}\n', b'\n',
            b'data: {"choices":[{"text":"","finish_reason":"length"}]}\n', b'\n',
            b'data: {"choices":[],"usage":{"prompt_tokens":1,"completion_tokens":128}}\n', b'\n',
        ]

        class Response(list):
            def close(self):
                pass

        with tempfile.TemporaryDirectory() as directory, patch("gpu_client.time.time", return_value=100.0), patch(
            "gpu_client.urllib.request.urlopen", return_value=Response(response)
        ) as urlopen:
            invoke("http://unused", "model", "prompt", "cap", directory, deadline_unix=145.0)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 45.0)

    @staticmethod
    def _inputs(directory):
        path = Path(directory) / "inputs.json"
        path.write_text(json.dumps({
            "version": 1,
            "short512": "short",
            "long": [
                {"label": "long1", "cold": "cold1", "continuation": "cold1 tail"},
                {"label": "long2", "cold": "cold2", "continuation": "cold2 tail"},
                {"label": "long3", "cold": "cold3", "continuation": "cold3 tail"},
            ],
            "sampling": {"temperature": 0, "max_tokens": 128, "ignore_eos": True},
        }), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
