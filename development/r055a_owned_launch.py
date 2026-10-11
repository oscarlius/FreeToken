"""R055a controller. Its --dry-run executes the same R055a preparation source."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shlex
from pathlib import Path

HERE = Path(__file__).resolve().parent
RID = "E2-R055a-gate-D06"
ADAPTER = "r055a_gate_d06_prepare.py"
REVIEW_SCHEMA = "ft_r055a_startup_review/v3"
SOURCE_DEPENDENCIES = (Path(__file__).name, ADAPTER, "r055a_dryrun_base_v1.py", "r055_owned_launch.py",
                       "r055_gate_d06_prepare.py", "d07_g3g4_prepare.py", "t16_private_port_base_runner.py",
                       "t17_d14_runner.py", "t17_d14_observe.py", "t16_full_tail_base_runner.py")


def source_hashes():
    return {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest() for name in SOURCE_DEPENDENCIES}


def _dry_base():
    path = HERE / "r055a_dryrun_base_v1.py"
    spec = importlib.util.spec_from_file_location("r055a_owned_dry_base", path)
    module = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(module)
    return module


def adapter_module():
    path = HERE / ADAPTER
    spec = importlib.util.spec_from_file_location("r055a_prepare", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def _legacy():
    path = HERE / "r055_owned_launch.py"
    spec = importlib.util.spec_from_file_location("r055a_legacy", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    module.RID = RID
    module.ADAPTER = ADAPTER
    module.SOURCE_DEPENDENCIES = SOURCE_DEPENDENCIES
    module.source_hashes = source_hashes
    module.review_path = lambda: module.ROOT / "runs/dev_R055/reviews" / f"{RID}_startup_review_v3.json"
    def require_review():
        receipt = adapter_module().ROUNDS / f".dryrun_R055a_{RID}" / "dry_run_receipt.json"
        review = module.review_path()
        if review.is_symlink() or not review.is_file() or review.stat().st_mode & 0o222:
            raise RuntimeError("R055a startup review is absent or writable")
        if receipt.is_symlink() or not receipt.is_file() or receipt.stat().st_mode & 0o222:
            raise RuntimeError("R055a dry-run receipt is absent or writable")
        dry = json.loads(receipt.read_text(encoding="utf-8"))
        if dry.get("schema") != "ft_r055a_dry_run/v2" or any(dry.get(key) is not False for key in
                ("service_started", "requests_sent", "gpu_lock_taken", "batch_allocated", "formal_rid_directory_created")):
            raise RuntimeError("R055a dry-run receipt has side effects or wrong schema")
        if dry.get("source_sha256") != source_hashes():
            raise RuntimeError("R055a dry-run source inventory differs")
        expected_dry = {"rid": RID, "cwd": str(module.ROOT), "owner_path": str(Path(__file__).resolve()),
                        "adapter_path": str((HERE / ADAPTER).resolve()), "formal_directory": str(adapter_module().ROUNDS / RID),
                        "passed": True}
        if any(dry.get(key) != value for key, value in expected_dry.items()):
            raise RuntimeError("R055a dry-run identity binding differs")
        if dry.get("user", {}).get("uid") != os.getuid() or dry.get("worktrees", {}).get("parent", {}).get("head") != module.PARENT_COMMIT or dry.get("worktrees", {}).get("candidate", {}).get("head") != module.CANDIDATE_COMMIT:
            raise RuntimeError("R055a dry-run user or worktree binding differs")
        if os.getcwd() != str(module.ROOT) or dry.get("user", {}).get("user") != os.environ.get("USER"):
            raise RuntimeError("R055a launch user/cwd differs from the actual dry-run")
        document = json.loads(review.read_text(encoding="utf-8"))
        expected = {"schema": REVIEW_SCHEMA, "rid": RID, "card": module.CARD,
                    "candidate_commit": module.CANDIDATE_COMMIT, "parent_commit": module.PARENT_COMMIT,
                    "verdict": "PASS", "approved": True, "source_sha256": source_hashes(),
                    "dry_run_receipt_sha256": hashlib.sha256(receipt.read_bytes()).hexdigest(),
                    "dry_run_source_sha256": source_hashes()}
        if any(document.get(key) != value for key, value in expected.items()):
            raise RuntimeError("R055a startup review binding differs")
        return review
    module.require_leaf_review = require_review
    def admission(g):
        if g.LOCK.exists() or g.LOCK.is_symlink():
            raise RuntimeError("foreign GPU lock exists; R055a remains queued")
        g.require_r041_kept(module.ROOT)
        g.require_closed_round("E2-R050-gate-D15", "kept")
        module.require_candidate(); module.require_native_reuse(); require_review()
    module.admission = admission
    def child_argv(batch, receipt):
        return [str(module.ROOT / "venv/bin/python"), str(Path(__file__).resolve()), "--run", "--owned-child",
                "--batch", str(batch), "--launch-receipt", str(receipt)]
    module.argv = child_argv
    original_d07 = module.d07
    def candidate_d07():
        gate = original_d07()
        gate.CANDIDATE = module.CANDIDATE_COMMIT
        gate.WORKTREE = module.ROOT / 'wt/e2base1-p1'
        return gate
    module.d07 = candidate_d07
    module.pause_smoke = lambda gate, batch, run=None: pause_smoke(module, gate, batch, run)
    return module


def _prepare_pause_command(gate, run, worktree, port):
    """The formal and file-only smoke share the actual command writer."""
    env = gate.clean_environment(worktree, trace_dir=run / 'route')
    keys = {'CUDA_VISIBLE_DEVICES', 'FT_DEV_PAUSE_ENDPOINT', 'FT_DEV_ROUTE_TRACE', 'PYTHONPATH', 'VIRTUAL_ENV'}
    command = 'env ' + ' '.join(f'{key}={shlex.quote(env[key])}' for key in sorted(env) if key in keys)
    (run / 'SERVE_CMD.txt').write_text(command + ' ' + shlex.join(gate.serve_argv(port)) + '\n', encoding='utf-8')


def pause_smoke(legacy, gate, batch, run=None, *, file_dry_run=False, worktree_override=None):
    """A real, dynamically-port-bound service check; no CPU test calls this function."""
    run = legacy.ROOT / 'runs/dev_R055' / f'{legacy.RID}_batch{batch}_pause_smoke' if run is None else Path(run)
    run.mkdir(parents=True, exist_ok=False)
    port = gate.dynamic_fixture_port()
    proc = None
    prior_argv = None
    previous_observer = os.environ.get('R055_PAUSE_OBSERVATIONS')
    try:
        if callable(getattr(gate, 'serve_argv', None)):
            startup = legacy._freeze_pause_observer(run)
            prior_argv = gate.serve_argv
            gate.serve_argv = lambda _port: [str(gate.VENV / 'bin/python'), str(startup)] + prior_argv(_port)[1:]
            os.environ['R055_PAUSE_OBSERVATIONS'] = str(run / 'pause_observations.jsonl')
        worktree = Path(worktree_override) if file_dry_run and worktree_override is not None else legacy.require_candidate()
        if prior_argv is not None:
            env = gate.clean_environment(worktree, trace_dir=run / 'route')
            selected = {key: env.get(key) for key in ('CUDA_VISIBLE_DEVICES', 'FT_DEV_PAUSE_ENDPOINT', 'FT_DEV_ROUTE_TRACE', 'PYTHONPATH', 'VIRTUAL_ENV', 'PATH')}
            (run / 'ENV.txt').write_text(json.dumps({'worktree': str(worktree), 'candidate_commit': legacy.CANDIDATE_COMMIT, 'environment': selected}, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        _prepare_pause_command(gate, run, worktree, port)
        if file_dry_run:
            files = {}
            for name in ('serve.log', 'owned_process.json', 'health.json', 'serve_args.txt',
                         'before.json', 'pause_completed.json', 'pause_cancel.json',
                         'after_cancel.json', 'pause_observations.jsonl', 'route/.writable'):
                path = run / name
                path.parent.mkdir(parents=True, exist_ok=True)
                files[name] = _dry_base().write_probe(path, 'CPU FILE PROBE ONLY; no measurement\n')
            files.update({name: hashlib.sha256((run / name).read_bytes()).hexdigest()
                          for name in ('ENV.txt', 'SERVE_CMD.txt', 'r055_pause_startup.py', 'r055_pause_observer.py')})
            return {'directory': str(run), 'port': port, 'files': files,
                    'service_started': False, 'requests_sent': False}
        proc = gate.start_server(run, worktree, port, run / 'route')
        if prior_argv is not None:
            text = (run / 'serve.log').read_text(encoding='utf-8')
            position = text.find('Parsed arguments')
            if position < 0:
                raise RuntimeError('R055 pause service did not publish parsed arguments')
            (run / 'serve_args.txt').write_text('\n'.join(text[position:].splitlines()[:2]) + '\n', encoding='utf-8')
        gate.invoke_cold_eq(legacy.require_candidate(), port, f'{legacy.RID}-pause-before', run / 'before.json')
        normal = legacy.pause_request(port, 1.0, 5.0)
        (run / 'pause_completed.json').write_text(json.dumps(normal, indent=2) + '\n')
        cancel = legacy.pause_request(port, 30.0, 0.05)
        (run / 'pause_cancel.json').write_text(json.dumps(cancel, indent=2) + '\n')
        gate.invoke_cold_eq(legacy.require_candidate(), port, f'{legacy.RID}-pause-after-cancel', run / 'after_cancel.json')
        if not isinstance(normal, dict) or normal.get('status') != 'accepted' or (not isinstance(normal.get('request_id'), str)) or (not normal['request_id']):
            raise RuntimeError('R055 pause endpoint lacks an accepted request identity')
        if not isinstance(cancel, dict) or cancel.get('status') != 'timeout' or (not isinstance(cancel.get('request_id'), str)) or (not cancel['request_id']) or (cancel.get('request_id') == normal.get('request_id')) or ('cancel enqueue' in str(cancel.get('error', ''))):
            raise RuntimeError('R055 pause cancel lacks a verified API cancellation receipt')
        evidence = legacy._trace_pause_backend(run, normal['request_id'], cancel['request_id']) if prior_argv is not None else {'test_double': True}
        return {'run': str(run), 'port': port, 'owned_process': str(run / 'owned_process.json'), 'before': str(run / 'before.json'), 'pause': str(run / 'pause_completed.json'), 'cancel': str(run / 'pause_cancel.json'), 'after_cancel': str(run / 'after_cancel.json'), 'backend_evidence': evidence}
    finally:
        if prior_argv is not None:
            gate.serve_argv = prior_argv
        if previous_observer is None:
            os.environ.pop('R055_PAUSE_OBSERVATIONS', None)
        else:
            os.environ['R055_PAUSE_OBSERVATIONS'] = previous_observer
        if proc is not None:
            try:
                gate.load_owned_lifecycle().stop_owned_process(proc)
            except BaseException as cleanup_error:
                cleanup_error.owned_process = proc
                cleanup_error.owned_cleanup_failed = True
                raise

def pause_file_dry_run(run: Path, port: int, worktree: Path) -> dict:
    legacy = _legacy()
    gate = legacy.d07()
    # The same pause_smoke writes the observer/env/argv files before its Popen boundary.
    return pause_smoke(legacy, gate, 1, run, file_dry_run=True, worktree_override=worktree)


def main(argv_in=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--owned-child", action="store_true")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--launch-receipt", type=Path)
    options = parser.parse_args(argv_in)
    if options.dry_run:
        if options.run or options.owned_child or options.batch is not None or options.launch_receipt is not None:
            parser.error("--dry-run does not accept launch arguments")
        result = adapter_module().dry_run()
        print(json.dumps(result, sort_keys=True))
        return 0
    if options.run:
        legacy = _legacy()
        args = ["--run"]
        if options.owned_child:
            if options.batch is None or options.launch_receipt is None:
                parser.error("child requires batch and receipt")
            args += ["--owned-child", "--batch", str(options.batch), "--launch-receipt", str(options.launch_receipt)]
        elif options.batch is not None or options.launch_receipt is not None:
            parser.error("controller does not accept child arguments")
        return legacy.main(args)
    if options.owned_child or options.batch is not None or options.launch_receipt is not None:
        parser.error("--run required for launch arguments")
    print(json.dumps({"schema": "ft_r055a_owned_launch/v1", "rid": RID, "requests_sent": False,
                      "gpu_lock_taken": False, "source_execution_ready": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
