"""Own the immutable T16 cold-helper archive used by the D17 adapter."""
import hashlib
from pathlib import Path

NAMES=('cold_eq.py','probe_ft_cold32k.py','ft_probe_ckpt_tax.py','serve_args_diff.py')
# The retained cold script inserts the live scripts path. Preload its only local
# dependency from the archive so that insertion cannot change the imported code.
COLD_WRAPPER="""import importlib.util, pathlib, runpy, sys
root=pathlib.Path(__file__).resolve().parent/'raw'
path=root/'probe_ft_cold32k.py'
spec=importlib.util.spec_from_file_location('probe_ft_cold32k',path)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
assert pathlib.Path(module.__file__).resolve()==path.resolve()
runpy.run_path(str(root/'cold_eq.py'),run_name='__main__')
"""

def freeze_helpers(root, originals, expected_md5, overrides=None):
 overrides=overrides or {}
 if set(overrides)-set(NAMES):raise ValueError('unknown helper override')
 root,originals=Path(root),Path(originals);root.mkdir(exist_ok=False);(root/'raw').mkdir()
 for name in NAMES:
  source=originals/name
  raw=overrides[name] if name in overrides else source.read_bytes()
  if source.is_symlink() or hashlib.md5(raw).hexdigest()!=expected_md5[name]:
   raise ValueError('canonical T16 helper differs: '+name)
  (root/'raw'/name).write_bytes(raw)
  (root/name).write_bytes(COLD_WRAPPER.encode() if name=='cold_eq.py' else raw)
 for path in sorted(root.rglob('*'),reverse=True):path.chmod(0o444 if path.is_file() else 0o555)
 root.chmod(0o555)

def bind_protocol(protocol, root):
 root=Path(root)
 if root.is_symlink() or not root.is_dir() or root.stat().st_mode & 0o222:
  raise ValueError('sealed T16 helper archive required')
 expected=protocol['TOOL_MD5'] if isinstance(protocol,dict) else protocol.TOOL_MD5
 runner=protocol['Runner'] if isinstance(protocol,dict) else protocol.Runner
 hashes={}
 for name in NAMES:
  paths=[root/'raw'/name,root/name]
  for path in paths:
   if any(item.is_symlink() for item in (path,*path.parents)) or not path.is_file() or path.stat().st_mode & 0o222:
    raise ValueError('sealed regular helper path required')
  raw=paths[0].read_bytes();entry=paths[1].read_bytes()
  if hashlib.md5(raw).hexdigest()!=expected[name]:raise ValueError('canonical T16 helper bytes differ: '+name)
  if entry!=(COLD_WRAPPER.encode() if name=='cold_eq.py' else raw):raise ValueError('T16 helper entrypoint differs: '+name)
  hashes[name]=hashlib.sha256(raw).hexdigest()
 if isinstance(protocol,dict):protocol['SCR']=root
 else:protocol.SCR=root
 runner.__init__.__globals__['SCR']=root
 return hashes
