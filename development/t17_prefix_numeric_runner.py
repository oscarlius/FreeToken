"""Measure the R023 prefix using its unchanged default chunking path."""
import argparse
import json
from pathlib import Path
import re
import signal
import sys

import t17_matched_runner as matched
from t17_matched_runner import original, helper, artifacts

HERE = Path(__file__).resolve().parent


def validate_prefix_coordinates(record, uid, device):
    if str(record['uid'])!=str(uid) or record['absolute_interval']!=[512,8192]:
        raise ValueError('captured prefix identity/interval differs')
    segments=record['segments']
    if [(s['absolute_start'],s['absolute_end'],s['cached_tokens'],s['device_tokens']) for s in segments] != [(512,4608,512,4608),(4608,8192,4608,device)]:
        raise ValueError('actual default child coordinates differ')
    expected_track=(device-1)//64*64
    h=record['h']
    expected={'absolute_boundary':8192,'target_boundary_row':3584,'cached_tokens':4608,'device_tokens':device,
              'actual_track_boundary_row':expected_track-4608,'actual_track_absolute_boundary':expected_track,
              'actual_track_h_row':(expected_track-4608)//64,'computed_h_row':56}
    if any(h.get(key)!=value for key,value in expected.items()) or 'track_boundary_row' in h:
        raise ValueError('actual tracker and target h coordinates are not separately proved')


def capture(arm, uid, device):
    root = arm / 'numeric'
    final = json.loads((root / ('final_' + str(uid) + '.json')).read_bytes())
    if (final.get('valid') is not True or str(final.get('uid')) != str(uid)
            or final.get('observed_boundary') != 8192 or final.get('diagnostic_only') is not True):
        raise ValueError('first-GDN prefix evidence incomplete')
    path = root / final['receipt_file']
    if path.is_symlink() or root.resolve() not in path.resolve().parents or helper.sha256(path) != final['receipt_sha256']:
        raise ValueError('numeric receipt differs')
    installed = [json.loads(p.read_bytes()) for p in root.glob('installed_*.json')]
    if (len(installed) != 1 or installed[0]['FT_LM_CHUNK'] != '4096'
            or installed[0]['observer_source_sha256'] != helper.sha256(HERE/'t17_prefix_numeric_observe.py')
            or installed[0]['startup_source_sha256'] != helper.sha256(HERE/'t17_prefix_numeric_startup.py')):
        raise ValueError('actual numeric observer/default-chunk source binding differs')
    record=json.loads(path.read_bytes());validate_prefix_coordinates(record,uid,device)
    return {'final': final, 'receipt': record, 'installed': installed[0]}


class Run(matched.Run):
    def startup_wrapper(self):
        return HERE / 't17_prefix_numeric_startup.py'

    def environment(self, wt, arm=None, d0=False):
        env = super().environment(wt, arm, d0)
        env.pop('FT_T17_MATCHED', None)
        env['FT_LM_CHUNK'] = '4096'
        if arm is not None:
            env['FT_T17_PREFIX_NUMERIC'] = str(arm / 'numeric')
        return env

    def execute(self):
        prior = matched.prerequisite();helper.t16_prerequisite()
        self.gate(original.WT, helper.CANDIDATE)
        if not self.options.run:
            print(json.dumps({'preflight':'PASS','diagnostic_only':True,'prerequisite':prior}));return
        self.lock_take();owned = False
        try:
            if self.directory.exists():raise FileExistsError('numeric round already exists')
            self.directory.mkdir();owned = True
            original.put(self.directory/'prerequisite.json',prior)
            source_files={}
            for source in sorted(HERE.rglob('*.py')):
                if source.is_symlink() or source.stat().st_mode&0o222:raise ValueError('execution dependency is not frozen')
                relative=source.relative_to(HERE);target=self.directory/'source'/relative
                target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as stream:stream.write(source.read_bytes())
                source_files[str(relative)]=helper.sha256(target)
            original.put(self.directory/'source_binding.json',source_files)
            inputs_path = HERE/'real_inputs.json'
            if helper.sha256(inputs_path) != helper.sha256(matched.R023/'real_inputs.json'):
                raise ValueError('exact R023 input changed')
            case = json.loads(inputs_path.read_bytes())['cases'][0]
            if case['length'] != 8192:raise ValueError('original prefix case required')
            with (self.directory/'real_inputs.json').open('xb') as stream:stream.write(inputs_path.read_bytes())
            def warm(arm):
                donor = self.request(arm,'donor',case['donor'],0,2)
                prefix = capture(arm,donor['uid'],8193)
                hit = self.request(arm,'short',case['short'],8192,128)
                return donor,hit,prefix
            donor,hit,hot = self.service('numeric_warm',warm)
            cold = self.service('numeric_cold',lambda arm:self.request(arm,'query',case['short'],0,128))
            warm_arm,cold_arm = self.directory/'numeric_warm',self.directory/'numeric_cold'
            fresh = capture(cold_arm,cold['uid'],8257)
            raw = artifacts.validate_case({'name':'default-prefix-8192','length':8192,'trace_index':case['trace_index'],
                                           'context':case['expected_ngram']},cold_arm,warm_arm,tail=65,
                                          cold_request='query',hit_request='short',state_root=warm_arm/'dump')
            original.put(self.directory/('diagnostic_batch'+str(self.options.batch)+'.json'),
                         {'schema':'ft_t17_prefix_numeric/v1','rid':self.options.rid,'batch':self.options.batch,
                          'diagnostic_only':True,'candidate_commit':helper.CANDIDATE,'FT_LM_CHUNK':4096,
                          'warm_prefix':hot,'cold_prefix':fresh,'raw_validator':raw,
                          'acceptance':'numeric evidence pending independent analysis; original_T17_not_met_retained'})
            self.set_status(state='complete_measurements_pending_review')
        except BaseException as error:
            if owned:self.set_status(state='failed',error=repr(error))
            raise
        finally:
            try:self.stop()
            finally:
                if self.proc is None:self.lock_release()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rid',required=True);parser.add_argument('--batch',type=int,required=True)
    parser.add_argument('--run',action='store_true');options=parser.parse_args()
    if sys.platform!='linux' or not re.fullmatch(r'E2-R\d{3}-diagnostic-T17',options.rid) or options.batch<1:
        parser.error('Linux and exact diagnostic round/batch required')
    options.gate='T17-diagnostic';run=Run(options)
    for signum in (signal.SIGINT,signal.SIGTERM):
        signal.signal(signum,lambda signum,frame:(_ for _ in ()).throw(InterruptedError('owned numeric signal')))
    run.execute()


if __name__=='__main__':main()
