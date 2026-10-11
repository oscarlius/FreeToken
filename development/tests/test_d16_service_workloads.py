import functools
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


ROOT = Path(__file__).parents[1]
w = load('d16_workloads', ROOT / 'd16_service_workloads.py')
helper = load('d16_retained_http', ROOT / 't17_d14_runner.py')


def test_actual_retained_http_helper_collects_two_concurrent_and_alone_repeats(tmp_path):
    lock = threading.Lock(); state = {'uid': 0, 'active': 0, 'peak': 0}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == '/internal/t17/exact-ids'
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            assert payload['max_tokens'] == 128
            with lock:
                uid = state['uid']; state['uid'] += 1
                state['active'] += 1; state['peak'] = max(state['peak'], state['active'])
            time.sleep(0.03)
            digest = hashlib.sha256(struct.pack('<%di' % len(payload['input_ids']), *payload['input_ids'])).hexdigest()
            body = json.dumps({'uid': uid, 'finished': True, 'text': 'fixture',
                               'input_ids_sha256': digest, 'usage': {'completion_tokens': 128}}).encode()
            self.send_response(200); self.end_headers(); self.wfile.write(body)
            with lock: state['active'] -= 1
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever); thread.start()
    try:
        client = functools.partial(helper.exact_id_request, 'http://127.0.0.1:' + str(server.server_port))
        root = tmp_path / 'collection'
        result = w.collect(client, [[1, 2], [3, 4]], slots=2, root=root,
                           observations_path=tmp_path / 'native_observations.jsonl')
        rows = [row for group in result['batch'] + result['alone'] for row in group]
        assert len(rows) == 8 and len({row['uid'] for row in rows}) == 8 and state['peak'] >= 2
        assert len(list((root / 'responses').glob('*.response.bin'))) == 8
        assert json.loads((root / 'collection.json').read_text())['physical_batch_verified'] is False
        assert w.finalize(result, lambda uid: {}, {'terminal': 'complete'})['verdict'] == 'unverified'
    finally:
        server.shutdown(); thread.join(); server.server_close()


def test_wrong_input_hash_preserves_failure_artifact(tmp_path):
    def incorrect(ids, **kwargs):
        return {'status': 200, 'response': {'uid': 0, 'finished': True,
                'input_ids_sha256': 'a' * 64, 'usage': {'completion_tokens': 128}}}
    with pytest.raises(w.WorkloadError, match='binding differs'):
        w.collect(incorrect, [[1]], slots=1, root=tmp_path / 'failed', observations_path=tmp_path / 'observations')
    assert list((tmp_path / 'failed/failures').glob('*.txt'))
    assert not (tmp_path / 'failed/collection.json').exists()


def test_existing_collection_is_never_overwritten(tmp_path):
    root = tmp_path / 'existing'; root.mkdir(); (root / 'keep').write_text('original')
    with pytest.raises(FileExistsError):
        w.collect(None, [[1]], slots=1, root=root, observations_path=tmp_path / 'observations')
    assert (root / 'keep').read_text() == 'original'


@pytest.mark.parametrize('mode', ['batch', 'alone'])
def test_one_arm_retained_http_collection_can_use_fresh_servers(tmp_path, mode):
    # Distinct server instances each begin at UID zero: no serial warm-up request
    # consumes a UID, and the selected mode submits exactly one pair per process.
    roots = []
    for repetition in range(2):
        state = {'uid': 0}
        lock = threading.Lock()
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                with lock:
                    uid = state['uid']; state['uid'] += 1
                digest = hashlib.sha256(struct.pack('<%di' % len(payload['input_ids']), *payload['input_ids'])).hexdigest()
                body = json.dumps({'uid': uid, 'finished': True, 'text': 'fixture',
                                   'input_ids_sha256': digest, 'usage': {'completion_tokens': 128}}).encode()
                self.send_response(200); self.end_headers(); self.wfile.write(body)
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            client = functools.partial(helper.exact_id_request, 'http://127.0.0.1:' + str(server.server_port))
            root = tmp_path / str(repetition); roots.append(root)
            result = w.collect(client, [[1,2],[3,4]], slots=2, root=root,
                               observations_path=root/'observations.jsonl', mode=mode, repetitions=1)
            selected = result[mode]
            unused = result['alone' if mode == 'batch' else 'batch']
            assert unused == [] and len(selected) == 1
            assert sorted(row['uid'] for row in selected[0]) == [0,1]
            assert state['uid'] == 2
            assert len(list((root/'responses').glob('*.response.bin'))) == 2
            assert json.loads((root/'collection.json').read_text())['physical_batch_verified'] is False
        finally:
            server.shutdown(); thread.join(); server.server_close()
    assert roots[0] != roots[1]
