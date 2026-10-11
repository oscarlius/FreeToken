import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    import torch
except ImportError:
    torch = None

SCRIPT = Path(__file__).parents[1] / "state_eq.py"


def fixture(directory, *, resume=False):
    directory.mkdir(parents=True)
    roles = ("conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx")
    files = {}
    for index, role in enumerate(roles):
        name = f"role{index}.pt"
        torch.save(torch.ones(1, 1, 2), directory / name)
        files[role] = name
    rows = [{"seq": 1, "kind": "donate", "length": 64, "uid": 1, "files": files}]
    if resume:
        rows.append({"seq": 2, "kind": "resume", "length": 64, "uid": 1, "files": files})
    (directory / "index.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


@unittest.skipIf(torch is None, "Torch CPU required")
class LabelTests(unittest.TestCase):
    def test_labels_reflect_actual_test_resume_and_keep_length_lines(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "E2-R999"
            ref, test, restored = root / "dump_B", root / "dump_B2", root / "dump_A"
            fixture(ref)
            fixture(test)
            fixture(restored, resume=True)
            results = []
            for other in (test, restored):
                result = subprocess.run([sys.executable, str(SCRIPT), str(ref), str(other)],
                                        text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                results.append(result.stdout)
            no_restore = next(line for line in results[0].splitlines() if line.startswith("结论"))
            restore = next(line for line in results[1].splitlines() if line.startswith("结论"))
            self.assertNotIn("恢复", no_restore)
            self.assertIn("E2-R999/dump_B 对 E2-R999/dump_B2", no_restore)
            self.assertIn("恢复", restore)
            self.assertIn("E2-R999/dump_B 对 E2-R999/dump_A", restore)
            self.assertEqual([line for line in results[0].splitlines() if line.startswith("len=")],
                             [line for line in results[1].splitlines() if line.startswith("len=")])
            original = os.environ.get("FT_D04_ORIGINAL_STATE_EQ")
            if original:
                prior = subprocess.run([sys.executable, original, str(ref), str(test)], text=True, capture_output=True)
                self.assertEqual(prior.returncode, 0, prior.stderr)
                self.assertEqual([line for line in prior.stdout.splitlines() if line.startswith("len=")],
                                 [line for line in results[0].splitlines() if line.startswith("len=")])


if __name__ == "__main__":
    unittest.main()
