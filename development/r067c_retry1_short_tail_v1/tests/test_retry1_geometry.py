from __future__ import annotations

import json
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("retry1_geometry", HERE / "geometry.py")
geometry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geometry)
prefill_rows, valid_geometry = geometry.prefill_rows, geometry.valid_geometry


class Retry1GeometryTest(unittest.TestCase):
    def test_actual_failed_seed_fixture_is_one_segmented_request(self):
        rows = prefill_rows((HERE / "fixtures" / "hot_p8192_seed.serve-window.txt").read_text())
        response = json.loads((HERE / "fixtures" / "hot_p8192_seed.response.json").read_text())
        self.assertEqual(rows, [
            {"new_sequences": 1, "new_tokens": 512, "cached_tokens": 0},
            {"new_sequences": 1, "new_tokens": 7681, "cached_tokens": 0},
        ])
        self.assertTrue(valid_geometry(rows, expected_cached=0, expected_new=8193))
        self.assertEqual(response["usage"], {"prompt_tokens": 8193, "completion_tokens": 2, "cached_tokens": 0})
        window = (HERE / "fixtures" / "hot_p8192_seed.serve-window.txt").read_text()
        self.assertEqual(window.count('POST /internal/t17/exact-ids HTTP/1.1" 200 OK'), 1)

    def test_old_sum_of_per_row_sequence_counts_rejects_fixture(self):
        rows = prefill_rows((HERE / "fixtures" / "hot_p8192_seed.serve-window.txt").read_text())
        self.assertEqual(sum(row["new_sequences"] for row in rows), 2)
        self.assertNotEqual(sum(row["new_sequences"] for row in rows), 1)

    def test_negative_wrong_cache_wrong_token_or_multi_sequence_is_rejected(self):
        good = [{"new_sequences": 1, "new_tokens": 512, "cached_tokens": 0},
                {"new_sequences": 1, "new_tokens": 7681, "cached_tokens": 0}]
        self.assertFalse(valid_geometry([{**good[0], "cached_tokens": 1}, good[1]], expected_cached=0, expected_new=8193))
        self.assertFalse(valid_geometry([{**good[0], "new_tokens": 511}, good[1]], expected_cached=0, expected_new=8193))
        self.assertFalse(valid_geometry([{**good[0], "new_sequences": 2}, good[1]], expected_cached=0, expected_new=8193))
        self.assertFalse(valid_geometry([], expected_cached=0, expected_new=8193))


if __name__ == "__main__":
    unittest.main(verbosity=2)
