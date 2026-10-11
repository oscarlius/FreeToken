import importlib.util
import json
from pathlib import Path
import pytest

PATH = Path(__file__).parents[1] / "r041_closed_fixture.py"
spec = importlib.util.spec_from_file_location("fixture", PATH)
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)


def test_fixture_marker_rejects_missing_or_non_fixture_admission(tmp_path):
    with pytest.raises(fixture.FixtureError, match="marker"):
        fixture.assert_fixture_only(tmp_path)
    marker = tmp_path / "fixture_only.json"
    marker.write_text(json.dumps({"schema": fixture.MARKER_SCHEMA, "fixture_only": True,
                                  "model_admitted": True, "admitted": False,
                                  "gpu_started": False, "requests_sent": False}))
    with pytest.raises(fixture.FixtureError, match="never claim"):
        fixture.assert_fixture_only(tmp_path)


def test_fixture_marker_requires_exact_frozen_inputs(tmp_path):
    (tmp_path / "realinput_28.json").write_text("synthetic")
    (tmp_path / "fixture_only.json").write_text(json.dumps({
        "schema": fixture.MARKER_SCHEMA, "fixture_only": True,
        "model_admitted": False, "admitted": False, "gpu_started": False,
        "requests_sent": False, "fixture_input": "realinput_28.json",
    }))
    with pytest.raises(fixture.FixtureError, match="exact R035"):
        fixture.assert_fixture_only(tmp_path)


def test_copy_refuses_existing_destination_without_contacting_remote(tmp_path):
    destination = tmp_path / "already"; destination.mkdir()
    with pytest.raises(fixture.FixtureError, match="must not already exist"):
        fixture.copy_r035_inputs(destination)


def test_first_case_raw_fixture_reaches_unmocked_audit_case(tmp_path):
    torch = pytest.importorskip("torch")
    import shutil
    review_path = Path(__file__).parents[1] / "t17_continuation_review.py"
    spec = importlib.util.spec_from_file_location("review_fixture", review_path)
    review = importlib.util.module_from_spec(spec); spec.loader.exec_module(review)
    source = tmp_path / "sources"; suite = source / "equiv_suite"; suite.mkdir(parents=True)
    development = Path(__file__).parents[1]
    for name in ("__init__.py", "raw.py", "schedule.py", "gate.py"):
        shutil.copyfile(development / "e2d16-tools" / "scripts" / "equiv_suite" / name, suite / name)
    for name in ("t17_d14_artifacts.py", "t17_operator_observe.py"):
        shutil.copyfile(development / name, source / name)
    length, tail = 8192, 65
    donor = list(range(length + 1)); query = donor + list(range(tail - 1))
    import struct, hashlib
    token_sha = lambda values: hashlib.sha256(struct.pack("<%di" % len(values), *values)).hexdigest()
    case = {"name": "prefix-8192-tail-65", "length": length, "tail": tail, "trace_index": 0,
            "donor": donor, "query": query, "context": query[length-2:length],
            "input_ids_sha256": token_sha(query)}
    built = fixture.build_first_case(tmp_path / "round", case, source_root=source)
    readers = review.load_readers(tmp_path / "round")
    value = review.audit_case(tmp_path / "round", case, built["saved"], readers)
    assert value["case"] == case["name"]
    assert value["verdict"] == "measurements_pass_pending_independent_review"
