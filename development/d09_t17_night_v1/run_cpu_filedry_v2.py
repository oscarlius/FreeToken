from pathlib import Path
import subprocess,sys
subprocess.run([sys.executable,str(Path(__file__).with_name('d09_t17_runner_v2.py')),'--filedry'],check=True)
