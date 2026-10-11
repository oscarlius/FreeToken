"""Fail-closed runtime for the independently versioned T17/T20 continuation runner."""
from __future__ import annotations
import hashlib, json, os, re, subprocess
from pathlib import Path
from types import SimpleNamespace

SHA = re.compile(r"[0-9a-f]{40}$")
REQUIRED_SOURCE_FILES=("t17_continuation_runner.py","t17_d14_runner.py","t17_d14_gpu.py","t17_d14_artifacts.py","t17_d14_observe.py","t16_full_tail_base_runner.py","t17_operator_observe.py","t17_operator_startup.py","t17_continuation_launch.py","t17_owned_launch_protocol.py","t17_continuation_runner_v2.py","t17_continuation_runtime_v2.py","t17_continuation_selection.py","t17_continuation_launch_v2.py","batchNN_T20_v2.sh")
GENERATED_SOURCE_FILES = ("t17_d14_startup.py", "t17_d14_exact_ids.py")
class RuntimeErrorV2(ValueError): pass

def _sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def _load(path: Path) -> dict:
    if path.is_symlink() or not path.is_file(): raise RuntimeErrorV2("regular evidence file required")
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise RuntimeErrorV2("evidence object required")
    return value
def _frozen(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o222: raise RuntimeErrorV2("sealed read-only file required")

def _source_file(root: Path, name: str) -> Path:
    if not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts:
        raise RuntimeErrorV2("invalid CPU source path")
    path = root / name
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise RuntimeErrorV2("source path contains a symlink")
    _frozen(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeErrorV2("CPU source path escapes root")
    return path

def verify_candidate(worktree: Path|str, candidate: str, parent: str) -> dict:
    root=Path(worktree).resolve()
    if Path(worktree).is_symlink() or not SHA.fullmatch(candidate) or not SHA.fullmatch(parent): raise RuntimeErrorV2("explicit full parent/candidate SHA and regular worktree required")
    head=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    dirty=subprocess.check_output(["git","-C",str(root),"status","--porcelain","--untracked-files=no"],text=True)
    if head != candidate or dirty: raise RuntimeErrorV2("new candidate HEAD or tracked-clean state differs")
    if subprocess.run(["git","-C",str(root),"merge-base","--is-ancestor",parent,candidate]).returncode: raise RuntimeErrorV2("declared parent is not an ancestor of candidate")
    return {"worktree":str(root),"parent_commit":parent,"candidate_commit":candidate,"clean":True}

def verify_cpu_report(report: Path|str, source_root: Path|str, *, source_review=None, source_review_sha256=None, run_kind="t17") -> dict:
    report=Path(report); root=Path(source_root); _frozen(report); value=_load(report)
    if source_review is not None:
        # Independent source readiness permits the requested test startup only.
        # It does not turn CPU replay into actual GPU/model lifecycle evidence.
        import importlib.util
        source = Path(__file__).with_name("t17_source_admission.py")
        spec = importlib.util.spec_from_file_location("ft_t17_source_startup", source)
        admission = importlib.util.module_from_spec(spec); spec.loader.exec_module(admission)
        if run_kind != "t17":
            admission = admission.for_run(run_kind)
        checked = admission.verify(report, source_review, source_review_sha256)
        if root.resolve() != source.parent.resolve() or checked.get("source_execution_ready") is not True or checked.get("model_admitted") is not False:
            raise RuntimeErrorV2("owned source-startup package required")
        return {"cpu_report":str(report),"cpu_report_sha256":_sha(report),"files":value["files"],"argv":value["argv"],"log_sha256":value["log_sha256"],"candidate_commit":value["candidate_commit"],"source_execution_ready":True,"model_admitted":False,"independent_review_sha256":checked["independent_review_sha256"]}
    if value.get("runtime_lifecycle_verified") is not True:
        raise RuntimeErrorV2("CPU dry-plan tests cannot admit execution; retained runtime lifecycle remains unverified")
    files=value.get("files")
    log = value.get("log_path")
    if value.get("verdict") != "PASS" or not isinstance(files,dict) or not files or not isinstance(value.get("argv"),list) or not isinstance(value.get("candidate_commit"),str) or not isinstance(log,str) or not isinstance(value.get("log_sha256"),str): raise RuntimeErrorV2("new CPU PASS report with source inventory, argv, candidate, and log required")
    log_path = _source_file(report.parent, log)
    if _sha(log_path) != value["log_sha256"]: raise RuntimeErrorV2("CPU report log bytes differ")
    if not set((*REQUIRED_SOURCE_FILES, *GENERATED_SOURCE_FILES)) <= set(files): raise RuntimeErrorV2("CPU report lacks required frozen source inventory")
    for name,digest in files.items():
        path = _source_file(root, name)
        if not isinstance(digest,str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None: raise RuntimeErrorV2("invalid CPU source inventory")
        if _sha(path) != digest: raise RuntimeErrorV2("CPU report source differs: "+name)
    raise RuntimeErrorV2("independent source-startup review required; a runtime boolean cannot authorize test execution")

def verify_t16(rounds: Path|str, closure: Path|str, *, rid: str, batch: int, parent: str, candidate: str) -> dict:
    import importlib.util
    directory=Path(rounds)/rid; _frozen(Path(closure)); binding=_load(Path(closure))
    if rid == 'E2-R041-gate-D17':
        # T20 startup may inspect only D04 registration metadata for an already
        # sealed prerequisite; raw R041 recomputation belongs to D04 closure.
        source=Path(__file__).with_name('d07_g3g4_prepare.py')
        spec=importlib.util.spec_from_file_location('t20_closed_round_gate',source); gate=importlib.util.module_from_spec(spec); spec.loader.exec_module(gate)
        round_json=gate.require_closed_round(rid,'kept')
        manifest=round_json.with_name('MANIFEST.sha256'); r=_load(round_json)
        if not (r.get('base',{}).get('commit')==parent and r.get('experimental',{}).get('candidate_commit')==candidate):
            raise RuntimeErrorV2('registered R041 identity differs')
        return {'round':rid,'batch':batch,'parent_commit':parent,'candidate_commit':candidate,
                'round_sha256':_sha(round_json),'manifest_sha256':_sha(manifest),
                'closure_sha256':_sha(Path(closure)),'directory':str(directory)}
    manifest=directory/"MANIFEST.sha256"; _frozen(manifest)
    declared={}
    for line in manifest.read_text().splitlines():
        digest,name=line.split("  ",1); path=directory/name.removeprefix("./")
        _frozen(path)
        if _sha(path)!=digest: raise RuntimeErrorV2("sealed manifest differs")
        declared[name.removeprefix("./")]=digest
    gate=directory/f"gate_batch{batch}.json"; review=directory/f"review_batch{batch}.json"; round_json=directory/"round.json"
    for path in (gate,review,round_json):
        _frozen(path)
        # D04 pins mutable round metadata through its immutable history and the
        # external closure receipt rather than including it in MANIFEST.sha256.
        if path != round_json and path.name not in declared: raise RuntimeErrorV2("sealed T16 evidence missing")
    r,g,i=_load(round_json),_load(gate),_load(review)
    review_passed = i.get('verdict') == 'PASS'
    if rid == 'E2-R041-gate-D17':
        result_path = directory/'result.json'; _frozen(result_path)
        raw = _load(result_path)
        if declared.get('result.json') != _sha(result_path):
            raise RuntimeErrorV2('manifest-bound R041 result required')
        warm_control = 'a9dca443cd07e1f60d1533e0a678935a09d21636'
        review_passed = (
            i.get('schema') == 'ft_d17_r041_independent_audit/v1'
            and i.get('verdict') == 'kept_pending_independent_review'
            and i.get('candidate_commit') == candidate and i.get('control_commit') == warm_control
            and i.get('result_sha256') == g.get('result_sha256') == _sha(result_path)
            and g.get('warm_control_commit') == warm_control
            and raw.get('schema') == 'ft_d17_r041/v1' and raw.get('rid') == rid
            and raw.get('candidate_commit') == candidate and raw.get('control_commit') == warm_control
            and raw.get('verdict') == 'measurements_pass_pending_independent_review'
            and raw.get('cold',{}).get('control_commit') == parent
            and raw.get('cold',{}).get('candidate_commit') == candidate
            and raw.get('cold',{}).get('passed') is True)
    if not (r.get("round_id")==rid and r.get("card")=="T16" and r.get("verdict")=="kept" and r.get("closed_at") and r.get("retractions")==[] and r.get("base",{}).get("commit")==parent and r.get("experimental",{}).get("candidate_commit")==candidate and r.get("independent_review_sha256")==_sha(review) and g.get("proposed_verdict")=="kept" and review_passed and i.get("rid")==rid and i.get("batch")==batch and g.get("parent_commit")==parent and g.get("new_commit")==candidate): raise RuntimeErrorV2("sealed kept T16/independent PASS chain differs")
    if not (directory/"round_history").is_dir() or (directory/"round_history").is_symlink(): raise RuntimeErrorV2("D04 history chain missing")
    # Delegate canonical writer SHA/history validation to the retained implementation.
    import importlib.util
    legacy_path=Path(__file__).with_name("t17_continuation_runner.py")
    spec=importlib.util.spec_from_file_location("ft_t17_v2_d04",legacy_path); legacy=importlib.util.module_from_spec(spec); spec.loader.exec_module(legacy)
    legacy.d04_check(directory)
    expected={"round":rid,"batch":batch,"parent_commit":parent,"candidate_commit":candidate,"round_sha256":_sha(round_json),"gate_sha256":_sha(gate),"review_sha256":_sha(review),"manifest_sha256":_sha(manifest)}
    if any(binding.get(k)!=v for k,v in expected.items()): raise RuntimeErrorV2("closure receipt is not pinned to sealed T16 chain")
    return expected | {"closure_sha256":_sha(Path(closure)),"directory":str(directory)}

def _validate_case_choices(plan: dict, cases_by_name: dict) -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("t17_selection_execution", Path(__file__).with_name("t17_continuation_selection.py"))
    selection = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selection)
    inputs = Path(plan["inputs"])
    _frozen(inputs)
    document = selection.load_realinput28(inputs)
    if _sha(inputs) != plan["inputs_sha256"]:
        raise RuntimeErrorV2("input bytes changed after planning")
    declared = plan["selection"]
    proof = declared.get("d17_tree_proof")
    options = {} if proof is None else {"d17_worktree": proof["git_worktree"], "d17_base": proof["base_commit"], "d17_candidate": proof["candidate_commit"]}
    r041 = declared.get('r041_proof')
    if r041 is not None:
        if not isinstance(r041, dict) or not isinstance(r041.get('verification_inputs'), dict):
            raise RuntimeErrorV2('complete R041 raw-verification inputs required at execution')
        options.update(r041['verification_inputs'])
    retained = declared.get("retained_review")
    if retained is not None:
        if not isinstance(retained, dict):
            raise RuntimeErrorV2("complete retained-case review required at execution")
        options.update({"resume_review": retained.get("review"),
                        "resume_review_sha256": retained.get("review_sha256"),
                        "target_candidate": plan["candidate"]["candidate_commit"]})
    chosen = selection.select(document, run_kind=declared["run_kind"], cases=declared["case_mode"],
                              envelope_cases=declared["envelope_mode"], assigned_rid=plan["rid"],
                              d14_baseline_receipt=declared.get("d14_baseline_receipt"), **options)
    expected = [{"name": name, "input_ids_sha256": chosen["case_input_sha256"][name],
                 "allow_cold_envelope": name in chosen["ordinary_cold_envelope_cases"]}
                for name in chosen["measurement_cases"]]
    actual_cases = {row["name"]: row for row in document["cases"]}
    if chosen != declared or expected != plan["case_choices"] or cases_by_name != actual_cases:
        raise RuntimeErrorV2("case selection changed or caller substituted input IDs")


def execute(plan: dict, *, cases_by_name: dict, sealed_preflight: Path|str, run_kind: str="t17") -> dict:
    """Run through the retained lifecycle after revalidating a sealed preflight.

    The legacy module is loaded under a unique name, so these mutable bindings are
    process-scoped and never patch the frozen source module or another runner.
    """
    receipt=Path(sealed_preflight); _frozen(receipt)
    if _load(receipt) != plan or plan.get("execution_ready") is not True or plan.get("admitted") is not False:
        raise RuntimeErrorV2("execution requires the exact sealed preflight; it is never model admission")
    paths=plan.get("preflight_paths",{})
    if not isinstance(paths,dict): raise RuntimeErrorV2("sealed preflight paths required")
    cpu=verify_cpu_report(paths["cpu_report"],paths["source_root"],source_review=paths.get("source_review"),source_review_sha256=paths.get("source_review_sha256"),run_kind=run_kind)
    source_root = Path(paths["source_root"]).resolve()
    expected_report = source_root.parent / "startup_cpu_report.json" if cpu.get("source_execution_ready") is True else source_root / "cpu_validation.json"
    if source_root != Path(__file__).resolve().parent or Path(paths["cpu_report"]).resolve() != expected_report:
        raise RuntimeErrorV2("execution must load its own frozen source and CPU archive")
    candidate=verify_candidate(plan["candidate"]["worktree"],plan["candidate"]["candidate_commit"],plan["candidate"]["parent_commit"])
    if cpu["candidate_commit"] != candidate["candidate_commit"]: raise RuntimeErrorV2("CPU report candidate differs from sealed candidate")
    prior=verify_t16(paths["rounds"],paths["closure_binding"],rid=plan["prior_t16"]["round"],batch=plan["prior_t16"]["batch"],parent=candidate["parent_commit"],candidate=candidate["candidate_commit"])
    if prior != plan["prior_t16"]: raise RuntimeErrorV2("sealed T16 prerequisite changed")
    if plan.get("run_kind", plan.get("selection", {}).get("run_kind")) != run_kind:
        raise RuntimeErrorV2("run kind differs from sealed selection")
    _validate_case_choices(plan, cases_by_name)
    if plan.get("cpu") != cpu or plan.get("candidate") != candidate:
        raise RuntimeErrorV2("sealed CPU/candidate binding changed")
    if plan.get('t20_full') is not None:
        if run_kind != 't20' or plan['rid'] != 'E2-R040':
            raise RuntimeErrorV2('full measurement callback requires the actual T20 round')
        selection = plan.get('selection', {})
        sample4 = selection.get('case_mode') == 't20-sample4' and selection.get('measurement_cases') == ['prefix-8192-tail-65', 'prefix-12416-tail-4097', 'prefix-12736-tail-8193', 'prefix-18944-tail-4097'] and selection.get('r041_proof') is not None
        explicit_all = selection.get('case_mode') == 'all' and selection.get('selection_reason') == 't20_explicit_all28' and len(selection.get('measurement_cases', ())) == 28
        if not (sample4 or explicit_all):
            raise RuntimeErrorV2('actual T20 sample4 preflight requires registered R041/R038 closure; diagnostic all28 cannot launch')
        for name in ('t20_measurements.py', 'e2_runtime.py', 't00_runner.py', 't08_runner.py', 't16_runner.py',
                     'd16_native_process_collection.py', 'd16_service_workloads.py',
                     'd16_exact_service_startup.py', 'equiv_suite/native_workloads.py',
                     'batchNN_E2-R040.sh', 'batchNN_E2-R040_continuation_v3.sh'):
            if cpu['files'].get(name) != _sha(_source_file(source_root, name)):
                raise RuntimeErrorV2('full T20 execution source missing or changed: ' + name)
        full = plan['t20_full']
        _frozen(Path(full['d16_source_review']))
        if _sha(Path(full['d16_source_review'])) != full['d16_source_review_sha256']:
            raise RuntimeErrorV2('full T20 D16 review changed before execution')
    directory=Path(plan["directory"])
    rounds_root = Path(paths["rounds"])
    if directory != rounds_root / plan["rid"] or directory.resolve().parent != rounds_root.resolve():
        raise RuntimeErrorV2("output must be the assigned canonical round directory")
    if directory.exists() or directory.is_symlink(): raise RuntimeErrorV2("exclusive output directory must not exist")
    import importlib.util, sys
    runner_path=Path(__file__).with_name("t17_continuation_runner.py")
    if runner_path.resolve() != source_root / "t17_continuation_runner.py":
        raise RuntimeErrorV2("legacy runner is outside the verified execution archive")
    spec=importlib.util.spec_from_file_location("ft_t17_v2_legacy_runner",runner_path)
    if spec is None or spec.loader is None: raise RuntimeErrorV2("legacy lifecycle import unavailable")
    old=importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
    return _execute_lifecycle(old, plan, cases_by_name=cases_by_name, run_kind=run_kind, owned_helpers=True)


def _execute_lifecycle(old, plan: dict, *, cases_by_name: dict, run_kind: str, owned_helpers: bool=False):
    """Retained orchestration, shared with isolated CPU fixture tests.

    Production callers must use execute() and its validated preflight. CPU replay
    calls this private helper with a test-only backend in an isolated process.
    """
    directory = Path(plan["directory"])
    candidate=plan["candidate"]
    old.WT=Path(candidate["worktree"]); old.PARENT=candidate["parent_commit"]; old.CANDIDATE=candidate["candidate_commit"]
    old.T16_RID=plan["prior_t16"]["round"]; old.T16_BATCH=plan["prior_t16"]["batch"]
    actual_gpu, actual_artifacts=old._imports()
    if owned_helpers:
        import importlib.util
        spec=importlib.util.spec_from_file_location("ft_t17_owned_helpers",Path(__file__).with_name("d17_frozen_helpers.py"))
        helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
        helpers.bind_protocol(actual_gpu.protocol,Path(__file__).parent/"helpers")
    actual_gpu.WT=old.WT; actual_gpu.helper.PARENT=old.PARENT; actual_gpu.helper.CANDIDATE=old.CANDIDATE; actual_gpu.helper.T16_RID=old.T16_RID; actual_gpu.helper.T16_BATCH=old.T16_BATCH
    if run_kind not in ("t17", "t20"):
        raise RuntimeErrorV2("unknown continuation run kind")
    class TaggedObservedRun(actual_gpu.Run):
        def set_status(self, **values):
            return actual_gpu.protocol['Runner'].set_status(
                self, rid=self.options.rid, card=run_kind.upper(), **values)

        def lock_take(self):
            # Preserve the retained exclusive resource-lock protocol, including
            # its exact token/inode ownership checks, with the actual card label.
            import time
            self.token = json.dumps({'owner': self.options.rid, 'card': run_kind.upper(),
                                     'pid': os.getpid(), 'since': time.strftime('%F %T %Z')})
            descriptor = os.open(actual_gpu.protocol['LOCK'], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            with os.fdopen(descriptor, 'w') as stream:
                stream.write(self.token)
            self.lock_inode = actual_gpu.protocol['LOCK'].stat().st_ino
    actual_gpu.Run = TaggedObservedRun
    selected={row["name"]:row["allow_cold_envelope"] for row in plan["case_choices"]}
    _,_,real_continuation=old._suite_modules(old.WT)
    class SelectedContinuation:
        def run_case(self, resources, case):
            resources.allow_cold_envelope=selected[case["name"]]
            return real_continuation.run_case(resources,case)
    from types import SimpleNamespace
    options=SimpleNamespace(rid=plan["rid"],batch=plan["batch"],directory=directory,run=True,gate=run_kind.upper(),inputs=Path(plan["inputs"]),input_provenance=plan["input_provenance"],execution_archive=plan["execution_archive"],diagnostic_producer=None)
    full = plan.get('t20_full')
    if full is not None:
        if run_kind != 't20' or plan['rid'] != 'E2-R040':
            raise RuntimeErrorV2('full measurement callback requires the actual T20 round')
        import importlib.util
        component_path = Path(__file__).with_name('t20_measurements.py')
        spec = importlib.util.spec_from_file_location('ft_t20_actual_measurements', component_path)
        component = importlib.util.module_from_spec(spec); spec.loader.exec_module(component)
        def after_cases(base):
            if _sha(options.inputs) != plan['inputs_sha256']:
                raise RuntimeErrorV2('full T20 real input source changed during continuation')
            return component.run_full_measurements(base, candidate_commit=candidate['candidate_commit'],
                realinputs=_load(options.inputs), d16_wrapper=component_path.with_name('d16_exact_service_startup.py'),
                d16_source_review=full['d16_source_review'], d16_source_review_sha256=full['d16_source_review_sha256'])
        options.after_cases = after_cases
    instance=old.Run(options,gpu=actual_gpu,artifacts=actual_artifacts,continuation=SelectedContinuation())
    result=instance.execute([cases_by_name[row["name"]] for row in plan["case_choices"]],plan["prior_t16"],run=True)
    if getattr(instance.base,"proc",None) is not None: raise RuntimeErrorV2("legacy lifecycle returned while child process remains alive")
    result["run_kind"]=run_kind; result["selection_schema"]=plan["selection"]["schema"]
    if plan.get("retained_source_commit") is not None:
        result["retained_source_commit"] = plan["retained_source_commit"]
        result["measurement_scope"] = "remaining_cases_only"
        result["all28_accepted"] = False
    with (directory / 'v2_result.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, sort_keys=True, allow_nan=False)
    return result
