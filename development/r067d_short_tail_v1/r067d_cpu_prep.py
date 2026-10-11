"""CPU-only preparation for the independent E2-R067d short-tail round.

This module deliberately contains no launcher: it prepares configuration and
replays immutable, already-recorded windows before any GPU admission exists.
"""
from __future__ import annotations
import ast, copy, hashlib, json, re, shutil, socket, subprocess, time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RETRY2 = HERE.parent / "r067c_retry2_short_tail_v1" / "RETRY2_CONFIG_CPU_ONLY.json"
RID = "E2-R067d-d20-short-tail-v1"
REMOTE = "/data2/FreeToken/development/r067d_short_tail_v1"
RUN = f"/data2/FreeToken/runs/dev_R067/{RID}"
PORTS = tuple(range(31001, 31021))
ROW = re.compile(r"Prefill batch, #new-seq: (\d+), #new-token: (\d+), #cached-token: (\d+)")
RECIPE = {s['name']: tuple(s['argv']) for s in json.loads(RETRY2.read_text())['services']}

def sha_bytes(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def argv_sha256(argv: list[str]) -> str: return sha_bytes(json.dumps(argv, separators=(",", ":")).encode())
def now() -> str: return datetime.now(timezone.utc).isoformat()

def actual_argv(service: dict) -> list[str]:
    """The sole construction point for launch argv and its stored digest."""
    argv = list(RECIPE[service['name']])
    argv[5] = f"{service['service_dir']}/t17_d14_startup.py"
    argv[argv.index("--port") + 1] = str(service["port_pair"]["api"])
    return argv

def actual_environment(service: dict) -> dict:
    env = dict(service['env'])
    assert env['MASTER_PORT'] == str(service['port_pair']['tcpstore'])
    return env

def verify_service_binding(service: dict) -> None:
    rendered = actual_argv(service)
    assert rendered == service["argv"], service["name"]
    assert rendered[rendered.index("--port") + 1] == str(service["port_pair"]["api"]), service["name"]
    assert actual_environment(service)["MASTER_PORT"] == str(service["port_pair"]["tcpstore"]), service["name"]
    assert service["argv_sha256"] == argv_sha256(rendered), service["name"]

def verify_service_bindings(items: list[dict]) -> None:
    ports: list[int] = []
    for service in items:
        verify_service_binding(service)
        ports.extend((service["port_pair"]["api"], service["port_pair"]["tcpstore"]))
    assert len(ports) == 20 and len(set(ports)) == 20, "per-round port reuse"

def services() -> list[dict]:
    inherited = json.loads(RETRY2.read_text())["services"]
    answer = []
    for index, old in enumerate(inherited):
        s = copy.deepcopy(old); arm = f"{RUN}/services/{s['name']}"; api, tcpstore = PORTS[index * 2:index * 2 + 2]
        s["service_dir"] = s["cwd"] = arm
        s["port_pair"] = {"api": api, "tcpstore": tcpstore, "probe": "simultaneous wildcard bind; no listen/connect; timeout <=120s", "revalidate_before_spawn": True}
        for key in ("FT_DEV_STATE_DUMP", "FT_T17_INPUT_RECEIPTS", "FT_T17_OBSERVATIONS", "PYTHONPATH"):
            s["env"][key] = s["env"][key].replace("E2-R067c-d20-short-tail-retry2", RID)
        s["env"]["MASTER_PORT"] = str(tcpstore)
        s["argv"] = actual_argv(s); s["argv_sha256"] = argv_sha256(s["argv"])
        answer.append(s)
    return answer

def config() -> dict:
    return {"schema": "ft_r067d_cpu_prep/v1", "rid": RID, "created_utc": now(), "round_kind": "independent_new_round", "not_a_retry_of": "E2-R067c-d20-short-tail-retry2", "input_binding": json.loads(RETRY2.read_text())["input_binding"], "services": services(), "budget": {"services": 10, "generation_calls": 14}, "retries": {"failed_harness_future_retries_max": 2, "used": 0}, "admission": {"gpu": False, "service": False, "http_generation": False}}

def parse_rows(text: str) -> list[dict[str, int]]:
    return [{"new_sequences": int(a), "new_tokens": int(b), "cached_tokens": int(c)} for a,b,c in ROW.findall(text)]

def validate_runtime_window(text: str, *, expected_new: int, expected_cache: int, token_budget: int, raw_usage: dict | None=None, prompt_tokens: int | None=None, expected_completion: int | None=None, post_count: int | None=None) -> list[dict[str, int]]:
    rows = parse_rows(text)
    assert rows, "no prefill geometry rows"
    assert all(r["new_sequences"] == 1 for r in rows), "new_sequences"
    assert all(r["cached_tokens"] == expected_cache for r in rows), "cache"
    assert sum(r["new_tokens"] for r in rows) == expected_new, "cross-row new-token sum"
    assert sum(r["new_tokens"] for r in rows) <= token_budget, "overbudget"
    if raw_usage is not None:
        assert raw_usage.get('prompt_tokens') == prompt_tokens, 'prompt_tokens'
        assert raw_usage.get('cached_tokens') == expected_cache, 'usage cached_tokens'
        if expected_completion is not None:
            assert raw_usage.get('completion_tokens') == expected_completion, 'completion_tokens'
    if post_count is not None: assert post_count == 1, 'POST count'
    return rows

def validate_window(text: str, **kwargs): return validate_runtime_window(text, **kwargs)

def bind_probe(ports: tuple[int, int], timeout_s: int = 120, *, socket_factory=socket.socket, monotonic=time.monotonic, sleeper=time.sleep) -> None:
    # Used only by a future explicit launcher; CPU FILEdry never invokes it.
    assert 0 < timeout_s <= 120
    deadline = monotonic() + timeout_s
    last = None
    while monotonic() <= deadline:
        handles = []
        try:
            for port in ports:
                sock = socket_factory(); handles.append(sock); sock.bind(("0.0.0.0", port))
            return
        except OSError as exc:
            last = exc
        finally:
            for sock in handles: sock.close()
        remaining=deadline-monotonic()
        if remaining <= 0: break
        sleeper(min(1, remaining))
    raise OSError(f"pair {ports} remained unavailable for {timeout_s}s") from last

def probe_or_capture(ports: tuple[int, int], evidence_dir: Path, timeout_s: int = 120, **clock) -> None:
    """Future launcher seam: capture live ownership before classifying a bind failure."""
    try:
        bind_probe(ports, timeout_s, **clock)
    except OSError:
        assert not evidence_dir.exists(); evidence_dir.mkdir(parents=True)
        for tool, name in ((["ss", "-tanp"], "ss-tanp.txt"), (["lsof", "-nP", "-iTCP"], "lsof.txt")):
            try: result = subprocess.run(tool, text=True, capture_output=True, check=False); body = result.stdout + result.stderr
            except FileNotFoundError: body = "tool unavailable\n"
            (evidence_dir / name).write_text(body)
        raise RuntimeError("failed_harness: port bind failure captured before classification")

def materialize_real_windows(source_root: Path, target: Path) -> dict:
    """Copy immutable source windows once, recording paths and byte digests."""
    files = {
        "retry2_seed.txt": source_root / "dev_R067/E2-R067c-d20-short-tail-retry2/services/hot_p8192/seed.serve-window.txt",
        "retry2_t1.txt": source_root / "dev_R067/E2-R067c-d20-short-tail-retry2/services/hot_p8192/query_t1.serve-window.txt",
        "retry2_t64.txt": source_root / "dev_R067/E2-R067c-d20-short-tail-retry2/services/hot_p8192/query_t64.serve-window.txt",
        "smoke481_short.txt": source_root / "production/RESTORE481-E2-R067c-20261009-03/smoke_first/short.serve-window.txt",
        "smoke481_long.txt": source_root / "production/RESTORE481-E2-R067c-20261009-03/smoke_first/long.serve-window.txt",
        "smoke184_short.txt": source_root / "production/ROLLBACK-E2-20261009-COND-01/smoke_first/short.serve-window.txt",
        "smoke184_long.txt": source_root / "production/ROLLBACK-E2-20261009-COND-01/smoke_first/long.serve-window.txt",
    }
    assert not target.exists(); target.mkdir(parents=True)
    owner = source_root / "production/ROLLBACK-E2-20261009-COND-01/owner.json"
    assert owner.is_file(); owner_text = owner.read_text()
    assert "184c965" in owner_text, "rollback owner is not the genuine 184c965 runtime"
    proof = {"schema": "ft_r067d_real_windows/v1", "source_root": str(source_root), "at_utc": now(), "files": {}, "runtime_bindings": {"rollback184_owner": str(owner), "rollback184_owner_sha256": sha_bytes(owner.read_bytes()), "commit": "184c965964b5f79deaecf1b1e3e0eda3187c829d"}}
    for name, source in files.items():
        assert source.is_file(), source
        destination = target / name; shutil.copyfile(source, destination)
        proof["files"][name] = {"source": str(source), "sha256": sha_bytes(destination.read_bytes())}
    (target / "manifest.json").write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    return proof

def replay_readiness(raw_dir: Path) -> dict:
    """GPU admission is closed until all named source windows are independently real."""
    required = ("retry2_seed.txt", "retry2_t1.txt", "retry2_t64.txt", "smoke481_short.txt", "smoke481_long.txt", "smoke184_short.txt", "smoke184_long.txt")
    manifest_path = raw_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {"files": {}}
    present = {name: (raw_dir / name).is_file() for name in required}
    for name in required:
        item = manifest.get('files', {}).get(name, {})
        present[name] = present[name] and sha_bytes((raw_dir/name).read_bytes()) == item.get('sha256')
    for name in ("smoke184_short.txt", "smoke184_long.txt"):
        item = manifest.get("files", {}).get(name, {})
        if not isinstance(item, dict): item = {}
        # A restore-481 log with an 184 binary manifest is not an 184 runtime log.
        present[name] = present[name] and manifest.get("runtime_bindings", {}).get("commit") == "184c965964b5f79deaecf1b1e3e0eda3187c829d" and "ROLLBACK-E2-20261009-COND-01" in str(item.get("source", ""))
    complete = all(present.values())
    return {"schema": "ft_r067d_replay_readiness/v1", "at_utc": now(), "required": present,
            "replay_sources_complete": complete, "gpu_admitted": False,
            "blocker": "independent review and root admission required" if complete else "genuine immutable 184c965 runtime windows are required"}

def filedry(out: Path) -> dict:
    c = json.loads((HERE/'R067D_CONFIG_CPU_ONLY.json').read_text())
    packet = json.loads((HERE/'R067D_PREPARED_RUNNER_PACKET.json').read_text())
    assert packet['config_sha256'] == sha_bytes((HERE/'R067D_CONFIG_CPU_ONLY.json').read_bytes())
    assert packet['helper_sha256'] == sha_bytes(Path(__file__).read_bytes())
    assert replay_readiness(HERE/'raw_windows_v4')['replay_sources_complete']
    assert len(c["services"]) == 10 and len(set(PORTS)) == 20
    verify_service_bindings(c["services"])
    assert sum(len(s.get("requests", [s.get("request")])) for s in c["services"]) == 14
    assert not out.exists(); out.mkdir(parents=True)
    (out / "R067D_CONFIG_CPU_ONLY.json").write_text(json.dumps(c, indent=2, sort_keys=True) + "\n")
    for service in c["services"]:
        arm = out / "services" / service["name"]; arm.mkdir(parents=True)
        for source in sorted((HERE/'tooling').glob('*.py')):
            shutil.copyfile(source, arm / source.name)
        (arm / "no_start.json").write_text(json.dumps({"service_started": False, "gpu_started": False, "http_generation": False, "argv_sha256": service["argv_sha256"]}, sort_keys=True) + "\n")
    # Execute exactly the two helpers called by the real child. Its top level
    # (GPU lock, process ownership, HTTP and formal-round writes) is never run.
    import io, sys
    from types import SimpleNamespace
    tree=ast.parse(packet['child_source'])
    names={'start_prepared_service','judge_prepared_window'}
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert len(nodes)==2
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in names]
    assert {n.func.id for n in calls}==names, 'CPU helpers must be actual runtime consumers'
    namespace={'Path':Path,'subprocess':subprocess,'r067d_tools':sys.modules[__name__]}
    exec(compile(ast.Module(nodes,[]),'<r067d-real-runtime-helpers>','exec'),namespace)
    would_spawn=[]; probes=[]; judgments=[]
    def fake_probe(ports, evidence_dir, timeout):
        probes.append({'ports':list(ports),'timeout_s':timeout})
    def fake_popen(argv, **kwargs):
        would_spawn.append({'argv':argv,'env':kwargs['env'],'argv_sha256':argv_sha256(argv),'cwd':str(kwargs['cwd'])})
        return SimpleNamespace(pid=-1)
    for service in c['services']:
        namespace['start_prepared_service'](service,actual_environment(service),io.BytesIO(),probe=fake_probe,popen=fake_popen)
        prefix=int(re.search(r'_p(\d+)',service['name']).group(1))
        requests=service['requests'] if service['kind']=='hot' else [service['request']]
        for item in requests:
            tail=item.get('tail',int(re.search(r'_t(\d+)',service['name']).group(1)) if service['kind']=='cold' else 1)
            prompt=prefix+1 if item['role']=='seed' else prefix+tail
            cached=prefix if service['kind']=='hot' and item['role']!='seed' else 0
            new=tail if cached else prompt
            window=(f'Prefill batch, #new-seq: 1, #new-token: {new}, #cached-token: {cached}\nPOST /internal/t17/exact-ids HTTP/1.1" 200 OK\n').encode()
            raw={'response':{'usage':{'prompt_tokens':prompt,'cached_tokens':cached,'completion_tokens':item['max_tokens']}}}
            rows,valid=namespace['judge_prepared_window'](service,item,range(prompt),window,raw,prefix,tail)
            assert valid and rows
            judgments.append({'service':service['name'],'role':item['role'],'valid':valid,'synthetic_transport':True})
    assert len(would_spawn)==10 and len(probes)==10 and len(judgments)==14
    dry={'would_spawn':would_spawn,'probes':probes,'runtime_judgments':judgments,'fake_popen':True,'real_popen':False,'synthetic_transport':True}
    (out/'prepared_child_cpu_mode.json').write_text(json.dumps(dry,sort_keys=True)+'\n')
    receipt = {"schema": "ft_r067d_cpu_filedry/v7", "rid": RID, "at_utc": now(), "services": 10, "calls": 14, "port_pairs": 10, "unique_ports": 20, 'actual_launch_helper_calls':10,'actual_judge_helper_calls':14,'synthetic_transport':True,'packet_sha256':sha_bytes((HERE/'R067D_PREPARED_RUNNER_PACKET.json').read_bytes()),'config_sha256':packet['config_sha256'],'helper_sha256':packet['helper_sha256'], "gpu_started": False, "service_started": False, "http_generation": False, "admit": False}
    (out / "receipt.json").write_text(json.dumps(receipt, sort_keys=True) + "\n")
    receipt["receipt_sha256"] = sha_bytes((out / "receipt.json").read_bytes()); return receipt
