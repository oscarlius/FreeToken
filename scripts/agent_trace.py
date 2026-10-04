#!/usr/bin/env python3
"""D07 dev-only ACK companion for the frozen agent-trace tool."""
import hashlib
import os
import sys
from pathlib import Path

_ORIGINAL = Path(__file__).with_name("_agent_trace_original.py")
_SHA256 = "332a1870378d5bffa4891180280060e70f6135b6acff21b48603a5fc98ad44d9"
_source = _ORIGINAL.read_bytes()
if hashlib.sha256(_source).hexdigest() != _SHA256:
    raise RuntimeError("frozen agent-trace companion hash mismatch")
_ns = {"__name__": "agent_trace_frozen", "__file__": str(_ORIGINAL)}
exec(compile(_source, str(_ORIGINAL), "exec"), _ns)

_consume, _write, _payload = _ns["consume_stream"], _ns["write_json"], _ns["build_payload"]
_evidence, _budgets = [], []

def consume_stream(events, t0):
    dev = []
    def seen():
        for event in events:
            if isinstance(event, dict) and "ft_dev" in event:
                dev.append(event["ft_dev"])
            yield event
    result = _consume(seen(), t0)
    if not dev or result.get("finish_reason") not in {"stop", "length", "tool_calls"}:
        raise RuntimeError("D07 requires ft_dev ACKs and finish_reason")
    uid = dev[0].get("uid")
    prior_seq = prior_cumulative = 0; acks = []
    for item in dev:
        if item.get("schema") != "ft_dev_stream/v1" or type(item.get("uid")) is not int or isinstance(item["uid"], bool) or item["uid"] < 0 or item["uid"] != uid:
            raise RuntimeError("invalid ft_dev UID/schema")
        seq, delta, cumulative = item.get("request_seq"), item.get("completion_tokens_delta"), item.get("completion_tokens_cumulative")
        if type(seq) is not int or type(delta) is not int or type(cumulative) is not int or isinstance(delta, bool) or delta not in (0, 1) or seq != prior_seq + 1 or cumulative != prior_cumulative + delta:
            raise RuntimeError("non-contiguous ft_dev acknowledgement")
        prior_seq, prior_cumulative = seq, cumulative
        acks.append({"completion_tokens_delta": delta, "request_seq": seq, "completion_tokens_cumulative": cumulative})
    if not any(item["completion_tokens_delta"] for item in acks):
        raise RuntimeError("D07 requires positive ACKs")
    if not _budgets:
        raise RuntimeError("route evidence lacks wire max_tokens")
    budget = _budgets.pop(0)
    if prior_cumulative > budget:
        raise RuntimeError("ACK completion exceeds wire max_tokens")
    usage = result.get("usage") or {}
    if usage.get("completion_tokens") is not None and usage["completion_tokens"] != prior_cumulative:
        raise RuntimeError("usage completion disagrees with ACKs")
    _evidence.append({"ack_schema": "ft_route_ack/v1", "uid": uid, "token_events": acks, "completion_tokens": prior_cumulative, "max_tokens": budget, "finish_reason": result["finish_reason"]})
    return result

def write_json(path, doc):
    rounds = doc.get("rounds") if isinstance(doc, dict) else None
    if rounds is not None:
        if len(rounds) != len(_evidence):
            raise RuntimeError("ACK evidence did not match written rounds")
        for row, proof in zip(rounds, _evidence):
            # generate stores metrics in round.record; replay stores them directly
            # in each round.  Preserve each established schema shape.
            target = row["record"] if "record" in row else row
            target.update(proof)
    return _write(path, doc)


def build_payload(*args, **kwargs):
    payload = _payload(*args, **kwargs)
    _budgets.append(payload["max_tokens"])
    return payload

def main():
    route_evidence = "--route-evidence" in sys.argv
    if route_evidence:
        sys.argv.remove("--route-evidence")
        _evidence.clear()
        _budgets.clear()
        _ns["consume_stream"] = consume_stream
        _ns["write_json"] = write_json
        _ns["build_payload"] = build_payload
    else:
        _ns["consume_stream"] = _consume
        _ns["write_json"] = _write
        _ns["build_payload"] = _payload
    return _ns["main"]()


if __name__ == "__main__":
    raise SystemExit(main())
