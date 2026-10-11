"""Actual R019/R021 regressions, plus missing-tail and transfer rejection."""
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("t16_shared_prefill", HERE / "t16_full_tail_base_runner.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
FIXTURES = json.loads((HERE / "tests/fixtures/t16_failed_full_tail.json").read_text())


def fixture_arms(tmp_path, rid):
    data = FIXTURES[rid]
    paths = []
    for name, records in data["arms"].items():
        arm = tmp_path / name
        arm.mkdir()
        (arm / "serve.log").write_text("".join(
            "#new-seq: %d, #new-token: %d, #cached-token: %d\n" % tuple(row)
            for row in records["events"]))
        (arm / "d0_prefill.jsonl").write_text("".join(json.dumps(row) + "\n" for row in records["rows"]))
        paths.append(arm)
    paths.sort(key=lambda p: not p.name.startswith("PARENT"))
    return paths


@pytest.mark.parametrize("rid", sorted(FIXTURES))
def test_failed_rounds_have_complete_observed_tail(tmp_path, rid):
    parent, new = fixture_arms(tmp_path, rid)
    result = runner.check_prefill(parent, new)
    assert result["parent_rows"] == result["new_rows"] == result["all_prefill_events"] == 13
    assert result["h2d"] == "SAME"


@pytest.mark.parametrize("failure", ["missing_tail", "missing_event", "h2d", "d2d", "parent_metadata"])
def test_actual_fixture_still_rejects_data_errors(tmp_path, failure):
    parent, new = fixture_arms(tmp_path, "E2-R021-gate-D14")
    if failure == "missing_event":
        log = new / "serve.log"
        log.write_text("\n".join(log.read_text().splitlines()[:-1]) + "\n")
    else:
        path = (parent if failure == "parent_metadata" else new) / "d0_prefill.jsonl"
        records = runner.rows(path)
        if failure == "missing_tail":
            records.pop()
        elif failure == "parent_metadata":
            records[0]["reqs"][0]["new_tokens"] += 1
        else:
            records[0][failure + "_bytes"] += 1
        path.write_text("".join(json.dumps(row) + "\n" for row in records))
    with pytest.raises(ValueError):
        runner.check_prefill(parent, new)


def test_tail_coverage_is_explicit_and_never_inferred_from_card(tmp_path):
    path = tmp_path / "prefill_while_alive.json"
    path.write_text(json.dumps({"events": 13, "rows": 13}))
    with pytest.raises(ValueError, match="explicit"):
        runner.prefill_tail_contract(tmp_path)
    path.write_text(json.dumps({"includes_terminal_prefill": True}))
    assert runner.prefill_tail_contract(tmp_path) is True


def test_live_comparison_and_final_comparison_share_source_contract():
    source = (HERE / "t16_full_tail_base_runner.py").read_text()
    assert "self.options.gate in ('D03', 'D06', 'D07')" not in source
    assert "parent_tail_fix=prefill_tail_contract(compare_to)" in source
