import hashlib
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"


def load(name):
    spec = importlib.util.spec_from_file_location(name, RUNTIME / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


entry = load("r040g_d16_remaining_prepare_v1")


def test_actual_entry_binds_r040g_to_effb_measurement_worktree():
    assert entry.RID == "E2-R040g"
    assert entry.CANDIDATE == "effb9969706922ddad9e59b96377e46469ebe97f"
    assert entry.WT == entry.ROOT / "wt/e2base1-p1"
    base = entry.base_module()
    assert (base.RID, base.CANDIDATE, base.PARENT, base.WT) == (
        entry.RID, entry.CANDIDATE, entry.CANDIDATE, entry.WT)


def test_historical_commit_is_separate_from_new_candidate_in_all_retained_bindings():
    source = (RUNTIME / "r040g_d16_remaining_prepare_v1.py").read_text()
    assert entry.HISTORICAL_COMMIT == "0aa23431e5b800797543bdecbf35a01045131d7d"
    assert entry.HISTORICAL_COMMIT != entry.CANDIDATE
    assert source.count("!= HISTORICAL_COMMIT") == 3
    assert "not_candidate_commit': CANDIDATE" in source


def test_r040f_failed_harness_is_the_only_after_round_and_has_pinned_metadata():
    assert entry.R040F_CLOSED_METADATA["round.json"] == "93849b4f7ae64162c0b9fd6eeb4c05e9e62e6c6b58d406ef0f58f658e56f8ebc"
    assert entry.R040F_CLOSED_METADATA["MANIFEST.sha256"] == "606ff18cd4e2eec6e8cd3a1a1682bbe2d03ed2608d9af431cc81027742ef01a7"
    assert entry.R040F_TERMINAL_REVIEW_SHA256 == "01f98811080cfcd3ad07889d45ad710fddd6c113dbfb3b5d1d0e9da2d14e3bac"
    assert entry.execute.__kwdefaults__["after"] == "E2-R040f"
    assert "require_closed_round('E2-R040f', 'failed_harness')" in (RUNTIME / "r040g_d16_remaining_prepare_v1.py").read_text()


def test_renamed_entry_base_and_dryrun_are_manifest_bound_and_actual_collector_is_unchanged():
    manifest = {name: digest for digest, name in (line.split(maxsplit=1) for line in (RUNTIME / "MANIFEST.sha256").read_text().splitlines())}
    for name in ("r040g_d16_remaining_prepare_v1.py", "r040g_d16_supplement_prepare_base_v1.py",
                 "r040g_d16_remaining_dryrun_v1.py", "d16_native_process_collection_v2.py",
                 "d16_native_capture_shutdown_v3.py", "d16_exact_service_startup.py",
                 "r040a_private_port_owner_v3.py", "t17_d14_exact_ids.py"):
        assert manifest[name] == hashlib.sha256((RUNTIME / name).read_bytes()).hexdigest()
    for name in ("d16_native_process_collection_v2.py", "d16_native_capture_shutdown_v3.py",
                 "d16_exact_service_startup.py", "r040a_private_port_owner_v3.py", "t17_d14_exact_ids.py"):
        assert (RUNTIME / name).read_bytes() == (ROOT / "source" / name).read_bytes()


def test_actual_dryrun_uses_collector_source_review_not_a_synthetic_plan():
    source = (RUNTIME / "r040g_d16_remaining_dryrun_v1.py").read_text()
    assert "collector.collect_parking_processes" in source
    assert "collector.collect_cache_processes" in source
    assert "collector.collect_native_processes" in source
    assert "source_review_sha256" in source
    assert "service_started': False" in source

def test_section10_accepts_r055a_partial_cold_and_r055b_failed_metadata():
    class Protocol:
        def require_closed_round(self, rid, verdict):
            assert (rid, verdict) == ("E2-R055b-gate-D06", "failed_harness")
            return Path("/sealed/E2-R055b-gate-D06/round.json")
    def read(path):
        text = str(path).replace("\\", "/")
        if text.endswith("E2-R055a-gate-D06_v2.json"):
            return {"verdict": "failed_harness"}
        if "E2-R055a-gate-D06" in text:
            return {"verdict": "failed_harness", "supplemental_independent_raw_review":
                    {"partial_cold_verdict": "PASS", "sha256": "10161a2fe801414c3aa611487ead1d8a64a2e7baf1853d90ad4bca7fa7a08aa4"}}
        return {}
    def digest(path):
        text = str(path).replace("\\", "/")
        if text.endswith("E2-R055a-gate-D06_v2.json"): return "e785009fe2adecf1116c94b8416bb99093f6d31f14b98bb8df8a3ff3475bd127"
        if text.endswith("E2-R055a-gate-D06/round.json"): return "0c7467a274b93cfd54cdd7d3e70e4b43da6289f93c9a61519dbb3749d75e15b3"
        if text.endswith("E2-R055a-gate-D06/MANIFEST.sha256"): return "b38e9da3be0781958916fcc5714c8d750645cc10e1ebf4381fe72f5768064ab0"
        if text.endswith("E2-R055b-gate-D06/round.json"): return "13915b0d4657cf9e4ea1e40c64331c938d653f5b318ae16ebaac6f68b8503a4f"
        if text.endswith("E2-R055b-gate-D06/MANIFEST.sha256"): return "4961ee160759810533dd5702196d38a7760d4f556e6783e8e1f417e84a23432c"
        raise AssertionError(text)
    basis = entry.r055_section10_basis(Protocol(), read_json=read, digest=digest)
    assert basis["default_path"]["partial_cold_verdict"] == "PASS"
    assert basis["r055b_verdict"] == "failed_harness"
    assert basis["r055c_authorized"] is False
