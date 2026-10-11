import importlib.util
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent
SOURCE=HERE/'r049_t21_ordinary_prepare_v12.py'
def load():
 spec=importlib.util.spec_from_file_location('r049_v11_retained',SOURCE); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
@pytest.mark.skipif(not Path('/data2/FreeToken/runs/dev_T21/reviews/E2-R049a_L1_recompute_v1/review.json').is_file(),reason='Linux retained L1 review only')
def test_linux_actual_retained_l1_review_binds_exact_eight_service_plan():
 m=load(); r=m.require_retained_l1_review(); assert r['requests']==24 and r['complete_L1_retained'] is True
 assert [x['name'] for x in m.assert_plan(m.arms())]==['P1','PA1','L2','P2','PA2','L_D0','P_D0','PA_D0']
