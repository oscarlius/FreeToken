import time
import unittest
from unittest.mock import patch
from gpu_window import bounded_restore_command

class RestoreBudget(unittest.TestCase):
    def test_expired_restore_budget_spawns_nothing(self):
        with patch('gpu_window.subprocess.Popen') as popen:
            with self.assertRaises(TimeoutError):bounded_restore_command(['python'],'unused','unused',time.time()-1,90)
        popen.assert_not_called()

    def test_expired_stop_budget_spawns_nothing(self):
        with patch('gpu_window.subprocess.Popen') as popen:
            with self.assertRaises(TimeoutError):bounded_restore_command(['python','stop_approved_restore.py'],'unused','stop481',time.time()-1,180)
        popen.assert_not_called()

if __name__=='__main__':unittest.main()
