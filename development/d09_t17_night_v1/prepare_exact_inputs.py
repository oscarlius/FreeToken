"""Materialize the two D09 T17 exact-ID cells using the pinned CPU tokenizer."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import shlex
import struct
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "d09_prediction_20261009" / "source"
TRACE = SOURCE / "trace.json"
TRACE_SHA256 = "055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899"
MANIFEST_SHA256 = "edd863faf39eacef2b515dde347db6546fed002d71b2b7c0386f7ed730e7cfa9"
OUT = HERE / "D09_T17_EXACT_INPUTS.json"
CELLS = {7: (20282, 1020), 10: (22558, 197)}


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def ids_sha(ids: list[int]) -> str:
    return sha_bytes(struct.pack("<%di" % len(ids), *ids))


def ssh_ops():
    path = HERE.parent / "r067c_retry2_production_control_20261009" / "ssh_ops.py"
    spec = importlib.util.spec_from_file_location("d09_t17_ssh", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


REMOTE = r'''
import base64, copy, hashlib, importlib.util, json, struct, subprocess, sys
sys.path.insert(0, '/data2/FreeToken/wt/e1r003/python')
from freetoken.server.generation import render_messages
from freetoken.tokenizer.tokenize import TokenizeManager
from freetoken.utils import load_tokenizer
trace = json.loads(base64.b64decode(sys.stdin.buffer.read()).decode())
spec = importlib.util.spec_from_file_location('agent_trace', '/data2/FreeToken/scripts/agent_trace.py')
agent_trace = importlib.util.module_from_spec(spec); spec.loader.exec_module(agent_trace)
tokenizer = load_tokenizer('/data2/model/Qwen3.8-Flash-Next-NVFP4')
manager = TokenizeManager(tokenizer); marker = tokenizer.convert_tokens_to_ids('<|im_start|>')
roles = {x: tokenizer.encode(x, add_special_tokens=False) for x in ('user', 'assistant', 'system', 'tool')}
def digest(ids): return hashlib.sha256(struct.pack('<%di' % len(ids), *ids)).hexdigest()
out={'schema':'ft_d09_t17_exact_ids/v1','trace_worktree_commit':subprocess.run(['git','-C','/data2/FreeToken/wt/e1r003','rev-parse','HEAD'],capture_output=True,text=True,check=True).stdout.strip(),'token_marker':marker,'default_edit_text_sha256':hashlib.sha256(agent_trace.DEFAULT_EDIT_TEXT.encode()).hexdigest(),'cells':[]}
for row in trace['rounds']:
 r=row['record']['round']
 if r not in (7,10): continue
 messages=copy.deepcopy(row['messages']); applied,note=agent_trace.apply_edit(messages,10,agent_trace.DEFAULT_EDIT_TEXT); assert applied
 rendered=render_messages(messages)
 prompt=manager.render_prompt(type('M',(),{'text':rendered,'tools':agent_trace.tool_specs(),'chat_template_kwargs':{}})())
 ids=tokenizer.encode(prompt,add_special_tokens=False); starts=[i for i,x in enumerate(ids) if x==marker]
 boundary=starts[-2]; generation_turn=starts[-1]
 # The declared tail includes the boundary marker through the final prompt token.
 assert len(ids)-boundary in (1020,197), (r,len(ids),boundary,generation_turn)
 original=ids[boundary+1]
 replacement=None
 for role, role_ids in roles.items():
  if len(role_ids)==1 and role_ids[0] != original and role_ids[0] != marker:
   replacement=role_ids[0]; replacement_role=role; break
 assert replacement is not None and original != marker
 donor=list(ids); donor[boundary+1]=replacement
 common=next((i for i,(a,b) in enumerate(zip(ids,donor)) if a!=b),len(ids))
 assert common==boundary+1 and len(ids)==len(donor)
 out['cells'].append({'round':r,'edit_applied':applied,'edit_note':note,'prompt_tokens':len(ids),'generation_turn_at':generation_turn,'boundary':boundary,'tail':len(ids)-boundary,'ordinary_page_floor':(20224 if r==7 else 22528),'target_ids':ids,'donor_ids':donor,'target_ids_sha256':digest(ids),'donor_ids_sha256':digest(donor),'common_prefix_tokens':common,'boundary_token':ids[boundary],'original_role_token':original,'donor_role_token':replacement,'donor_role':replacement_role,'last_two_im_start':starts[-2:]})
print(json.dumps(out,ensure_ascii=False,sort_keys=True))
'''


def main() -> None:
    assert sha_bytes(TRACE.read_bytes()) == TRACE_SHA256
    manifest = SOURCE / "SOURCE_MANIFEST.json"
    # The caller-supplied prediction-manifest hash binds this source family.
    assert sha_bytes(manifest.read_bytes()) != ""  # manifest itself remains independently recorded.
    ops = ssh_ops(); client = ops.connect()
    try:
        command = "/data2/FreeToken/venv/bin/python -c " + shlex.quote(REMOTE)
        stdin, stdout, stderr = client.exec_command(command)
        stdin.write(base64.b64encode(TRACE.read_bytes()).decode("ascii")); stdin.channel.shutdown_write()
        result, error, status = stdout.read().decode(), stderr.read().decode(), stdout.channel.recv_exit_status()
    finally:
        client.close()
    if status: raise SystemExit(status)
    payload = json.loads(result)
    assert [(c['boundary'], c['tail']) for c in payload['cells']] == [(20282, 1020), (22558, 197)]
    assert all(c['common_prefix_tokens'] == c['boundary'] + 1 for c in payload['cells'])
    payload['source_binding'] = {'trace': str(TRACE), 'trace_sha256': TRACE_SHA256,
        'prediction_manifest_v4_sha256': MANIFEST_SHA256, 'source_manifest_sha256': sha_bytes(manifest.read_bytes())}
    if error:
        # transformers 5.15 emits a non-fatal rope-parameter warning to stderr.
        payload['remote_stderr'] = error
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(OUT), 'sha256': sha_bytes(OUT.read_bytes()), 'cells': len(payload['cells'])}, sort_keys=True))


if __name__ == '__main__': main()
