import json,sys
from pathlib import Path
from hybrid_service import warmup
if __name__=='__main__':
 warmup(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]),float(sys.argv[3]))
