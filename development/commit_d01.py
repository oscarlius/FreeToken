import ast
import pathlib
import subprocess

root = pathlib.Path(__file__).parent / "e2d01"


def git(*args, data=None):
    return subprocess.check_output(["git", *args], cwd=root, input=data)


def original(path):
    return git("show", f"E2-pre:{path}").decode().replace("\r\n", "\n")


def current(path):
    return (root / path).read_text(encoding="utf-8")


def index_text(path, text):
    digest = git("hash-object", "-w", "--stdin", data=text.encode()).decode().strip()
    git("update-index", "--add", "--cacheinfo", "100644", digest, path)


def method(text, name):
    tree = ast.parse(text)
    owner = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OffloadMoeCache")
    node = next(n for n in owner.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return "".join(text.splitlines(keepends=True)[node.lineno - 1:node.end_lineno])


def commit(message):
    print(git("commit", "-m", message).decode(), end="")


assert git("rev-parse", "--short=7", "HEAD").strip() == b"3db7b50"
assert not git("diff", "--cached", "--name-only").strip()
prefill_path = "python/freetoken/scheduler/prefill.py"
prefill = original(prefill_path)
prefill = prefill.replace("    anchor_ids: frozenset = frozenset()\n",
                          "    anchor_ids: frozenset = frozenset()\n    prefill_anchor_cut: bool = True\n")
prefill = prefill.replace("if self.anchor_ids and chunk_size", "if self.prefill_anchor_cut and self.anchor_ids and chunk_size")
prefill = prefill.replace("            anchor_ids=self.anchor_ids,\n",
                          "            anchor_ids=self.anchor_ids,\n            prefill_anchor_cut=self.prefill_anchor_cut,\n")
index_text(prefill_path, prefill)
scheduler_path = "python/freetoken/scheduler/scheduler.py"
scheduler = original(scheduler_path).replace(
    "            keep_images_whole=self._bidirectional_mm,\n",
    "            keep_images_whole=self._bidirectional_mm,\n            prefill_anchor_cut=config.prefill_anchor_cut,\n")
index_text(scheduler_path, scheduler)
git("add", "python/freetoken/scheduler/config.py", "python/freetoken/server/args.py")
commit("feat(scheduler): decouple prefill anchor cuts from decode checkpoints")

offload_path = "python/freetoken/moe/offload_cache.py"
offload = original(offload_path)
finished_offload = current(offload_path)
for name in ("_d0_flush_chunk", "begin_prefill"):
    offload = offload.replace(method(offload, name), method(finished_offload, name), 1)
offload = offload.replace("    def _d0_flush_chunk(self)",
                          method(finished_offload, "_d0_set_segment") + "\n\n    def _d0_flush_chunk(self)", 1)
index_text(offload_path, offload)
git("add", prefill_path, "python/freetoken/core.py", "python/freetoken/scheduler/prefill_trace.py",
    "python/freetoken/engine/engine.py", "python/freetoken/layers/moe.py")
commit("feat(instrument): record prefill reasons and stable request metadata")

git("add", scheduler_path, offload_path, "python/freetoken/scheduler/cache.py")
commit("feat(instrument): report successful decode anchor snapshots")

git("add", "tests/scheduler/test_switch_defaults.py", "tests/scheduler/test_prefill_anchor_cut_switch.py",
    "tests/scheduler/test_prefill_d0_metadata.py", "tests/scheduler/test_anchor_cut_scheduler_wiring.py",
    "tests/scheduler/test_hybrid_cache_manager.py")
commit("test(scheduler): verify anchor cut independence and telemetry alignment")
assert not git("status", "--porcelain").strip()
git("bundle", "create", str(root.parent / "d01-delivery.bundle"), "exp/e1r008-anchorcut", "^E2-pre")
