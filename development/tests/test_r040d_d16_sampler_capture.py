"""CPU coverage for R040d's actual instance hook and strict delivery binding."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from r040d_d16_sampler_capture import CaptureError, SamplerCapture
from r040d_d16_service_capture_adapter import ServiceCaptureAdapter, ServiceCaptureError


@dataclass
class Request:
    uid: int
    device_len: int


@dataclass
class Batch:
    reqs: list[Request]
    sampled: list[int]


@dataclass
class Token:
    uid: int
    next_token: int


class Sampler:
    def sample(self, logits, args):
        return list(logits)


class Engine:
    def __init__(self):
        self.sampler = Sampler()

    def forward_batch(self, batch: Batch):
        return self.sampler.sample(batch.sampled, None)


def setup():
    engine, capture = Engine(), SamplerCapture()
    for uid in range(4):
        capture.bind_query(uid, 512 + uid)
    capture.attach(engine)
    return engine, capture, ServiceCaptureAdapter(capture, {uid: 128 for uid in range(4)})


def test_actual_hook_binds_four_uids_across_128_forwards_with_varying_order():
    engine, capture, delivery = setup()
    for generation in range(128):
        order = [(generation + shift) % 4 for shift in (2, 0, 3, 1)]
        sampled = [uid * 1000 + generation for uid in order]
        engine.forward_batch(Batch([Request(uid, 512 + uid + generation) for uid in order], sampled))
        # Delivery order need not equal the current physical batch order.
        for uid in range(4):
            delivery.observe_detokenize(Token(uid, uid * 1000 + generation))
    delivery.finalize()
    assert len(capture.captures) == 128
    assert all(len(rows) == 4 for rows in capture.captures)
    assert capture.history(3)[-1] == 3127


def test_actual_hook_rejects_a_partial_sampler_result_before_history_changes():
    engine, capture, _delivery = setup()
    batch = Batch([Request(uid, 512 + uid) for uid in range(4)], [10, 11, 12])
    with pytest.raises(CaptureError, match="rows do not equal"):
        engine.forward_batch(batch)
    assert all(capture.history(uid) == () for uid in range(4))


def test_actual_hook_rejects_history_gap_across_forwards():
    engine, _capture, _delivery = setup()
    engine.forward_batch(Batch([Request(uid, 512 + uid) for uid in range(4)], [10, 11, 12, 13]))
    with pytest.raises(CaptureError, match="history is missing or out of order"):
        engine.forward_batch(Batch([Request(uid, 514 + uid) for uid in range(4)], [20, 21, 22, 23]))


def test_delivery_rejects_missing_or_wrong_physical_row_immediately():
    engine, _capture, delivery = setup()
    engine.forward_batch(Batch([Request(uid, 512 + uid) for uid in range(4)], [10, 11, 12, 13]))
    with pytest.raises(ServiceCaptureError, match="does not match"):
        delivery.observe_detokenize(Token(2, 99))
    delivery.observe_detokenize(Token(2, 12))
    with pytest.raises(ServiceCaptureError, match="lacks a physical"):
        delivery.observe_detokenize(Token(2, 13))
