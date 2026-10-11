"""Strict R040d delivery verifier fed by ``r040d_d16_sampler_capture``."""
from __future__ import annotations

from r040d_d16_sampler_capture import CaptureError, SamplerCapture, _uid


class ServiceCaptureError(ValueError):
    pass


class ServiceCaptureAdapter:
    """Verify every actual DetokenizeMsg against the physical sampler history."""

    def __init__(self, sampler: SamplerCapture, expected_tokens: dict[str | int, int]) -> None:
        if not expected_tokens or any(type(count) is not int or count <= 0 for count in expected_tokens.values()):
            raise ServiceCaptureError("expected token counts must be positive")
        self.sampler = sampler
        self.expected = {_uid(uid): count for uid, count in expected_tokens.items()}
        self.deliveries: dict[str | int, list[int]] = {uid: [] for uid in self.expected}

    def observe_detokenize(self, message: object) -> None:
        uid, token = _uid(getattr(message, "uid", None)), getattr(message, "next_token", None)
        if uid not in self.expected or type(token) is not int:
            raise ServiceCaptureError("DetokenizeMsg UID/token binding differs")
        generation = len(self.deliveries[uid])
        physical = self.sampler.history(uid)
        if generation >= self.expected[uid] or generation >= len(physical):
            raise ServiceCaptureError("DetokenizeMsg lacks a physical sampler row")
        if token != physical[generation]:
            raise ServiceCaptureError("DetokenizeMsg does not match physical sampler token")
        self.deliveries[uid].append(token)

    def finalize(self) -> None:
        for uid, expected in self.expected.items():
            if len(self.sampler.history(uid)) != expected:
                raise ServiceCaptureError("physical sampler history does not equal expected delivery count")
            if len(self.deliveries[uid]) != expected:
                raise ServiceCaptureError("not every expected query has an actual DetokenizeMsg delivery")
