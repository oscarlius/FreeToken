"""CPU proof: the published pinned recipe never imports the disk-only extension."""
import ast
import builtins
import hashlib
import importlib.abc
import json
from pathlib import Path
import sys
from types import SimpleNamespace

from release_config import MODES, serve_argv


def main():
    worktree, commit, _, _ = MODES['release']
    kernel = worktree / 'python/freetoken/kernel'
    assert not list(kernel.glob('_row_store*.so'))
    argv = serve_argv('release')
    assert argv[argv.index('--ple-backend') + 1] == 'pinned'
    blocked = []

    class NoRowStore(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname in ('freetoken.kernel._row_store', 'freetoken.kernel.row_store'):
                blocked.append(fullname)
                raise AssertionError('Unexpected row-store dependency: ' + fullname)
            return None

    guard = NoRowStore()
    sys.meta_path.insert(0, guard)
    try:
        import torch
        import freetoken.cli
        import freetoken.models.qwen4_exp.model
        import freetoken.kernel._cpu_moe
        import freetoken.kernel._pinned_tensor
        assert not torch.cuda.is_initialized() and not blocked
        source = worktree / 'python/freetoken/models/qwen4_exp/model.py'
        tree = ast.parse(source.read_text())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'Qwen4ExpForCausalLM')
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'load_host_tables')
        # Execute the unmodified source method with tiny CPU stand-ins for PLE banks.
        # The import dispatcher records which backend this actual method selects.
        imports = []
        attachments = []
        table = SimpleNamespace(bank=SimpleNamespace(tensor=object(), nbytes=123), weight_scale=1.0)
        ple = SimpleNamespace(PinnedUVATable=lambda tensor, scale: ('pinned', tensor, scale),
                              ZeroTable=object, derive_ngram_hash_constants=object)

        def source_import(name, globals=None, locals=None, fromlist=(), level=0):
            imports.append((name, list(fromlist), level))
            if name == 'ple':
                return ple
            if name == 'weight':
                return SimpleNamespace(load_ple_table=lambda *args: table)
            raise AssertionError('Unexpected backend import in pinned branch: ' + name)

        namespace = {'__builtins__': {**vars(builtins), '__import__': source_import}}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(source), 'exec'), namespace)
        fake = SimpleNamespace(model=SimpleNamespace(ple_layers=[SimpleNamespace(ple_embedding=SimpleNamespace(attach_table=attachments.append))]),
                               _config=SimpleNamespace(qwen4_args=object()))
        result = namespace['load_host_tables'](fake, SimpleNamespace(ple_backend='pinned', use_dummy_weight=False, model_path='CPU_STANDIN'))
        assert result == 123 and len(attachments) == 1 and attachments[0][0] == 'pinned'
        assert [item[0] for item in imports] == ['ple', 'weight']
        assert not blocked and not torch.cuda.is_initialized()
    finally:
        sys.meta_path.remove(guard)
    paths = ['python/freetoken/models/qwen4_exp/model.py', 'python/freetoken/models/qwen4_exp/ple_disk.py',
             'python/freetoken/kernel/row_store.py', 'python/freetoken/kernel/__init__.py', 'python/freetoken/engine/config.py']
    proof = {'schema': 'ft_row_store_optional_CPU/v1', 'worktree': str(worktree), 'commit': commit,
             'release_ple_backend': 'pinned', 'extension_absent': True, 'blocked_import_attempts': blocked,
             'real_cli_model_and_extensions_imported': True, 'actual_load_host_tables_method_CPU_standins': True,
             'actual_method_imports': imports, 'cuda_initialized': False, 'GPU_started': False,
             'scope': 'row_store.py itself requires extension; disk feature imports it lazily. It is optional for the explicitly pinned publication recipe, not for the generic disk default.',
             'source_sha256': {path: hashlib.sha256((worktree / path).read_bytes()).hexdigest() for path in paths},
             'source_lines': {'model.py': [225, 228, 243, 256, 258, 262], 'ple_disk.py': [106, 115],
                              'row_store.py': [16], 'engine/config.py': [35, 36]}}
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
