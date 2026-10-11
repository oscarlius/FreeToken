import importlib.util
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("retry2_hash_domain_packet", HERE / "retry2_hash_domain_packet.py")
packet = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(packet)

HISTORICAL = Path("/data2/FreeToken/runs/dev_R067/E2-R067d-d20-short-tail-retry1/services/hot_p8192/state_dump")
BATCH161 = Path("/data2/FreeToken/runs/dev_R067/E2-R067e-20261010_batch161_2192859_170151379/services/hot_p8192/state_dump")


def test_actual_hot_dump_plain_domain_differs_from_engine_and_engine_is_stable():
    if not HISTORICAL.exists() or not BATCH161.exists():
        pytest.skip("requires archived remote hot dumps")
    assert packet.plain_hash(HISTORICAL) == packet.plain_hash(BATCH161)
    assert packet.engine_canonical_hash(HISTORICAL) == packet.engine_canonical_hash(BATCH161)
    assert packet.plain_hash(HISTORICAL) != packet.engine_canonical_hash(HISTORICAL)
    assert packet.plain_hash(HISTORICAL) == "b18f8621f3e4b6c8740bfc3aa8374fdefe7eb4f3dd4d0e95c5f2ca1791f7aed5"
    assert packet.engine_canonical_hash(HISTORICAL) == "2116edf91af9daa8e4a889202044b5377afa9d6d9ddf772424f44ac8bc691390"


def test_new_packet_uses_engine_domain_for_every_cold_arm():
    if not HISTORICAL.exists():
        pytest.skip("requires archived remote hot dumps")
    result = packet.build_unapproved_packet()
    assert result["budget"] == {"services": 10, "generation_calls": 14, "harness_attempts_remaining": 1}
    for service in result["services"]:
        if service["kind"] == "cold":
            boundary = str(int(service["name"].split("_p", 1)[1].split("_", 1)[0]))
            assert service["env"]["FT_DEV_COLD_DONOR_EXPECTED_STATE_SHA256"] == result["donor"][boundary]["engine_canonical_hash"]
            assert service["env"]["FT_DEV_COLD_DONOR_HASH_DOMAIN"].startswith("engine-v1/")


@pytest.mark.parametrize("name", packet.STATE_NAMES)
def test_every_required_component_changes_engine_hash(tmp_path, name):
    torch = pytest.importorskip("torch")
    base = {
        "conv_states": torch.zeros((1, 2), dtype=torch.bfloat16),
        "recurrent_states": torch.zeros((1, 2), dtype=torch.float32),
        "ple_conv": torch.zeros((1, 2), dtype=torch.bfloat16),
        "ple_ngram_ctx": torch.zeros((1, 2), dtype=torch.int32),
    }
    for key, value in base.items():
        torch.save(value, tmp_path / f"donate_0001_dev_{key}.pt")
    before = packet.engine_canonical_hash(tmp_path)
    changed = base[name].clone(); changed.view(torch.uint8).flatten()[0] = 1
    torch.save(changed, tmp_path / f"donate_0001_dev_{name}.pt")
    assert packet.engine_canonical_hash(tmp_path) != before


