"""CPU boundary tests; fixture metadata does not establish model acceptance."""
import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import urllib.request

import pytest


ROOT = Path(__file__).parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_model_or_network(monkeypatch):
    def denied(*_args, **_kwargs):
        pytest.fail("CPU collector review attempted a process or network connection")

    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    for method in ("connect", "connect_ex"):
        monkeypatch.setattr(socket.socket, method, denied)
    monkeypatch.setattr(urllib.request, "urlopen", denied)
    monkeypatch.setattr(subprocess, "Popen", denied)


@pytest.fixture
def adapter():
    return load(ROOT / "r040a_d16_process_collection_v4.py", "r040a_v4_review")


def owner(tmp_path, *, dry, first_args=True, fail_at=None):
    class FileOwner:
        def environment(self, worktree, arm=None, d0=False):
            return {"PYTHONPATH": "cpu-fixture", "CUDA_VISIBLE_DEVICES": ""}

        def startup_wrapper(self):
            return "original-wrapper"

        def service(self, name, operation, **kwargs):
            arm = self.directory / name
            arm.mkdir()
            environment = self.environment(self.worktree, arm, True)
            self.calls.append((name, kwargs, environment, self.startup_wrapper()))
            self.first_args = {"during_arm": name}
            if name == self.fail_at:
                raise RuntimeError("CPU arm sentinel")
            return operation(arm)

    result = FileOwner()
    result.directory = tmp_path / "output"
    result.directory.mkdir()
    result.worktree = tmp_path / "worktree"
    result.options = SimpleNamespace(rid="E2-R040a-CPU-BOUNDARY")
    result.port = 51449
    result.base_url = "http://127.0.0.1:51449"
    result._r040a_file_dry_run = dry
    result.calls = []
    result.fail_at = fail_at
    if first_args:
        result.first_args = {"original": "suite"}
    return result


def frozen_cpu_module(monkeypatch, tmp_path):
    """Load the actual v2 functions, stubbing only imports and source attestation."""
    workloads = ModuleType("d16_service_workloads")
    retained = ModuleType("t17_d14_runner")
    shutdown = ModuleType("d16_native_capture_shutdown_v3")

    def no_measurement(*_args, **_kwargs):
        pytest.fail("file dry-run entered measurement collection")

    workloads.collect = no_measurement
    retained.exact_id_request = no_measurement
    shutdown.read_sealed_service_delivery = no_measurement
    for module in (workloads, retained, shutdown):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    frozen = load(ROOT / "d16_native_process_collection_v2.py", "r040a_v2_cpu_reference")
    wrapper = tmp_path / "shutdown_startup.py"
    wrapper.write_text("# CPU source archive fixture\n")
    wrapper.chmod(0o444)
    review = tmp_path / "source_review.json"
    review.write_text('{"source": "CPU attestation fixture"}\n')
    report = tmp_path / "source_cpu_report.json"
    report.write_text('{"scope": "CPU fixture only"}\n')
    proof = {
        "source_files": {
            "startup_wrapper": {
                "path": str(wrapper),
                "sha256": hashlib.sha256(wrapper.read_bytes()).hexdigest(),
            }
        },
        "review": str(review),
        "cpu_report": str(report),
    }
    attestations = []

    def verify(actual_wrapper, actual_review, digest):
        assert actual_wrapper == wrapper
        assert actual_review == review and digest == "CPU-review-pin"
        attestations.append((actual_wrapper, actual_review, digest))
        return proof

    monkeypatch.setattr(frozen, "verify_source_review", verify)
    return frozen, wrapper, review, report, proof, attestations


def common(wrapper, review):
    return {"wrapper": wrapper, "source_review": review,
            "source_review_sha256": "CPU-review-pin"}


@pytest.mark.parametrize("name", ["native", "parking", "cache"])
def test_formal_dispatch_injects_exact_owner_endpoint(adapter, monkeypatch, tmp_path, name):
    current = owner(tmp_path, dry=False)
    calls = []

    def formal(*args, **kwargs):
        calls.append((args, kwargs))
        return "formal-sentinel"

    frozen = SimpleNamespace(**{"collect_" + name + "_processes": formal})
    monkeypatch.setattr(adapter, "_frozen", lambda: frozen)
    collect = getattr(adapter, "collect_" + name + "_processes")
    options = {"slots": 2} if name == "native" else {}
    inputs = [[1], [2]] if name == "native" else [1]
    assert collect(current, inputs, wrapper="source", **options) == "formal-sentinel"
    assert calls[0][0] == (current, inputs)
    assert calls[0][1]["base_url"] == current.base_url
    assert calls[0][1]["wrapper"] == "source"


