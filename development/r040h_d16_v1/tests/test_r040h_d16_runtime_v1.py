"""CPU regression for R040h's real retry wiring; never launches a service."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

RUNTIME = Path(__file__).parents[1] / "runtime"


def load(name):
    spec = importlib.util.spec_from_file_location(name, RUNTIME / f"{name}.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_runtime_warm_priming_uses_contiguous_int32():
    source = (RUNTIME / "d16_exact_service_startup.py").read_text()
    assert "torch.zeros((1, 1), dtype=torch.int32, device=cache.device).contiguous()" in source


def test_filedry_collector_skips_cold_and_has_exact_eight_services(monkeypatch, tmp_path):
    entry = load("r040h_d16_remaining_prepare_v1")
    dry = load("r040h_d16_remaining_dryrun_v1")
    collector = SimpleNamespace(
        collect_cache_processes=lambda *_a, **_k: {"arms": [{"arm": "warm_0"}, {"arm": "warm_1"}]},
        collect_native_processes=lambda *_a, **_k: {"arms": [{"arm": f"interleave_{n}"} for n in range(6)]},
    )
    original_load = entry.load
    monkeypatch.setattr(entry, "load", lambda path, name: collector if path.name == "r040f_d16_process_collection_v2.py" else original_load(path, name))
    monkeypatch.setattr(entry, "d04_binding", lambda: {})
    monkeypatch.setattr(dry.os, "getuid", lambda: 1000, raising=False)
    # Exercise the dry-run body without its host/lock admission dependencies.
    owner = SimpleNamespace(proc=None, port=31415)
    monkeypatch.setattr(entry, "source_bindings", lambda: {"entry": "sha"})
    monkeypatch.setattr(entry, "base_module", lambda: SimpleNamespace(shared_protocol=lambda: SimpleNamespace(LOCK=tmp_path / "lock", load_owned_lifecycle=lambda: object()), prepare=lambda *_: None))
    monkeypatch.setattr(entry, "predecessor_checks", lambda *_: None)
    monkeypatch.setattr(entry, "create_service_owner", lambda *_a, **_k: owner)
    monkeypatch.setattr(entry, "retained_r040e_slots4_binding", lambda *_: {"slots4": True})
    monkeypatch.setattr(entry, "retained_r040g_partial_binding", lambda *_: {"parking": {"arms": [1]*4}, "cache_cold": {"arms": [1]*2}})
    monkeypatch.setattr(entry, "metadata_input_binding", lambda *_: {})
    monkeypatch.setattr(entry, "r055_section10_basis", lambda *_: {})
    monkeypatch.setattr(dry, "foreign_lock_snapshot", lambda *_: {"state": "absent"})
    monkeypatch.setattr(dry, "foreign_lock_after", lambda *_: "unchanged_absent")
    monkeypatch.setattr(dry, "getpass", SimpleNamespace(getuser=lambda: "cpu"))
    monkeypatch.setattr(dry.subprocess, "check_output", lambda *_a, **_k: "cpu-time\n")
    entry.ROUNDS = tmp_path; entry.RID = "E2-R040h"; entry.HERE = RUNTIME
    out = tmp_path / ".dryrun_r040h_cpu"
    receipt = dry.dry_run(out, entry=entry, after="E2-R040g", collector_review=tmp_path / "review",
                          collector_review_sha256="x", seed_sha256="y")
    assert receipt["service_file_scopes"] == 8 and receipt["maximum_generation_calls"] == 10
    assert [row["arm"] for row in receipt["arms"]["cache"]["arms"]] == ["warm_0", "warm_1"]


def test_actual_run_body_rejects_wrong_warm_or_interleave_scope(monkeypatch):
    entry = load("r040h_d16_remaining_prepare_v1")
    class Base:
        def shared_protocol(self): return object()
        load_source = staticmethod(lambda path, name: object())
        write_new = staticmethod(lambda *_: None)
        def run_supplement_body(self, *_a, **_k):
            return ({"d16": {"cache": {"arms": [{"arm": "warm_0"}]}, "interleave": {"arms": [{}] * 6}}}, {"p": 1})
    base = Base()
    monkeypatch.setattr(entry, "base_module", lambda: base)
    monkeypatch.setattr(entry, "require_dry_run_receipt", lambda *_: {"path": "dry", "sha256": "x", "document": {"collector_review": "r", "collector_review_sha256": "s"}})
    monkeypatch.setattr(entry, "require_startup_review", lambda *_: {})
    monkeypatch.setattr(entry, "create_service_owner", lambda *_: object())
    monkeypatch.setattr(entry, "retained_r040e_slots4_binding", lambda *_: {})
    monkeypatch.setattr(entry, "retained_r040g_partial_binding", lambda *_: {"parking": {"arms": [{}]*4}, "cache_cold": {"arms": [{}]*2}})
    monkeypatch.setattr(entry, "load", lambda *_: object())
    def execute(**_):
        with pytest.raises(RuntimeError, match="scope differs"):
            base.run_supplement_body(None, None, None, None, None)
    base.execute = execute
    entry.execute(dry_receipt=Path("dry"), after="E2-R040g")


@pytest.mark.parametrize('mismatch', [None, 'tokens', 'states'])
def test_actual_run_body_combines_retained_evidence_before_publication(monkeypatch, mismatch):
    from copy import deepcopy
    entry = load('r040h_d16_remaining_prepare_v1')
    reference = {'input_ids_sha256': 'input', 'tokens': [783] * 128,
                 'text': ' Y' * 128, 'states': {'before': 'x', 'after': 'y'}}
    cold = [dict(deepcopy(reference), arm=f'cold_{n}') for n in range(2)]
    warm = [dict(deepcopy(reference), arm=f'warm_{n}') for n in range(2)]
    if mismatch:
        warm[0][mismatch] = 'different'
    retained = {'parking': {'arms': [{'arm': str(n)} for n in range(4)]},
                'cache_cold': {'arms': cold}}
    published = []
    class Base:
        load_source = staticmethod(lambda *_: None)
        write_new = staticmethod(lambda *_: None)
        shared_protocol = staticmethod(lambda: None)
        def run_supplement_body(self, *args, **kwargs):
            assert 'write_json' not in kwargs, 'partial result must not be published'
            return {'d16': {'cache': {'arms': warm}, 'interleave': {'arms': [{}] * 6}}}, {'source': 'sealed'}
        def execute(self, **kwargs):
            return self.run_supplement_body(write_json=lambda name, value: published.append((name, deepcopy(value))))
    base = Base()
    monkeypatch.setattr(entry, 'base_module', lambda: base)
    monkeypatch.setattr(entry, 'require_dry_run_receipt', lambda *_: {})
    monkeypatch.setattr(entry, 'load', lambda *_: object())
    monkeypatch.setattr(entry, 'retained_r040e_slots4_binding', lambda *_: {})
    monkeypatch.setattr(entry, 'retained_r040g_partial_binding', lambda *_: deepcopy(retained))
    if mismatch:
        with pytest.raises(RuntimeError, match='differs from retained cold controls'):
            entry.execute(dry_receipt=Path('dry'))
        assert published == []
    else:
        result, provenance = entry.execute(dry_receipt=Path('dry'))
        assert [row['arm'] for row in result['d16']['cache']['arms']] == ['cold_0', 'cold_1', 'warm_0', 'warm_1']
        assert result['d16']['parking'] == retained['parking']
        assert (result['new_services'], result['new_generation_calls']) == (8, 10)
        assert published == [('d16_input_provenance.json', provenance), ('r040h_d16_supplement.json', result)]


def test_actual_warm_initializer_sends_native_int32_contiguous_ids(tmp_path, monkeypatch):
    import json
    from contextlib import nullcontext
    torch = pytest.importorskip('torch')
    startup = load('d16_exact_service_startup')
    calls = []
    class Cache:
        device = 'cpu'
        num_layers = cache_size = 2
        id_of_slot = torch.full((2,), -1, dtype=torch.int32)
        is_cpu_layer = staticmethod(lambda _: False)
        is_unpinned_layer = staticmethod(lambda _: False)
        copy_missing = reset_stats = staticmethod(lambda: None)
        def reset(self):
            self.id_of_slot.fill_(-1)
        def ensure_experts(self, layer, ids):
            assert ids.dtype == torch.int32 and ids.is_contiguous()
            calls.append((layer, ids.tolist()))
            self.id_of_slot[layer] = layer
    cache = Cache()
    engine = SimpleNamespace(moe_offload_cache=cache,
        stream=SimpleNamespace(synchronize=lambda: None), forward_batch=lambda *_: None)
    scheduler = SimpleNamespace(engine=engine, engine_stream_ctx=nullcontext(), shutdown=lambda: None)
    monkeypatch.setenv('FT_D16_CACHE_INIT', 'warm')
    monkeypatch.setenv('FT_D16_SERVICE_CAPTURE_DIR', str(tmp_path))
    monkeypatch.setenv('FT_D16_EXECUTION_ID', 'cpu:tp0')
    startup.configure_expert_cache(scheduler)
    assert calls == [(0, [[0]]), (1, [[0]])]
    record = json.loads((tmp_path / 'expert_cache/initialization.json').read_text())
    assert record['resident_count'] == 2 and record['priming_requests'] == 0
