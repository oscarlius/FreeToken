import importlib.util
from pathlib import Path

path = Path(__file__).with_name("actual_bd57_r052_replay.py")
spec = importlib.util.spec_from_file_location("actual_bd57_r052_replay", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_actual_bd57_cachemanager_and_scheduler_retain_uid6_boundary_after_uid7_decode():
    result = module.replay()
    assert result["uid6_donor_cached_len"] == 13_376
    assert result["uid7_final_cached_len"] == 13_554
    assert result["floor_64"] == 13_504
    assert result["followup_cached_len"] == 13_376
    assert result["missing_to_floor"] == 128
    assert result["d09_entry_created"] is False
    assert result["decode_created_track"] is False
