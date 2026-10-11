import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_authorization_is_explicitly_policy_only_and_preserves_order():
    value = json.loads((HERE / "night_tail_queue_authorization.json").read_text())
    assert value["candidate_commit"] == "0aa23431e5b800797543bdecbf35a01045131d7d"
    assert value["independent_queue"]["E2-R047"]["policy_override_only"] == [
        "E2-R040g measured", "E2-R045 measured", "E2-R044 measured"]
    assert value["independent_queue"]["E2-R052a"]["after"] == "E2-R047 terminal (measured or not_met)"
    assert value["independent_queue"]["E2-R044"]["after"] == "E2-R052a terminal (measured or not_met)"
    assert "measured" not in value["factual_predecessors"]["E2-R040g"]["facts"]["verdict"]
    assert "measured" not in value["factual_predecessors"]["E2-R045_latest"]["facts"]["conclusion"]


def test_frozen_sources_are_not_modified_by_task_owned_clones():
    sources = [
        HERE.parent / "r047_runtime_v12" / "r047_prepare_v11.py",
        HERE.parent / "r052_runtime_v8" / "r052_t11_followup_prepare.py",
        HERE.parent / "r044_runtime_v7" / "r044_prepare_v6.py",
    ]
    before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    for name in ("r047_authorized_v13.py", "r052a_authorized_v9.py", "r044_authorized_v8.py"):
        compile((HERE / name).read_text(), name, "exec")
    after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    assert after == before
