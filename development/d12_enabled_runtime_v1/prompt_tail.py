"""Single-request prompt-tail observation using the pinned D03 collector/writer.

Only explicit instance installation adds observers. The model's forward methods,
request inputs, chunk schedule and returned tensors remain the original path.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import MethodType, SimpleNamespace
import weakref


D03_FILES = {
    "python/freetoken/dev_tools/logits.py": "3c3d1f38d1cec266343b365ef15a2f78bc64560f4c4ddc0e6387b2fbe0b04d0d",
    "python/freetoken/layers/embedding.py": "69bf5f40d5f234a4eb83181436ba9c2c8ed2556d316e56956996d49602055fd4",
    "python/freetoken/kvcache/linear_state_pool.py": "69c0e486d1fb6b5a044dca1f02ea5ccbaebb72fcbbc409a0e7f09bebaf6be92d",
    "scripts/logits_probe.py": "7ab4fd3a256c2fd3d510bd63d77b5181a648e5d8f8609ebf1a52b68f3a6c45e7",
}
ROLES = {"conv_states", "recurrent_states", "slot:ple_conv", "slot:ple_ngram_ctx"}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _raw(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_d03(root):
    root = Path(root).absolute()
    paths = []
    for relative, digest in D03_FILES.items():
        path = root / relative
        if path.resolve() != path or not path.is_file() or _sha(path.read_bytes()) != digest:
            raise ValueError("D12 pinned D03 source differs: " + relative)
        paths.append(path)
    return paths


def load_d03(root):
    modules = []
    for path in validate_d03(root):
        # A layers package name preserves embedding.py's relative imports while
        # resolving its dependencies from the active candidate, not another venv.
        name = "freetoken.layers._d12_d03_" + path.stem
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return SimpleNamespace(collector=modules[0].capture_logits,
                           project=modules[1].ParallelLMHead.project_rows,
                           write=modules[2].LinearStatePool.dump_dev_tensors,
                           reader=modules[3])


def make_policy(binding, d03, max_hidden_bytes, k=64):
    if type(k) is not int or not 1 <= k <= 64 or type(max_hidden_bytes) is not int or max_hidden_bytes <= 0:
        raise ValueError("D12 prompt tail requires bounded K and hidden bytes")
    rows = []
    for request in binding["requests"]:
        ids = request["input_ids"]
        if (not isinstance(ids, list) or len(ids) <= k
                or any(type(token) is not int or not 0 <= token < 2**31 for token in ids)):
            raise ValueError("D12 prompt tail requires a nonempty derived prefix")
        rows.append({"uid": request["uid"], "payload_sha256": request["payload_sha256"],
                     "input_ids_json_sha256": request["input_ids_json_sha256"],
                     "input_prefix_sha256": d03.reader.sha(ids), "input_length": len(ids),
                     "prefix_length": len(ids) - k, "prefix_sha256": d03.reader.sha(ids[:-k]),
                     "suffix_sha256": d03.reader.sha(ids[-k:]), "k": k,
                     "positions": list(range(len(ids) - k, len(ids)))})
    if not rows or len({row["uid"] for row in rows}) != len(rows):
        raise ValueError("D12 prompt tail requires distinct declared UIDs")
    return {"schema": "ft_d12_prompt_tail_policy/v1", "bundle_sha256": binding["bundle_sha256"],
            "requests": rows, "max_retained_hidden_bytes": max_hidden_bytes, "d03_source_sha256": D03_FILES,
            "prompt_tail_fixed_input": True, "restore_arm": False, "generated_suffix": False,
            "output_equivalence_verified": False,
            "input_definition": "P=input[:-K], X=input[-K:]; original ordinary request and cache history"}


class PromptTailCapture:
    """Observe final-layer children; feed their post-mixer rows to D03 unchanged."""

    def __init__(self, engine, binding, state_root, destination, d03, context_provider, emit,
                 *, max_hidden_bytes, k=64):
        import torch

        self.torch, self.engine, self.d03 = torch, engine, d03
        self.state_root, self.destination = Path(state_root), Path(destination)
        if os.environ.get("FT_DEV_LOGITS_DUMP") != str(self.destination):
            raise ValueError("D12 prompt tail dump environment differs")
        self.policy = make_policy(binding, d03, max_hidden_bytes, k)
        self.specs = {row["uid"]: row for row in self.policy["requests"]}
        self.head = engine.model.lm_head
        self.layer = engine.model.model.layers.op_list[-1]
        self.mixer = engine.model.model.hyper_connection_mixer
        if self.head.tp_size != 1 or self.mixer.use_combine is not False:
            raise ValueError("D12 prompt-tail projection requires TP1 and the top mixer")
        self.original_layer, self.original_mix = self.layer.forward, self.mixer.mix
        if getattr(self.original_layer, "_d12_prompt_tail", False):
            raise ValueError("D12 prompt tail is already installed")
        self.provider, self.emit = context_provider, emit
        self.pending, self.observed, self.completed = [], {uid: [] for uid in self.specs}, set()
        self.max_hidden_bytes = max_hidden_bytes
        self.facade = SimpleNamespace(_dev_logits_rows={}, _dev_logits_states={})
        self.facade.dump_dev_tensors = MethodType(d03.write, self.facade)
        self.projector = SimpleNamespace(project_rows=lambda rows: d03.project(self.head, rows))
        self.destination.mkdir(parents=True, exist_ok=False)
        policy_raw = _raw(self.policy)
        with (self.destination / "policy.json").open("xb") as stream:
            stream.write(policy_raw)
        self.policy_sha = _sha(policy_raw)

        def layer_forward(hidden, batch):
            result = self.original_layer(hidden, batch)
            if not batch.is_prefill:
                return result
            context = dict(self.provider())
            spec = self.specs.get(context["uid"])
            if spec is None:
                raise ValueError("D12 prompt tail saw an undeclared UID")
            start, end = context["child_start"], context["child_end"]
            if end > spec["input_length"]:
                raise ValueError("D12 prompt tail extends beyond the frozen input")
            lo, hi = max(start, spec["prefix_length"]), min(end, spec["input_length"])
            if lo < hi:
                if not isinstance(result, torch.Tensor) or result.ndim != 2 or result.shape[0] != end - start:
                    raise ValueError("D12 final-layer hidden geometry differs")
                size = result.numel() * result.element_size()
                self.reserve(size)
                self.pending.append({"context": context, "lo": lo, "hi": hi,
                                     "source": weakref.ref(result), "hidden": result.detach().clone(),
                                     "actual_mixed": None, "bytes": size})
            return result

        def mix(hidden):
            result = self.original_mix(hidden)
            for row in self.pending:
                if row["source"]() is hidden:
                    if row["actual_mixed"] is not None:
                        raise ValueError("D12 top mixer observed a child twice")
                    start = row["context"]["child_start"]
                    # The actual last-child mix is sufficient; release its full
                    # residual clone before any extra earlier-child projection.
                    row["hidden"] = None
                    selected = result[0][row["lo"] - start:row["hi"] - start]
                    self.reserve(selected.numel() * selected.element_size())
                    row["actual_mixed"] = selected.detach().clone()
            return result

        layer_forward._d12_prompt_tail = True
        self.layer_wrapper, self.mix_wrapper = layer_forward, mix
        self.layer.forward, self.mixer.mix = layer_forward, mix

    def reserve(self, additional_bytes):
        tensors = [row[key] for row in self.pending for key in ("hidden", "actual_mixed")
                   if row[key] is not None]
        tensors += [tensor for rows in self.facade._dev_logits_rows.values() for tensor in rows.values()]
        retained = sum(tensor.numel() * tensor.element_size() for tensor in tensors)
        if retained + additional_bytes > self.max_hidden_bytes:
            raise ValueError("D12 prompt-tail hidden budget exhausted")

    def observe_state(self, event):
        """Called after the existing segment observer captured the outer state."""
        if event["schema"] != "ft_d12_post_prefill_state/v1":
            return
        outer = event["outer"]
        uid, outer_index = outer["uid"], outer["outer_segment_index"]
        spec = self.specs[uid]
        rows = [row for row in self.pending if row["context"]["uid"] == uid
                and row["context"]["outer_segment_index"] == outer_index]
        if outer["end"] == spec["input_length"]:
            tensors = {}
            if set(event["role_files"]) != ROLES:
                raise ValueError("D12 prompt tail lacks complete end-state roles")
            for role, item in event["role_files"].items():
                path = self.state_root / item["path"]
                if (Path(item["path"]).name != item["path"] or path.resolve() != path.absolute()
                        or _sha(path.read_bytes()) != item["sha256"]):
                    raise ValueError("D12 prompt-tail end-state file differs")
                tensor = self.torch.load(path, map_location="cpu", weights_only=True)
                if not isinstance(tensor, self.torch.Tensor) or tensor.ndim < 2 or tensor.shape[1] != 1:
                    raise ValueError("D12 prompt-tail end-state tensor differs")
                tensors[role] = tensor
            pool = self.engine.linear_state_pool
            layers = {role: list(pool._group.layer_ids) for role in ("conv_states", "recurrent_states")}
            for name in ("ple_conv", "ple_ngram_ctx"):
                layers["slot:" + name] = list(pool._state_layer_index[name]) or [-1]
            self.facade._dev_logits_states[uid] = {"tensors": tensors, "metadata": {
                "layer_ids": layers, "input_prefix_sha256": spec["input_prefix_sha256"],
                "state_length": spec["input_length"], "restore_proof": None,
                "d12_policy_sha256": self.policy_sha, "d12_projection_segments": self.observed[uid]}}
        for row in rows:
            context = row["context"]
            mixed = row["actual_mixed"]
            mode = "actual_top_mixer"
            if mixed is None:
                # Preserve the complete original child GEMM geometry. Mixing
                # only selected rows may change rounding despite per-token math.
                full_mixed = self.original_mix(row["hidden"])[0]
                start = context["child_start"]
                mixed = full_mixed[row["lo"] - start:row["hi"] - start]
                mode = "diagnostic_full_child_top_mixer"
            self.observed[uid].append({**context, "positions": list(range(row["lo"], row["hi"])),
                                       "top_mixer_source": mode})
            params = SimpleNamespace(_dev_logits_k=spec["k"], _dev_input_length=spec["input_length"],
                                     _dev_input_sha256=spec["input_prefix_sha256"])
            proxy = SimpleNamespace(uid=uid, cached_len=row["lo"], extend_len=row["hi"] - row["lo"],
                                    sampling_params=params)
            self.reserve(mixed.numel() * mixed.element_size())
            self.d03.collector(self.facade, SimpleNamespace(padded_reqs=[proxy]), mixed, self.projector)
            self.pending = [other for other in self.pending if other is not row]
        if outer["end"] == spec["input_length"]:
            if uid in self.completed or self.facade._dev_logits_rows.get(uid):
                raise ValueError("D12 prompt-tail rows are duplicate or incomplete")
            index = self.destination / "index.jsonl"
            records = [json.loads(line) for line in index.read_bytes().splitlines()] if index.exists() else []
            matching = [row for row in records if row["uid"] == uid]
            if len(matching) != 1:
                raise ValueError("D12 prompt tail did not publish exactly one complete capture")
            record = matching[0]
            logits = self.d03.reader.read_tensor(self.destination, record, "logits")
            if logits.shape[1] != self.head.num_embeddings:
                raise ValueError("D12 prompt tail did not capture the full vocabulary")
            if self.d03.reader.binding(record, logits) != (
                    spec["input_prefix_sha256"], spec["k"], spec["input_length"], spec["positions"]):
                raise ValueError("D12 prompt-tail D03 input binding differs")
            self.completed.add(uid)
            self.emit({"schema": "ft_d12_prompt_tail_logits/v1", "context": {"uid": uid,
                       "outer_segment_index": outer_index}, "policy_sha256": self.policy_sha,
                       "record": record, "output_equivalence_verified": False})

    def finish(self):
        if self.completed != set(self.specs) or self.pending or self.facade._dev_logits_rows:
            raise ValueError("D12 prompt-tail capture is incomplete")

    def restore(self):
        errors = []
        for owner, attr, wrapper, original in (
                (self.layer, "forward", self.layer_wrapper, self.original_layer),
                (self.mixer, "mix", self.mix_wrapper, self.original_mix)):
            if getattr(owner, attr) is not wrapper:
                errors.append(attr)
            else:
                setattr(owner, attr, original)
        self.pending.clear()
        self.facade._dev_logits_rows.clear()
        self.facade._dev_logits_states.clear()
        if errors:
            raise RuntimeError("D12 prompt-tail ownership changed: " + ",".join(errors))
