"""T07 same-tree D0 ABABAB and held-out cold lengths."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import signal
import statistics
import subprocess
import sys

from e2_runtime import CardRunner, WT, SCR, PY
from t16_runner import TOOL_MD5, check_det, write_new
from t00_runner import validate_d0


def difference(a, b):
    if len(a) != 6 or len(b) != 6 or not all(math.isfinite(x) and x > 0 for x in a + b):
        raise ValueError('six valid samples per arm required')
    delta = statistics.mean(a) - statistics.mean(b)
    half_width = 2 * math.sqrt(statistics.variance(a) / 6 + statistics.variance(b) / 6)
    return {'difference': delta, 'relative': delta / statistics.mean(b),
            'interval': [delta - half_width, delta + half_width]}


def same_inputs(records):
    inputs = [tuple(record[key] for key in ('cold_id','built_tokens','prompt_tokens','cached_tokens')) for record in records]
    if len(set(inputs)) != 1:
        raise ValueError(f'cold inputs differ: {inputs}')
    return inputs[0]


class CostRunner(CardRunner):
    def sample(self, arm, env, label, cold_id, target):
        with (arm / (label + '.stdout')).open('x') as out, (arm / (label + '.err')).open('x') as err:
            subprocess.run([PY, str(SCR / 'cold_eq.py'), cold_id, str(arm / (label + '.json')), str(target), '128'],
                           env=env,cwd=WT,stdout=out,stderr=err,check=True,timeout=1800)
        result = check_det([arm / (label + '.json')] * 2,target,128)
        record = result['records'][0]
        if record['cold_id'] != cold_id or not math.isfinite(record['decode_tps']) or record['decode_tps'] <= 0:
            raise ValueError('invalid decode measurement')
        return record

    def execute(self):
        if hashlib.md5((SCR / 'cold_eq.py').read_bytes()).hexdigest() != TOOL_MD5['cold_eq.py']:
            raise ValueError('original cold probe differs')
        groups = {'A': [], 'B': []}
        with self.round_scope() as admitted:
            if admitted is None:
                print('T07 PREFLIGHT PASS',flush=True)
                return
            for p in range(1,4):
                for label,d0 in [('A',True),('B',False)]:
                    name = f'{label}_d0{"on" if d0 else "off"}_p{p}'
                    reference = groups['A'][0] if groups['A'] else None
                    with self.service(name,d0=d0,reference=reference) as (arm,env):
                        self.sample(arm,env,'first_shot',self.options.rid+'-first-'+name,32052)
                        for target in (8000,16000,32052,48000):
                            for rep in (1,2):
                                self.sample(arm,env,f'c_{target}_r{rep}',f'{self.options.rid}-t{target}-r{rep}',target)
                        if d0:
                            write_new(arm / 'd0_while_alive.json', {'service_pid': self.proc.pid,
                                      'process_alive': self.proc.poll() is None, **validate_d0(arm)})
                    groups[label].append(arm)
            results = {}
            comparisons = []
            for target in (8000,16000,32052,48000):
                metric_groups = {}
                for label in ('A','B'):
                    metric_groups[label] = [json.loads((arm / f'c_{target}_r{rep}.json').read_text())['record']
                                           for arm in groups[label] for rep in (1,2)]
                for rep in (1,2):
                    files = [arm / f'c_{target}_r{rep}.json' for label in ('A','B') for arm in groups[label]]
                    same_inputs([json.loads(path.read_text())['record'] for path in files])
                    # A/B and within-arm comparisons are observations; differences are retained for T10.
                    texts = [json.loads(path.read_text())['text'] for path in files]
                    comparisons.append({'target':target,'rep':rep,'cross_arm_same':[texts[p]==texts[p+3] for p in range(3)],
                                        'A_within_same':len(set(texts[:3]))==1,'B_within_same':len(set(texts[3:]))==1,
                                        'text_sha256':[hashlib.sha256(t.encode()).hexdigest() for t in texts]})
                result = {metric: difference([r[metric] for r in metric_groups['A']], [r[metric] for r in metric_groups['B']])
                          for metric in ('ttft_s','decode_tps')}
                n = statistics.mean(r['prompt_tokens'] for r in metric_groups['A']) / 1000
                fitted = .175*n+.0002*n*n+.2
                prediction = 3.0 if target == 8000 else fitted
                result.update(samples=metric_groups,prediction_s=prediction,
                              holdout_relative=(statistics.mean(r['ttft_s'] for r in metric_groups['A'])-prediction)/prediction)
                results[str(target)] = result
            write_new(self.directory / 'measurement_summary.json', {'results':results,'text_comparisons':comparisons,
                      'proposed_verdict':'measured','code_version':admitted['code_version']})
            self.set_status(state='complete_measurements_pending_review')
            print('T07 MEASUREMENTS COMPLETE; independent review and closure pending',flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rid')
    parser.add_argument('--batch',type=int)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--self-test',action='store_true')
    opts = parser.parse_args()
    if opts.self_test:
        result = difference([2.]*6,[1.]*6)
        assert result['difference']==1. and result['interval']==[1.,1.]
        sample = {'cold_id':'case','built_tokens':32052,'prompt_tokens':32064,'cached_tokens':0}
        same_inputs([sample]*6)
        try:
            same_inputs([sample, {**sample,'prompt_tokens':32065}])
        except ValueError:
            pass
        else:
            raise AssertionError('different inputs accepted')
        try:
            difference([2.]*5,[1.]*6)
        except ValueError:
            pass
        else:
            raise AssertionError('sample truncation accepted')
        print('T07 SELFTEST PASS')
        return
    if sys.platform!='linux' or opts.batch is None or not opts.rid or not re.fullmatch(r'E2-R\d{3}',opts.rid):
        parser.error('Linux test host and leader assigned RID/batch required')
    opts.gate,opts.runner_file='T07',__file__
    runner=CostRunner(opts)
    for signum in (signal.SIGINT,signal.SIGTERM):
        signal.signal(signum,lambda signum,frame: (_ for _ in ()).throw(InterruptedError(f'signal {signum}')))
    runner.execute()


if __name__=='__main__':
    main()
