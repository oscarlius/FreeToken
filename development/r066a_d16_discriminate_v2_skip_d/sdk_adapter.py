"""R066a reuses the immutable R066 SDK collector; it adds no collector or endpoint."""
from __future__ import annotations
import hashlib, importlib.util, json
from pathlib import Path
HERE=Path(__file__).resolve().parent; R066=HERE.parent/'r066_d16_discriminate_v2'
R066_SDK_SHA='a50d01a1cbecfadf061bac5c553e9cd08005b458922d0ef574babefc52ca8d19'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(R066/'sdk_adapter.py')!=R066_SDK_SHA: raise RuntimeError('frozen R066 adapter differs')
spec=importlib.util.spec_from_file_location('r066a_frozen_r066_sdk',R066/'sdk_adapter.py'); r066=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(r066)
CriterionMismatch=r066.CriterionMismatch; collect_one=r066.collect_one; pair=r066.pair; discriminate=r066.discriminate; write=r066.write; inputs=r066.inputs; body_sha=r066.body_sha
def result(run,service,doc): write(Path(run)/'criteria_result.json',{'schema':'ft_r066a_d16_criteria/v1','rid':'E2-R066a-d16-discriminate-v2-skip-D','service':service,**doc})
def run_service(base,model,service,run):
 out=Path(run)/service/'calls'; out.mkdir(); item=inputs()
 try:
  if service=='B':
   rec=collect_one(base,model,'B1',item['long'],out)
   if body_sha(rec)!=r066.B_BODY_SHA: raise CriterionMismatch('B body SHA differs')
   write(out/'cached_tokens_observation.json',rec['cached_tokens_observation']); write(out/'service_result.json',{'service':'B','passed':True,'calls':1}); return rec
  if service!='C': raise ValueError('only B/C are approved')
  b=json.loads((Path(run)/'B/calls/B1.json').read_text()); long,_=pair(base,model,[('C_long',item['long']),('C_short',item['short'])],out); r066.r065.comparable(b,long,('finish_reason','usage'))
  records=pair(base,model,[('C_alpha',item['alpha']),('C_beta',item['beta'])],out)
  for rec,key,other in zip(records,('alpha','beta'),('beta','alpha')): discriminate(rec['projection']['text'],item[key]['marker'],item[other]['marker'])
  write(out/'service_result.json',{'service':'C','passed':True,'calls':4}); result(run,'C',{'proposed_verdict':'passed_R066a_criteria','handoff_ready':True,'scope':{'services':2,'calls':5},'d_status':'skipped_existing_recipe_runtime_unavailable','c_long_body_matches_B_observation':body_sha(long)==r066.B_BODY_SHA,'cached_tokens_policy':'observation_only_missing_is_not_zero'}); return records
 except BaseException as exc:
  if not (Path(run)/'criteria_result.json').exists(): result(run,service,{'proposed_verdict':'not_met' if isinstance(exc,CriterionMismatch) else 'failed_harness','handoff_ready':False,'reason':str(exc),'exception_type':type(exc).__name__})
  raise
