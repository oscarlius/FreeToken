import hashlib,importlib.util,json
from pathlib import Path
P=Path(__file__).parents[1]/"t06_seed_agent_trace.py";s=importlib.util.spec_from_file_location("w",P);w=importlib.util.module_from_spec(s);s.loader.exec_module(w)
def test_each_seed_is_in_actual_first_wire_content(monkeypatch,tmp_path):
 seen=[]
 for name,seed_text in {'seed12k':'ONE','seed_45k':'TWO','seed_real':'THREE'}.items():
  seed=tmp_path/name;seed.write_text(seed_text);out=tmp_path/f'{name}.json';orig='TASK'
  class M:
   _ns={'TASK_PROMPT':orig}
   def main(self):
    prompt=self._ns['TASK_PROMPT'];seen.append(prompt);out.write_text(json.dumps({'rounds':[{'messages':[{'content':prompt}],'record':{'messages_sha':'wire'}}]}));return 0
  monkeypatch.setattr(w,'load',lambda _:M())
  assert w.main(['--seed-file',str(seed),'--client','x','--out',str(out),'--rounds','12','--max-tokens','2048'])==0
  b=json.loads(out.with_suffix('.seed_binding.json').read_text())
  assert b['seed_raw_sha256']==hashlib.sha256(seed_text.encode()).hexdigest()
 assert seen==['ONE\n\nTASK','TWO\n\nTASK','THREE\n\nTASK']
