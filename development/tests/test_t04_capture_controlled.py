from __future__ import annotations

import hashlib
import importlib.util
import json
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest


MODULE_PATH = Path(__file__).parents[1] / "t04_capture_controlled.py"
SPEC = importlib.util.spec_from_file_location("t04_capture_controlled", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
controlled = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controlled)


class FakeProbe:
    def __init__(self, *, cached_len: int, restore_proof=None):
        self.cached_len = cached_len
        self.restore_proof = restore_proof
        self.calls = []
        self.full_prompt = []
        self.k = 0

    @staticmethod
    def sha(tokens):
        return hashlib.sha256(struct.pack(f"<{len(tokens)}i", *tokens)).hexdigest()

    def post(self, base_url, model, prompt, k):
        self.calls.append((base_url, model, list(prompt), k))
        return {"usage": {"prompt_tokens": len(prompt)}}

    def latest(self, dump, old, *, expected_sha, expected_k, expected_length):
        self.full_prompt = list(self.calls[-1][2])
        self.k = expected_k
        assert expected_sha == self.sha(self.full_prompt)
        assert expected_length == len(self.full_prompt)
        row = {
            "seq": old + 1,
            "uid": 17,
            "extra": {
                "cached_len": self.cached_len,
                "restore_proof": self.restore_proof,
            },
        }
        return row, SimpleNamespace(shape=(expected_k, 11))

    def binding(self, row, logits):
        return self.sha(self.full_prompt), self.k, len(self.full_prompt), list(
            range(len(self.full_prompt) - self.k, len(self.full_prompt))
        )

    @staticmethod
    def valid_restore_proof(proof, uid, cached_len):
        return (
            isinstance(proof, dict)
            and proof.get("kind") in {"host", "device"}
            and proof.get("uid") == uid
            and type(proof.get("source_slot")) is int
            and proof["source_slot"] > 0
            and type(proof.get("destination_slot")) is int
            and proof["destination_slot"] > 0
            and type(proof.get("length")) is int
            and 0 < proof["length"] <= cached_len
        )


def prefix(length=12780):
    return list(range(1, length + 1))


def proof(length=12672):
    return {
        "kind": "host",
        "uid": 17,
        "source_slot": 1,
        "destination_slot": 2,
        "length": length,
    }


def capture(tmp_path, probe, mode, **kwargs):
    dump = tmp_path / "dump"
    dump.mkdir()
    return controlled.capture_controlled(
        probe=probe,
        base_url="http://127.0.0.1:8095",
        prefix=prefix(),
        suffix=list(range(200, 232)),
        dump=dump,
        model="candidate",
        mode=mode,
        **kwargs,
    )


def test_fresh_posts_only_full_request_and_writes_no_scientific_result(tmp_path):
    probe = FakeProbe(cached_len=0)
    result = capture(tmp_path, probe, "fresh")

    expected = prefix() + list(range(200, 232))
    assert probe.calls == [("http://127.0.0.1:8095", "candidate", expected, 32)]
    assert result["cached_len"] == 0
    assert result["restore_proof"] is None
    assert result["warm_usage"] is None
    assert result["branch_usage"] is None
    assert result["measurement_usage"] == {"prompt_tokens": len(expected)}
    assert result["priming"] == {"warm_usage": None}
    assert "bitwise" not in result
    saved = json.loads((tmp_path / "dump" / "controlled_capture.json").read_text())
    assert saved == result


def test_branch_bank_seeds_distinct_branch_then_measures_unchanged_full_input(tmp_path):
    probe = FakeProbe(cached_len=12672, restore_proof=proof())
    result = capture(tmp_path, probe, "branch-bank")

    source = prefix()
    expected_full = source + list(range(200, 232))
    assert len(probe.calls) == 2
    _, _, seeded, seed_k = probe.calls[0]
    assert seed_k == 0
    assert seeded[:12672] == source[:12672]
    assert seeded[12672] != source[12672]
    assert probe.calls[1] == ("http://127.0.0.1:8095", "candidate", expected_full, 32)
    assert result["priming"]["warm_usage"] is None
    assert result["priming"]["branch_usage"] == {"prompt_tokens": len(seeded)}
    assert result["warm_usage"] is None
    assert result["branch_usage"] == {"prompt_tokens": len(seeded)}
    assert result["measurement_usage"] == {"prompt_tokens": len(expected_full)}
    archive = json.loads((tmp_path / "dump" / "branch_ids.json").read_text())
    assert archive["common_prefix_length"] == 12672
    assert archive["branch_ids"] == seeded
    assert archive["full_input_sha256"] == probe.sha(expected_full)


@pytest.mark.parametrize(
    ("mode", "cached_len", "restore_proof"),
    [
        ("fresh", 1, None),
        ("branch-bank", 12672, None),
        ("branch-bank", 12671, proof()),
        ("branch-bank", 12672, proof(1)),
    ],
)
def test_cache_contracts_fail_closed(tmp_path, mode, cached_len, restore_proof):
    probe = FakeProbe(cached_len=cached_len, restore_proof=restore_proof)
    with pytest.raises(RuntimeError):
        capture(tmp_path, probe, mode)
    assert not (tmp_path / "dump" / "controlled_capture.json").exists()


def test_diagnostic_is_direct_and_does_not_infer_cache_science(tmp_path):
    probe = FakeProbe(cached_len=77, restore_proof={"anything": "unverified"})
    result = capture(tmp_path, probe, "diagnostic")

    assert len(probe.calls) == 1
    assert probe.calls[0][-1] == 32
    assert result["cached_len"] == 77
    assert result["restore_proof"] == {"anything": "unverified"}
    assert set(result) == {
        "uid", "dump_seq", "k", "input_length", "input_sha256", "positions",
        "logits_shape", "cached_len", "restore_proof", "mode", "priming",
        "warm_usage", "branch_usage", "measurement_usage",
    }


def test_frozen_probe_source_hash_is_pinned_to_candidate():
    candidate = MODULE_PATH.parent / "e2d03" / "scripts" / "logits_probe.py"
    assert controlled.sha256_file(candidate) == controlled.FROZEN_PROBE_SHA256


def test_probe_executes_the_single_hash_validated_read(monkeypatch, tmp_path):
    good = b"identity = 'reviewed'\n"
    path = tmp_path / "probe.py"
    path.write_bytes(b"identity = 'replaced'\n")
    reads = []
    def read_once(candidate):
        assert candidate == path
        reads.append(candidate)
        return good if len(reads) == 1 else b"identity = 'unreviewed'\n"
    monkeypatch.setattr(Path, "read_bytes", read_once)
    monkeypatch.setattr(controlled, "FROZEN_PROBE_SHA256", hashlib.sha256(good).hexdigest())
    module = controlled.load_frozen_probe(path)
    assert module.identity == "reviewed" and len(reads) == 1
    assert module.__file__ == str(path)


def test_changed_probe_bytes_are_rejected_before_execution(monkeypatch, tmp_path):
    path = tmp_path / "probe.py"
    path.write_bytes(b"raise AssertionError('must not execute')\n")
    with pytest.raises(RuntimeError, match="SHA256 mismatch"):
        controlled.load_frozen_probe(path)
