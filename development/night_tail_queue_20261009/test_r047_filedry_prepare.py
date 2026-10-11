import importlib.util
from pathlib import Path


MODULE = Path(__file__).with_name("r047_filedry_prepare.py")
spec = importlib.util.spec_from_file_location("night_r047_filedry", MODULE)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_inspect_keeps_v12_identity_and_six_arm_budget():
    value = module.inspect()
    assert value["candidate_commit"] == "0aa23431e5b800797543bdecbf35a01045131d7d"
    assert value["service_arms"] == 6
    assert value["serve_baseline"] == {
        "memory_ratio": "0.88", "kv_reserve_tokens": "98304", "max_seq_len_override": "98304",
    }
    assert value["filedry_effects"] == {
        "service_started": False, "requests_sent": False, "gpu_lock_taken": False,
        "batch_allocated": False, "formal_rid_directory_created": False,
    }


def test_linux_filedry_is_not_reimplemented(monkeypatch, tmp_path):
    monkeypatch.setattr(module.sys, "platform", "win32")
    try:
        module.file_dry(tmp_path / "executor", tmp_path / "review", tmp_path / "wt", tmp_path / "out", tmp_path / "dry")
    except RuntimeError as error:
        assert "existing Linux" in str(error)
    else:
        raise AssertionError("non-Linux FILEdry reached a subprocess")
