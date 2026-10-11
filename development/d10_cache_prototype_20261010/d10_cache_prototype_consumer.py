"""D10 cache prototype controller entrypoint; default off."""
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location("d10_cache_owned",HERE/"d10_cache_owned_parent.py");m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
if __name__=="__main__":m.main()
