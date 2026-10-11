from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import time

import pytest


DEVELOPMENT = Path(__file__).resolve().parents[1]
RUNNER = DEVELOPMENT / "d03_gpu_selfcheck_f506.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("d03_gpu_selfcheck_f506_under_test", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def manifest(module, path: Path, candidate: Path, *, commit: str | None = None):
    sources = {}
    for relative in module.TOKENIZER_SOURCES:
        source = candidate / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"# actual candidate source {relative}\n", encoding="utf-8")
        sources[str(relative)] = module.sha256(source)
    model = candidate / "model"
    model.mkdir()
    model_files = {}
    for name in module.TOKENIZER_FILES:
        file = model / name
        file.write_text(name, encoding="utf-8")
        model_files[name] = module.sha256(file)
    ids = [71, 72, 73]
    packed = b"".join(item.to_bytes(4, "little", signed=True) for item in ids)
    digest = hashlib.sha256(packed).hexdigest()
    data = {
        "schema": module.RAW_SCHEMA,
        "ids": ids,
        "candidate_commit": commit or module.CANDIDATE_COMMIT,
        "candidate_worktree": str(candidate),
        "trace_sha256": "trace",
        "messages_sha": "messages",
        "request_sha256": "request",
        "raw_ids_sha256": digest,
        "input_length": len(ids),
        "candidate_tokenizer": {
            "manager_module": "freetoken.tokenizer.tokenize.TokenizeManager",
            "construction": module.TOKENIZER_CONSTRUCTION,
            "source_sha256": sources,
            "model_files_sha256": model_files,
            "absent_model_files": [],
            "encoded_ids_sha256_int32le": digest,
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def test_pins_single_historical_protocol_and_retargets_f506():
    module = load_runner()
    assert hashlib.sha256((DEVELOPMENT / "d03_gpu_selfcheck.py").read_bytes()).hexdigest() == module.BASE_SHA256
    assert module._protocol["PARENT_COMMIT"] == "c30ae0d7003c3bbbf56867ce74da797332fa7ed5"
    assert module._protocol["CANDIDATE_COMMIT"] == "f5067bbe05da51d5f78185213435a8be095a684a"
    assert module._protocol["SELF_CHECK_OUTPUT"] == module.OUTPUT
    assert module.OUTPUT.name == "gpu_selfcheck_f5067bb"
    assert module.REQUIRED_BOUNDARY == 12672
    assert module.HISTORICAL_ENVELOPE == {"points": 814, "outside_points": 199, "max_finite_ratio": 5.489091417}


def test_f506_raw_manifest_requires_actual_candidate_tokenizer(tmp_path, monkeypatch):
    module = load_runner()
    candidate = tmp_path / "e2d03-continuation"
    monkeypatch.setattr(module, "CANDIDATE", candidate)
    monkeypatch.setattr(module, "MODEL_PATH", candidate / "model")
    path = tmp_path / "raw.json"
    data = manifest(module, path, candidate)
    assert module.raw_binding(path, "trace", {"messages_sha": "messages"}, "request", 2)[0] == [71, 72, 73]

    data["candidate_commit"] = module.PARENT_COMMIT
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="f506 candidate tokenizer"):
        module.raw_binding(path, "trace", {"messages_sha": "messages"}, "request", 2)

    data["candidate_commit"] = module.CANDIDATE_COMMIT
    data["candidate_tokenizer"]["encoded_ids_sha256_int32le"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="f506 candidate tokenizer"):
        module.raw_binding(path, "trace", {"messages_sha": "messages"}, "request", 2)


def test_environment_clears_development_flags_and_selects_gpu_zero(monkeypatch, tmp_path):
    module = load_runner()
    monkeypatch.setenv("FT_DEV_STATE_DUMP", "leak")
    monkeypatch.setenv("FT_D3_TEST", "leak")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "")
    runner = object.__new__(module.SelfCheck)
    env = runner.environment(tmp_path / "worktree", tmp_path / "arm")
    assert "FT_DEV_STATE_DUMP" not in env
    assert "FT_D3_TEST" not in env
    assert env["CUDA_VISIBLE_DEVICES"] == "0"
    assert env["PYTHONPATH"] == str(tmp_path / "worktree" / "python")


