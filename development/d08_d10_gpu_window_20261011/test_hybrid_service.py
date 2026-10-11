import unittest
from unittest.mock import patch
from types import SimpleNamespace
from hybrid_service import expected_argv,capture_birth,require_master_context

class ArgvGate(unittest.TestCase):
    def test_only_prefix_and_strategy_change(self):
        baseline=['taskset','-c','1,3-47','ft','serve','--port','8095','--moe-strategy','offload','--mamba-host-slots','0']
        self.assertEqual(expected_argv(baseline),['numactl','--interleave=all','taskset','-c','1,3-23,25,27-47','ft','serve','--port','8095','--moe-strategy','hybrid','--mamba-host-slots','0'])
        self.assertEqual(baseline[8],'offload')

    def test_unknown_prefix_rejected(self):
        with self.assertRaises(ValueError):expected_argv(['taskset','-c','0','ft','serve','--moe-strategy','offload'])

    def test_baseline_strategy_must_be_offload(self):
        with self.assertRaises(ValueError):expected_argv(['taskset','-c','1,3-47','ft','serve','--moe-strategy','hybrid'])

    def test_missing_birth_uses_fresh_private_session_proof(self):
        d07=SimpleNamespace(process_identity=lambda pid:None)
        with patch('hybrid_service.os.getpgid',return_value=123,create=True),patch('hybrid_service.os.getsid',return_value=123,create=True):
            proof=capture_birth(SimpleNamespace(pid=123),d07)
        self.assertEqual(proof['pgid'],123)
        self.assertIsNone(proof['start_ticks'])

    def test_foreign_group_not_claimed_after_missing_birth(self):
        d07=SimpleNamespace(process_identity=lambda pid:None)
        with patch('hybrid_service.os.getpgid',return_value=999,create=True),patch('hybrid_service.os.getsid',return_value=123,create=True):
            with self.assertRaises(RuntimeError):capture_birth(SimpleNamespace(pid=123),d07)

    def test_direct_import_cannot_start_hybrid_component(self):
        with self.assertRaisesRegex(RuntimeError,'actual GPU master entry'):
            require_master_context({},9999999999,None)

if __name__=='__main__':unittest.main()
