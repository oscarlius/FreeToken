import importlib.util,json
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent
def mod(name):
 s=importlib.util.spec_from_file_location(name,HERE/f'{name}.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
p=mod('d10_aiperf_parse_v6');d=mod('d10_prototype_owned_parent_v6')
def test_real_r045_parses_but_speed_gate_is_per_request_not_output_length():
 rows=p.parse_profile(HERE/'fixtures/wave1');assert [x['completion_tokens'] for x in rows]==[46,58]
 with pytest.raises(RuntimeError,match='decode speed'):p.original_gate(HERE/'fixtures/wave1')
def test_eos_short_output_is_valid_parse_schema(tmp_path):
 raw=json.loads((HERE/'fixtures/wave1/profile_export.jsonl').read_text().splitlines()[0]);raw['metrics']['usage_completion_tokens']['value']=1;raw['metrics']['output_token_count']['value']=1
 (tmp_path/'profile_export.jsonl').write_text(json.dumps(raw)+'\n');assert p.parse_profile(tmp_path)[0]['completion_tokens']==1
def test_filedry_is_v6_not_old_body():
 x=d.filedry();assert x['entrypoint']=='d10_prototype_owned_parent_v6.py';assert x['plan']['budget']['aiperf_calls']==8
