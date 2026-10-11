"""Owned controller/child launch for the D10 staggered-decode T16 gate."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import inspect
import json
import os
import subprocess
import sys
import tempfile
import time
import socket
from pathlib import Path
from types import SimpleNamespace

ROOT = Path("/data2/FreeToken")
DEV = Path(__file__).resolve().parent
PARENT_COMMIT = "481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9"
SPECS = {
    "D10": ("E2-D10-T16-night-20261010", "22ff3a389eae3724cdca9a45f2e19577082a2032", "d10_t16_full_runner_v3.py"),
}
RECEIPT_WAIT_SECONDS = 30
D10_QUEUE_PREDECESSORS = ()


def d07():
    path = DEV / "d07_g3g4_prepare.py"
    spec = importlib.util.spec_from_file_location("r050_d07", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def source_hashes(card):
    """The R startup review binds the executable leaf launcher and adapter."""
    _, _, adapter = SPECS[card]
    return {
        name: hashlib.sha256((DEV / name).read_bytes()).hexdigest()
        for name in (Path(__file__).name, adapter, "d07_g3g4_prepare.py", "t16_private_port_dryrun_r062_v1.py", "round_json_append.py",
                     "t16_frozen_helpers_v1/cold_eq.py", "t16_frozen_helpers_v1/probe_ft_cold32k.py",
                     "t16_frozen_helpers_v1/ft_probe_ckpt_tax.py", "t16_frozen_helpers_v1/serve_args_diff.py")
    }


def review_path(card):
    rid, _, _ = SPECS[card]
    version = 3
    return ROOT / "runs/dev_T16/reviews" / f"{rid}_startup_review_v{version}.json"


def dry_run_receipt_path(card):
    rid, _, _ = SPECS[card]
    version = 3
    return ROOT / 'runs/dev_T16/reviews' / f'{rid}_file_dry_run_v{version}.json'


def require_file_dry_run(card):
    path = dry_run_receipt_path(card)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError('real-path dry-run receipt is absent or writable')
    if Path.cwd().resolve() != ROOT.resolve():
        raise RuntimeError('real-path dry-run receipt requires canonical measurement cwd')
    doc = json.loads(path.read_text())
    rid, commit, _ = SPECS[card]
    expected = {'schema': 'ft_t16_real_path_dry_run/v1', 'rid': rid,
                'candidate_commit': commit, 'parent_commit': PARENT_COMMIT,
                'source_sha256': source_hashes(card), 'script': str(Path(__file__).resolve()),
                'uid': os.getuid(), 'passed': True, 'batch_allocated': False,
                'gpu_lock_taken': False, 'service_started': False, 'requests_sent': False,
                'user': __import__('getpass').getuser(), 'cwd': str(ROOT),
                'candidate_worktree': str(ROOT / 'wt/d10-staggered-v1'), 'formal_round_created': False}
    if any(doc.get(key) != wanted for key, wanted in expected.items()):
        raise RuntimeError('real-path dry-run receipt binding differs')
    return path


def require_leaf_review(card):
    """Accept only a sealed R review for the exact sources this leaf will run."""
    rid, commit, _ = SPECS[card]
    path = review_path(card)
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError("leaf startup review is absent or writable")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("leaf startup review is unreadable") from exc
    expected = {
        "schema": "ft_t16_leaf_startup_review/v1",
        "rid": rid,
        "card": card,
        "candidate_commit": commit,
        "parent_commit": PARENT_COMMIT,
        "verdict": "PASS",
        "approved": True,
        "source_sha256": source_hashes(card),
        "file_dry_run_sha256": hashlib.sha256(require_file_dry_run(card).read_bytes()).hexdigest(),
    }
    if any(value.get(key) != wanted for key, wanted in expected.items()):
        raise RuntimeError("leaf startup review binding differs")
    return path


def require_candidate(card):
    """Small git identity checks only; no payload scans or candidate mutation."""
    _, commit, _ = SPECS[card]
    worktree = ROOT / "wt" / "d10-staggered-v1"
    if worktree.is_symlink():
        raise RuntimeError("candidate worktree is symlinked")
    try:
        head = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip()
        dirty = subprocess.check_output(
            ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=no"], text=True
        )
        ancestor = subprocess.run(
            ["git", "-C", str(worktree), "merge-base", "--is-ancestor", PARENT_COMMIT, "HEAD"],
            check=False,
        ).returncode
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("candidate worktree is unavailable") from exc
    if head != commit or dirty or ancestor:
        raise RuntimeError("candidate worktree identity, cleanliness, or ancestry differs")
    adapter_module(SPECS[card][2]).require_native_provenance()
    return worktree


def required_rounds(card):
    return ()


def admission(g, card):
    """Metadata-only predecessor, review, candidate and foreign-lock checks."""
    if g.LOCK.exists() or g.LOCK.is_symlink():
        raise RuntimeError("foreign GPU lock exists; T16 gate remains queued")
    for rid, verdict in required_rounds(card):
        g.require_closed_round(rid, verdict)
    require_candidate(card)
    require_leaf_review(card)


def require_user_scope_approval(card):
    """A sealed D10 scope record opens the controller after the live queue."""
    rid, commit, _ = SPECS[card]
    path = ROOT / "runs/dev_T16/reviews" / f"{rid}_user_scope_approval_v3.json"
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
        raise RuntimeError("D10 user scope approval is absent or writable")
    doc = json.loads(path.read_text(encoding="utf-8"))
    expected = {"schema": "ft_t16_user_scope_approval/v1", "rid": rid,
                "candidate_commit": commit, "parent_commit": PARENT_COMMIT,
                "queue_predecessors": list(D10_QUEUE_PREDECESSORS),
                "arms": 8, "planned_generation_calls": 100, "approved": True}
    if any(doc.get(key) != value for key, value in expected.items()):
        raise RuntimeError("D10 user scope approval binding differs")
    return path


def argv(card, batch, receipt):
    return [
        str(ROOT / "venv/bin/python"),
        str(Path(__file__).resolve()),
        "--run", "--card", card, "--owned-child", "--batch", str(batch),
        "--launch-receipt", str(receipt),
    ]


def controller(card):
    if sys.platform != "linux":
        raise RuntimeError("Linux only")
    rid, commit, _ = SPECS[card]
    require_user_scope_approval(card)
    gate = d07()
    admission(gate, card)
    owned = gate.load_owned_lifecycle()
    helper = owned.verified_module(ROOT / "runs/plan_batches/e2_launch.py", gate.ATOMIC_HELPER_SHA, "r050_atomic")
    batch = helper.next_batch(gate.ROUNDS)
    receipt = ROOT / "runs/dev_T16" / f"launch_{rid}_batch{batch}.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    child_argv = argv(card, batch, receipt)
    reserved = {
        "schema": "ft_t16_owned_launch/v1",
        "state": "reserved",
        "rid": rid,
        "batch": batch,
        "candidate_commit": commit,
        "argv_sha256": gate.argv_sha256(child_argv),
        "controller": gate.process_birth(),
    }
    got = owned.reserve_process(helper, batch, rid, child_argv, receipt, reserved)
    identity = owned.process_identity(got["batch_pid"])
    child_identity = {
        "pid": identity["pid"],
        "start_ticks": identity["start_ticks"],
        "execution_id": f"{identity['pid']}:{identity['start_ticks']}",
    }
    return gate.publish_child_binding(receipt, got, child_identity, lifecycle=owned)


def require_receipt(gate, card, batch, path):
    rid, commit, _ = SPECS[card]
    mine = gate.process_birth()
    expected = gate.argv_sha256(argv(card, batch, path))
    deadline = time.monotonic() + RECEIPT_WAIT_SECONDS
    static = {"schema": "ft_t16_owned_launch/v1", "rid": rid, "batch": batch,
              "candidate_commit": commit, "argv_sha256": expected}
    while time.monotonic() < deadline:
        if path.is_symlink():
            raise RuntimeError("T16 child receipt is symlinked")
        if not path.is_file():
            time.sleep(.05)
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("T16 child receipt is unreadable") from exc
        if any(document.get(key) != value for key, value in static.items()):
            raise RuntimeError("T16 child launch receipt binding differs")
        state = document.get("state")
        if state == "reserved":
            time.sleep(.05)
            continue
        if state != "launched":
            raise RuntimeError("T16 child receipt state is unknown")
        child = document.get("child")
        if child is None:
            time.sleep(.05)
            continue
        if document.get("batch_pid") != mine["pid"] or child != mine:
            raise RuntimeError("T16 child launch receipt binding differs")
        return document
    raise RuntimeError("T16 child launch receipt did not reach launched state")


def adapter_module(name):
    path = DEV / name
    spec = importlib.util.spec_from_file_location("t16_leaf_" + name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def child(card, batch, receipt):
    if sys.platform != "linux":
        raise RuntimeError("Linux only")
    rid, commit, name = SPECS[card]
    gate = d07()
    admission(gate, card)
    require_receipt(gate, card, batch, receipt)
    owner = gate.take_d07_gpu_lock(rid, batch)
    runner, release = None, True
    try:
        module = adapter_module(name)

        class OwnedRunner(module.CandidateRunner):
            def lock_take(self):
                return None

            def lock_release(self):
                return None

            def stop(self):
                try:
                    return super().stop()
                except BaseException:
                    self._owned_cleanup_failed = True
                    raise

        runner = OwnedRunner(SimpleNamespace(
            case=card, rid=rid, batch=batch, candidate_commit=commit, run=True, gate=None
        ))
        # The retained gate verifies this exact child-owned lock on every arm.
        # Only the outer child releases it; the leaf never acquires a second lock.
        runner.token = owner['lock_token']
        runner.lock_inode = owner['lock_inode']
        runner.execute()
        return {"rid": rid, "batch": batch, "candidate_commit": commit,
                "verdict": "pending_review", "proposed_verdict": "kept"}
    finally:
        if runner is not None and getattr(runner, "_owned_cleanup_failed", False):
            release = False
        elif runner is not None and runner.proc is not None and gate.load_owned_lifecycle().owned_group_alive(runner.proc.pid):
            release = False
        if release:
            gate.release_d07_gpu_lock(owner)


def file_dry_run(card):
    """Exercise the real leaf's file writers under the actual round filesystem."""
    if sys.platform != 'linux':
        raise RuntimeError('real-path dry run requires the Linux measurement user')
    if Path.cwd().resolve() != ROOT.resolve():
        raise RuntimeError('dry run requires canonical measurement cwd')
    gate = d07()
    if gate.LOCK.exists() or gate.LOCK.is_symlink():
        raise RuntimeError('dry run remains queued while a GPU batch holds the lock')
    rid, commit, name = SPECS[card]
    formal = gate.ROUNDS / rid
    if formal.exists() or formal.is_symlink():
        raise RuntimeError('formal round already exists; dry run must not alter it')
    for predecessor, verdict in required_rounds(card):
        gate.require_closed_round(predecessor, verdict)
    require_candidate(card)
    sources = source_hashes(card)
    for relative in sources:
        path = DEV / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222:
            raise RuntimeError('freeze the actual execution sources before dry run')
    target = dry_run_receipt_path(card)
    if target.exists() or target.is_symlink():
        raise RuntimeError('dry-run receipt already exists; use a new source/review version')
    # Test the same metadata/wrapper parent filesystems without consuming a
    # batch number, ledger entry, launch receipt, process, or GPU reservation.
    probed_parents = []
    for parent in (ROOT / 'runs/dev_T16', ROOT / 'runs/plan_batches', target.parent):
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', prefix='.file-dry-run-', dir=parent,
                                         delete=False, encoding='utf-8') as handle:
            handle.write('CPU file-operation probe only\n')
            path = Path(handle.name)
        path.chmod(0o444)
        path.chmod(0o644)
        with path.open('a') as handle:
            handle.write('write permission restored\n')
        path.unlink()
        probed_parents.append(str(parent))
    tree = Path(tempfile.mkdtemp(prefix=f'.dryrun_{rid}_', dir=gate.ROUNDS))
    tree.chmod(0o755)
    wrapper = tree / 'dry_run_wrapper.sh'
    wrapper.write_text('#!/bin/sh\n# CPU file-operation probe; never executed\n')
    wrapper.chmod(0o444)
    module = adapter_module(name)
    options = SimpleNamespace(case=card, rid=rid, batch=1, candidate_commit=commit,
                              run=True, gate=None, file_dry_run=True,
                              dry_run_wrapper=str(wrapper))
    runner = module.CandidateRunner(options)
    runner.directory = tree / 'round'
    runner.status = runner.directory / 'status_batch1.json'
    runner.execute()
    complete = json.loads((runner.directory / 'file_dry_run_complete.json').read_text())
    if (not complete.get('arms') or runner.proc is not None or formal.exists()
            or gate.LOCK.exists() or any(complete.get(key) is not False
                for key in ('service_started', 'requests_sent', 'gpu_lock_taken'))):
        raise RuntimeError('dry run crossed a service, lock, or formal-output boundary')
    doc = {'schema': 'ft_t16_real_path_dry_run/v1', 'rid': rid,
           'candidate_commit': commit, 'parent_commit': PARENT_COMMIT,
           'source_sha256': sources, 'script': str(Path(__file__).resolve()),
           'uid': os.getuid(), 'user': gate.command(['id', '-un']) if hasattr(gate, 'command')
                   else subprocess.check_output(['id', '-un'], text=True).strip(),
           'cwd': str(Path.cwd()), 'dry_run_tree': str(tree),
           'candidate_worktree': str(ROOT / 'wt/d10-staggered-v1'),
           'parent_write_probes': probed_parents, 'private_port': runner.port,
           'arms': complete['arms'], 'passed': True, 'batch_allocated': False,
           'gpu_lock_taken': False, 'service_started': False, 'requests_sent': False,
           'formal_round_created': False,
           'timestamp': subprocess.check_output(['date', '+%Y-%m-%d %H:%M'], text=True).strip()}
    with target.open('x', encoding='utf-8') as stream:
        json.dump(doc, stream, indent=2); stream.write('\n')
    target.chmod(0o444)
    print(json.dumps(doc), flush=True)
    return doc


