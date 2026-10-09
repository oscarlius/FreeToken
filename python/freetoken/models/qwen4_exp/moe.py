from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import torch
from freetoken.kernel.triton.moe_shared_gate import shared_gate_mul_add, shared_gate_sigmoid
from freetoken.models.qwen3_5_moe.moe import Qwen3_5MoE
from freetoken.layers.moe import PendingOffloadDecode

if TYPE_CHECKING:
    from freetoken.models.config import ModelConfig


@dataclass
class PendingQwen4ExpMoE:
    shared: torch.Tensor
    gate: torch.Tensor
    routed: PendingOffloadDecode


class Qwen4ExpMoE(Qwen3_5MoE):
    """Qwen3_5MoE with the shared-expert gate on triton instead of gemv + sigmoid + mul + add.

    Same weights, same state dict. The gate reduction stays ahead of the routed experts, which may write into ``hidden_states`` in place.
    """

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        num_tokens, hidden_dim = hidden_states.shape
        hidden_states = hidden_states.view(-1, hidden_dim)
        router_logits = self.gate.forward(hidden_states)
        shared = self.shared_expert.forward(hidden_states)
        gate = shared_gate_sigmoid(hidden_states, self.shared_expert_gate.weight.view(-1))
        routed = self.experts.forward(hidden_states=hidden_states, router_logits=router_logits)
        return shared_gate_mul_add(routed, shared, gate).view(num_tokens, hidden_dim)

    def decode_prepare(self, hidden_states: torch.Tensor) -> PendingQwen4ExpMoE:
        """Prepare a real Qwen4Exp MoE decode layer for D10's copy/GEMM split."""
        num_tokens, hidden_dim = hidden_states.shape
        hidden_states = hidden_states.view(-1, hidden_dim)
        router_logits = self.gate.forward(hidden_states)
        shared = self.shared_expert.forward(hidden_states)
        gate = shared_gate_sigmoid(hidden_states, self.shared_expert_gate.weight.view(-1))
        routed = self.experts.decode_prepare(hidden_states, router_logits)
        return PendingQwen4ExpMoE(shared, gate, routed)

    def decode_copy(self, pending: PendingQwen4ExpMoE) -> None:
        self.experts.decode_copy(pending.routed)

    def decode_finish(self, pending: PendingQwen4ExpMoE) -> torch.Tensor:
        routed = self.experts.decode_finish(pending.routed)
        return shared_gate_mul_add(routed, pending.shared, pending.gate)


__all__ = ["Qwen4ExpMoE"]
