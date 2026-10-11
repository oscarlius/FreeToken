"""Test-only CPU fixture for the real D16 worker function; never a model server."""
import hashlib
import json
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import worker_capture


def main():
    capture, dump, _ = worker_capture.prepare_environment()
    cleanup_failure = os.environ.get("FT_D12_CPU_FIXTURE_CLEANUP_FAILURE") == "1"
    replay = worker_capture.load_from_env()
    natural = os.environ.get("FT_D12_CAPTURE_POLICY") == "natural-terminal-v1"
    requests = replay["requests"] if replay is not None else [{"uid": 0, "input_ids": [2, 3], "max_tokens": 1}]
    import torch
    from freetoken.core import SamplingParams
    from freetoken.message import DetokenizeMsg, UserMsg
    from freetoken.kvcache import linear_state_pool
    from equiv_suite import service_capture_startup

    assert linear_state_pool.DUMP_PATH == str(dump)
    assert Path(linear_state_pool.__file__).resolve() == Path(os.environ["FT_D12_NATIVE_SOURCE"]).resolve() / "python/freetoken/kvcache/linear_state_pool.py"

    class Cache:
        quant_format = "nvfp4"
        prefill_overlap = False
        prefill_routed_only_max_tokens = 256
        device = SimpleNamespace(type="cuda")  # Protocol shape only; all tensors below are CPU.

        def prepare_prefill_routed_only(self, layer, ids):
            assert ids.device.type == "cpu"
            return "cpu_fixture_no_cuda"  # Explicit fallback: never emits bank equality success.

    class Sampler:
        def sample(self, logits, args):
            return logits.argmax(-1)

    class Engine:
        def __init__(self):
            self.ctx = SimpleNamespace(route_tracer=None, batch=None)
            self.moe_offload_cache = Cache()
            self.sampler = Sampler()
            pool = linear_state_pool.LinearStatePool.__new__(linear_state_pool.LinearStatePool)
            pool.conv_states = torch.zeros(1, 1, 2, dtype=torch.bfloat16)
            pool.recurrent_states = torch.zeros(1, 1, 2, dtype=torch.float32)
            pool.slot_states = {"ple_conv": torch.zeros(1, 1, 2), "ple_ngram_ctx": torch.zeros(1, 1, 2, dtype=torch.int64)}
            self.linear_state_pool = pool

        def forward_batch(self, batch, logits):
            self.ctx.batch = batch
            try:
                if batch.is_prefill:
                    count = sum(req.device_len - req.cached_len for req in batch.reqs)
                    self.moe_offload_cache.prepare_prefill_routed_only(0, torch.zeros((count, 1), dtype=torch.int32))
                self.linear_state_pool.conv_states.add_(1)
                return self.sampler.sample(logits, SimpleNamespace(temperatures=None))
            finally:
                self.ctx.batch = None

    instances = []

    class Scheduler:
        def __init__(self, args):
            assert linear_state_pool.DUMP_PATH == str(dump)
            self.engine, self.gpus, self.shutdown_calls = Engine(), [], 0
            instances.append(self)

        def sync_all_ranks(self):
            assert getattr(self.shutdown, "_d12_capture", False)

        def _process_one_msg(self, message):
            return None

        def _schedule_next_batch(self):
            return None

        def send_result(self, message):
            return None

        @torch.inference_mode()  # Matches the actual Scheduler.run_forever boundary.
        def run_forever(self):
            for row in requests:
                user = UserMsg(uid=row["uid"], input_ids=torch.tensor(row["input_ids"], dtype=torch.int32),
                               sampling_params=SamplingParams(max_tokens=row["max_tokens"], temperature=0))
                self._process_one_msg(user)
                request = SimpleNamespace(uid=row["uid"], input_ids=user.input_ids, cached_len=0,
                                          device_len=len(row["input_ids"]), linear_slot_idx=0)
                count = row["uid"] + 1 if natural else 1
                for index in range(count):
                    request.device_len = len(row["input_ids"]) + index
                    batch = SimpleNamespace(reqs=[request], is_prefill=index == 0)
                    sampled = self.engine.forward_batch(batch, torch.tensor([[0., 2., 1.]]))
                    self.send_result(DetokenizeMsg(uid=row["uid"], next_token=int(sampled[0]), finished=index == count - 1))
            if cleanup_failure:
                self.engine.forward_batch = lambda *_: None  # Simulate loss of observer ownership.
                raise ValueError("cpu-fixture-primary-error")
            raise KeyboardInterrupt

        def shutdown(self):
            self.shutdown_calls += 1

    # Replace the hardware owner only. The imported D16 worker code, adapter,
    # sampler capture, D12 observers and native state-pool dump execute normally.
    scheduler_module = ModuleType("freetoken.scheduler")
    scheduler_module.Scheduler = Scheduler
    sys.modules["freetoken.scheduler"] = scheduler_module
    metadata_module = ModuleType("freetoken.kvcache.cache_status")
    metadata_module.compute_cache_status_meta = lambda _: {"scope": "cpu-fixture"}
    sys.modules["freetoken.kvcache.cache_status"] = metadata_module
    original_install = service_capture_startup.install_scheduler_capture
    original_factory = service_capture_startup.install_from_env
    original_prepare = Cache.prepare_prefill_routed_only
    acknowledgements = []
    args = SimpleNamespace(shell_mode=False, gpu_assigned=("0",), gpu=None, silent_output=False,
                           tp_info=SimpleNamespace(size=1, rank=0, is_primary=lambda: True))
    primary_error = None
    try:
        worker_capture.run_scheduler(args, SimpleNamespace(put=acknowledgements.append))
    except ValueError as exc:
        if not cleanup_failure or str(exc) != "cpu-fixture-primary-error":
            raise
        primary_error = str(exc)
    assert (primary_error is not None) == cleanup_failure
    assert service_capture_startup.install_scheduler_capture is original_install
    assert service_capture_startup.install_from_env is original_factory
    assert Cache.prepare_prefill_routed_only is original_prepare
    assert "Scheduler is ready" in acknowledgements
    delivery_file = "d12_natural_service_delivery.json" if natural else "service_delivery.json"
    delivery = json.loads((capture / delivery_file).read_text())
    natural_result = None
    if natural:
        from natural_capture import make_policy, read_natural_delivery
        from equiv_suite.sampler_capture import _self_identity
        from d16_native_capture_shutdown_v3 import read_sealed_service_delivery, NativeCaptureShutdownError
        assert not (capture / "service_delivery.json").exists()
        try:
            read_sealed_service_delivery(capture.parent)
        except NativeCaptureShutdownError:
            pass
        else:
            raise AssertionError("fixed D16 reader must reject natural artifacts")
        if not cleanup_failure:
            probe = Path(os.environ["FT_D16_D03_TOOL"])
            natural_result = read_natural_delivery(capture,
                expected_policy=make_policy(replay, int(os.environ["FT_D16_SERVICE_CAPTURE_MAX_CAPTURES"]),
                                            int(os.environ["FT_D16_SERVICE_CAPTURE_MAX_BYTES"])),
                process_identity=_self_identity(), logits_probe=probe,
                logits_probe_sha256="7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7")
    rows = [json.loads(line) for line in (capture / "d12_events.jsonl").read_text().splitlines()]
    assert len(rows) == 2 * len(requests)
    for row in rows:
        assert row["process_identity"] == delivery["process_identity"]
        uid = row["evidence"].get("context", row["evidence"].get("outer"))["uid"]
        admission = next(info for info in delivery["admission_receipts"] if info["uid"] == uid)
        assert row["physical_event_identity"] == admission["physical_event_identity"]
        if replay is not None:
            assert row["frozen_input"]["bundle_sha256"] == replay["bundle_sha256"]
    assert rows[0]["evidence"]["equality_verified"] is False
    for info in rows[1]["evidence"]["role_files"].values():
        assert hashlib.sha256((dump / info["path"]).read_bytes()).hexdigest() == info["sha256"]
    report = {"scope": "actual D16 startup and capture with CPU Scheduler fixture; no model or CUDA",
              "cuda_initialized": torch.cuda.is_initialized(), "native_shutdown_calls": instances[0].shutdown_calls,
              "service_terminal": delivery["terminal"], "event_schemas": [row["evidence"]["schema"] for row in rows],
              "bank_equality_claimed": False, "primary_error": primary_error,
              "frozen_admission_count": len(requests) if replay is not None else 0,
              "capture_mode": "natural-terminal-v1" if natural else "fixed-generation",
              "natural_reader": natural_result}
    assert delivery["terminal"] == ("failed" if cleanup_failure else "complete")
    if cleanup_failure:
        assert any("D12 cleanup failed" in message for message in delivery["errors"])
    with (capture / "cpu_fixture_result.json").open("x") as output:
        json.dump(report, output, indent=2)
    assert report["cuda_initialized"] is False


if __name__ == "__main__":
    main()
