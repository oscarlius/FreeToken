import importlib.util
from pathlib import Path

path = Path(__file__).with_name("d05_r052_gap_replay.py")
spec = importlib.util.spec_from_file_location("d05", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_retained_uid_bound_geometry():
    text = "\n".join([
        "D0 seg: idx=16 reason=anchor_cap reqs=6:768/12672",
        "D0 seg: idx=17 reason=continuation reqs=6:663/0",
        "GDN bank: archived boundary 13376 -> host slot 22",
        "GDN bank: resuming req 7 from host slot 22",
        "D0 seg: idx=18 reason=other reqs=7:56/13376",
        "[D3-DONATE] cached_len=13433 L=None ext=1",
        "GDN bank: resuming req 8 from host slot 22",
        "D0 seg: idx=19 reason=anchor_cap reqs=8:64/13376",
        "D0 seg: idx=20 reason=continuation reqs=8:128/0",
        "[D3-DONATE] cached_len=13569 L=13504 ext=1",
    ])
    result = module.analyze(text)
    assert result["floor_64"] == 13504 and result["gap"] == 128
    assert result["archive"]["uid"] == 6
    assert result["target_short_prefill"]["uid"] == 7
    assert result["target_short_prefill"]["track_len"] is None
    assert result["followup_track"]["uid"] == 8
    assert result["followup_track"]["track_len"] == 13504
    assert result["source_control_flow"]["target_finish_is_page_aligned"] is False


def test_rejects_cross_uid_evidence_gap():
    text = "\n".join([
        "D0 seg: idx=16 reason=anchor_cap reqs=6:768/12672",
        "GDN bank: archived boundary 13376 -> host slot 22",
        "GDN bank: resuming req 7 from host slot 22",
        "D0 seg: idx=18 reason=other reqs=7:56/13376",
        "[D3-DONATE] cached_len=13433 L=None ext=1",
    ])
    try:
        module.analyze(text)
    except ValueError as error:
        assert "UID 8" in str(error)
    else:
        raise AssertionError("cross-UID evidence must not establish the 13504 trajectory")
