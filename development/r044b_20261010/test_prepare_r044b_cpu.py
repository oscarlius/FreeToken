import importlib.util
from pathlib import Path

SOURCE = Path(__file__).with_name("prepare_r044b_cpu.py")
spec = importlib.util.spec_from_file_location("r044b", SOURCE)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)


def test_prefill_alias_maps_to_serverargs_field():
    parsed = mod.parse_server_args("Parsed ServerArgs(max_extend_tokens=4096, server_port=30000)")
    assert parsed["max_extend_tokens"] == "4096"
    assert parsed["max_prefill_length"] == "4096"


def test_packet_keeps_capture_caps_and_old_evidence(tmp_path):
    retry2 = tmp_path / "retry2.log"; r047 = tmp_path / "r047.log"
    retry2.write_text("ServerArgs(max_extend_tokens=4096)\n")
    r047.write_text("ServerArgs(max_extend_tokens=4096)\n")
    packet = mod.packet(retry2, r047)
    assert all(x["alias_resolved"] for x in packet["historical_replay"].values())
    assert packet["capture_contract"]["physical_capture_cap"] == 5824
    assert packet["capture_contract"]["sampler_rows_cap"] == 4800
    assert packet["capture_contract"]["capture_bytes_cap"] == 8 * 1024**3
