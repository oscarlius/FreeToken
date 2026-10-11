import hashlib, importlib.util
from pathlib import Path
import pytest

HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('parsev5',HERE/'d10_aiperf_parse_v5.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
FIXTURES=HERE/'fixtures'
def test_retained_r045_raw_extracts_ids_ttft_rate_and_counts():
 rows=m.require_original_over_30(FIXTURES/'wave1')+m.require_original_over_30(FIXTURES/'wave2')
 assert [r['completion_tokens'] for r in rows]==[46,58,46,58]
 assert all(r['request_id'] and r['ttft_ms']>0 and r['decode_tokens_per_second']>0 for r in rows)
 assert hashlib.sha256((FIXTURES/'wave1/profile_export.jsonl').read_bytes()).hexdigest()=='d251c48d6b13631070546622b05c57b08275e631b317579a2feef40fd52edb86'
 assert hashlib.sha256((FIXTURES/'wave2/profile_export.jsonl').read_bytes()).hexdigest()=='67655667cb4cdf47edcba38f06df84153242237bd26ce22090cb4cd794fa5e50'
def test_retained_real_raw_rejects_ignore_eos_256_without_fabrication():
 with pytest.raises(RuntimeError,match=r'exactly \[256, 256\]'):
  m.require_ignore_eos_256(FIXTURES/'wave1')
