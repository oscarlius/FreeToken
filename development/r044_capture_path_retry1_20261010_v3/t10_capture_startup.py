#!/usr/bin/env python3
"""T10-only terminal-aware adapter around the reviewed service sampler observer.

The base observer deliberately requires an exact delivery count.  T10 declares
200 as a cap, so this wrapper narrows each UID's delivery expectation only
after its real terminal DetokenizeMsg has arrived.  It changes no candidate or
collector source and rejects omitted, extra, or nonterminal deliveries.
"""
from __future__ import annotations
import os
import types


def install_terminal_cap(adapter):
    cap = int(os.environ["FT_T10_CAPTURE_MAX_TOKENS"])
    if cap <= 0:
        raise ValueError("T10 capture cap must be positive")
    original_expected = {uid: list(rows) for uid, rows in adapter._expected_by_uid.items()}
    if not original_expected or any(len(rows) != cap for rows in original_expected.values()):
        raise ValueError("T10 requires exactly cap-sized predeclared UID delivery sets")
    original_report = adapter._report

    def terminal_deliveries(self):
        extras = []
        for uid, expected in original_expected.items():
            rows = [row for row in self.deliveries if row["uid"] == uid]
            if not 1 <= len(rows) <= cap:
                raise ValueError("T10 UID delivery count is outside the declared cap")
            if any(row["generation_index"] != index or row["finished"] for index, row in enumerate(rows[:-1])):
                raise ValueError("T10 UID has a premature terminal delivery or reordered generation")
            if rows[-1]["generation_index"] != len(rows) - 1 or rows[-1]["finished"] is not True:
                raise ValueError("T10 UID lacks a real terminal delivery")
            sampled = self.registry.get(uid)["sampled_tokens"]
            if len(sampled) < len(rows):
                raise ValueError("T10 physical sampler history is shorter than deliveries")
            self._expected_by_uid[uid] = expected[:len(rows)]
            extras.extend({"uid": uid, "generation_index": generation, "sampled_token_id": token,
                           "delivered": False, "reason": "physical sample after delivered terminal generation"}
                          for generation, token in enumerate(sampled[len(rows):], start=len(rows)))
        return extras

    def report(self, terminal, error, extras):
        result = original_report(terminal, error, extras)
        result["t10_terminal_cap"] = {"declared_max_tokens": cap, "actual_delivery_counts": {
            str(uid): sum(row["uid"] == uid for row in self.deliveries) for uid in original_expected}}
        return result

    adapter._delivery_extras = types.MethodType(terminal_deliveries, adapter)
    adapter._report = types.MethodType(report, adapter)
    return adapter


def main(argv=None):
    from equiv_suite import service_capture_startup as startup
    original = startup.install_from_env
    def install(engine):
        adapter = original(engine)
        return None if adapter is None else install_terminal_cap(adapter)
    startup.install_from_env = install
    startup.main(argv)


if __name__ == "__main__":
    main()
