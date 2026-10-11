"""AIPerf 0.11 raw ``profile_export.jsonl`` reader for D10 evidence."""
from __future__ import annotations
import json
from pathlib import Path

SCHEMA='aiperf-profile-export/0.11'

def value(metrics: dict, name: str):
    field=metrics.get(name)
    if not isinstance(field,dict) or not isinstance(field.get('value'),(int,float)):
        raise RuntimeError('raw AIPerf metric missing or invalid: '+name)
    return field['value']

def parse_profile(directory: Path) -> list[dict]:
    """Read only AIPerf 0.11 profile exports, one exact record per request ID."""
    records=[]
    for path in directory.rglob('profile_export.jsonl'):
        for line in path.read_text(encoding='utf-8').splitlines():
            raw=json.loads(line); metadata=raw.get('metadata'); metrics=raw.get('metrics')
            if not isinstance(metadata,dict) or not isinstance(metrics,dict):
                raise RuntimeError('not an AIPerf profile_export record')
            request_id=metadata.get('x_request_id')
            if not isinstance(request_id,str) or not request_id: raise RuntimeError('raw AIPerf request ID missing')
            completion=value(metrics,'usage_completion_tokens')
            output=value(metrics,'output_token_count')
            if int(completion)!=completion or int(output)!=output or int(completion)!=int(output):
                raise RuntimeError('AIPerf completion/output count mismatch')
            records.append({'request_id':request_id,'completion_tokens':int(completion),
                            'ttft_ms':float(value(metrics,'time_to_first_token')),
                            'decode_tokens_per_second':float(value(metrics,'output_token_throughput_per_user'))})
    unique={row['request_id']:row for row in records}
    if len(unique)!=len(records): raise RuntimeError('duplicate AIPerf request ID')
    return records

def require_original_over_30(directory: Path) -> list[dict]:
    rows=parse_profile(directory)
    if len(rows)!=2 or any(row['completion_tokens']<=30 for row in rows):
        raise RuntimeError('original profile requires exactly two raw responses each > 30 tokens')
    return rows

def require_ignore_eos_256(directory: Path) -> list[dict]:
    rows=parse_profile(directory)
    if len(rows)!=2 or [row['completion_tokens'] for row in rows] != [256,256]:
        raise RuntimeError('ignore-EOS profile requires exactly [256, 256] raw completion counts')
    return rows

def validate_profiles(root: Path) -> dict:
    return {0:require_original_over_30(root/'profile0'),1:require_original_over_30(root/'profile1'),
            2:require_ignore_eos_256(root/'profile2'),3:require_ignore_eos_256(root/'profile3')}
