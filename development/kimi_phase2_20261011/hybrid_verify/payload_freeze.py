"""Stage-1 payload freezer for the 2026-10-11 hybrid verification window.

CPU-only. Starts no service, touches no GPU, stops nothing. Run on the server:

    cd /data2/FreeToken/development/kimi_phase2_20261011/hybrid_verify
    CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/data2/FreeToken/wt/release-e2/python \
    /data2/FreeToken/venv/bin/python -B payload_freeze.py --out payloads

Token counting and prompt rendering use the release-e2 (481d3a7) worktree's own
``TokenizeManager`` exactly the way ``freetoken.server.generation.count_prompt_tokens``
does: ``render_messages`` normalization, ``TokenizeMsg(text=messages, tools=tools,
chat_template_kwargs=None)``, ``manager.tokenize``. Each frozen payload is cross-checked
against the prompt_tokens that production actually reported for the same payload in
E2-R046g (round-01.api.json usage).

Per KIMI_RUNBOOK_PHASE2_20261011 section 1.4 the wire format for AIPerf is the frozen
single_turn shape (``{"text": ..., "output_length": 256, "extra": {...}}``, CRLF line
endings, same convention as inputs_X.jsonl): ``text`` is the payload rendered by the
release-e2 chat template, so the model sees the real conversation content at its real
length through the same chat endpoint path used by every previous X measurement.

LC2 lane 2 follows the runbook rule literally: add LC1 messages in order, keep as many
COMPLETE messages as fit in <= 32000 rendered tokens, drop a trailing assistant message.
The rule's outcome on the real LC1 payload is reported verbatim in PAYLOADS.json
(including when it is infeasible); a clearly-marked token-level prefix proposal is
emitted separately for the main session to rule on. The proposal file is never named
as an admission input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

MODEL = '/data2/FreeToken/models/Qwen3.8-Flash-Next-NVFP4-overlay'
WORKTREE = '/data2/FreeToken/wt/release-e2'
EXPECTED_COMMIT = '481d3a7074818b0b41f27d90a5cb0de6c6f2cfb9'

X_PATH = '/data2/FreeToken/development/d10_reanalysis_20261010/closed_loop_20261010/inputs_X.jsonl'
X_SHA = 'f63b3623bbb0ab10b0001d68a20138fb15a0ce8893f3a2d4c0202825a22a1162'

LC1_PATH = '/data2/_shared/runs/ft_rounds/E2-R046g/G_seed_real/round-01.payload.json'
LC1_SHA = 'e2f0533a6d8991d923a93a4644bcfcb2fc27cea9d9425043406002e881e41647'
LC1_API = '/data2/_shared/runs/ft_rounds/E2-R046g/G_seed_real/round-01.api.json'

LC2A_PATH = '/data2/_shared/runs/ft_rounds/E2-R046g/G_seed12k/round-01.payload.json'
LC2A_SHA = '8e542996dc2859107a337c7bc710e87bfb53099664d02eb847a15b6bd8ed2968'
LC2A_API = '/data2/_shared/runs/ft_rounds/E2-R046g/G_seed12k/round-01.api.json'

LC2_CAP_TOKENS = 32000
OUTPUT_LENGTH = 256
EXTRA = {'temperature': 0, 'top_p': 1, 'ignore_eos': False}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def drop_nones(value):
    if isinstance(value, dict):
        return {k: drop_nones(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [drop_nones(v) for v in value]
    return value


def load_manager():
    from transformers import AutoTokenizer
    from freetoken.tokenizer.tokenize import TokenizeManager
    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    return TokenizeManager(tokenizer)


def _msg(manager, messages, tools):
    from freetoken.core import SamplingParams
    from freetoken.message import TokenizeMsg
    from freetoken.server.generation import render_messages
    return TokenizeMsg(
        uid=0,
        text=render_messages(messages),
        sampling_params=SamplingParams(),
        chat_template_kwargs=None,
        tools=drop_nones(tools) if tools else None,
    )


def count_tokens(manager, messages, tools):
    (user,) = manager.tokenize([_msg(manager, messages, tools)])
    return int(user.input_ids.numel())


def render_prompt(manager, messages, tools):
    return manager.render_prompt(_msg(manager, messages, tools))


def write_jsonl(path, texts):
    with Path(path).open('xb') as handle:
        for text in texts:
            line = json.dumps(
                {'text': text, 'output_length': OUTPUT_LENGTH, 'extra': EXTRA},
                ensure_ascii=False,
            )
            handle.write(line.encode('utf8') + b'\r\n')


def production_prompt_tokens(api_path):
    doc = json.loads(Path(api_path).read_text())
    return doc.get('usage', {}).get('prompt_tokens')


def truncate_message_granularity(count, messages, cap):
    """The runbook LC2-lane-2 rule, verbatim: add messages in order, keep as many
    complete messages as fit within cap rendered tokens, drop a trailing assistant.
    ``count`` maps a message list to its rendered token count."""
    kept = []
    counts = []
    for message in messages:
        trial = kept + [message]
        n = count(trial)
        counts.append({'role': message.get('role'), 'cumulative_tokens': n})
        if n > cap:
            break
        kept = trial
    dropped_trailing_assistant = False
    if kept and kept[-1].get('role') == 'assistant':
        kept = kept[:-1]
        dropped_trailing_assistant = True
    final_tokens = count(kept) if kept else 0
    return {
        'kept_messages': kept,
        'kept_roles': [m.get('role') for m in kept],
        'kept_rendered_tokens': final_tokens,
        'dropped_trailing_assistant': dropped_trailing_assistant,
        'per_message_cumulative_tokens': counts,
        'feasible': bool(kept),
    }


def prefix_proposal(count, message0, cap):
    """NOT the runbook rule. A token-level prefix of LC1 message 0, kept as a single
    user message, capped at cap rendered tokens (tools included in the render via the
    count callable). Emitted only as a proposal artifact for the main session to rule on."""
    content = message0['content']
    lo, hi = 0, len(content)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if count([dict(message0, content=content[:mid])]) <= cap:
            lo = mid
        else:
            hi = mid - 1
    messages = [dict(message0, content=content[:lo])]
    tokens = count(messages)
    return messages, tokens, lo, len(content)


def worktree_state():
    head = subprocess.check_output(
        ['git', '-C', WORKTREE, 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(
        ['git', '-C', WORKTREE, 'status', '--porcelain'], text=True)
    return {
        'worktree': WORKTREE,
        'head': head,
        'head_matches_release_e2': head == EXPECTED_COMMIT,
        'dirty_lines': [line for line in dirty.splitlines() if line.strip()],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True, help='new output directory (must not exist)')
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)

    manifest = {'model': MODEL, 'worktree_state': worktree_state(), 'payloads': {}}
    if not manifest['worktree_state']['head_matches_release_e2']:
        raise RuntimeError('release-e2 worktree HEAD differs from 481d3a7')
    if manifest['worktree_state']['dirty_lines']:
        raise RuntimeError('release-e2 worktree is not clean')

    actual_x = sha256(X_PATH)
    manifest['payloads']['X'] = {
        'source': X_PATH, 'sha256': actual_x, 'matches_frozen_pin': actual_x == X_SHA,
        'note': 'two distinct ~1.2K-token prompts; reused unchanged from the frozen D08/D10 scope',
    }
    if actual_x != X_SHA:
        raise RuntimeError('frozen X input SHA differs')

    manager = load_manager()

    lc1 = json.loads(Path(LC1_PATH).read_text())
    lc1_sha = sha256(LC1_PATH)
    if lc1_sha != LC1_SHA:
        raise RuntimeError('LC1 source SHA differs from runbook pin')
    lc1_tokens = count_tokens(manager, lc1['messages'], lc1.get('tools'))
    lc1_rendered = render_prompt(manager, lc1['messages'], lc1.get('tools'))
    write_jsonl(out / 'inputs_LC1.jsonl', [lc1_rendered])
    lc1_prod = production_prompt_tokens(LC1_API)
    manifest['payloads']['LC1'] = {
        'source': LC1_PATH, 'sha256': lc1_sha,
        'messages': len(lc1['messages']), 'roles': [m.get('role') for m in lc1['messages']],
        'rendered_tokens': lc1_tokens,
        'production_prompt_tokens_round01': lc1_prod,
        'production_count_match': lc1_tokens == lc1_prod,
        'aiperf_input': str(out / 'inputs_LC1.jsonl'),
        'aiperf_input_sha256': sha256(out / 'inputs_LC1.jsonl'),
    }

    lc2a = json.loads(Path(LC2A_PATH).read_text())
    lc2a_sha = sha256(LC2A_PATH)
    if lc2a_sha != LC2A_SHA:
        raise RuntimeError('LC2 lane-1 source SHA differs from runbook pin')
    lc2a_tokens = count_tokens(manager, lc2a['messages'], lc2a.get('tools'))
    lc2a_rendered = render_prompt(manager, lc2a['messages'], lc2a.get('tools'))
    lc2a_prod = production_prompt_tokens(LC2A_API)
    manifest['payloads']['LC2_lane1'] = {
        'source': LC2A_PATH, 'sha256': lc2a_sha,
        'messages': len(lc2a['messages']), 'roles': [m.get('role') for m in lc2a['messages']],
        'rendered_tokens': lc2a_tokens,
        'production_prompt_tokens_round01': lc2a_prod,
        'production_count_match': lc2a_tokens == lc2a_prod,
    }

    lc1_count = lambda messages: count_tokens(manager, messages, lc1.get('tools'))
    rule = truncate_message_granularity(lc1_count, lc1['messages'], LC2_CAP_TOKENS)
    lane2 = {
        'derived_from': LC1_PATH, 'cap_tokens': LC2_CAP_TOKENS,
        'rule': 'keep longest prefix of complete messages under cap; drop trailing assistant',
        'feasible': rule['feasible'],
        'kept_roles': rule['kept_roles'],
        'kept_rendered_tokens': rule['kept_rendered_tokens'],
        'per_message_cumulative_tokens': rule['per_message_cumulative_tokens'],
    }
    if rule['feasible']:
        lc2b_rendered = render_prompt(manager, rule['kept_messages'], lc1.get('tools'))
        write_jsonl(out / 'inputs_LC2.jsonl', [lc2a_rendered, lc2b_rendered])
        lane2['aiperf_input'] = str(out / 'inputs_LC2.jsonl')
        lane2['aiperf_input_sha256'] = sha256(out / 'inputs_LC2.jsonl')
    else:
        proposal_messages, proposal_tokens, kept_chars, total_chars = prefix_proposal(
            lc1_count, lc1['messages'][0], LC2_CAP_TOKENS)
        proposal_payload = dict(lc1)
        proposal_payload['messages'] = proposal_messages
        (out / 'lc2b_proposal_prefix32k.payload.json').write_text(
            json.dumps(proposal_payload, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        proposal_rendered = render_prompt(manager, proposal_messages, lc1.get('tools'))
        write_jsonl(out / 'inputs_LC2.proposal.jsonl', [lc2a_rendered, proposal_rendered])
        lane2['proposal'] = {
            'status': 'NOT FROZEN - main session must rule; the runbook truncation rule is infeasible on the real LC1 payload',
            'method': 'token-level character prefix of LC1 message 0, single user message, tools retained in render',
            'kept_chars': kept_chars, 'message0_chars': total_chars,
            'rendered_tokens': proposal_tokens,
            'payload_json': str(out / 'lc2b_proposal_prefix32k.payload.json'),
            'payload_sha256': sha256(out / 'lc2b_proposal_prefix32k.payload.json'),
            'aiperf_input': str(out / 'inputs_LC2.proposal.jsonl'),
            'aiperf_input_sha256': sha256(out / 'inputs_LC2.proposal.jsonl'),
        }
    manifest['payloads']['LC2_lane2'] = lane2

    manifest_path = out / 'PAYLOADS.json'
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    print(json.dumps({'manifest': str(manifest_path), 'sha256': sha256(manifest_path),
                      'lc2_lane2_feasible': lane2['feasible']}, indent=2))


if __name__ == '__main__':
    sys.exit(main())
