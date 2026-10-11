from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

PATH = Path(__file__).parents[1] / "development" / "t16_gate_runner.py"
spec = importlib.util.spec_from_file_location("t16_gate_runner", PATH)
runner = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(runner)


REAL_EVENTS = [(1, 14, 0), (1, 32064, 0), (1, 6675, 0), (1, 6400, 0), (1, 624, 0), (1, 19, 6656), (1, 48, 6976), (1, 19, 6656), (1, 48, 6976), (1, 19, 6656), (1, 48, 6976), (1, 19, 6656), (1, 48, 6976)]
REAL_HASHES = {"E2-R019-gate-D06": ["5a50f8828f3e9efd004283b511d67da8e65ae2bbd170dfd0d60ef415601929bd", "fa8cba180e24d79fb7a35607b63c542da253bb285b0b37f9dd3e6f048cc352ae", "c615982df8c6eb48b6433b741b6c3fe9c2fda6830cc01b7f82e83467c54d3748", "04d27f5422f908c6d01f52f10ebe21cc60af3bbf461baad476e21d6732a48ce0"], "E2-R021-gate-D14": ["fef387366d69493ddfa46fea3a5bb61d7bc3c56359ecbe7c44b405addc117453", "2b7e63c9382c64b1eb35317de6a6edc952ee288913f7c575d01c1fa143f88ac8", "6484c16fc4c1f4cdd7111194a79ce3e71ad59b2aa387d548f8a2c726a7270076", "5f8a5cc1df255e307656092a6f4e5d3d0fd5c4b748b30ecca66b3dbb037de7ce"]}


def arm(tmp_path, count=13, actual=False):
    tmp_path.mkdir()
    events = REAL_EVENTS if actual else [(1, 100 + index, index) for index in range(count)]
    (tmp_path / "serve.log").write_text("".join(f"#new-seq: {a}, #new-token: {b}, #cached-token: {c}\n" for a, b, c in events))
    rows = [{"chunk": index, "h2d_bytes": 68136468480 if index < 2 else 62914068480, "d2d_bytes": 0 if index < 2 else 5222400000, "reqs": [{"new_tokens": new, "cached_tokens": cached}]} for index, (_, new, cached) in enumerate(events)]
    (tmp_path / "d0_prefill.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return tmp_path


@pytest.mark.parametrize("card", ["D06", "D07", "D14"])
def test_candidate_bindings_are_explicit(card):
    value = runner.candidate(card)
    assert len(value["parent_commit"]) == len(value["new_commit"]) == 40


@pytest.mark.parametrize("source", ["E2-R019-gate-D06", "E2-R021-gate-D14"])
def test_server_derived_completed_arm_contracts_bind_all_thirteen_rows(tmp_path, source):
    result = runner.validate_pair(arm(tmp_path / "parent", actual=True), arm(tmp_path / "new", actual=True))
    assert result["expected_rows"] == 13 and len(REAL_HASHES[source]) == 4
    assert result["parent"]["h2d_sum_bytes"] == 828327690240
    assert runner.old_prefill_count(tmp_path / "parent" / "serve.log") == 12


def test_missing_final_parent_row_fails_before_a_gate_is_written(tmp_path):
    parent, new = arm(tmp_path / "parent"), arm(tmp_path / "new")
    lines = (parent / "d0_prefill.jsonl").read_text().splitlines()
    (parent / "d0_prefill.jsonl").write_text("\n".join(lines[:-1]) + "\n")
    with pytest.raises(ValueError, match="count differs"):
        runner.validate_pair(parent, new)


def test_four_arm_execute_writes_shared_gate(tmp_path):
    calls = []
    class BaseRunner:
        def __init__(self, options):
            self.options = options; self.directory = tmp_path / options.rid; self.proc = None
        def gate(self, wt, commit): calls.append(("gate", wt.name, commit))
        def lock_take(self): calls.append(("lock",))
        def lock_release(self): calls.append(("release",))
        def stop(self): calls.append(("stop",))
        def set_status(self, **values): calls.append(("status", values["state"]))
        def run_arm(self, name, wt, commit, d0, compare_to=None):
            calls.append(("arm", name, d0)); path = self.directory / name; path.mkdir(); return path
    base = SimpleNamespace(Runner=BaseRunner, ROOT=tmp_path, write_new=lambda path, value: path.write_text(json.dumps(value)))
    (tmp_path / "wt" / "e2base").mkdir(parents=True); (tmp_path / "wt" / "e2d14").mkdir()
    subject = runner.shared_runner(base)(SimpleNamespace(case="D14", rid="E2-R022-gate-D14", batch=50, candidate_commit=runner.CANDIDATES["D14"]["new_commit"], run=True))
    subject.compare = lambda *items: {"checked": True}
    result = subject.execute()
    assert [item[1] for item in calls if item[0] == "arm"] == ["PARENT_b50", "NEW_b50", "PARENT_P_b50", "NEW_P_b50"]
    assert result["layer_major"] == {"checked": True}
    assert (subject.directory / "gate_batch50.json").is_file()
