"""Default-off switches must be declared defaults, not attributes injected by Scheduler.

``prefill.py`` read ``PrefillManager.layer_major`` and ``scheduler.py`` read
``Scheduler.d3_extra_anchor_ids`` unconditionally, while both were only assigned inside
``Scheduler.__init__``. Anything building a PrefillManager without a Scheduler -- the whole
chunked-prefill suite -- died on AttributeError, and serving without
``--enable-special-token-ckpt`` failed during init.
"""

from __future__ import annotations

import dataclasses
import inspect


def _defaults(cls):
    return {f.name: f.default for f in dataclasses.fields(cls)}


def test_prefill_switches_default_off():
    from freetoken.scheduler.prefill import PrefillAdder, PrefillManager

    for cls in (PrefillAdder, PrefillManager):
        d = _defaults(cls)
        assert d["layer_major"] is False, f"{cls.__name__}.layer_major must default to False"
        assert d["anchor_ids"] == frozenset(), f"{cls.__name__}.anchor_ids must default empty"


def test_scheduler_initializes_anchor_ids_before_reading_them():
    from freetoken.scheduler.scheduler import Scheduler

    lines = [ln.strip() for ln in inspect.getsource(Scheduler.__init__).splitlines()]
    init = next((i for i, ln in enumerate(lines) if ln.startswith("self.d3_extra_anchor_ids")), None)
    read = next((i for i, ln in enumerate(lines) if "set(self.d3_extra_anchor_ids)" in ln), None)
    assert init is not None, "no self.d3_extra_anchor_ids assignment found"
    assert read is not None, "attribute is no longer read -- drop this test with the code"
    assert init < read, "d3_extra_anchor_ids must be initialized before it is read"