def filedry(card):
    """Linux CPU-only controller/child receipt and listener-cleanup proof."""
    if sys.platform != 'linux': raise RuntimeError('Linux CPU FILEdry required')
    rid, commit, adapter = SPECS[card]
    root=DEV/'evidence_cpu_filedry_v7'
    if root.exists(): raise RuntimeError('FILEdry receipt already exists')
    root.mkdir(); receipt=root/'atomic_launch.json'
    sources=source_hashes(card)
    module = adapter_module(adapter)
    execute_source = inspect.getsource(module.CandidateRunner.execute)
    arm_source = inspect.getsource(module.CandidateRunner.run_arm)
    cold_source = (DEV / 't16_frozen_helpers_v1/cold_eq.py').read_text(encoding='utf-8')
    tax_source = (DEV / 't16_frozen_helpers_v1/ft_probe_ckpt_tax.py').read_text(encoding='utf-8')
    required_execute = ("('layer_major', True, None)", "('non_layer_major', False, [",
                        "('short', opts.rid + '-short', 2000, 128)",
                        "('chunked', opts.rid + '-chunked', 32052, 128)")
    required_arm = ("self.ready(arm)", "self.private_probe_bootstrap('cold_eq.py')",
                    "self.private_probe_bootstrap('ft_probe_ckpt_tax.py')", "tax['reps'] != 5")
    if any(token not in execute_source for token in required_execute) or any(token not in arm_source for token in required_arm):
        raise RuntimeError('frozen T16 call structure differs; do not synthesize a call count')
    if "urllib.request.urlopen(req, timeout=1800)" not in cold_source or 'REPS = ' not in tax_source:
        raise RuntimeError('frozen T16 client call sources differ; do not synthesize a call count')
    ready_calls = arm_source.count('self.ready(arm)')
    cold_probe_invocations = arm_source.count("self.private_probe_bootstrap('cold_eq.py')")
    tax_probe_invocations = arm_source.count("self.private_probe_bootstrap('ft_probe_ckpt_tax.py')")
    tax_reps = int(tax_source.split('REPS = ', 1)[1].splitlines()[0])
    tax_series = tax_source.count('first_real(') - 1  # Excludes the function definition; retains single and multi calls.
    profiles = (
        {'mode': 'layer_major', 'arms': 4, 'cold_cases_per_arm': 1},
        {'mode': 'non_layer_major', 'arms': 4, 'cold_cases_per_arm': 2},
    )
    if ready_calls != 1 or cold_probe_invocations != 1 or tax_probe_invocations != 1:
        raise RuntimeError('frozen T16 probe invocation structure is not one ready/cold/tax sequence per arm')
    for profile in profiles:
        profile['calls_per_arm'] = ready_calls + profile['cold_cases_per_arm'] + tax_probe_invocations * tax_series * tax_reps
        profile['calls'] = profile['arms'] * profile['calls_per_arm']
    planned_calls = sum(profile['calls'] for profile in profiles)
    if planned_calls != 100:
        raise RuntimeError(f'derived T16 call count {planned_calls} differs from approved full protocol 100')
    sealed={'rid':rid,'candidate_commit':commit,'adapter_sha256':sources[adapter],
            'native_provenance_sha256':hashlib.sha256((DEV/'d10_native_provenance_v2.json').read_bytes()).hexdigest(),
            'required_t16_verdict':'kept','d09_completed_terminals':'root-admission-bound-path-manifest-sha-verdict-cleanup'}
    receipt.write_text(json.dumps({'schema':'ft_d10_v7_filedry_atomic/v1','state':'launched','batch':0,**sealed})+'\n')
    arms=[]
    arm_number = 0
    for profile in profiles:
      for _ in range(profile['arms']):
        held=[]
        try:
            for _ in range(2):
                s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',0));held.append(s)
            ports=[s.getsockname()[1] for s in held]
        finally:
            for s in held:s.close()
        probe=[]
        for port in ports:
            s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',port));probe.append(s)
        for s in probe:s.close()
        arm={'arm':arm_number,'mode':profile['mode'],'calls':profile['calls_per_arm'],'listener_ports':ports,'post_cleanup_rebind':True};arms.append(arm)
        (root/f'arm_{arm_number}.json').write_text(json.dumps(arm)+'\n')
        arm_number += 1
    terminal={'schema':'ft_d10_v7_owned_filedry/v1','rid':rid,'candidate_commit':commit,'source_sha256':sources,
              'sealed_contract':sealed,'call_derivation':{'ready_per_arm':ready_calls,'cold_http_requests_per_selected_case':1,'cold_probe_invocations_per_arm':cold_probe_invocations,'tax_probe_invocations_per_arm':tax_probe_invocations,'tax_series':tax_series,'tax_reps':tax_reps,'profiles':profiles},'arms':len(arms),'calls':sum(a['calls'] for a in arms),'atomic_receipt':str(receipt),'all_listener_rebound':all(a['post_cleanup_rebind'] for a in arms),
              'gpu_started':False,'service_started':False,'http_started':False,'gpu_lock_taken':False,'formal_round_created':False,'independent_review_required':True}
    (root/'terminal.json').write_text(json.dumps(terminal,sort_keys=True,indent=2)+'\n');return root/'terminal.json'

