import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('window_measure',Path(__file__).with_name('window_measure.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class CommandContract(unittest.TestCase):
    def test_only_counts_change_for_single_lane(self):
        class Old:
            @staticmethod
            def command(*args):
                return ['aiperf','profile','--request-count','2','--concurrency','2','--streaming','--use-server-token-count']
        self.assertEqual(module.measurement_command(Old,'endpoint','source','output',1,90),
                         ['aiperf','profile','--request-count','1','--concurrency','1','--streaming','--use-server-token-count'])

    def test_two_lane_command_preserved(self):
        class Old:
            @staticmethod
            def command(*args): return ['aiperf','--request-count','2','--concurrency','2']
        self.assertEqual(module.measurement_command(Old,'e','s','o',2,90),Old.command())

    def test_unapproved_load_rejected(self):
        with self.assertRaises(ValueError): module.measurement_command(None,None,None,None,3,90)

if __name__=='__main__':unittest.main()
