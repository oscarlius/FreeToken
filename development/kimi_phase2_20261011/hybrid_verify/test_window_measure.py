import importlib.util
from pathlib import Path
import unittest
import tempfile

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

    def test_single_input_preserves_frozen_crlf_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'frozen.jsonl';target=Path(directory)/'lane0.jsonl'
            source.write_bytes(b'{"text":"lane0"}\r\n{"text":"lane1"}\r\n')
            module.copy_lane0_exact(source,target)
            self.assertEqual(target.read_bytes(),b'{"text":"lane0"}\r\n')

if __name__=='__main__':unittest.main()
