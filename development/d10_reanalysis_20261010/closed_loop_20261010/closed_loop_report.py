"""Read-only arithmetic over frozen measured receipts; never starts a runtime."""
import argparse,json,math
from pathlib import Path

def compute(speed,d0):
    if speed.get('status')!='complete' or d0.get('status')!='complete':raise ValueError('both terminal phases must be complete')
    by={x['group']:x for x in d0['results']};out={'m_scope':'nominal per-lane shared-batch equivalent, not independent UID miss rate','groups':{}}
    for x in speed['results']:
        g=x['group']
        if len(x['raw'])!=2:raise ValueError('exactly two measured lanes required')
        stats=by[g]['d0'];m=stats['m_equivalent_shared_batch_per_lane_average'];lanes=[]
        if not isinstance(m,(int,float)) or not math.isfinite(m) or not 0<=m<=1:raise ValueError('m must be finite within [0,1]')
        for r in x['raw']:
            L=r['L_k_tokens'];obs=r['per_lane_decode_tps']
            if not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in (L,obs)):raise ValueError('lane length and TPS must be finite positive')
            pred=1000/(18.4+.032*L+2*m*54.77)
            lanes.append({'prompt_tokens':r['prompt_tokens'],'completion_tokens':r['completion_tokens'],'finish_reasons':r['finish_reasons'],'L_k_tokens':L,'observed_tps':obs,'predicted_tps':pred,'observed_over_predicted':obs/pred})
        out['groups'][g]={'shared_equivalent_m':m,'D0_stats':stats,'lanes':lanes,'ideal_upper_per_lane_tps':1000/(2*m*54.77) if m else None}
    if set(out['groups'])!={'X','Y'}:raise ValueError('both X and Y required')
    x=out['groups']['X'];y=out['groups']['Y'];ratios=[r['observed_over_predicted'] for r in x['lanes']]
    anomaly=any(r['observed_tps']<7.8 for g in out['groups'].values() for r in g['lanes'])
    p1='ANOMALY_NO_CONCLUSION' if anomaly else ('SUPPORTED_90_110' if all(.9<=r<=1.1 for r in ratios) else ('OVER_110_REFIT_REQUIRED_NO_CONCLUSION' if any(r>1.1 for r in ratios) else 'BELOW_90_MODEL_NOT_SUPPORTED'))
    out.update({'P1':p1,'P1_scope':'X two lanes, per explicit user directive; Y evaluates P2','P2_equivalent_m_difference_pp':100*(x['shared_equivalent_m']-y['shared_equivalent_m']),'P2_preregistered_threshold_met':y['shared_equivalent_m']<=x['shared_equivalent_m']-.08,'D10_each_30_closed':p1=='SUPPORTED_90_110' and x['ideal_upper_per_lane_tps'] is not None and x['ideal_upper_per_lane_tps']<=30,'limitations':['D0 is a separate fresh service; speed used restored production cache state.','Stock D0 cannot attribute separate UID hit/miss totals for a shared bs2 cache.','X prompts are 1179/1231 input tokens, not 32K; Y uses original short R045 prompts and early EOS.','AIPerf speed spans each lane decode; D0 m uses common bs2 steps.']})
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('--speed',type=Path,required=True);p.add_argument('--d0',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    v=compute(json.loads(a.speed.read_text()),json.loads(a.d0.read_text()))
    with a.out.open('x') as f:json.dump(v,f,indent=2)
if __name__=='__main__':main()
