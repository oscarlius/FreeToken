from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).parent


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


ART = module('t17_d14_artifacts')
OBSERVE = module('t17_d14_observe')


class FakeTensor:
    def __init__(self, rows):
        self.rows = rows
        self.shape = self._shape(rows)
        self.dtype = 'int32'

    @classmethod
    def _shape(cls, value):
        return (len(value),) + cls._shape(value[0]) if isinstance(value, list) else ()

    def __getitem__(self, key):
        rows, column = key
        assert rows == slice(None)
        return FakeTensor([[row[column]] for row in self.rows])

    def flatten(self):
        return FakeTensor([self.tolist()])

    def tolist(self):
        def values(value):
            if isinstance(value, list):
                return sum((values(item) for item in value), [])
            return [value]
        return values(self.rows)


def fake_equal(left, right):
    return left.shape == right.shape and left.tolist() == right.tolist()


class ArtifactFixture:
    length = 8
    context = [1469, 17]
    query = list(range(6)) + context + list(range(65))
    donor = query[:9]

    def __init__(self, root):
        self.root = Path(root)
        self.cold = self.root / 'cold'
        self.hot = self.root / 'hot'
        self.cold.mkdir()
        self.hot.mkdir()
        (self.hot / 'state').mkdir()
        self.tensors = {}
        self._request(self.cold, 'cold', '1', self.query, 0, tokens=[31, 32])
        self._request(self.hot, 'donor', '2', self.donor, 0, tokens=[41, 42])
        self._request(self.hot, 'hit', '3', self.query, self.length, tokens=[31, 32])
        self._states()

    def _request(self, arm, name, uid, ids, cached, *, tokens, layer_child=False):
        rows = [
            {'kind': 'input', 'uid': uid, 'input_length': len(ids),
             'ids_int32le_sha256': ART.ids_sha(ids), 'input_ids': ids,
             'sampling': {'temperature': 0.0, 'max_tokens': 2 if name == 'donor' else 128,
                          'top_p': 1.0}},
            {'kind': 'admitted', 'uid': uid, 'prompt_tokens': len(ids), 'cached_tokens': cached},
            {'kind': 'prefill', 'uid': uid, 'cached_tokens': cached,
             'device_length': len(ids), 'extend_tokens': len(ids) - cached,
             'layer_major': True, 'reason': ''},
        ]
        if layer_child:
            rows.append({'kind': 'layer-children', 'uid': uid, 'outer_cached_tokens': self.length,
                         'children': [{'cached_tokens': self.length, 'device_tokens': self.length + 64,
                                       'has_initial_state': True}]})
        if cached:
            rows.append({'kind': 'restore-device', 'uid': uid, 'cached_tokens': self.length,
                         'src': 7, 'dst': 9})
        for index, token in enumerate(tokens):
            rows.append({'kind': 'token', 'uid': uid, 'token': token,
                         'finished': index == len(tokens) - 1, 'finish_reason': 'length'})
        observation = arm / 'observations.jsonl'
        start = len(observation.read_text().splitlines()) if observation.exists() else 0
        with observation.open('a', encoding='utf-8') as out:
            for row in rows:
                out.write(json.dumps(row) + '\n')
        response = {'uid': int(uid), 'text': 'actual raw text', 'finished': True, 'finish_reason': 'length',
                    'usage': {'prompt_tokens': len(ids), 'completion_tokens': len(tokens),
                              'cached_tokens': cached}, 'input_ids_sha256': ART.ids_sha(ids)}
        raw_file = f'{name}.response.bin'
        (arm / raw_file).write_bytes(json.dumps(response, separators=(',', ':')).encode())
        receipt = {'payload': {'input_ids': ids, 'max_tokens': 2 if name == 'donor' else 128,
                               'temperature': 0},
                   'response': response, 'status': 200,
                   'response_sha256': hashlib.sha256((arm / raw_file).read_bytes()).hexdigest(),
                   'raw_response_file': raw_file, 'expected_input_ids_sha256': ART.ids_sha(ids),
                   'observation_range': {'start': start, 'end': start + len(rows)}}
        (arm / f'{name}.json').write_text(json.dumps(receipt), encoding='utf-8')

    def _states(self):
        files = {}
        for role in ART.ROLES:
            donor_name = 'donor-' + role.replace(':', '_')
            resume_name = 'resume-' + role.replace(':', '_')
            for name in (donor_name, resume_name):
                (self.hot / 'state' / name).write_bytes(name.encode())
            source = [[[1469, 17]]] if role == 'slot:ple_ngram_ctx' else [[3]]
            target = [[[1469, 17], [1469, 17]]] if role == 'slot:ple_ngram_ctx' else [[3, 3]]
            self.tensors[donor_name] = FakeTensor(source)
            self.tensors[resume_name] = FakeTensor(target)
            files[role] = (donor_name, resume_name)
        donate = {'kind': 'donate', 'uid': '2', 'length': self.length, 'dev_slots': [7], 'seq': 2,
                  'files': {role: pair[0] for role, pair in files.items()}}
        resume = {'kind': 'resume-device', 'uid': '3', 'length': self.length, 'dev_slots': [7, 9], 'seq': 3,
                  'note': json.dumps({'src': 7, 'dst': 9}, sort_keys=True),
                  'files': {role: pair[1] for role, pair in files.items()}}
        (self.hot / 'state/index.jsonl').write_text(json.dumps(donate) + '\n' + json.dumps(resume) + '\n')

    def read(self, path):
        return self.tensors[path.name]

    def validate(self):
        case = {'name': 'fixture', 'length': self.length, 'trace_index': 0, 'context': self.context}
        return ART.validate_case(case, self.cold, self.hot, tail=65, read=self.read, equal=fake_equal)


