from __future__ import annotations
import hashlib, importlib.util, json
from pathlib import Path
import tempfile, unittest, copy
HERE=Path(__file__).resolve().parents[1]
def d07_argv_sha256(argv): return hashlib.sha256(json.dumps(argv,separators=(',',':')).encode()).hexdigest()
class Retry2PacketTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.config=json.loads((HERE/'RETRY2_CONFIG_CPU_ONLY.json').read_text());cls.packet=json.loads((HERE/'RETRY2_PREPARED_RUNNER_PACKET.json').read_text())
 def test_all_ten_rebound_argv_hashes_match_d07_algorithm(self):
  self.assertEqual(len(self.config['services']),10)
  for service in self.config['services']:
   with self.subTest(service=service['name']):
    self.assertIn('E2-R067c-d20-short-tail-retry2',json.dumps(service['argv']))
    self.assertNotIn('E2-R067c-d20-short-tail-retry1',json.dumps((service['argv'],service['env']),sort_keys=True))
    arm=f"/data2/FreeToken/runs/dev_R067/E2-R067c-d20-short-tail-retry2/services/{service['name']}"
    self.assertEqual((service['service_dir'],service['cwd']),(arm,arm))
    self.assertEqual(service['argv_sha256'],d07_argv_sha256(service['argv']))
 def test_runner_paths_hash_and_geometry_are_rebound(self):
  digest=hashlib.sha256((HERE/'RETRY2_CONFIG_CPU_ONLY.json').read_bytes()).hexdigest(); source=self.packet['child_source']
  self.assertTrue(self.packet['execution_prohibited']);self.assertEqual(self.packet['config_sha256'],digest)
  self.assertIn(f"assert sha(FD)=='{digest}'",source);self.assertIn('/development/r067c_retry2_short_tail_v1/',source);self.assertNotIn('/development/r067c_retry1_short_tail_v1/',source)
  self.assertIn("all(r['new_sequences']==1 for r in rows)",source);self.assertIn("usage']['prompt_tokens']==len(ids)",source)
  self.assertIn("not in json.dumps((service['argv'],service['env']),sort_keys=True)",source)
  self.assertLess(source.index("d07.argv_sha256(service['argv'])==service['argv_sha256']"),source.index('owner=d07.take_d07_gpu_lock'))
 def test_final_retry_contract_and_cpu_filedry(self):
  self.assertEqual(self.config['retry']['retry_index'],2);self.assertTrue(self.config['retry']['last_allowed_retry']);self.assertFalse(self.config['retry']['automatic_retry']);self.assertFalse(self.config['admission']['admit'])
  spec=importlib.util.spec_from_file_location('retry2_cpu_validate',HERE/'retry2_cpu_validate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  with tempfile.TemporaryDirectory() as temp:r=m.filedry(Path(temp)/'filedry')
  self.assertEqual((r['services'],r['calls'],r['artifacts']),(10,14,30))
  with self.assertRaises(RuntimeError):m.main(['--run'])
 def test_stale_digest_fails_shared_cpu_semantic_verifier(self):
  spec=importlib.util.spec_from_file_location('retry2_cpu_validate',HERE/'retry2_cpu_validate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  stale=copy.deepcopy(self.config);stale['services'][0]['argv_sha256']='6461108b184ad164a07537ba880f6e78df71204a96bd9c3eff6c112caa4ade44'
  with self.assertRaises(AssertionError):m.verify_service_bindings(stale)
if __name__=='__main__':unittest.main(verbosity=2)
