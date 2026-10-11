"""Actual v8 HTTP capture and owned Linux process cleanup; synthetic SSE only."""
from contextlib import contextmanager
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.request import urlopen

import pytest

if not os.environ.get("FT_D12_NATIVE_SOURCE"):
    pytest.skip("requires pinned Linux source packages", allow_module_level=True)
pytest.importorskip("openai")

from ordinary_evidence import collect_requests, observe_live_worker, observe_owned_listener, read_wire_response, record_stopped_worker
from owned_lifecycle import load_owned_lifecycle

SOURCE = Path(os.environ["FT_D12_NATIVE_SOURCE"])
BUNDLE = Path(os.environ["FT_D12_TEST_INPUT_BUNDLE"])
BUNDLE_SHA = "282ec437c54b0ba341aac5a0bc31e996ca0d53343d0f48d5b8fa488523ca00e2"
WIRE = Path(os.environ["FT_D12_WIRE_SOURCE"])
GATE = Path(os.environ["FT_D12_GATE_ROOT"])
EXECUTION = "cpu-ordinary-protocol-only"
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CLIENT = load("d12_cpu_ordinary_reader", os.environ["FT_D12_ORDINARY_CLIENT"])
LIFECYCLE = load_owned_lifecycle(load("d12_cpu_owned_gate", GATE / "d07_g3g4_prepare.py"))


SERVER = r'''
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
from http.server import BaseHTTPRequestHandler,HTTPServer
root,bundle=map(Path,sys.argv[1:3]);execution=sys.argv[3]
worker=subprocess.Popen([sys.executable,'-c','import time; time.sleep(90)'])
fields=Path('/proc',str(worker.pid),'stat').read_text().rpartition(') ')[2].split()
identity={'pid':worker.pid,'start_ticks':int(fields[19]),'execution_id':execution+':tp0'}
index=json.loads((bundle/'binding.json').read_bytes())['selected_history']; count=0
capture=root/'dev_D16/capture/admissions';capture.mkdir(parents=True)
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  (root/'get-handler-pid.txt').write_text(str(os.getpid()))
  self.send_response(200);self.send_header('Content-Length','0');self.end_headers()
 def do_POST(self):
  global count
  assert self.path=='/v1/chat/completions'
  body=self.rfile.read(int(self.headers['Content-Length']));payload=json.loads(body)
  uid=count;count+=1;expected=index[uid]
  assert payload==json.loads((bundle/expected['payload_path']).read_bytes())
  (root/f'received-{uid}.json').write_bytes(body)
  # Explicit synthetic admission. Process identities are real /proc evidence;
  # this does not claim that a model worker tokenized or sampled anything.
  row={'schema':'ft_equiv_service_admission/v1','uid':uid,'process_identity':identity}
  (capture/f'admission-{uid+1:06d}.json').write_text(json.dumps(row))
  base={'id':f'chatcmpl-{uid}','object':'chat.completion.chunk','created':1,'model':payload['model']}
  chunks=[{**base,'choices':[{'index':0,'delta':delta,'finish_reason':finish}]} for delta,finish in
          [({'role':'assistant','content':''},None),({'content':'CPU protocol fixture'},None),({},'stop')]]
  n=expected['input_tokens'];chunks.append({**base,'choices':[],'usage':{'prompt_tokens':n,'completion_tokens':1,'total_tokens':n+1}})
  raw=b''.join(b'data: '+json.dumps(c).encode()+b'\n\n' for c in chunks)+b'data: [DONE]\n\n'
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(raw)));self.end_headers()
  self.wfile.write(raw);self.wfile.flush()
http=HTTPServer(('127.0.0.1',0),Handler)
if len(sys.argv)>4:
 child=os.fork()
 if child==0:
  os.setsid()
  fields=Path('/proc/self/stat').read_text().rpartition(') ')[2].split()
  escaped={'pid':os.getpid(),'start_ticks':int(fields[19]),'pgid':os.getpgrp(),'session':os.getsid(0)}
  (root/'escaped.json').write_text(json.dumps(escaped))
  http.serve_forever()
 while not (root/'escaped.json').exists():time.sleep(.01)
(root/'ready.json').write_text(json.dumps({'port':http.server_port,'worker':identity}))
if len(sys.argv)>4:
 while True:time.sleep(.1)
http.serve_forever()
'''


