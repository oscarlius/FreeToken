from pathlib import Path
SOURCE=Path('/data2/FreeToken/development/r067d_short_tail_v1/tooling/t17_d14_startup.py')
if not SOURCE.is_file(): raise RuntimeError('pinned startup source missing')
exec(compile(SOURCE.read_bytes(),str(SOURCE),'exec'))
