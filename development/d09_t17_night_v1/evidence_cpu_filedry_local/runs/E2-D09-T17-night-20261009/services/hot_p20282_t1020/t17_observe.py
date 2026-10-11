from pathlib import Path
SOURCE=Path('/data2/FreeToken/development/r067d_short_tail_v1/tooling/t17_d14_observe.py')
if not SOURCE.is_file(): raise RuntimeError('pinned observation source missing')
exec(compile(SOURCE.read_bytes(),str(SOURCE),'exec'))
