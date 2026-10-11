set -euo pipefail
/data2/FreeToken/venv/bin/python - <<'PY'
import json,pathlib,statistics
d=pathlib.Path('/data2/_shared/runs/ft_rounds/E2-R000')
tax=json.loads((d/'t00_summary.json').read_text())['telemetry']['checkpoint_tax']
result={}
for side in ('OFF','ON'):
    for key in ('single','multi'):
        cold=[tax[f'{side}_p{n}'][key]['cold_index0'] for n in range(1,4)]
        hot=[v for n in range(1,4) for v in tax[f'{side}_p{n}'][key]['hot_indices1to4']]
        result[f'{side}_{key}']={'cold_mean_s':statistics.mean(cold),'cold_values_s':cold,
                                'hot_mean_s':statistics.mean(hot),'hot_median_s':statistics.median(hot),
                                'hot_min_s':min(hot),'hot_max_s':max(hot),'hot_n':len(hot)}
result['multi_ON_minus_OFF_cold_s']=result['ON_multi']['cold_mean_s']-result['OFF_multi']['cold_mean_s']
result['multi_ON_minus_OFF_hot_mean_s']=result['ON_multi']['hot_mean_s']-result['OFF_multi']['hot_mean_s']
result['multi_ON_minus_OFF_hot_median_s']=result['ON_multi']['hot_median_s']-result['OFF_multi']['hot_median_s']
print(json.dumps(result))
PY
