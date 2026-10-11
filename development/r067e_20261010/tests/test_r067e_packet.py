import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import r067e_packet as packet


def hot(prefix):
    base = Path(__file__).resolve().parents[1] / "fixtures"
    return base / f"hot_p{prefix}.observations.jsonl"


def test_schedule_is_extracted_from_hot_observations_not_inferred():
    schedule = packet.observed_seed_schedule(packet.observations(hot(8192)), 8192)
    assert schedule == [
        {"start": 0, "end": 512, "mode": "ordinary", "subchunks": [512]},
        {"start": 512, "end": 8193, "mode": "layer_major", "subchunks": [4096, 3585]},
        {"start": 8192, "end": 8193, "mode": "ordinary", "subchunks": [1]},
    ]
    packet.parse_schedule(schedule)


def test_hot_observation_drift_fails_closed():
    rows = packet.observations(hot(8192))
    rows[2]["children"][1]["device_tokens"] += 1
    with pytest.raises(AssertionError):
        packet.observed_seed_schedule(rows, 8192)


def test_packet_retains_budget_and_declares_pre_output_gate(tmp_path):
    dumps = {8192: tmp_path / "hot8192.pt", 8256: tmp_path / "hot8256.pt"}
    for path in dumps.values(): path.write_bytes(b"donor-dump-fixture")
    target = tmp_path / "packet.json"
    doc = packet.write_packet(target, {8192: hot(8192), 8256: hot(8256)}, dumps)
    assert doc["scope"]["services"] == 10 and doc["scope"]["generation_calls"] == 14
    assert doc["constraints"]["cache_type"] == "hybrid_radix"
    assert doc["runtime_gate"]["on_mismatch"] == "failed_harness_stop_no_output"
    assert json.loads(target.read_text())["rid"] == packet.RID


def test_prior_confounded_boundary_is_preserved_as_reinterpretation(monkeypatch, tmp_path):
    values = iter(("hot", "cold"))
    monkeypatch.setattr(packet, "state_tensor_hash", lambda _: next(values))
    result = packet.replay_prior_confounded_boundary(tmp_path / "hot", tmp_path / "cold")
    assert result["prior_terminal_verdict"] == "not_met"
    assert result["preserved_interpretation"] == "reference_confounded_before_tail"
