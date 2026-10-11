from __future__ import annotations

import importlib.util
import shutil
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "e2d03-continuation"
SPEC = importlib.util.spec_from_file_location("t04_boundary_cpu_gate", ROOT / "t04_boundary_cpu_gate.py")
assert SPEC and SPEC.loader
GATE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = GATE
SPEC.loader.exec_module(GATE)


def test_frozen_input_and_controlled_branch_recipe():
    inputs, geometry = GATE.read_frozen(ROOT / "t04_r015_boundary_inputs.json", ROOT / "t04_r015_geometry.json")
    variants = GATE.branch_variants(inputs)
    prefix = inputs["prefix_ids"]
    assert {name: len(ids) for name, ids in variants.items()} == {"Y96": 12768, "Y122": 12794, "Y129": 12801}
    assert variants["Y96"][:12672] == variants["Y122"][:12672] == variants["Y129"][:12672]
    assert variants["Y96"][12672] == 74
    # This is the controlled client's first-different-token construction, not markers invented by this test.
    assert variants["Y129"] == prefix[:12672] + [74] + prefix[12673:12801]
    assert "overridden to 64" in "\n".join(geometry["geometry_lines"])


@pytest.mark.parametrize("source", ("inputs", "geometry"))
def test_rejects_wrong_frozen_source_sha(tmp_path, source):
    inputs = ROOT / "t04_r015_boundary_inputs.json"
    geometry = ROOT / "t04_r015_geometry.json"
    changed = tmp_path / f"{source}.json"
    selected = inputs if source == "inputs" else geometry
    changed.write_bytes(selected.read_bytes() + b"\n")
    with pytest.raises(ValueError, match=("input SHA256" if source == "inputs" else "geometry SHA256")):
        GATE.read_frozen(changed if source == "inputs" else inputs, changed if source == "geometry" else geometry)


def test_rejects_runtime_source_sha_drift(tmp_path):
    copied = tmp_path / "runtime"
    for relative in ("python/freetoken/scheduler/prefill.py", "python/freetoken/attention/linear.py"):
        target = copied / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(RUNTIME / relative, target)
    with (copied / "python/freetoken/scheduler/prefill.py").open("ab") as handle:
        handle.write(b"\n# drift\n")
    with pytest.raises(ValueError, match="runtime prefill SHA256"):
        GATE.validate_runtime_sources(copied)


@pytest.mark.parametrize("name", ("freetoken.utils", "freetoken.kernel.fla.chunk"))
def test_rejects_cached_foreign_runtime_dependency(monkeypatch, tmp_path, name):
    foreign = tmp_path / "foreign.py"
    foreign.write_text("# foreign\n", encoding="utf-8")
    monkeypatch.setitem(sys.modules, name, types.SimpleNamespace(__file__=str(foreign)))
    with pytest.raises(ValueError, match="cached module outside"):
        GATE._runtime_modules(RUNTIME)


def test_final_segment_without_track_keeps_prior_archive_track():
    archives, final = GATE.classify_tracks([
        {"end": 12480, "track": 12416, "final": False},
        {"end": 12496, "track": None, "final": True},
    ])
    assert archives == [12416]
    assert final is None


def test_predict_requires_a_real_runtime_root():
    with pytest.raises(ValueError, match="runtime root"):
        GATE.predict(Path("missing-runtime"), ROOT / "t04_r015_boundary_inputs.json", ROOT / "t04_r015_geometry.json")


def test_cpu_runtime_prediction_all_scenarios():
    pytest.importorskip("torch", reason="Linux CPU runtime integration requires Torch")
    result = GATE.predict(RUNTIME, ROOT / "t04_r015_boundary_inputs.json", ROOT / "t04_r015_geometry.json")
    assert result["scope"].startswith("CPU prediction")
    assert "not GPU/model measurement proof" in result["scope"]
    assert result["runtime_sha256"] == {"prefill": GATE.PREFILL_SHA256, "linear": GATE.LINEAR_SHA256}
    for name, expected in GATE.EXPECTED.items():
        observed = result["scenarios"][name]
        assert observed["scheduler_chunk_ends"] == expected["chunks"]
        assert observed["archive_tracks_nonfinal_only"] == expected["archives"]



def test_output_is_exclusive_after_prediction(monkeypatch, tmp_path):
    out = tmp_path / "gate.json"
    monkeypatch.setattr(GATE, "predict", lambda *_: {"verified": True})
    assert GATE.main(["--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == '{\n  "verified": true\n}\n'
    with pytest.raises(FileExistsError):
        GATE.main(["--out", str(out)])