class TestArtifacts(unittest.TestCase):
    def test_accepts_exact_ids_tokens_receipt_and_joint_states(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture = ArtifactFixture(temp)
            result = fixture.validate()
        self.assertTrue(result['passed'])
        self.assertEqual(result['cold_token_ids'], [31, 32])
        self.assertEqual(result['actual_cached_tokens'], 8)

    def test_rejects_forged_endpoint_or_scheduler_evidence(self):
        def assert_rejected(change):
            with tempfile.TemporaryDirectory() as temp:
                fixture = ArtifactFixture(temp)
                change(fixture)
                with self.assertRaises(ValueError):
                    fixture.validate()

        def wrong_hash(f):
            path = f.hot / 'hit.json'; data = json.loads(path.read_text())
            data['expected_input_ids_sha256'] = '0' * 64; path.write_text(json.dumps(data))
        def forged_response(f):
            path = f.hot / 'hit.json'; data = json.loads(path.read_text())
            data['response']['text'] = 'forged'; path.write_text(json.dumps(data))
        def wrong_cache(f):
            path = f.hot / 'hit.json'; data = json.loads(path.read_text())
            data['response']['usage']['cached_tokens'] = 7; path.write_text(json.dumps(data))
        def missing_role(f):
            path = f.hot / 'state/index.jsonl'; rows = [json.loads(x) for x in path.read_text().splitlines()]
            del rows[1]['files']['slot:ple_conv']; path.write_text('\n'.join(json.dumps(x) for x in rows))
        def wrong_ngram(f):
            f.tensors['donor-slot_ple_ngram_ctx'] = FakeTensor([[[1, 2]]])
        def mutated_gdn(f):
            f.tensors['resume-conv_states'] = FakeTensor([[3, 4]])
        def forged_source(f):
            path = f.hot / 'state/index.jsonl'; rows = [json.loads(x) for x in path.read_text().splitlines()]
            rows[1]['dev_slots'] = [8, 9]; path.write_text('\n'.join(json.dumps(x) for x in rows))
        def child_without_initial(f):
            path = f.hot / 'observations.jsonl'; rows = [json.loads(x) for x in path.read_text().splitlines()]
            position = next(i for i, row in enumerate(rows) if row['uid'] == '3' and row['kind'] == 'token')
            rows.insert(position, {'kind': 'layer-children', 'uid': '3', 'outer_cached_tokens': 8,
                                   'children': [{'cached_tokens': 8, 'device_tokens': 72, 'has_initial_state': False}]})
            path.write_text('\n'.join(json.dumps(x) for x in rows))
            receipt = f.hot / 'hit.json'; data = json.loads(receipt.read_text())
            data['observation_range']['end'] += 1; receipt.write_text(json.dumps(data))

        for change in (wrong_hash, forged_response, wrong_cache, missing_role, wrong_ngram,
                       mutated_gdn, forged_source, child_without_initial):
            with self.subTest(change=change.__name__):
                assert_rejected(change)


class TestObserver(unittest.TestCase):
    def test_records_joint_restore_and_real_child_metadata_once(self):
        seen, counters = [], {'restore': 0, 'process': 0, 'forward': 0, 'chunks': 0}
        class Pool:
            def dump_state(self, *args, **kwargs):
                seen.append(('dump', args, kwargs))
        class Scheduler:
            def __init__(self): self.engine = type('E', (), {'linear_state_pool': Pool()})()
            def _restore_linear_states(self, batch): counters['restore'] += 1
            def _process_one_msg(self, msg): counters['process'] += 1
            def _forward(self, value): counters['forward'] += 1
        class IO:
            def _reply_tokenizer_rank0(self, messages): return messages
        class Engine:
            def _build_layer_major_chunks(self, batch):
                counters['chunks'] += 1
                return [type('B', (), {'reqs': [type('R', (), {'cached_len': 8, 'device_len': 72})()],
                                       'fla_metadata': type('M', (), {'has_initial_state': [type('I', (), {'item': lambda self: True})()]})()})()]
        OBSERVE.install(Scheduler, IO, Engine, sink=seen.append)
        req = type('R', (), {'uid': 'hit', 'cached_len': 8, 'mamba_restore_src': 7,
                              'linear_slot_idx': 9, 'device_len': 73, 'extend_len': 65, 'seg_reason': ''})()
        batch = type('B', (), {'is_prefill': True, 'reqs': [req], 'layer_major': True})()
        scheduler = Scheduler()
        scheduler._restore_linear_states(batch)
        scheduler._process_one_msg(type('UserMsg', (), {'uid': 'hit', 'input_ids': type('Ids', (), {'tolist': lambda self: [1, 2]})(),
                                                          'sampling_params': type('P', (), {'temperature': 0, 'max_tokens': 2, 'top_p': 1})()})())
        scheduler._forward(type('V', (), {'batch': batch})())
        Engine()._build_layer_major_chunks(batch)
        self.assertEqual(counters, {'restore': 1, 'process': 1, 'forward': 1, 'chunks': 1})
        dump = [x for x in seen if isinstance(x, tuple)][0]
        self.assertEqual(dump[2]['dev_slots'], [7, 9])
        child = [x for x in seen if isinstance(x, dict) and x['kind'] == 'layer-children'][0]
        self.assertEqual(child['children'][0], {'cached_tokens': 8, 'device_tokens': 72, 'has_initial_state': True})


if __name__ == '__main__':
    unittest.main()
