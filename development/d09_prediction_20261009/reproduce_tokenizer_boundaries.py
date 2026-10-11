"""Reproduce D09's CPU-only message-boundary eligibility without generation."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import shlex
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "source"
TRACE = SOURCE / "trace.json"
MANIFEST = SOURCE / "SOURCE_MANIFEST.json"
C_EDIT = SOURCE / "C_edit.json"
TRACE_SHA256 = "055ea005aadcbda32625f585a01f10e63d46cd1b87a88be769ec19144d68f899"
C_EDIT_SHA256 = "ca3e317837035bcf3607c571d5abc5a06e6a29bed96c025e7a15f37c341690f9"
EXPECTED_PROMPT_TOKENS = {5: 15262, 6: 20159, 7: 21302, 8: 22458, 10: 22755}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_ssh_ops():
    path = HERE.parent / "r067c_retry2_production_control_20261009" / "ssh_ops.py"
    spec = importlib.util.spec_from_file_location("d09_ssh_ops", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


REMOTE = r'''
import base64, copy, hashlib, importlib.util, json, sys
sys.path.insert(0, '/data2/FreeToken/wt/e1r003/python')
from freetoken.server.generation import render_messages
from freetoken.tokenizer.tokenize import TokenizeManager
from freetoken.utils import load_tokenizer
trace = json.loads(base64.b64decode(sys.stdin.buffer.read()).decode('utf-8'))
spec = importlib.util.spec_from_file_location('agent_trace', '/data2/FreeToken/scripts/agent_trace.py')
agent_trace = importlib.util.module_from_spec(spec); spec.loader.exec_module(agent_trace)
tokenizer = load_tokenizer('/data2/model/Qwen3.8-Flash-Next-NVFP4')
manager = TokenizeManager(tokenizer)
turn_token = tokenizer.convert_tokens_to_ids('<|im_start|>')
out = {'schema': 'freetoken.d09.tokenizer-cpu-reproducer-output/v1',
       'trace_worktree_commit': __import__('subprocess').run(
           ['git', '-C', '/data2/FreeToken/wt/e1r003', 'rev-parse', 'HEAD'],
           capture_output=True, text=True, check=True).stdout.strip(),
       'tokenizer': type(tokenizer).__name__, 'turn_token': turn_token,
       'chat_template_sha256': hashlib.sha256(str(tokenizer.chat_template).encode()).hexdigest(),
       'default_edit_text_sha256': hashlib.sha256(agent_trace.DEFAULT_EDIT_TEXT.encode()).hexdigest(),
       'rows': []}
for source_round in trace['rounds']:
    round_id = source_round['record']['round']
    if round_id not in (5, 6, 7, 8, 10):
        continue
    messages = copy.deepcopy(source_round['messages'])
    applied, note = agent_trace.apply_edit(messages, 10, agent_trace.DEFAULT_EDIT_TEXT)
    messages = render_messages(messages)
    prompt = manager.render_prompt(type('M', (), {
        'text': messages, 'tools': agent_trace.tool_specs(), 'chat_template_kwargs': {}})())
    ids = tokenizer.encode(prompt, add_special_tokens=False)
    starts = [i for i, value in enumerate(ids) if value == turn_token]
    turn_at, boundary = starts[-1], starts[-2]
    out['rows'].append({'round': round_id, 'edit_applied': applied, 'edit_note': note,
                        'prompt_tokens': len(ids), 'generation_turn_at': turn_at,
                        'previous_message_boundary': boundary, 'tail_tokens': turn_at - boundary,
                        'eligible': boundary >= 8192 and turn_at - boundary <= 1024})
print(json.dumps(out, ensure_ascii=False, sort_keys=True))
'''


def main() -> None:
    source_manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert sha256(TRACE) == TRACE_SHA256 == source_manifest["trace"]["sha256"]
    assert sha256(C_EDIT) == C_EDIT_SHA256 == source_manifest["C_edit"]["sha256"]
    c_edit = json.loads(C_EDIT.read_text(encoding="utf-8"))
    assert {row["round"]: row["prompt_tokens"] for row in c_edit["rounds"] if row["round"] in EXPECTED_PROMPT_TOKENS} == EXPECTED_PROMPT_TOKENS

    ops = load_ssh_ops()
    client = ops.connect()
    try:
        command = "/data2/FreeToken/venv/bin/python -c " + shlex.quote(REMOTE)
        stdin, stdout, stderr = client.exec_command(command)
        stdin.write(base64.b64encode(TRACE.read_bytes()).decode("ascii"))
        stdin.channel.shutdown_write()
        output = stdout.read().decode("utf-8")
        error = stderr.read().decode("utf-8")
        status = stdout.channel.recv_exit_status()
    finally:
        client.close()
    if error:
        print(error, end="", file=__import__("sys").stderr)
    if status:
        raise SystemExit(status)
    result = json.loads(output)
    assert {row["round"]: row["prompt_tokens"] for row in result["rows"]} == EXPECTED_PROMPT_TOKENS
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
