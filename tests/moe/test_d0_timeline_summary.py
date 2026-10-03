from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest


def _script_path() -> Path:
    configured = os.environ.get("FT_D0_TIMELINE_SCRIPT")
    if configured:
        return Path(configured)
    return (Path(__file__).parent / "../../../../scripts/d0_timeline_summary.py").resolve()


@pytest.fixture(scope="module")
def timeline_module():
    spec = importlib.util.spec_from_file_location("d0_timeline_summary", _script_path())
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(step, step_ms, layers, *, bs=1, rids=None):
    return {
        "step": step,
        "t": float(step),
        "bs": bs,
        "rids": list(range(bs)) if rids is None else rids,
        "step_ms": step_ms,
        "layers": layers,
    }


def _layer(layer, copy_start, copy_end, compute_start, compute_end):
    return {
        "layer": layer,
        "copy_start_ms": copy_start,
        "copy_end_ms": copy_end,
        "compute_start_ms": compute_start,
        "compute_end_ms": compute_end,
    }


def _write(tmp_path, records):
    path = tmp_path / "timeline.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


def test_summary_uses_interval_unions_and_linear_percentiles(timeline_module, tmp_path):
    path = _write(
        tmp_path,
        [
            _record(1, 10, [_layer(0, 0, 4, 2, 7), _layer(1, 1, 5, 5, 8)]),
            _record(2, 20, [_layer(0, 0, 10, 10, 20), _layer(1, 5, 15, 12, 18)]),
        ],
    )
    summary = timeline_module.summarize(timeline_module.load_timeline(path))

    assert summary["layers"]["0"]["copy_ms"] == {"median": 7.0, "p90": 9.4}
    assert summary["layers"]["1"]["compute_ms"] == {"median": 4.5, "p90": 5.7}
    assert summary["steps"][0] == {"step": 1, "overlap_ms": 3.0, "overlap_ratio": 0.3, "bubble_ms": 2.0}
    assert summary["steps"][1] == {"step": 2, "overlap_ms": 5.0, "overlap_ratio": 0.25, "bubble_ms": 0.0}
    assert summary["overall"]["bubble_ms"] == {"median": 1.0, "p90": 1.8}


def test_zero_step_is_finite_and_has_no_nan(timeline_module, tmp_path):
    path = _write(tmp_path, [_record(1, 0, [_layer(0, 0, 0, 0, 0)])])
    summary = timeline_module.summarize(timeline_module.load_timeline(path))
    assert summary["steps"][0] == {"step": 1, "overlap_ms": 0.0, "overlap_ratio": 0.0, "bubble_ms": 0.0}


@pytest.mark.parametrize(
    "records",
    [
        [],
        ["not json"],
        [_record(1, 1, [_layer(0, 0, 1, 0, 1)], bs=2, rids=[1])],
        [_record(1, 1, [{"layer": 0}])],
        [_record(1, 1, [_layer(0, 0, 1, 0, 1), _layer(0, 0, 1, 0, 1)])],
        [_record(1, 1, [_layer(0, 0, 1, 0, 1)]), _record(1, 1, [_layer(0, 0, 1, 0, 1)])],
        [_record(1, 1, [_layer(0, 0, 1, 0, 1)]), _record(2, 1, [_layer(1, 0, 1, 0, 1)])],
        [_record(1, 1, [_layer(0, 0, float("nan"), 0, 1)])],
    ],
)
def test_loader_fails_closed(timeline_module, tmp_path, records):
    path = tmp_path / "bad.jsonl"
    if records == ["not json"]:
        path.write_text("not json\n", encoding="utf-8")
    else:
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    with pytest.raises(timeline_module.TimelineError):
        timeline_module.load_timeline(path)


def test_cli_json_and_missing_input(timeline_module, tmp_path, capsys):
    path = _write(tmp_path, [_record(1, 1, [_layer(0, 0, 1, 0, 1)])])
    assert timeline_module.main([str(path)]) == 0
    assert "Per-layer durations" in capsys.readouterr().out
    assert timeline_module.main([str(path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["steps"][0]["step"] == 1
    assert timeline_module.main([str(tmp_path / "missing.jsonl")]) == 2
    assert "cannot read" in capsys.readouterr().err
