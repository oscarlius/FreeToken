"""Runtime-only T17 operator-boundary observer service entry point."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import struct
import sys

_ORIGINAL_ARGV = list(sys.argv)


def ids_sha(ids):
    """Hash actual tokenizer IDs using the continuation suite's int32-le wire form."""
    return hashlib.sha256(struct.pack("<%di" % len(ids), *ids)).hexdigest()


def _configuration():
    try:
        output = Path(os.environ["FT_T17_OPERATOR"])
        target_sha = os.environ["FT_T17_OPERATOR_QUERY_SHA"]
        query_tokens = int(os.environ["FT_T17_OPERATOR_QUERY_TOKENS"])
        boundary = int(os.environ["FT_T17_OPERATOR_BOUNDARY"])
    except (KeyError, ValueError) as exc:
        raise ValueError("explicit T17 operator diagnostic environment required") from exc
    if not target_sha or query_tokens <= boundary or boundary < 0:
        raise ValueError("invalid T17 operator query binding")
    return output, target_sha, query_tokens, boundary


def startup():
    output, target_sha, query_tokens, boundary = _configuration()
    # The staged ``t17_d14_startup`` module installs the frozen exact-ID hooks
    # at import time.  Do not call its CLI entry point or execute it a second time.
    import t17_d14_startup  # noqa: F401
    import t17_operator_observe
    from freetoken.core import get_global_ctx
    from freetoken.engine.engine import Engine
    from freetoken.scheduler.io import SchedulerIOMixin
    from freetoken.scheduler.scheduler import Scheduler

    original_init = Engine.__init__
    original_process = Scheduler._process_one_msg
    original_reply = SchedulerIOMixin._reply_tokenizer_rank0
    active = {}

    def sink(row):
        with (output / "observations.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")

    def init_operator(self, config):
        original_init(self, config)
        output.mkdir(parents=True, exist_ok=True)
        observer = t17_operator_observe.install(
            self.model.model, lambda: get_global_ctx().batch, output, boundary, query_tokens, target_sha, sink=sink)
        if active:
            raise ValueError("one observed engine per worker required")
        active["observer"] = observer
        self._t17_operator_observer = observer
        with (output / ("installed_" + str(os.getpid()) + ".json")).open("x", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "boundary": boundary, "query_tokens": query_tokens,
                       "target_input_sha": target_sha,
                       "observer_source_sha256": hashlib.sha256(Path(t17_operator_observe.__file__).read_bytes()).hexdigest(),
                       "startup_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, stream, sort_keys=True)
            stream.write("\n")

    def process_operator(self, msg):
        observer = active.get("observer")
        if observer is not None and type(msg).__name__ == "UserMsg":
            ids = msg.input_ids.tolist()
            digest = ids_sha(ids)
            if digest == target_sha:
                observer.bind_query(msg.uid, digest, len(ids))
                sink({"kind": "operator-tokenizer-binding", "uid": str(msg.uid),
                      "input_numel": len(ids), "input_ids_sha256": digest})
        return original_process(self, msg)

    def reply_operator(self, messages):
        observer = getattr(self.engine, "_t17_operator_observer", None)
        if observer is not None:
            for message in messages:
                if (type(message).__name__ == "DetokenizeMsg" and message.finished
                        and str(message.uid) in observer.bindings):
                    result = {"uid": str(message.uid), "valid": False}
                    try:
                        receipt = observer.finalize(message.uid)
                        result.update(valid=True, receipt_file=receipt["receipt_file"], receipt_sha256=receipt["receipt_sha256"])
                    except ValueError as error:
                        result["error"] = str(error)
                    with (output / ("final_" + str(message.uid) + ".json")).open("x", encoding="utf-8") as stream:
                        json.dump(result, stream, sort_keys=True); stream.write("\n")
        return original_reply(self, messages)

    Engine.__init__ = init_operator
    Scheduler._process_one_msg = process_operator
    SchedulerIOMixin._reply_tokenizer_rank0 = reply_operator


def cpu_worker(queue):
    """Exercise the spawned frozen startup without constructing an Engine or CUDA."""
    import t17_d14_exact_ids
    from freetoken.engine.engine import Engine
    from freetoken.scheduler.io import SchedulerIOMixin
    from freetoken.scheduler.scheduler import Scheduler

    class ProofQueue:
        def put(self, result):
            result.update(operator_engine_init=Engine.__init__.__name__,
                          operator_process=Scheduler._process_one_msg.__name__,
                          operator_reply=SchedulerIOMixin._reply_tokenizer_rank0.__name__)
            queue.put(result)

    t17_d14_exact_ids.cpu_probe(ProofQueue())


if __name__ in ("__main__", "__mp_main__"):
    startup()
if __name__ == "__main__":
    argv = list(_ORIGINAL_ARGV)
    if argv[1:] == ["--cpu-startup-probe"]:
        import multiprocessing
        context = multiprocessing.get_context("spawn")
        queue = context.Queue(); process = context.Process(target=cpu_worker, args=(queue,))
        process.start(); proof = queue.get(timeout=45); process.join(45)
        if (process.exitcode != 0 or proof.get("cuda_initialized")
                or proof.get("operator_engine_init") != "init_operator"
                or proof.get("operator_process") != "process_operator"
                or proof.get("operator_reply") != "reply_operator"):
            raise ValueError("actual operator startup spawn proof differs")
        print(json.dumps({"schema":"ft_t17_operator_spawn/v1","gpu_started":False,"worker":proof},sort_keys=True))
    else:
        from freetoken.cli import main
        # Importing the frozen generated startup can rewrite argv[0].  Restore
        # the original user arguments before presenting the normal CLI.
        sys.argv = ["ft", *argv[1:]]
        main()
