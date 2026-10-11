"""Official OpenAI SDK transport retaining the v3 raw-SSE reader contract."""
from __future__ import annotations
import importlib.util, json, os
from pathlib import Path
import httpx
from openai import APIStatusError, OpenAI

HERE=Path(__file__).resolve().parent; V3=HERE/'r046c_t06_ordinary_client_v3.py'
def _load():
 s=importlib.util.spec_from_file_location('r061e_v3_reader',V3);m=importlib.util.module_from_spec(s);assert s.loader;s.loader.exec_module(m);return m
_reader=_load()
HTTP_CLIENT=httpx.Client
sha256=_reader.sha256; write_new=_reader.write_new; _v2=_reader._v2
_input_for_uid=_reader._input_for_uid; _tokens_for_uid=_reader._tokens_for_uid; bind=_reader.bind
API_SCHEMA=_reader.API_SCHEMA; INPUT_SCHEMA=_reader.INPUT_SCHEMA; TOKEN_SCHEMA=_reader.TOKEN_SCHEMA
_STANDARD={'model','messages','stream','stream_options','max_tokens','max_completion_tokens','temperature','top_p','stop','n','presence_penalty','frequency_penalty','logit_bias','logprobs','response_format','seed','tools','tool_choice','parallel_tool_calls','user','service_tier','reasoning_effort'}
def ordinary_request(base_url: str,input_path: Path,output: Path,timeout: float=1800)->dict:
 if os.environ.get('FT_DEV_PAUSE_ENDPOINT')=='1':raise RuntimeError('ordinary client refuses pause environment')
 if base_url.rstrip('/').endswith(':8095/v1'):raise RuntimeError('ordinary client must not contact 8095')
 payload=json.loads(input_path.read_text(encoding='utf-8'))
 if payload.get('stream') is not True or (payload.get('stream_options') or {}).get('include_usage') is not True:raise ValueError('ordinary request requires stream usage')
 standard={k:v for k,v in payload.items() if k in _STANDARD}; extra={k:v for k,v in payload.items() if k not in _STANDARD}
 if extra: standard['extra_body']=extra
 raw_path=output.with_suffix('.sse'); partial=bytearray()
 try:
  with HTTP_CLIENT(trust_env=False,timeout=timeout) as transport,OpenAI(base_url=base_url.rstrip('/'),api_key='fixture',max_retries=0,timeout=timeout,http_client=transport) as client:
   with client.chat.completions.with_streaming_response.create(**standard) as response:
    for chunk in response.iter_bytes():partial.extend(chunk)
 except APIStatusError as exc:
  try:partial.extend(exc.response.read())
  except Exception:pass
  raw_path.parent.mkdir(parents=True,exist_ok=True);raw_path.write_bytes(bytes(partial));raise RuntimeError('ordinary SSE HTTP error; raw response preserved') from exc
 except Exception as exc:
  raw_path.parent.mkdir(parents=True,exist_ok=True);raw_path.write_bytes(bytes(partial));raise RuntimeError('ordinary SSE read error; partial raw response preserved') from exc
 raw_path.parent.mkdir(parents=True,exist_ok=True);raw_path.write_bytes(bytes(partial));uid,usage,finish=_v2().parse_sse(bytes(partial))
 value={'schema':API_SCHEMA,'mode':'ordinary_sse','pause_enabled':False,'payload_source':{'path':str(input_path),'sha256':sha256(input_path)},'sse':str(raw_path),'sse_sha256':sha256(raw_path),'id':f'chatcmpl-{uid}','uid':uid,'usage':usage,'finish_reason':finish}
 write_new(output,value);return value
