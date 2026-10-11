"""Replay the frozen T10 business trace using ordinary SSE with API UID binding."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ORIGINAL_SHA = '332a1870378d5bffa4891180280060e70f6135b6acff21b48603a5fc98ad44d9'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def replay(original_path, trace, output, base_url, model, phase, timeout=1800):
    original_path, trace, output = map(Path, (original_path, trace, output))
    if output.exists() or output.is_symlink():
        raise RuntimeError('T10 replay output already exists')
    if original_path.is_symlink() or hashlib.sha256(original_path.read_bytes()).hexdigest() != ORIGINAL_SHA:
        raise RuntimeError('T10 frozen business replay source differs')
    original = load(original_path, 't10_frozen_business_replay')
    adapter = load(Path(__file__).with_name('r049_t21_ordinary_adapter_v2.py'), 't10_ordinary_transport')
    receipts = []
    original_write = original.write_json
    directory = output.with_suffix('.requests')
    directory.mkdir(parents=True, exist_ok=False)

    def post_events(url, payload, request_timeout):
        index = len(receipts)
        payload_path = directory / f'{index:02d}.payload.json'
        api_path = directory / f'{index:02d}.api.json'
        with payload_path.open('x', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False)
        api = adapter.ordinary_stream_request(base_url, payload_path, api_path, request_timeout)
        receipts.append({'uid': api['uid'], 'api': str(api_path),
                         'api_sha256': adapter.sha(api_path), 'payload': str(payload_path),
                         'payload_sha256': adapter.sha(payload_path), 'sse_sha256': api['sse_sha256']})
        for line in Path(api['sse']).read_text(encoding='utf-8').splitlines():
            if line.startswith('data:') and line[5:].strip() != '[DONE]':
                yield json.loads(line[5:].strip())

    def write(path, document):
        rows = document.get('rounds', [])
        if len(rows) != 12 or len(rows) != len(receipts):
            raise RuntimeError('T10 ordinary UID count differs from twelve replay requests')
        for row, receipt in zip(rows, receipts):
            if row.get('error') is not None or row.get('dry_run'):
                raise RuntimeError('T10 ordinary replay request did not complete')
            row.update(receipt, transport='ordinary_sse_no_ft_dev_ack')
        document['ordinary_request_bindings'] = receipts
        return original_write(path, document)

    original.post_events = post_events
    original.write_json = write
    original.REPLAY_MAX_TOKENS = 200
    args = argparse.Namespace(trace=str(trace), out=str(output), base_url=base_url,
                              model=model, thinking='auto', rounds=None,
                              edit_at_idx=None, edit_text=None, dry_run=False,
                              timeout=timeout, fresh_note=f'E2-R044-{phase}-real')
    return original.cmd_replay(args)


def main(argv=None):
    parser = argparse.ArgumentParser()
    for key in ('original', 'trace', 'out'):
        parser.add_argument('--' + key, type=Path, required=True)
    for key in ('base-url', 'model', 'phase'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args(argv)
    return replay(args.original, args.trace, args.out, args.base_url, args.model, args.phase)


if __name__ == '__main__':
    raise SystemExit(main())
