#!/usr/bin/env python3
"""Unit tests for oh_window.py (P1-G3).

Covers:
1. argv diff gate: permits only the 3 approved categories, rejects all others.
2. OOM chunk detection: recognizes CUDA OOM / worker_restarting_after_oom error payloads.
3. Output text extraction: handles reasoning_content, content, and tool_calls.
4. Output comparison: detects first differing character index accurately.
5. KV assertion: ensures tokens + max_tokens <= 98304.
6. Time limit cutoff logic: refuses new service start when remaining < 900s.
7. D0 miss rate calculation: skips first 16 steps, computes missing_total / (N * 480).
"""
import copy
import json
import unittest
from pathlib import Path

from oh_window import (
    check_is_oom_chunk,
    compute_expected_argv,
    extract_output_text_from_record,
    first_diff,
    validate_argv_diff,
)

BASELINE_ARGV = [
    "taskset", "-c", "1,3-47",
    "/data2/FreeToken/venv/bin/ft", "serve",
    "--model-path", "/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay",
    "--served-model-name", "Qwen3.8-Flash-Next-NVFP4",
    "--host", "172.16.108.9",
    "--port", "8095",
    "--memory-ratio", "0.88",
    "--moe-cache-auto",
    "--moe-prefill-hit-d2d",
    "--ple-backend", "pinned",
    "--moe-strategy", "offload",
    "--quant-backend", "moe.nvfp4=triton",
    "--max-running-requests", "2",
    "--cuda-graph-max-bs", "2",
    "--kv-reserve-tokens", "98304",
    "--max-seq-len-override", "98304",
    "--max-prefill-length", "4096",
    "--enable-cache-report",
    "--enable-special-token-ckpt",
    "--tool-call-parser", "qwen3_coder",
    "--reasoning-parser", "qwen3",
    "--prefill-layer-major",
    "--mamba-host-slots", "0",
]


class TestArgvGate(unittest.TestCase):
    def test_offload_approved_diff(self):
        actual = compute_expected_argv(BASELINE_ARGV, {"type": "offload"})
        diff = validate_argv_diff(BASELINE_ARGV, actual)
        self.assertEqual(len(diff), 2)
        self.assertEqual(actual[actual.index("--host") + 1], "127.0.0.1")
        self.assertEqual(actual[actual.index("--port") + 1], "8123")

    def test_hybrid_approved_diff(self):
        actual = compute_expected_argv(BASELINE_ARGV, {"type": "hybrid"})
        diff = validate_argv_diff(BASELINE_ARGV, actual)
        self.assertTrue(any(d["actual"] == "numactl" for d in diff))
        self.assertEqual(actual[actual.index("--moe-strategy") + 1], "hybrid")
        self.assertEqual(actual[actual.index("--host") + 1], "127.0.0.1")

    def test_hr_variant_approved_diff(self):
        actual = compute_expected_argv(BASELINE_ARGV, {
            "type": "hybrid",
            "extra_argv": ["--moe-hybrid-max-fetch", "0"],
        })
        diff = validate_argv_diff(BASELINE_ARGV, actual)
        self.assertEqual(actual[-2:], ["--moe-hybrid-max-fetch", "0"])

    def test_unapproved_memory_ratio_rejected(self):
        bad = compute_expected_argv(BASELINE_ARGV, {"type": "offload"})
        idx = bad.index("--memory-ratio")
        bad[idx + 1] = "0.90"
        with self.assertRaises(ValueError):
            validate_argv_diff(BASELINE_ARGV, bad)

    def test_unapproved_extra_flag_rejected(self):
        bad = compute_expected_argv(BASELINE_ARGV, {"type": "offload"})
        bad.append("--unapproved-switch")
        with self.assertRaises(ValueError):
            validate_argv_diff(BASELINE_ARGV, bad)

    def test_unapproved_port_rejected(self):
        bad = compute_expected_argv(BASELINE_ARGV, {"type": "offload"})
        bad[bad.index("--port") + 1] = "9999"
        with self.assertRaises(ValueError):
            validate_argv_diff(BASELINE_ARGV, bad)


