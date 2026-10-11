from __future__ import annotations
import importlib.util
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parents[1]
PARSER = HERE / "r044b_retry2_parser.py"
RAW_PARSER = Path("/data2/FreeToken/development/r044_capture_path_retry2_20261010/d04_original/serve_args_diff.py")
RAW_LOG = Path("/data2/_shared/runs/ft_rounds/E2-R044b-20261010/ordinary/B1/serve.log")
OWNED = Path("/data2/_shared/runs/ft_rounds/E2-R044b-20261010/ordinary/B1/owned_process.json")
RAW_SHA256 = "49b60931e3fec7a3fe782873a3ac0e3558a155523a5a499fd56ba657445ff9e7"

def module():
    spec = importlib.util.spec_from_file_location("r044b_retry2_parser", PARSER)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

def test_alias_normalization_requires_extend_and_rejects_conflict():
    value = module()
    raw = {"model_path":"x", "server_port":"1", "prefill_layer_major":"False", "max_extend_tokens":"4096", "mamba_host_slots":"0", "enable_cache_report":"True", "special_token_ckpt":"True", "_unique_suffix":"'.pid=7'"}
    normalized = value.normalize_alias(raw)
    assert "max_prefill_length" not in raw
    assert normalized["max_prefill_length"] == normalized["max_extend_tokens"] == "4096"
    with pytest.raises(ValueError, match="required raw ServerArgs"):
        value.normalize_alias({key: item for key, item in raw.items() if key != "max_extend_tokens"})
    with pytest.raises(ValueError, match="alias differs"):
        value.normalize_alias({**raw, "max_prefill_length":"8192"})

@pytest.mark.skipif(not (RAW_PARSER.is_file() and RAW_LOG.is_file() and OWNED.is_file()), reason="requires retained batch157 raw files on target")
def test_batch157_b1_raw_serverargs_alias_regression():
    value = module()
    assert value.sha256(RAW_LOG) == RAW_SHA256
    identity = value.serve_identity(RAW_LOG, OWNED, False, RAW_PARSER)
    assert "max_prefill_length" not in identity["raw_parsed"]
    assert identity["raw_parsed"]["max_extend_tokens"] == "4096"
    assert identity["normalized"]["max_prefill_length"] == "4096"
    assert identity["normalized"]["server_port"] == "<dynamic-port>"
    assert identity["normalized"]["_unique_suffix"] == "'.pid=1798591'"
    assert identity["owned_process"]["pid"] == 1798591





