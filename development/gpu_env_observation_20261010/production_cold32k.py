"""One authorized cold32K measurement after the exact production SDK gate passes."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time
import urllib.request

PROBE = Path('/data2/FreeToken/development/d09_gpu_reapplication_20261010/protocol_t16/t16_frozen_helpers_v1/probe_ft_cold32k.py')
COMMIT = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')


def measure(run: Path, output_name: str = 'cold32k_new_environment'):
    approval = json.loads((run / 'deployment_approval.json').read_text())
    smoke = json.loads((run / 'smoke_execution_result.json').read_text())
    owner = json.loads((run / 'owner.json').read_text())
    active = json.loads(Path('/data2/FreeToken/run/production.active.json').read_text())
    assert approval['restore_commit'] == COMMIT
    assert smoke['exit_code'] == 0 and smoke['classification'] == 'passed'
    assert owner['approval_id'] == active['approval_id'] == approval['approval_id']
    assert owner['mode'] == active['mode'] == 'release'
    baseline = Path(approval['first_cold_baseline'])
    assert hashlib.sha256(baseline.read_bytes()).hexdigest() == approval['first_cold_baseline_sha256']
    ollama = json.loads(subprocess.check_output(['docker', 'inspect', 'ollama'], text=True))[0]
    assert not ollama['State']['Running'], 'ollama restoration is not authorized'
    if Path(output_name).name != output_name or output_name in ('', '.', '..'):
        raise ValueError('output_name must be a single task-owned directory name')
    directory = run / output_name
    directory.mkdir(exist_ok=False)
    now = datetime.datetime.now().astimezone().isoformat()
    cold_id = 'new-env-' + datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')
    spec = importlib.util.spec_from_file_location('frozen_cold_probe', PROBE)
    probe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    tokenizer = probe.AutoTokenizer.from_pretrained(probe.MODEL_DIR, trust_remote_code=True)
    text, built = probe.build_text(tokenizer, 32052, cold_id)
    payload = {'model': probe.MODEL, 'messages': [{'role': 'user', 'content': text}],
               'max_tokens': 128, 'temperature': 0, 'stream': True,
               'stream_options': {'include_usage': True},
               'chat_template_kwargs': {'enable_thinking': False}}
    env = {'recorded_at': now, 'uptime': subprocess.check_output(['uptime'], text=True).strip(),
           'r_threads': sum(line.strip().startswith('R') for line in subprocess.check_output(['ps', '-eLo', 'stat='], text=True).splitlines()),
           'ollama_running': False, 'production_commit': COMMIT, 'window': 98304,
           'comparison_environment': '环境不同', 'probe_sha256': hashlib.sha256(PROBE.read_bytes()).hexdigest(),
           'measurement': 'request dispatch to first nonempty delta.content; thinking disabled'}
    write_new(directory / 'environment.json', env)
    write_new(directory / 'payload.json', payload)
    request = urllib.request.Request('http://172.16.108.9:8095/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    start = time.perf_counter(); first = last = None; usage = None; finish = None
    with (directory / 'stream.jsonl').open('x', encoding='utf-8') as raw:
        with opener.open(request, timeout=300) as response:
            for line in response:
                elapsed = time.perf_counter() - start
                raw.write(json.dumps({'elapsed_s': elapsed, 'line': line.decode(errors='replace')}) + '\n')
                raw.flush()
                if elapsed > 300:
                    raise TimeoutError('cold32K exceeds 300 seconds')
                text_line = line.decode(errors='replace').strip()
                if not text_line.startswith('data:'): continue
                body = text_line[5:].strip()
                if body == '[DONE]': break
                event = json.loads(body)
                usage = event.get('usage') or usage
                for choice in event.get('choices', []):
                    finish = choice.get('finish_reason') or finish
                    if choice.get('delta', {}).get('content'):
                        if first is None: first = elapsed
                        last = elapsed
    usage = usage or {}; completion = usage.get('completion_tokens', 0)
    cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens')
    valid = cached == 0 and abs(usage.get('prompt_tokens', 0) - 32052) < 2000 and first is not None and completion >= 2
    result = {'schema': 'ft_production_cold32k_new_environment/v1', 'verdict': 'valid' if valid else 'failed_harness',
              'cold_id': cold_id, 'built_tokens': built, 'usage': usage, 'finish_reason': finish,
              'ttft_s': first, 'wall_s': time.perf_counter() - start,
              'decode_tps': (completion - 1) / (last - first) if first is not None and last > first and completion >= 2 else None,
              'comparison': {'environment': '环境不同', 'R056_ttft_s': [6.41, 6.47], 'b163_ttft_s': [7.77, 8.01]},
              'environment': env}
    write_new(directory / 'result.json', result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if valid else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--output-name', default='cold32k_new_environment')
    args = parser.parse_args()
    raise SystemExit(measure(args.run_dir, args.output_name))
