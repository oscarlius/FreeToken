import importlib.util
import json
import os
from pathlib import Path
import pytest

P = Path(__file__).parent / 'eta_retry2_microbench.py'
spec = importlib.util.spec_from_file_location('eta_retry2', P)
eta = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eta)

BASE = ['taskset','-c','1,3-47','/data2/FreeToken/venv/bin/ft','serve','--model-path','m','--moe-strategy','offload','--max-running-requests','2']


def test_final_engine_argv_is_exact_and_has_no_unsupported_stats_flag():
    assert eta.final_engine_argv(BASE) == ['--model-path','m','--moe-strategy','offload','--max-running-requests','2']
    with pytest.raises(RuntimeError):
        eta.final_engine_argv(BASE + ['--moe-collect-stats'])


def test_copy_budget_is_48_real_layer_calls_totaling_367():
    budget = eta.copy_budget(48)
    assert len(budget) == 48 and sum(budget) == 367 and set(budget) == {7, 8}
    with pytest.raises(RuntimeError): eta.copy_budget(47)


def test_slot_selection_is_disjoint_and_requires_free_budget():
    slots = eta.choose_copy_slots(2700, list(range(480)))
    assert len(slots) == 367 and not set(slots) & set(range(480))
    with pytest.raises(RuntimeError): eta.choose_copy_slots(1000, [])


def test_eta_always_calculates_with_deviation_and_measured_bound():
    result = eta.classify_eta(40.0, 60.0, 75.0)
    assert result['deviation_exceeded'] is True
    assert 'eta' in result and result['measured_bound_tok_s'] > 0


def test_map_proof_requires_a_stable_actual_graph_replay():
    class Tensor:
        def __init__(self, values): self.values = values
        def clone(self): return Tensor(self.values[:])
        def detach(self): return self
        def cpu(self): return self
        def tolist(self): return self.values
    class Torch:
        @staticmethod
        def equal(a, b): return a.values == b.values
        class cuda:
            @staticmethod
            def synchronize(): pass
    class Cache:
        slot_for_id = Tensor([1]); id_of_slot = Tensor([2])
    class Graph:
        def replay(self): pass
    proof = eta.warm_until_stable_cache(Torch, Graph(), Cache())
    assert proof['map_state_unchanged'] is True and proof['occupied_slots'] == 1


def test_graph_route_proof_requires_live_per_layer_slot_resolution_not_stable_map():
    class Scalar:
        def __init__(self, value): self.value = value
        def item(self): return self.value
    class Tensor:
        def __init__(self, values, ptr=1):
            self.values, self._ptr = values, ptr
            self.device = type('Device', (), {'type': 'cuda'})()
            self.shape = (1, len(values))
        def detach(self): return self
        def reshape(self, _): return self
        def cpu(self): return self
        def tolist(self): return self.values
        def data_ptr(self): return self._ptr
    class Ids:
        def __getitem__(self, slot): return Scalar(slot)
    class Slots:
        def __getitem__(self, key): return Scalar(key[0])
    class Cache:
        cache_size, num_experts = 100, 1
        id_of_slot, slot_for_id = Ids(), Slots()
    buffers = {layer: Tensor([layer], layer + 1) for layer in range(eta.LAYERS)}
    slots, rows = eta.prove_graph_route_residency(buffers, Cache())
    assert slots == set(range(eta.LAYERS)) and len(rows) == eta.LAYERS
    buffers[0] = Tensor([-1])
    with pytest.raises(RuntimeError, match='invalid/nonresident'):
        eta.prove_graph_route_residency(buffers, Cache())
    buffers[0] = Tensor([0], 2)
    with pytest.raises(RuntimeError, match='aliases'):
        eta.prove_graph_route_residency(buffers, Cache())


def test_graph_route_proof_rejects_descriptor_not_tied_to_cuda_graph():
    class Tensor:
        device = type('Device', (), {'type': 'cpu'})()
    class Cache: pass
    with pytest.raises(RuntimeError, match='not a captured CUDA tensor'):
        eta.prove_graph_route_residency({layer: Tensor() for layer in range(eta.LAYERS)}, Cache())


def test_copy_targets_must_be_free_and_disjoint_from_actual_graph_routes():
    class Scalar:
        def __init__(self, value): self.value = value
        def item(self): return self.value
    class Ids:
        def __getitem__(self, slot): return Scalar(-1 if slot == 9 else 100)
    class Cache:
        id_of_slot = Ids()
    eta.validate_copy_targets(Cache(), [9], {1, 2})
    with pytest.raises(RuntimeError, match='graph-routed'):
        eta.validate_copy_targets(Cache(), [2], {1, 2})
    with pytest.raises(RuntimeError, match='physically free'):
        eta.validate_copy_targets(Cache(), [3], set())


def _binding(schema, **state):
    source = eta.sha256(P)
    return {'schema': schema, **state,
            'source_pins': {'candidate_commit': eta.EXPECTED_COMMIT, 'eta_sha256': source},
            'measure': {'eta_path': eta.ETA_RELATIVE_PATH, 'input_x_sha256': eta.EXPECTED_INPUT_SHA},
            'paths_hashes': {'eta_retry2_microbench.py': source, 'inputs_X.jsonl': eta.EXPECTED_INPUT_SHA}}


def _readonly(path, value):
    path.write_text(json.dumps(value)); os.chmod(path, 0o444)


def test_receipt_rejects_writable_schema_and_binding(tmp_path):
    p = tmp_path / 'admit.json'; p.write_text('{}')
    with pytest.raises(RuntimeError): eta.validate_admission(p)
    _readonly(p, _binding(eta.ADMISSION_SCHEMA, admit=True))
    assert eta.validate_admission(p) == eta.sha256(p)
    os.chmod(p, 0o644); p.write_text(json.dumps(_binding('wrong', admit=True))); os.chmod(p, 0o444)
    with pytest.raises(RuntimeError): eta.validate_admission(p)


def test_cpu_review_requires_pass(tmp_path):
    p = tmp_path / 'review.json'; _readonly(p, _binding(eta.CPU_REVIEW_SCHEMA, status='FAIL'))
    with pytest.raises(RuntimeError): eta.validate_cpu_review(p)
