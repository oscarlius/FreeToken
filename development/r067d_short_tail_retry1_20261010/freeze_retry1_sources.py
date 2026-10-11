"""Create the source binding used by the retry1 CPU packet; no runtime action."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from r067d_cpu_prep import HERE, RID, SOURCE_CONFIG, sha_bytes


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def main() -> None:
    original = HERE.parent / 'r067d_short_tail_v1'
    candidate = HERE / 'frozen_candidate'
    config = json.loads(SOURCE_CONFIG.read_text())
    schedule_paths = sorted({Path(s['env']['FT_DEV_PREFILL_SCHEDULE']) for s in config['services'] if s['env'].get('FT_DEV_PREFILL_SCHEDULE')})
    paths = {
        'original_config': SOURCE_CONFIG,
        'original_packet': original / 'R067D_PREPARED_RUNNER_PACKET.json',
        'candidate_engine': candidate / 'engine.py',
        'candidate_cache': candidate / 'cache.py',
        'candidate_linear_attention': candidate / 'linear.py',
        'recorded_v1_cold_A_log': HERE / 'raw_replay/v1_cold_A_p8192_t1_serve.log',
    }
    for path in schedule_paths:
        paths[f'schedule_{path.stem}'] = HERE.parent / 'r067_d20_short_tail_v1' / 'config_v2/schedules' / path.name
    proof = {
        'schema': 'ft_r067d_retry1_source_freeze/v1',
        'rid': RID,
        'change_scope': 'scheduled cold arms omit --cache-type naive only',
        'files': {name: {'path': str(path), 'sha256': sha(path)} for name, path in paths.items()},
        'remote_candidate_paths': {
            'candidate_engine': '/data2/FreeToken/wt/d20_short_tail_v1/python/freetoken/engine/engine.py',
            'candidate_cache': '/data2/FreeToken/wt/d20_short_tail_v1/python/freetoken/scheduler/cache.py',
            'candidate_linear_attention': '/data2/FreeToken/wt/d20_short_tail_v1/python/freetoken/attention/linear.py',
        },
        'runtime_prohibited': {'gpu_started': False, 'service_started': False, 'http_generation': False},
    }
    (HERE / 'RETRY1_SOURCE_FREEZE.json').write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