@pytest.mark.parametrize("name", ["native", "parking", "cache"])
@pytest.mark.parametrize("foreign", ["http://127.0.0.1:8095", "http://127.0.0.1:51450"])
@pytest.mark.parametrize("location", ["supplied", "owner"])
def test_foreign_endpoint_rejected_before_module_load(
        adapter, monkeypatch, tmp_path, name, foreign, location):
    current = owner(tmp_path, dry=False)
    if location == "owner":
        current.base_url = foreign
    monkeypatch.setattr(adapter, "_frozen", lambda: pytest.fail("loaded foreign dispatch"))
    options = {"slots": 2} if name == "native" else {}
    with pytest.raises(ValueError, match="endpoint differs"):
        getattr(adapter, "collect_" + name + "_processes")(
            current, [[1], [2]] if name == "native" else [1],
            wrapper="source", base_url=foreign if location == "supplied" else None, **options)


@pytest.mark.parametrize("dry", [False, True])
@pytest.mark.parametrize("override", [{"fixture_only": True}, {"request_factory": object()}])
def test_native_refuses_fixture_or_client_override(adapter, monkeypatch, tmp_path, dry, override):
    current = owner(tmp_path, dry=dry)
    frozen = SimpleNamespace(collect_native_processes=lambda *_a, **_k:
                             pytest.fail("fixture/client reached formal collector"))
    monkeypatch.setattr(adapter, "_frozen", lambda: frozen)
    with pytest.raises(ValueError, match="fixture|client"):
        adapter.collect_native_processes(current, [[1], [2]], slots=2,
                                         wrapper="source", file_dry_run=dry, **override)


@pytest.mark.parametrize("name", ["native", "parking", "cache"])
@pytest.mark.parametrize("owner_dry,dry", [(False, True), (True, False), (False, 1)])
def test_dry_mode_mismatch_is_rejected_before_import(
        adapter, monkeypatch, tmp_path, name, owner_dry, dry):
    current = owner(tmp_path, dry=owner_dry)
    monkeypatch.setattr(adapter, "_frozen", lambda: pytest.fail("loaded mismatched dry mode"))
    options = {"slots": 2} if name == "native" else {}
    with pytest.raises(ValueError, match="dry mode differs"):
        getattr(adapter, "collect_" + name + "_processes")(
            current, [[1], [2]] if name == "native" else [1],
            wrapper="source", file_dry_run=dry, **options)


@pytest.mark.parametrize("slots,interleave", [(2, False), (4, False), (2, True)])
def test_native_dry_reuses_original_validation_and_source_archive(
        adapter, monkeypatch, tmp_path, slots, interleave):
    current = owner(tmp_path, dry=True)
    frozen, wrapper, review, report, _, attestations = frozen_cpu_module(monkeypatch, tmp_path)
    original_collect, original_configured = frozen.collect_native_processes, frozen.configured
    original_arms = frozen._collect_arms
    monkeypatch.setattr(adapter, "_frozen", lambda: frozen)
    inputs = [[index + 1] for index in range(slots)]
    if interleave:
        inputs[1] = [2] * 4097
    result = adapter.collect_native_processes(current, inputs, slots=slots,
        file_dry_run=True, interleave=interleave, **common(wrapper, review))
    assert frozen.collect_native_processes is original_collect
    assert frozen.configured is original_configured and frozen._collect_arms is not original_arms
    assert len(attestations) == 1
    folder = current.directory / "dev_D16" / ("native_interleave" if interleave else f"native_slots_{slots}")
    assert (folder / "execution_sources/startup_wrapper.py").read_bytes() == wrapper.read_bytes()
    assert (folder / "execution_sources/independent_review.json").read_bytes() == review.read_bytes()
    assert (folder / "execution_sources/cpu_report.json").read_bytes() == report.read_bytes()
    expected_names = [f"dev_D16_{slots}_batch_{rep}_None" for rep in (0, 1)]
    expected_names += [f"dev_D16_{slots}_single_{rep}_{slot}"
                       for rep in (0, 1) for slot in range(slots)]
    assert [call[0] for call in current.calls] == expected_names
    for index, (_, options, environment, actual_wrapper) in enumerate(current.calls):
        assert options == {"health_only": True, "max_running_requests": 4}
        assert actual_wrapper == wrapper
        expected = json.loads(Path(environment["FT_D16_SERVICE_CAPTURE_EXPECTED_JSON"]).read_text())
        assert len(expected) == 128 * (slots if index < 2 else 1)
    assert result["not_measurement"] and not result["service_started"] and not result["requests_sent"]
    assert not (folder / "collection.json").exists() and not (folder / "evidence.json").exists()
    assert current.first_args == {"original": "suite"}