@contextmanager
def owned_fixture(root, *, escaped=False):
    root.mkdir()
    with (root / "fixture.log").open("x") as log:
        proc = subprocess.Popen([sys.executable, "-c", SERVER, str(root), str(BUNDLE), EXECUTION] + (["escape"] if escaped else []),
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": "", "PYTHONDONTWRITEBYTECODE": "1"})
        try:
            deadline = time.monotonic() + 10
            while not (root / "ready.json").exists():
                assert proc.poll() is None, (root / "fixture.log").read_text()
                assert time.monotonic() < deadline
                time.sleep(.02)
            ready = json.loads((root / "ready.json").read_text())
            owner = SimpleNamespace(proc=proc, port=ready["port"], service_birth=LIFECYCLE.process_identity(proc.pid),
                                    owned_lifecycle=lambda: LIFECYCLE)
            yield owner
        finally:
            if (root / "escaped.json").exists():
                birth = json.loads((root / "escaped.json").read_bytes())

                def escaped_poll():
                    current = LIFECYCLE.process_identity(birth["pid"])
                    if current is None:
                        return 0
                    assert all(current[key] == birth[key] for key in birth), "escaped test child PID was reused"
                    return 0 if current["state"] == "Z" else None

                assert birth["pid"] == birth["pgid"] == birth["session"]
                escaped_poll()
                LIFECYCLE.stop_owned_process(SimpleNamespace(pid=birth["pid"], poll=escaped_poll),
                                             term_timeout=5, kill_timeout=5)
            LIFECYCLE.stop_owned_process(proc, term_timeout=5, kill_timeout=5)
            proc.wait(timeout=5)


def collect(owner, root):
    return collect_requests(owner, capture=root / "dev_D16/capture", execution_id=EXECUTION,
        input_root=BUNDLE, input_sha256=BUNDLE_SHA, output=root / "wire", api_source=SOURCE / "python/freetoken/server/openai_api.py",
        ordinary_client=CLIENT, wire_root=WIRE, timeout=5)


@pytest.fixture(scope="module")
def collected(tmp_path_factory):
    root = tmp_path_factory.mktemp("ordinary-parent") / "owned"
    with owned_fixture(root) as owner:
        result = collect(owner, root)
        yield root, owner, result


def test_actual_three_http_requests_and_stopped_owned_worker(tmp_path):
    root = tmp_path / "owned"
    with owned_fixture(root) as owner:
        result = collect(owner, root)
        collection = root / "wire/collection.json"
        assert list(result["responses"]) == ["0", "1", "2"]
        for uid in range(3):
            assert (root / f"received-{uid}.json").read_bytes() == (root / f"wire/uid-{uid}.request-body.json").read_bytes()
            assert result["responses"][str(uid)]["decoded"]["completion"]["choices"][0]["message"]["content"] == "CPU protocol fixture"
        assert result["worker_stopped_verified"] is False and result["output_equivalence_verified"] is False
        with pytest.raises(ValueError, match="survives"):
            record_stopped_worker(LIFECYCLE, root / "premature.json", collection_path=collection,
                                  collection_sha256=sha(collection))
        assert not (root / "premature.json").exists()
    stopped = record_stopped_worker(LIFECYCLE, root / "stopped.json", collection_path=collection,
                                    collection_sha256=sha(collection))
    assert stopped["worker_stopped_verified"] is True and stopped["owned_group_alive"] is False
    assert stopped["output_equivalence_verified"] is False
    assert stopped["collection"]["sha256"] == sha(collection)
    assert LIFECYCLE.owned_group_alive(owner.proc.pid) is False


@pytest.mark.parametrize("fault", ["api_uid", "usage", "clock_event", "clock_order", "first", "missing_done", "raw_sha"])
def test_reader_rejects_changed_wire_metadata(collected, tmp_path, fault):
    root, _, _ = collected
    api_path = tmp_path / "response.api.json"
    original = json.loads((root / "wire/uid-0.api.json").read_bytes())
    api = copy.deepcopy(original)
    for key, suffix in (("sse", ".sse"), ("events", ".events.jsonl")):
        path = api_path.with_suffix(suffix)
        shutil.copyfile(api[key], path)
        api[key] = str(path)
    if fault == "api_uid": api["uid"] = 1
    elif fault == "usage": api["usage"]["completion_tokens"] += 1
    elif fault in ("clock_event", "clock_order"):
        path = Path(api["events"])
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if fault == "clock_event": rows[1]["event"]["choices"][0]["delta"]["content"] = "different"
        else: rows[1]["monotonic_ns"] = api["dispatch_monotonic_ns"] - 1
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
        api["events_sha256"] = sha(path)
    elif fault == "first": api["first_output_event"]["monotonic_ns"] += 1
    elif fault == "missing_done":
        path = Path(api["sse"])
        path.write_bytes(path.read_bytes().replace(b"data: [DONE]\n\n", b""))
        api["sse_sha256"] = api["raw_sse_sha256"] = sha(path)
    elif fault == "raw_sha": api["sse_sha256"] = api["raw_sse_sha256"] = "0" * 64
    api_path.write_text(json.dumps(api))
    with pytest.raises(ValueError):
        read_wire_response(api_path, api_sha256=sha(api_path), payload_path=api["payload_source"]["path"],
            payload_sha256=api["input_sha256"], expected_uid=0, api_source=SOURCE / "python/freetoken/server/openai_api.py",
            ordinary_client=CLIENT, wire_root=WIRE)


@pytest.mark.parametrize("field", ["start_ticks", "pgid", "session", "state"])
def test_external_worker_birth_rejects_wrong_group_and_reused_pid(collected, monkeypatch, field):
    root, owner, result = collected
    original = LIFECYCLE.process_identity

    def changed(pid):
        value = original(pid)
        if pid == result["worker_identity"]["pid"]:
            value[field] = "Z" if field == "state" else value[field] + 1
        return value

    monkeypatch.setattr(LIFECYCLE, "process_identity", changed)
    with pytest.raises(ValueError, match="worker birth/group/session"):
        observe_live_worker(LIFECYCLE, owner.service_birth, root / "dev_D16/capture",
                            execution_id=EXECUTION, expected_uids=[0, 1, 2])


def test_no_output_overwrite_or_implicit_replay(collected):
    root, owner, _ = collected
    before = sha(root / "wire/collection.json")
    with pytest.raises(FileExistsError):
        collect(owner, root)
    assert sha(root / "wire/collection.json") == before
    assert not (root / "received-3.json").exists()


def test_foreign_loopback_listener_rejected_before_any_post(collected, tmp_path):
    root, owner, _ = collected
    foreign = tmp_path / "foreign"
    with owned_fixture(foreign) as unrelated:
        wrong = SimpleNamespace(**{**vars(owner), "port": unrelated.port})
        with pytest.raises(ValueError, match="listener is outside the owned process group"):
            collect_requests(wrong, capture=root / "dev_D16/capture", execution_id=EXECUTION,
                input_root=BUNDLE, input_sha256=BUNDLE_SHA, output=tmp_path / "attempt",
                api_source=SOURCE / "python/freetoken/server/openai_api.py", ordinary_client=CLIENT, wire_root=WIRE, timeout=5)
        assert not (foreign / "received-0.json").exists()
        assert not (tmp_path / "attempt/collection.json").exists()


def test_shared_listener_escaped_child_rejected_before_post(tmp_path):
    root = tmp_path / "escaped-owner"
    with owned_fixture(root, escaped=True) as owner:
        birth = json.loads((root / "escaped.json").read_bytes())
        assert birth["pgid"] != owner.service_birth["pgid"]
        with urlopen(f"http://127.0.0.1:{owner.port}/health", timeout=5) as response:
            assert response.status == 200
        assert int((root / "get-handler-pid.txt").read_text()) == birth["pid"]
        with pytest.raises(ValueError, match="listener is outside the owned process group"):
            collect(owner, root)
        assert not (root / "received-0.json").exists()
        assert not (root / "wire/collection.json").exists()
    assert LIFECYCLE.owned_group_alive(birth["pgid"]) is False


def test_listener_receipt_states_uid_and_sampling_scope(collected):
    root, _, _ = collected
    for uid in range(3):
        for boundary in ("before", "after"):
            row = json.loads((root / f"wire/uid-{uid}.listener-{boundary}.json").read_bytes())
            assert row["scanned_uid"] == os.getuid()
            assert row["same_uid_listener_exclusivity_verified"] is True
            assert row["global_listener_exclusivity_verified"] is False
            assert row["holders"] and "point-in-time" in row["scope"]
            assert row["pid_domain"]["pid_namespace"] == os.readlink("/proc/self/ns/pid")
            assert row["pid_domain"]["boot_id"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            assert "within observer PID namespace" in row["scope"]


def test_current_uid_fd_permission_denied_fails_closed(collected, monkeypatch):
    _, owner, _ = collected
    original = os.scandir

    def denied(path):
        if str(path) == f"/proc/{owner.proc.pid}/fd":
            raise PermissionError("fixture denies same-UID process FD observation")
        return original(path)

    monkeypatch.setattr(os, "scandir", denied)
    with pytest.raises(PermissionError, match="same-UID"):
        observe_owned_listener(LIFECYCLE, owner.service_birth, owner.port)


@pytest.mark.parametrize("fault", ["collection_sha", "worker_identity", "frontend_identity", "worker_proof_sha"])
def test_stop_rejects_unbound_collection(collected, tmp_path, fault):
    root, _, _ = collected
    folder = tmp_path / "copy"
    folder.mkdir()
    path = folder / "collection.json"
    doc = json.loads((root / "wire/collection.json").read_bytes())
    for uid in range(3):
        binding = doc["responses"][str(uid)]["live_worker"]
        new = folder / f"uid-{uid}.live-worker.json"
        shutil.copyfile(binding["path"], new)
        binding["path"] = str(new)
    if fault == "worker_identity": doc["worker_identity"]["pid"] += 1
    elif fault == "frontend_identity": doc["frontend_birth"]["start_ticks"] += 1
    elif fault == "worker_proof_sha": doc["responses"]["2"]["live_worker"]["sha256"] = "0" * 64
    path.write_text(json.dumps(doc))
    digest = "0" * 64 if fault == "collection_sha" else sha(path)
    with pytest.raises(ValueError):
        record_stopped_worker(LIFECYCLE, folder / "stop.json", collection_path=path, collection_sha256=digest)
    assert not (folder / "stop.json").exists()


@pytest.mark.parametrize("fault", ["boot_id", "pid_namespace", "missing_domain"])
def test_stop_rejects_foreign_pid_domain_before_pid_lookup(collected, tmp_path, monkeypatch, fault):
    root, _, _ = collected
    doc = json.loads((root / "wire/collection.json").read_bytes())
    if fault == "missing_domain":
        doc.pop("pid_domain")
    else:
        doc["pid_domain"][fault] = "foreign"
    path = tmp_path / "collection.json"
    path.write_text(json.dumps(doc))

    def forbidden(pid):
        raise AssertionError("foreign PID domain must fail before process lookup")

    monkeypatch.setattr(LIFECYCLE, "process_identity", forbidden)
    with pytest.raises(ValueError, match="three-request collection"):
        record_stopped_worker(LIFECYCLE, tmp_path / "stop.json", collection_path=path, collection_sha256=sha(path))
    assert not (tmp_path / "stop.json").exists()


def test_unmounted_pid_namespace_proc_view_rejected(collected, monkeypatch):
    _, owner, _ = collected
    current_pid = os.getpid()
    monkeypatch.setattr(os, "getpid", lambda: current_pid + 1)
    with pytest.raises(ValueError, match="/proc view does not match"):
        observe_owned_listener(LIFECYCLE, owner.service_birth, owner.port)


@pytest.mark.parametrize("change_on_read", [2, 3])
def test_listener_holder_pid_domain_checked_after_fd_match_and_again(collected, monkeypatch, change_on_read):
    _, owner, _ = collected
    original = os.readlink
    path = f"/proc/{owner.proc.pid}/ns/pid"
    reads = 0

    def changed(link):
        nonlocal reads
        if str(link) == path:
            reads += 1
            # First read checks the frontend; subsequent reads must check the
            # actual FD holder at discovery and at the final stable recheck.
            if reads >= change_on_read:
                return "pid:[different-namespace]"
        return original(link)

    monkeypatch.setattr(os, "readlink", changed)
    with pytest.raises(ValueError, match="listener holder"):
        observe_owned_listener(LIFECYCLE, owner.service_birth, owner.port)
    assert reads == change_on_read
