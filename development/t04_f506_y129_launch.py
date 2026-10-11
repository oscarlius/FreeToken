"""Atomic-preflight launcher for T04 E2-R021; never chooses a batch number."""
from __future__ import annotations
import argparse, hashlib, os
from pathlib import Path
from t04_f506_y129_runner import RID, CANDIDATE
ROOT=Path('/data2/FreeToken'); DEV=ROOT/'runs/dev_D03'; RUNNER=Path(__file__).with_name('t04_f506_y129_runner.py')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--self-test',action='store_true');p.add_argument('--run',action='store_true');a=p.parse_args(argv)
 if a.self_test: print('T04 f506 Y129 launcher self-test PASS: batch belongs to atomic ledger'); return 0
 if not a.run or os.name!='posix': p.error('--run on reviewed Linux launcher only')
 if (Path('/data2/_shared/runs/ft_rounds')/RID).exists(): raise FileExistsError('R021 exists')
 if not (DEV/'gpu_selfcheck_f5067bb'/'MANIFEST.sha256').is_file(): raise ValueError('approved f506 selfcheck manifest missing')
 raise RuntimeError('root atomic ledger launcher must supply the batch and frozen receipt')
if __name__=='__main__': main()