@pytest.mark.parametrize("inputs,slots,interleave", [
    ([[1]], 2, False), ([[True], [2]], 2, False), ([[1], [2]], 2, True),
])
def test_native_dry_invalid_input_fails_in_original_preamble(
        adapter, monkeypatch, tmp_path, inputs, slots, interleave):
    current = owner(tmp_path, dry=True)
    frozen, wrapper, review, _, _, attestations = frozen_cpu_module(monkeypatch, tmp_path)
    monkeypatch.setattr(adapter, "_frozen", lambda: frozen)
    with pytest.raises(ValueError, match="D16"):
        adapter.collect_native_processes(current, inputs, slots=slots,
            file_dry_run=True, interleave=interleave, **common(wrapper, review))
    assert not attestations and not current.calls
    assert not (current.directory / "dev_D16").exists()


def test_native_source_archive_rechecks_bytes_before_dry_service(adapter, monkeypatch, tmp_path):
    current = owner(tmp_path, dry=True)
    frozen, wrapper, review, _, proof, _ = frozen_cpu_module(monkeypatch, tmp_path)
    proof["source_files"]["startup_wrapper"]["sha256"] = "0" * 64
    monkeypatch.setattr(adapter, "_frozen", lambda: frozen)
    with pytest.raises(ValueError, match="changed while archiving"):
        adapter.collect_native_processes(current, [[1], [2]], slots=2,
                                         file_dry_run=True, **common(wrapper, review))
    assert not current.calls and current.first_args == {"original": "suite"}


@pytest.mark.parametrize("kind", ["parking", "cache"])
@pytest.mark.parametrize("first_args", [False, True])
@pytest.mark.parametrize("fail", [False, True])
def test_state_dry_preserves_order_configuration_and_restores_on_failure(
        adapter, monkeypatch, tmp_path, kind, first_args, fail):
    names = ["control_0", "control_1", "restore_0", "restore_1"] if kind == "parking" else [
        "cold_0", "cold_1", "warm_0", "warm_1"]
    current = owner(tmp_path, dry=True, first_args=first_args,
                    fail_at=names[2] if fail else None)
    directory = current.directory
    environment_function = current.environment.__func__
    wrapper_function = current.startup_wrapper.__func__
    frozen, wrapper, review, _, _, attestations = frozen_cpu_module(monkeypatch, tmp_path)
    monkeypatch.setattr(adapter, "_frozen", lambda: frozen)
    collect = getattr(adapter, "collect_" + kind + "_processes")
    if fail:
        with pytest.raises(RuntimeError, match="CPU arm sentinel"):
            collect(current, [11, 12], file_dry_run=True, **common(wrapper, review))
    else:
        result = collect(current, [11, 12], file_dry_run=True, **common(wrapper, review))
        assert len(result["arms"]) == 4 and result["not_measurement"]
    assert len(attestations) == 1
    assert [call[0] for call in current.calls] == (names[:3] if fail else names)
    for index, (_, options, environment, actual_wrapper) in enumerate(current.calls):
        assert options == {"health_only": True, "max_running_requests": 4,
                           "mamba_host_slots": 5 if kind == "parking" else 0}
        assert actual_wrapper == wrapper
        if kind == "parking":
            assert environment["FT_DEV_PAUSE_ENDPOINT"] == "1"
            assert environment["FT_D16_PARK_RESTORE"] == ("0" if index < 2 else "1")
        else:
            assert environment["FT_D16_CACHE_INIT"] == ("cold" if index < 2 else "warm")
        assert len(json.loads(Path(environment["FT_D16_SERVICE_CAPTURE_EXPECTED_JSON"]).read_text())) == 128
    assert current.directory == directory
    assert current.environment.__func__ is environment_function
    assert current.startup_wrapper.__func__ is wrapper_function
    assert "environment" not in current.__dict__ and "startup_wrapper" not in current.__dict__
    assert hasattr(current, "first_args") is first_args
    if first_args:
        assert current.first_args == {"original": "suite"}
    assert not (directory / "dev_D16" / ("native_" + kind) / "collection.json").exists()


def test_native_service_failure_restores_original_owner(adapter, monkeypatch, tmp_path):
    current = owner(tmp_path, dry=True, fail_at="dev_D16_2_single_0_0")
    directory = current.directory
    frozen, wrapper, review, _, _, _ = frozen_cpu_module(monkeypatch, tmp_path)
    monkeypatch.setattr(adapter, "_frozen", lambda: frozen)
    with pytest.raises(RuntimeError, match="CPU arm sentinel"):
        adapter.collect_native_processes(current, [[1], [2]], slots=2,
                                         file_dry_run=True, **common(wrapper, review))
    assert current.directory == directory and current.first_args == {"original": "suite"}
    assert "environment" not in current.__dict__ and "startup_wrapper" not in current.__dict__
