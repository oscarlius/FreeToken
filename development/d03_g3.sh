set -euo pipefail
CUDA_VISIBLE_DEVICES='' /data2/FreeToken/venv/bin/python - <<'PY'
import importlib.util,json,pathlib
source=pathlib.Path('/data2/FreeToken/wt/e1r003st/scripts/state_envelope.py')
spec=importlib.util.spec_from_file_location('state_envelope',source)
module=importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name]=module
spec.loader.exec_module(module)
history=pathlib.Path('/data2/_shared/runs/ft_rounds/E1-R003-stateeq')
assert history.is_dir(),history
ref,test=history/'dump_B',history/'dump_A'
try:
    module.compare(ref,test,[])
except module.EnvelopeError as exc:
    assert 'length' in str(exc),exc
    print('STRICT LENGTH REJECTION PASS',str(exc))
else:
    raise AssertionError('historical unequal length sets silently accepted')
rows,summary=module.compare(ref,test,[],lengths={12416,14080,21568})
out=pathlib.Path('/data2/FreeToken/runs/dev_D03/g3_envelope_refB.csv')
module.write_csv(out,rows)
print('G3 SUMMARY',json.dumps(summary,allow_nan=False))
expected={
12416:{'conv_states':['0.24','11.77','14.59','11.69','10.89','8.50'],
       'recurrent_states':['0.40','3.18','14.23','3.62','8.21','9.71']},
14080:{'conv_states':['0.00','9.89','11.05','15.58','9.68','8.40'],
       'recurrent_states':['0.18','4.98','14.22','6.91','14.04','12.29']},
21568:{'conv_states':['0.12','15.07','16.76','17.83','14.04','11.18'],
       'recurrent_states':['0.39','15.54','20.78','13.74','24.49','17.42']}}
for length,roles in expected.items():
    for role,wanted in roles.items():
        found=[r for r in rows if r['length']==length and r['role']==role]
        actual=[f"{100*r['relative_l2']:.2f}" for r in [found[0],*found[-5:]]]
        assert actual==wanted,(length,role,actual,wanted)
        print('G3',length,role,','.join(actual))
print('G3 HISTORICAL TABLE REPRODUCTION PASS')
PY
