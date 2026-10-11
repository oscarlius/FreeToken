import json
from pathlib import Path
import socket
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import hybrid_service
import window_measure
import gpu_window
import d0_service
import hashlib


class Retry2Contract(unittest.TestCase):
    def test_master_requires_d0_pin(self):
        names=('gpu_window.py','hybrid_service.py','window_measure.py','d0_service.py','warmup_client.py')
        pins={str(gpu_window.HERE/name):hashlib.sha256((gpu_window.HERE/name).read_bytes()).hexdigest() for name in names}
        gpu_window.validate_controller_pins({'controller_source_pins':pins})
        del pins[str(gpu_window.HERE/'d0_service.py')]
        with patch('gpu_window.subprocess.Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'pin set'):gpu_window.validate_controller_pins({'controller_source_pins':pins})
            spawn.assert_not_called()

    def test_d0_rejects_wrong_or_missing_pin_before_spawn(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'admission.json'
            for pins in ({},{str(Path(d0_service.__file__).resolve()):'0'*64}):
                path.write_text(json.dumps({'controller_source_pins':pins}))
                with patch('d0_service.subprocess.Popen') as spawn:
                    with self.assertRaisesRegex(ValueError,'source pin'):d0_service.execute(path,time.time()+60)
                    spawn.assert_not_called()

    def test_cleanup_probe_accepts_reusable_timewait_port(self):
        sockets=[]
        class Probe:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def setsockopt(self,*args):sockets.append(('reuse',args))
            def bind(self,address):sockets.append(('bind',address))
        d07=SimpleNamespace(require_gpu_idle=lambda:None)
        with patch('hybrid_service.socket.socket',return_value=Probe()),patch('hybrid_service.subprocess.check_output',return_value=''):
            hybrid_service.idle(d07)
        self.assertEqual([x[0] for x in sockets],['reuse','bind','reuse','bind'])
        self.assertEqual(sockets[0][1],(socket.SOL_SOCKET,socket.SO_REUSEADDR,1))

    def test_warmup_uses_exact_sdk_short_long_before_measurement(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);inputs=root/'inputs.json';adapter=root/'sdk.py'
            inputs.write_text(json.dumps({'items':{'short':{'n':512},'long':{'n':8257}}}))
            adapter.write_text("def collect_one(base,model,key,item,out):\n return {'projection':{'usage':{'prompt_tokens':item['n'],'completion_tokens':128},'finish_reason':'length'}}\n")
            import hashlib
            doc={'warmup_inputs_path':str(inputs),'warmup_adapter_path':str(adapter),
                 'warmup_inputs_sha256':hashlib.sha256(inputs.read_bytes()).hexdigest(),
                 'warmup_adapter_sha256':hashlib.sha256(adapter.read_bytes()).hexdigest()}
            old=SimpleNamespace(sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest())
            with patch('window_measure.load_old',return_value=old):hybrid_service.warmup(doc,root,time.time()+10)
            receipt=json.loads((root/'warmup/terminal.json').read_text())
            self.assertTrue(receipt['not_scored'])
            self.assertEqual([x['usage']['prompt_tokens'] for x in receipt['records']],[512,8257])

    def test_d0_only_single_request_scope(self):
        old=SimpleNamespace(command=lambda *args:['aiperf','--request-count','2','--concurrency','2'])
        actual=window_measure.measurement_command(old,'url','input','output',1,60)
        self.assertEqual(actual,['aiperf','--request-count','1','--concurrency','1'])


if __name__=='__main__':unittest.main()