def main(argv_in=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--filedry", action="store_true")
    parser.add_argument("--card", choices=SPECS)
    parser.add_argument("--owned-child", action="store_true")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--launch-receipt", type=Path)
    args = parser.parse_args(argv_in)
    if args.filedry:
        if args.run or args.dry_run or args.owned_child or args.batch or args.launch_receipt or not args.card: parser.error('--filedry requires only --card')
        print(filedry(args.card));return 0
    if args.dry_run:
        if args.run or not args.card or args.owned_child or args.batch or args.launch_receipt:
            parser.error('--dry-run requires only --card; no launch arguments allowed')
        file_dry_run(args.card)
        return 0
    if not args.run:
        if args.card or args.owned_child or args.batch or args.launch_receipt:
            parser.error("--run required for launch arguments")
        print(json.dumps({"schema": "ft_t16_gate_prepare/v1", "requests_sent": False,
                          "gpu_lock_taken": False, "gates": SPECS}))
        return 0
    if not args.card:
        parser.error("--card required")
    if args.owned_child:
        if args.batch is None or args.launch_receipt is None:
            parser.error("child requires batch and receipt")
        child(args.card, args.batch, args.launch_receipt)
        return 0
    if args.batch is not None or args.launch_receipt is not None:
        parser.error("controller does not accept child arguments")
    controller(args.card)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
