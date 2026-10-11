"""Test-private CPU replay of the actual retained continuation lifecycle."""
from __future__ import annotations
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    sys.modules[name] = obj
    spec.loader.exec_module(obj)
    return obj


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--scenario', choices=('success', 'request_error', 'stop_error'), required=True)
    args = parser.parse_args()
    stage = args.stage.resolve()
    assert stage.is_relative_to(Path('/data2/FreeToken/runs/dev_D16'))
    assert os.environ.get('CUDA_VISIBLE_DEVICES') == ''
    sources = stage / 'source_tools'
    admission = module('retained_fixture_admission', sources / 't17_source_admission.py')
    retained = admission.RETAINED_FIXTURE_ROOT
    admission._verify_snapshot(stage)
    snapshot = retained / 'snapshot'
    fixture = json.loads((retained / 'fixture_manifest.json').read_text())
    assert fixture['fixture_only'] is True and fixture['admitted'] is False
    sys.path.insert(0, str(sources))
    runtime = module('fixture_v2_runtime', sources / 't17_continuation_runtime_v2.py')
    old = module('fixture_legacy_runner', sources / 't17_continuation_runner.py')
    old.HERE = sources
    old.TOOLS = sources / 'equiv_suite'
    gpu, artifacts = old._imports()
    inherited = gpu.Run
    protocol = gpu.protocol
    runner_globals = protocol['Runner'].__init__.__globals__
    fake_lock = stage / (args.scenario + '.cpu_fixture.lock')
    assert fake_lock != Path('/data2/_shared/gpu.lock')
    protocol['LOCK'] = fake_lock
    runner_globals['LOCK'] = fake_lock
    runner_globals['SCR'] = sources / 'helpers'
    launcher = module('fixture_owned_stop', sources / 't17_owned_launch_protocol.py')
    manifest = fixture['snapshot_files']
    inputs = json.loads((snapshot / 'real_inputs.json').read_text())
    case = next(row for row in inputs['cases'] if row['name'] == 'prefix-8192-tail-65')
    calls = []
    instances = []

    class ReplayRun(inherited):
        def __init__(self, options):
            super().__init__(options)
            instances.append(self)

        def service(self, name, operation, *, schedule=None, health_only=False):
            assert health_only is True
            arm = snapshot / name.replace('-', '_')
            assert arm.is_dir()
            self.case_arms[name] = arm
            if schedule is not None:
                assert schedule.is_file() and not schedule.stat().st_mode & 0o222
            self.proc = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],
                                         env=dict(os.environ, CUDA_VISIBLE_DEVICES=''),
                                         start_new_session=True)
            identity = old._suite_modules()[2]._proc_identity(self.proc.pid)
            calls.append({'kind': 'cpu_service', 'arm': name, 'identity': identity})
            self.set_status(state='loading', arm=name, service_pid=self.proc.pid, fixture_only=True)
            try:
                self.set_status(state='probing', arm=name, service_pid=self.proc.pid, fixture_only=True)
                return operation(arm)
            finally:
                self.stop()

        def request(self, arm, label, ids, cached, max_tokens):
            relative = (arm / (label+'.json')).relative_to(snapshot).as_posix()
            assert old.sha(arm / (label+'.json')) == manifest[relative]['sha256']
            evidence = artifacts.request_evidence(arm, label, cached, max_tokens)
            assert evidence['input_ids'] == ids and len(evidence['tokens']) == max_tokens
            calls.append({'kind': 'raw_request', 'arm': arm.name, 'label': label,
                          'source_sha256': manifest[relative]['sha256']})
            if args.scenario != 'success' and label == 'hit':
                raise RuntimeError('fixture request failure after actual raw validation')
            return evidence['response']

        def stop(self):
            if self.proc is None:
                return
            if args.scenario == 'stop_error':
                calls.append({'kind': 'stop_failed', 'pid': self.proc.pid})
                raise RuntimeError('fixture stop failure while owned CPU process remains alive')
            process = self.proc
            launcher.stop_owned_process(process, term_timeout=5, kill_timeout=5)
            process.wait(timeout=5)
            assert not launcher.owned_group_alive(process.pid)
            calls.append({'kind': 'cpu_stop', 'pid': process.pid, 'group_dead': True})
            self.proc = None

    gpu.Run = ReplayRun
    old._imports = lambda: (gpu, artifacts)
    prior = runtime.verify_t16('/data2/_shared/runs/ft_rounds',
                              '/data2/FreeToken/runs/dev_D14/r032_closure_binding_20261005.json',
                              rid='E2-R032-gate-D14', batch=60,
                              parent='e4f32022a5aa4d8734d87d9f6eb15e98c1edde42',
                              candidate='e45e2c2115f7321ac2adf7b365cb6bcbfa89acd7')
    cpu_archive = json.loads((sources / 'cpu_validation.json').read_text())
    directory = stage / ('replay_'+args.scenario)
    plan = {'fixture_only': True, 'admitted': False, 'rid': 'CPU-REPLAY-'+args.scenario,
            'batch': 1, 'directory': str(directory), 'candidate': {
                'worktree': '/data2/FreeToken/wt/e2d14-schedule',
                'parent_commit': prior['parent_commit'], 'candidate_commit': prior['candidate_commit']},
            'prior_t16': prior, 'inputs': str(snapshot / 'real_inputs.json'),
            'input_provenance': {'fixture_only': True, 'source_model_round': 'E2-R034a'},
            'execution_archive': {'files': cpu_archive['files']},
            'selection': {'schema': 'ft_v2_cpu_replay_selection/v1'},
            'case_choices': [{'name': case['name'], 'allow_cold_envelope': True}]}
    failed = False
    try:
        result = runtime._execute_lifecycle(old, plan, cases_by_name={case['name']: case}, run_kind='t20')
        assert args.scenario == 'success'
        assert result['admitted'] is False
        assert len(result['cases']) == 1
        assert (directory / 'source_tools/cpu_validation.json').is_file()
        assert (directory / 'schedules' / case['name'] / 'schedule.json').is_file()
        assert (directory / 'v2_result.json').is_file()
        status = json.loads((directory / 'status_batch1.json').read_text())
        assert status['card'] == status['gate'] == 'T20'
        assert len([row for row in calls if row['kind'] == 'cpu_service']) == 4
        assert len([row for row in calls if row['kind'] == 'cpu_stop']) == 4
        raw_case = json.loads((directory / 'cases' / (case['name']+'.json')).read_text())
        assert raw_case['operator_evidence']['reference_repeat']['equal'] is True
        assert raw_case['ordinary_cold_envelope']['recorded'] is True
    except RuntimeError as error:
        assert args.scenario != 'success' and 'fixture' in str(error)
        failed = True
        assert (directory / 'failed_harness.json').is_file()
        assert json.loads((directory / 'status_batch1.json').read_text())['state'] == 'failed'
    instance = instances[0]
    if args.scenario == 'stop_error':
        assert failed and instance.proc is not None and fake_lock.exists()
        assert launcher.owned_group_alive(instance.proc.pid)
        # Recovery operates only on the directly spawned, reserved CPU child.
        process = instance.proc
        launcher.stop_owned_process(process, term_timeout=5, kill_timeout=5)
        process.wait(timeout=5)
        assert not launcher.owned_group_alive(process.pid)
        calls.append({"kind": "cpu_stop", "pid": process.pid, "group_dead": True, "recovered_after_stop_error": True})
        instance.proc = None
        instance.lock_release()
    assert instance.proc is None and not fake_lock.exists()
    assert len({row['identity']['execution_id'] for row in calls if row['kind']=='cpu_service'}) == len([row for row in calls if row['kind']=='cpu_service'])
    report = {'scenario': args.scenario, 'fixture_only': True, 'admitted': False,
              'gpu_started': False, 'requests_sent': False, 'source_model_round': 'E2-R034a',
              'original_model_generation': False, 'calls': calls, 'verdict': 'PASS'}
    (stage / (args.scenario+'_replay.json')).write_text(json.dumps(report, indent=2))
    print(json.dumps({'scenario': args.scenario, 'verdict': 'PASS', 'fixture_only': True}))


if __name__ == '__main__':
    main()
