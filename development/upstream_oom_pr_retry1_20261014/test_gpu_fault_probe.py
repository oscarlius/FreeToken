import tempfile
import unittest
from pathlib import Path

from gpu_fault_probe import FaultPlan, injection_enabled, install_backend_factory_observer, observer_enabled


class ProbeTests(unittest.TestCase):
    def test_fault_plan_is_uid_epoch_and_step_selective(self):
        plan = FaultPlan()
        self.assertFalse(plan.should_inject([0], 0))
        self.assertFalse(plan.should_inject([1], 1))
        for _ in range(8):
            self.assertFalse(plan.should_inject([1], 0))
        self.assertTrue(plan.should_inject([1], 0))
        self.assertFalse(plan.should_inject([1], 0))

    def test_fault_switch_is_exact_and_observer_only_mode_does_not_enable_fault(self):
        self.assertFalse(injection_enabled({}))
        self.assertFalse(injection_enabled({"FT_PR_OOM_INJECT": "0"}))
        self.assertFalse(injection_enabled({"FT_PR_OOM_ARTIFACTS": "/tmp/artifacts"}))
        self.assertTrue(injection_enabled({"FT_PR_OOM_INJECT": "1"}))

    def test_candidate_on_controller_environment_enables_observer_and_fault(self):
        candidate_on = {
            "FT_PR_OOM_ARTIFACTS": "/tmp/candidate/native",
            "FT_UPSTREAM_NATIVE_IDS": "/tmp/candidate/native",
            "FT_PR_OOM_INJECT": "1",
        }
        self.assertTrue(observer_enabled(candidate_on))
        self.assertTrue(injection_enabled(candidate_on))

    def test_factory_observer_records_epochs_without_changing_factory_call(self):
        class Process:
            pid = 9
        class Handle:
            processes = [Process()]
        class Api:
            @staticmethod
            def run_api_server(config, factory, run_shell):
                return factory(3)
        with tempfile.TemporaryDirectory() as directory:
            install_backend_factory_observer(Api, directory)
            Api.run_api_server(None, lambda epoch: Handle(), False)
            self.assertIn('"epoch": 3', (Path(directory) / "backend_handles.jsonl").read_text())


if __name__ == "__main__":
    unittest.main()
