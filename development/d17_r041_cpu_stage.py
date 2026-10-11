"""Freeze only the diagnostic R041 raw-reader CPU contracts, without admission."""
from pathlib import Path
import d16_path_readers_stage as stage

def main():
    here = Path(__file__).resolve().parent
    stage.TESTS = ("development/tests/test_d17_r041_bitwise.py",)
    def sources():
        return {"stage_source.py": Path(stage.__file__).read_bytes(),
                "r041_stage_source.py": Path(__file__).read_bytes(),
                "development/d17_r041_bitwise.py": (here/"d17_r041_bitwise.py").read_bytes(),
                "development/tests/test_d17_r041_bitwise.py": (here/"tests/test_d17_r041_bitwise.py").read_bytes(),
                "tests/conftest.py": (here/"e2d16-readers/tests/conftest.py").read_bytes(),
                "d03_tools/logits_probe.py": stage.D03_TOOL.read_bytes()}
    stage.source_files = sources
    stage.main()

if __name__ == "__main__": main()