def test_required_assets_and_optional_absence_are_bound(tmp_path, monkeypatch):
    module = load_runner()
    candidate = tmp_path / 'candidate'
    monkeypatch.setattr(module, 'CANDIDATE', candidate)
    monkeypatch.setattr(module, 'MODEL_PATH', candidate / 'model')
    path = tmp_path / 'raw.json'
    data = manifest(module, path, candidate)
    optional = candidate / 'model/special_tokens_map.json'
    optional.unlink()
    data['candidate_tokenizer']['model_files_sha256'].pop(optional.name)
    data['candidate_tokenizer']['absent_model_files'] = [optional.name]
    path.write_text(json.dumps(data), encoding='utf-8')
    assert module.raw_binding(path, 'trace', {'messages_sha': 'messages'}, 'request', 2)[0] == [71, 72, 73]
    (candidate / 'model/chat_template.jinja').unlink()
    with pytest.raises(ValueError, match='required tokenizer asset missing'):
        module.raw_binding(path, 'trace', {'messages_sha': 'messages'}, 'request', 2)


def test_isolated_bootstrap_uses_candidate_paths_without_site_initialization(tmp_path):
    module = load_runner()
    probe = module.SelfCheck._bootstrap(tmp_path / "candidate", serve=False)
    serve = module.SelfCheck._bootstrap(tmp_path / "candidate", serve=True)
    assert "sys.path[:0]=[str(root/'python'),str(root)]" in probe
    assert "assert freetoken.__file__ == str(root/'python/freetoken/__init__.py')" in probe
    assert "TokenizeManager" in probe and "ChatCompletionRequest" in probe
    assert "from freetoken.cli import main" in serve


def test_owned_group_members_rejects_wrong_session_and_ignores_zombies(monkeypatch, tmp_path):
    module = load_runner()
    proc = tmp_path / "proc"
    proc.mkdir()
    for pid, stat in {
        "101": "101 (service) S 0 100 100", "102": "102 (zombie) Z 0 100 100",
    }.items():
        (proc / pid).mkdir()
        (proc / pid / "stat").write_text(stat, encoding="utf-8")
    monkeypatch.setattr(module.os, "killpg", lambda *_: None, raising=False)
    original_iterdir = module.Path.iterdir
    monkeypatch.setattr(module.Path, "iterdir", lambda self: original_iterdir(proc) if self == Path("/proc") else original_iterdir(self))
    assert module.owned_group_members(100) == {101}
    (proc / "101" / "stat").write_text("101 (wrong) S 0 100 999", encoding="utf-8")
    with pytest.raises(RuntimeError, match="reserved session"):
        module.owned_group_members(100)


