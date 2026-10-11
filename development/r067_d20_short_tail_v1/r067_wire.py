"""Stable, importable R067 message types for tokenizer/backend process transport."""
from __future__ import annotations

from dataclasses import dataclass

from freetoken.message.backend import UserMsg
from freetoken.message.tokenizer import TokenizeMsg


@dataclass
class R067ExactIdsMsg(TokenizeMsg):
    input_ids_exact: list[int] | None = None
    schedule_id: str = ""


@dataclass
class R067UserMsg(UserMsg):
    r067_cold: dict | None = None


def register_wire_types() -> None:
    import freetoken.message.backend as backend
    import freetoken.message.tokenizer as tokenizer
    backend.R067UserMsg = R067UserMsg
    tokenizer.R067ExactIdsMsg = R067ExactIdsMsg
