"""Root-owned four-request R045 measurement on the already running release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

HERE = Path(__file__).resolve().parent
RUN = Path('/data2/FreeToken/runs/evaluation/E2-R045-aiperf-481-20261009-01-retry1')
PROD = Path('/data2/FreeToken/runs/production/DEPLOY-E2-20261009-REDEPLOY-01')
MODEL = 'Qwen3.8-Flash-Next-NVFP4'
TOKENIZER = '/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay'
AIPERF = '/data2/FreeToken/evaluation/toolchain/venv-aiperf/bin/aiperf'
INPUT_SHA = '9ac31867b8d9303b2b00109828e3e66ecd66699ce6d109dc7b11e994c8ce1cc3'
COMMIT = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'


def write(path, value):
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write('\n')


def health():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open('http://172.16.108.9:8095/health', timeout=10) as r:
        return json.load(r)


def identity():
    active = json.loads(Path('/data2/FreeToken/run/production.active.json').read_text())
    owner = json.loads((PROD / 'owner.json').read_text())
    assert active == owner and owner['commit'] == COMMIT
    assert owner['approval_id'] == PROD.name
    for key in ['service', 'supervisor']:
        item = owner[key]
        fields = Path(f"/proc/{item['pid']}/stat").read_text().rsplit(')', 1)[1].split()
        assert int(fields[19]) == item['start_ticks'] and fields[0] != 'Z'
    h = health()
    assert h['maintenance'] == 'serving' and h['backend_epoch'] == 0
    assert h['instance_id'] == '3742809b-f878-4b42-83fa-f14bbadf638b'
    assert h['restart_attempts'] == 0
    return {'owner': owner, 'health': h, 'at': time.time()}


def argv(wave):
    return [AIPERF, 'profile', '--model', MODEL, '--endpoint-type', 'chat',
            '--streaming', '--url', 'http://172.16.108.9:8095',
            '--input-file', str(HERE / 'inputs.jsonl'), '--custom-dataset-type', 'single_turn',
            '--dataset-sampling-strategy', 'sequential', '--request-count', '2',
            '--concurrency', '2', '--wait-for-model-timeout', '0',
            '--request-timeout-seconds', '300', '--no-server-metrics', '--no-gpu-telemetry',
            '--ui', 'none', '--tokenizer', 'builtin', '--use-server-token-count',
            '--use-legacy-max-tokens', '--export-level', 'raw',
            '--output-artifact-dir', str(RUN / f'wave{wave}')]


def preflight():
    assert hashlib.sha256((HERE / 'inputs.jsonl').read_bytes()).hexdigest() == INPUT_SHA
    version = subprocess.check_output([AIPERF, '--version'], text=True).strip()
    assert version == '0.11.0', version
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(TOKENIZER, local_files_only=True)
    records = [json.loads(x) for x in (HERE / 'inputs.jsonl').read_text().splitlines()]
    smoke = json.loads(Path('/data2/FreeToken/development/r065_d16_discriminate_v1/inputs.json').read_text())['items']
    prefixes = []
    for index, record in enumerate(records):
        ids = tok.apply_chat_template([{'role': 'user', 'content': record['text']}], tokenize=True, add_generation_prompt=True)
        for key, item in smoke.items():
            smoke_ids = item.get('input_ids') or tok.encode(item['prompt'], add_special_tokens=False)
            n = 0
            for a, b in zip(ids, smoke_ids):
                if a != b:
                    break
                n += 1
            assert n < 64, (index, key, n)
            prefixes.append({'record': index, 'smoke': key, 'common_tokens': n, 'cache_page_tokens': 64})
    return {'status': 'CPU_FILEDRY_PASS', 'version': version, 'inputs_sha256': INPUT_SHA,
            'prefix_check': prefixes, 'commands': [argv(1), argv(2)], 'identity': identity(),
            'authority': 'user 2026-10-09 16:30: existing production; no stop/new service/second GPU lock',
            'ceiling': {'new_services': 0, 'profiles': 2, 'generation_requests': 4,
                        'warmup_requests': 0, 'readiness_generation_requests': 0},
            'failure_policy': 'no automatic retry; root classifies first; no product retry'}


def run():
    admission = json.loads((HERE / 'ROOT_ADMISSION_RETRY1.json').read_text())
    assert admission['admit'] is True and admission['generation_ceiling'] == 4
    assert admission['runner_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    check = preflight()
    RUN.mkdir(parents=True, exist_ok=False)
    write(RUN / 'admission.json', admission)
    write(RUN / 'preflight.json', check)
    log_start = (PROD / 'serve.log').stat().st_size
    write(RUN / 'start.json', {'at': time.time(), 'log_offset': log_start})
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='', HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               NO_PROXY='172.16.108.9,127.0.0.1,localhost', no_proxy='172.16.108.9,127.0.0.1,localhost')
    rc = 0
    for wave in [1, 2]:
        write(RUN / f'wave{wave}_before.json', identity())
        write(RUN / f'wave{wave}_command.json', argv(wave))
        with (RUN / f'wave{wave}.stdout.log').open('xb') as out, (RUN / f'wave{wave}.stderr.log').open('xb') as err:
            result = subprocess.run(argv(wave), env=env, stdout=out, stderr=err, timeout=480)
        write(RUN / f'wave{wave}_exit.json', {'exit_code': result.returncode, 'at': time.time()})
        write(RUN / f'wave{wave}_after.json', identity())
        if result.returncode:
            rc = result.returncode
            break
    with (PROD / 'serve.log').open('rb') as f:
        f.seek(log_start)
        with (RUN / 'production_serve_delta.log').open('xb') as output:
            output.write(f.read())
    write(RUN / 'terminal.json', {'exit_code': rc, 'at': time.time(), 'production': identity(),
                                'classification': 'exports_pending_review' if rc == 0 else 'failed_harness'})
    return rc


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.run:
        raise SystemExit(run())
    print(json.dumps(preflight(), indent=2))
