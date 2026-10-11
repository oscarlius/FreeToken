from pathlib import Path
from r067d_cpu_prep import HERE, materialize_real_windows
print(materialize_real_windows(Path('/data2/FreeToken/runs'), HERE/'raw_windows_v4'))