def test_stop_waits_for_the_owned_group_not_only_the_leader(monkeypatch):
    module = load_runner()
    observations = iter(({4100, 4101}, set(), set(), set()))
    monkeypatch.setattr(module, "owned_group_members", lambda pgid: next(observations))
    monkeypatch.setattr(module, 'process_birth', lambda pid: 'owned-birth')
    signals = []
    monkeypatch.setattr(module.os, "killpg", lambda pgid, signal: signals.append((pgid, signal)), raising=False)
    monkeypatch.setattr(module.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setitem(module._protocol, "output", lambda argv: "0")

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def connect_ex(self, address):
            return 1

    class SocketModule:
        socket = Socket

    class Proc:
        pid = 4100

        def wait(self, timeout):
            return 0

    monkeypatch.setitem(module._protocol, "socket", SocketModule())
    runner = object.__new__(module.SelfCheck)
    runner.proc = Proc()
    runner._service_birth = 'owned-birth'
    runner.stop()
    assert signals == [(4100, module.signal.SIGINT)]
    assert runner.proc is None


def test_failed_cleanup_retains_lock_ownership(monkeypatch):
    module = load_runner()
    monkeypatch.setattr(module, "owned_group_members", lambda pgid: {4100, 4101})
    monkeypatch.setattr(module, 'process_birth', lambda pid: 'owned-birth')
    monkeypatch.setattr(module.os, "killpg", lambda *_: None, raising=False)
    monkeypatch.setattr(module, "STOP_STEPS", ((module.signal.SIGINT, 0),))
    released = []
    monkeypatch.setattr(module.BaseSelfCheck, "lock_release", lambda self: released.append(True))

    class Proc:
        pid = 4100

        def wait(self, timeout):
            return 0

    runner = object.__new__(module.SelfCheck)
    runner.proc = Proc()
    runner._service_birth = 'owned-birth'
    with pytest.raises(RuntimeError, match="did not stop"):
        runner.stop()
    runner.lock_release()
    assert runner.proc is not None
    assert runner._cleanup_failed is True
    assert released == []


def test_reused_foreign_session_is_never_signalled(monkeypatch):
    module = load_runner()
    monkeypatch.setattr(module, 'owned_group_members', lambda pid: {4100})
    monkeypatch.setattr(module, 'process_birth', lambda pid: 'foreign-birth')
    monkeypatch.setattr(module.os, 'killpg', lambda *_: pytest.fail('foreign group was signalled'), raising=False)
    runner = object.__new__(module.SelfCheck)
    runner.proc = type('Proc', (), {'pid': 4100})()
    runner._service_birth = 'owned-birth'
    with pytest.raises(RuntimeError, match='birth changed'):
        runner.stop()
    assert runner.proc is not None and runner._cleanup_failed is True


def test_default_path_refuses_server_start_and_run_requires_fresh_manifest():
    module = load_runner()
    with pytest.raises(SystemExit):
        module.main([])
    with pytest.raises(SystemExit):
        module.main(["--run"])


def test_builtin_cpu_selftest_has_no_run_or_gpu_dependency(capsys):
    module = load_runner()
    module.self_test()
    assert "SELFTEST PASS" in capsys.readouterr().out


@pytest.mark.skipif(os.name != "posix", reason="Linux process group lifecycle")
def test_stop_kills_real_child_after_leader_exits(monkeypatch, tmp_path):
    module = load_runner()
    marker = tmp_path / "child.pid"
    child = (
        "import os,signal,time,sys; signal.signal(signal.SIGINT,signal.SIG_IGN); "
        "signal.signal(signal.SIGTERM,signal.SIG_IGN); open(sys.argv[1],'w').write(str(os.getpid())); time.sleep(30)"
    )
    leader = (
        "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[1]]); time.sleep(30)"
    )
    process = subprocess.Popen([sys.executable, "-c", leader, str(marker), child], start_new_session=True)
    monkeypatch.setattr(module, "STOP_STEPS", ((module.signal.SIGINT, 0.1), (module.signal.SIGTERM, 0.1),
                                                (module.signal.SIGKILL, 3)))
    monkeypatch.setitem(module._protocol, "output", lambda argv: "0")

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def connect_ex(self, address):
            return 1

    class SocketModule:
        socket = Socket

    monkeypatch.setitem(module._protocol, "socket", SocketModule())
    runner = object.__new__(module.SelfCheck)
    runner.proc = process
    runner._service_birth = module.process_birth(process.pid)
    try:
        deadline = time.monotonic() + 5
        while not marker.is_file():
            assert time.monotonic() < deadline, "child did not initialize"
            time.sleep(0.01)
        runner.stop()
        assert process.poll() is not None
        assert not module.owned_group_members(process.pid)
    finally:
        try:
            os.killpg(process.pid, module.signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
