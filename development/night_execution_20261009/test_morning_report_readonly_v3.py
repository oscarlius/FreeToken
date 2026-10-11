import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('report',Path(__file__).with_name('morning_report_readonly_v3.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class MorningReportCPU(unittest.TestCase):
 def fixture(self,root):
  c={'not_before':'2026-10-10T09:00:00+08:00','production_root':str(root),'observer_start_epoch':1791578948.1479154,'expected_owner':{'service':[2,3],'supervisor':[4,5]}}
  d=root/'overnight_observation';d.mkdir();row={'at':1791594000.1,'watchdog_latest':{'at':1791593970,'healthy':True},'active_owner_matches':True,'supervisor_alive':True,'service_alive':True,'monitor_alive':True,'watchdog_fresh':True,'alerts_count':0,'backend_epoch':0,'restart_attempts':0}
  first=dict(row,at=1791578948.1482558,watchdog_latest={'at':1791578897.1402504,'healthy':False})
  terminal={'at':1791594000.2,'until':c['not_before'],'samples':2,'issues':[{'sample':1}],'final':row,'classification':'requires_review','eligible_to_request_push_approval':False,'push_approved':False,'push_executed':False}
  # Real terminal intentionally DOES NOT contain until_epoch.
  (d/'terminal.json').write_text(json.dumps(terminal));(d/'samples.jsonl').write_text(json.dumps(first)+'\n'+json.dumps(row)+'\n')
  (d/'start.json').write_text(json.dumps({'at':c['observer_start_epoch'],'until':c['not_before'],'until_epoch':1791594000,'source_run':str(root),'generation_requests':0,'service_mutations':0}))
  (root/'owner.json').write_text(json.dumps({'service':{'pid':2,'start_ticks':3},'supervisor':{'pid':4,'start_ticks':5}}))
  return c,d,terminal
 def test_real_terminal_schema_without_until_epoch(self):
  with tempfile.TemporaryDirectory() as tmp:
   c,d,t=self.fixture(Path(tmp))
   with patch.object(m,'now',return_value=dt.datetime.fromisoformat('2026-10-10T09:00:01+08:00')):
    _,actual,rows,bad=m.observation(c)
   self.assertEqual(actual,t);self.assertEqual(bad['unhealthy'],1);self.assertEqual(bad['unhealthy_after_first'],0);self.assertTrue(bad['terminal_verdict_consistent'])
 def test_early_clock_refuses_even_existing_fake_terminal(self):
  with tempfile.TemporaryDirectory() as tmp:
   c,d,t=self.fixture(Path(tmp))
   with patch.object(m,'now',return_value=dt.datetime.fromisoformat('2026-10-10T08:59:59+08:00')):
    with self.assertRaisesRegex(RuntimeError,'wall-time'):m.observation(c)
 def test_missing_terminal_refuses(self):
  with tempfile.TemporaryDirectory() as tmp:
   c,d,t=self.fixture(Path(tmp));(d/'terminal.json').unlink()
   with patch.object(m,'now',return_value=dt.datetime.fromisoformat('2026-10-10T09:00:01+08:00')):
    with self.assertRaisesRegex(RuntimeError,'absent'):m.observation(c)
 def test_wrong_final_refuses(self):
  with tempfile.TemporaryDirectory() as tmp:
   c,d,t=self.fixture(Path(tmp));t['final']['alerts_count']=5;(d/'terminal.json').write_text(json.dumps(t))
   with patch.object(m,'now',return_value=dt.datetime.fromisoformat('2026-10-10T09:00:01+08:00')):
    with self.assertRaisesRegex(RuntimeError,'final differs'):m.observation(c)
 def test_anomalies_never_replaced_with_healthy(self):
  rows=[{'at':1,'watchdog_latest':None,'backend_epoch':None,'restart_attempts':None},{'at':2,'watchdog_latest':{'healthy':False},'backend_epoch':1,'restart_attempts':1,'alerts_count':2}]
  actual=m.summarize(rows);self.assertEqual(actual['unhealthy_after_first'],1);self.assertEqual(actual['alerts_max'],2);self.assertEqual(actual['active_owner_matches_failures'],2);self.assertIn(None,actual['epochs'])
 def test_urls_remove_credentials(self):
  self.assertEqual(m.clean_url('https://SECRET@example.com/a.git?token=SECRET'),'https://example.com/a.git')
  self.assertEqual(m.clean_url('SECRET@example.com:a.git'),'example.com:a.git')
 def test_exclusive_preserves_existing_bytes(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'existing';p.write_text('preserve')
   with self.assertRaises(FileExistsError):m.exclusive(p,'replace')
   self.assertEqual(p.read_text(),'preserve')

if __name__=='__main__':unittest.main()
