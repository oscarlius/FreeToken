from pathlib import Path
import shutil
SOURCE=Path('/data2/FreeToken/development/r067d_short_tail_v1/tooling/t17_d14_exact_ids.py')
if not SOURCE.is_file(): raise RuntimeError('pinned exact-ID source missing')
exec(compile(SOURCE.read_bytes(),str(SOURCE),'exec'))
