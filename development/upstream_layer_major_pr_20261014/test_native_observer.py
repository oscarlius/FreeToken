"""CPU contract for native ID observation and transparent forwarding."""
import json
import tempfile
import unittest
from dataclasses import dataclass

from native_observer import install


@dataclass
class Reply:
    uid: int
    next_token: int
    finished: bool
    finish_reason: str | None = None


@dataclass
class Admission:
    uid: int
    prompt_tokens: int
    cached_tokens: int


class ObserverTest(unittest.TestCase):
    def test_accumulates_native_ids_and_forwards_identical_messages(self):
        class IO:
            def _reply_tokenizer_rank0(self, messages):
                self.forwarded = messages
                return 17

        with tempfile.TemporaryDirectory() as directory:
            path = install(IO, Reply, directory, Admission)
            instance = IO()
            instance._reply_tokenizer_rank0([Admission(5, 32012, 0)])
            first = [Reply(5, 101, False), object()]
            self.assertEqual(instance._reply_tokenizer_rank0(first), 17)
            self.assertIs(instance.forwarded, first)
            self.assertFalse(path.exists())
            final = [Reply(5, 102, True, "length")]
            self.assertEqual(instance._reply_tokenizer_rank0(final), 17)
            self.assertIs(instance.forwarded, final)
            record = json.loads(path.read_text())
            self.assertEqual(record["uid"], 5)
            self.assertEqual(record["native_token_ids"], [101, 102])
            self.assertEqual(record["finish_reason"], "length")
            self.assertEqual(record["prompt_tokens"], 32012)
            self.assertEqual(record["cached_tokens"], 0)


if __name__ == "__main__":
    unittest.main()
