import json
from pathlib import Path
import tempfile
import unittest

import gpu_window

COMPARE = Path(__file__).resolve().with_name('output_compare.py')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def raw_line(prompt_tokens, text):
    chunk = json.dumps({'choices': [{'delta': {'reasoning_content': text[:3], 'content': text[3:]}}],
                        'usage': {'prompt_tokens': prompt_tokens}})
    return json.dumps({'responses': [{'packets': [{'name': 'data', 'value': chunk}]}]})


def measurement(root, service, phase, repeat, speeds, tokens=256):
    directory = root / f'service_{service}' / f'{phase}_{repeat}'
    directory.mkdir(parents=True, exist_ok=True)
    results = [{'request_id': f'{service}-{phase}-{repeat}-{i}', 'completion_tokens': tokens,
                'prompt_tokens': 1200 + i, 'finish_reasons': ['length'],
                'inter_token_latency_ms': 1000 / tps, 'decode_tps': tps,
                'counted': tokens >= 128} for i, tps in enumerate(speeds)]
    write_json(directory / 'terminal.json',
               {'status': 'measured', 'service': service, 'phase': phase, 'repeat': repeat,
                'calls': len(speeds), 'results': results})


class VerdictComputation(unittest.TestCase):
    def build_tree(self, root, h1_two=(25.3, 25.5, 25.4, 25.6)):
        measurement(root, 'O1', 'x_two', 1, (17.0, 17.1))
        measurement(root, 'O1', 'x_two', 2, (17.2, 17.0))
        measurement(root, 'O2', 'x_two', 1, (16.9, 17.0))
        measurement(root, 'O2', 'x_two', 2, (17.1, 16.8))
        measurement(root, 'H1', 'x_two', 1, h1_two[:2])
        measurement(root, 'H1', 'x_two', 2, h1_two[2:])
        for service in ('O1', 'H1', 'O2'):
            measurement(root, service, 'x_single', 1, (30.1,))
            measurement(root, service, 'x_single', 2, (30.2,))
            measurement(root, service, 'lc1_single', 1, (20.0,))
            measurement(root, service, 'lc1_single', 2, (20.1,))
        measurement(root, 'H2', 'x_single', 1, (30.1,))
        for service, pairs in (('H1', (('x_single', 1), ('x_single', 2), ('x_two', 1), ('x_two', 2))),
                               ('H2', (('x_single', 1),))):
            for phase, repeat in pairs:
                directory = root / f'service_{service}' / f'{phase}_{repeat}'
                count = 2 if phase == 'x_two' else 1
                lines = [raw_line(1200 + i, 'abcdef') for i in range(count)]
                (directory / 'profile_export_raw.jsonl').write_text('\n'.join(lines) + '\n')
        write_json(root / 'service_O1' / 'quality60_score.json', {'score_pass': 47, 'total': 60})
        write_json(root / 'service_H1' / 'quality60_score.json', {'score_pass': 45, 'total': 60})

    def doc(self):
        return {'output_compare_path': str(COMPARE),
                'service_order': ['O1', 'H1', 'H2', 'O2'],
                'inputs': {'X': {}, 'LC1': {}}}

    def test_pre_registered_thresholds_met(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.build_tree(root)
            verdict = gpu_window.compute_verdicts(root, self.doc())
        criteria = verdict['criteria']
        self.assertEqual(criteria['J1']['status'], 'met')
        self.assertAlmostEqual(criteria['J1']['threshold'], 17.0125 * 1.15)
        self.assertEqual(criteria['J2']['status'], 'met')
        self.assertEqual(criteria['J3']['status'], 'met')
        self.assertEqual(criteria['J4']['status'], 'reproducible')
        self.assertAlmostEqual(criteria['J5']['lc1_single']['ratio'], 1.0, places=6)
        self.assertEqual(criteria['J5']['lc2_two']['status'], 'not_in_admission')
        self.assertEqual(verdict['overall'], 'complete')

    def test_weak_hybrid_two_lane_is_not_met(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.build_tree(root, h1_two=(18.0, 19.0, 25.4, 25.6))
            verdict = gpu_window.compute_verdicts(root, self.doc())
        self.assertEqual(verdict['criteria']['J1']['status'], 'not_met')

    def test_short_lane_is_excluded_and_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.build_tree(root)
            measurement(root, 'H1', 'x_two', 2, (25.4,), tokens=100)
            verdict = gpu_window.compute_verdicts(root, self.doc())
        self.assertEqual(len(verdict['short_lanes_excluded']), 1)
        self.assertEqual([r['repeat'] for r in verdict['short_lanes_excluded']], [2])

    def test_abnormal_lane_marks_overall(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.build_tree(root)
            measurement(root, 'O2', 'x_two', 2, (7.0, 17.0))
            verdict = gpu_window.compute_verdicts(root, self.doc())
        self.assertEqual(verdict['overall'], 'abnormal')


if __name__ == '__main__':
    unittest.main()