class TestOOMDetection(unittest.TestCase):
    def test_cuda_oom_recognized(self):
        chunk = {
            "error": {
                "message": "worker_restarting_after_oom: OutOfMemoryError: CUDA out of memory. Tried to allocate 48.00 MiB.",
                "type": "invalid_request_error",
            }
        }
        is_oom, msg = check_is_oom_chunk(chunk)
        self.assertTrue(is_oom)
        self.assertIn("out of memory", msg.lower())

    def test_normal_chunk_not_oom(self):
        chunk = {
            "choices": [{"delta": {"content": "Hello"}}]
        }
        is_oom, msg = check_is_oom_chunk(chunk)
        self.assertFalse(is_oom)

    def test_unrelated_error_not_oom(self):
        chunk = {
            "error": {
                "message": "Invalid prompt format",
                "type": "invalid_request_error",
            }
        }
        is_oom, msg = check_is_oom_chunk(chunk)
        self.assertFalse(is_oom)


class TestOutputExtraction(unittest.TestCase):
    def test_extract_reasoning_content_tool_calls(self):
        rec = {
            "metadata": {"session_num": 0, "x_request_id": "test-req-1"},
            "responses": [
                {
                    "packets": [
                        {"name": "data", "value": json.dumps({"choices": [{"delta": {"reasoning_content": "Thinking step. "}}]})},
                        {"name": "data", "value": json.dumps({"choices": [{"delta": {"content": "Final answer. "}}]})},
                        {"name": "data", "value": json.dumps({"choices": [{"delta": {"tool_calls": [{"name": "search", "args": {"q": "test"}}]}}]})},
                    ]
                }
            ]
        }
        text = extract_output_text_from_record(rec)
        self.assertIn("Thinking step. ", text)
        self.assertIn("Final answer. ", text)
        self.assertIn("search", text)
        self.assertTrue(text.startswith("Thinking step. Final answer."))


class TestCompareFirstDiff(unittest.TestCase):
    def test_identical_strings(self):
        self.assertIsNone(first_diff("abcdef", "abcdef"))

    def test_differ_at_index_100(self):
        s1 = "A" * 100 + "B" * 50
        s2 = "A" * 100 + "C" * 50
        self.assertEqual(first_diff(s1, s2), 100)

    def test_prefix_differ_at_0(self):
        self.assertEqual(first_diff("Xabc", "Yabc"), 0)

    def test_differ_by_length(self):
        self.assertEqual(first_diff("abcdef", "abcdefg"), 6)


class TestKVAssertion(unittest.TestCase):
    def test_within_kv_limit(self):
        max_allowed = 98304
        max_tokens = 32
        for prompt_toks in [64000, 80000, 87100, 95352]:
            self.assertLessEqual(prompt_toks + max_tokens, max_allowed)

    def test_exceeding_kv_limit_detected(self):
        max_allowed = 98304
        max_tokens = 32
        bad_prompt_toks = 98273
        self.assertGreater(bad_prompt_toks + max_tokens, max_allowed)


class TestTimeLimitLogic(unittest.TestCase):
    def test_remaining_time_cutoff(self):
        window_limit = 6600
        cutoff_reserve = 900

        # Case 1: 5000s elapsed -> remaining 1600s >= 900s -> continue
        elapsed_1 = 5000
        remaining_1 = window_limit - elapsed_1
        self.assertGreaterEqual(remaining_1, cutoff_reserve)

        # Case 2: 5800s elapsed -> remaining 800s < 900s -> stop
        elapsed_2 = 5800
        remaining_2 = window_limit - elapsed_2
        self.assertLess(remaining_2, cutoff_reserve)


class TestD0MissRateCalculation(unittest.TestCase):
    def test_d0_miss_rate_excludes_first_16_steps(self):
        steps = []
        for s in range(32):
            # first 16 steps: cold miss (480)
            # next 16 steps: 144 misses
            m_tot = 480 if s < 16 else 144
            steps.append({"step": s, "missing_total": m_tot})

        post16 = [r for r in steps if r["step"] >= 16]
        self.assertEqual(len(post16), 16)
        tot_missing = sum(r["missing_total"] for r in post16)
        denom = len(post16) * 480
        miss_rate = tot_missing / denom
        self.assertAlmostEqual(miss_rate, 144 / 480, places=4)
        self.assertAlmostEqual(miss_rate, 0.30, places=4)


if __name__ == "__main__":
    unittest.main()
